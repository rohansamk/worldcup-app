"""Google Sheets I/O. Thin wrapper around gspread with Streamlit-aware caching.

All reads are cached for 30 s to stay within gspread's 60 req/min quota when
multiple players are looking at the leaderboard. Writes call `invalidate()`
so the next read picks up fresh data.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from config import (
    DEADLINE_KEY,
    SHEET_ID,
    TAB_HEADERS,
    TAB_PRED_BRACKET,
    TAB_PRED_MATCHES,
)

LOCAL_SA_PATH = Path(__file__).parent / ".streamlit" / "service_account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@st.cache_resource
def _client() -> gspread.Client:
    if LOCAL_SA_PATH.exists():
        info = json.loads(LOCAL_SA_PATH.read_text())
    else:
        # Streamlit Community Cloud deploy path: paste the service account
        # JSON under [gcp_service_account] in the app's Secrets UI.
        info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource
def _spreadsheet() -> gspread.Spreadsheet:
    return _client().open_by_key(SHEET_ID)


def _ws(tab: str) -> gspread.Worksheet:
    ss = _spreadsheet()
    header = TAB_HEADERS.get(tab, [])
    try:
        ws = ss.worksheet(tab)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=tab, rows=200, cols=max(len(header), 4))
        if header:
            ws.update("A1", [header])
        return ws
    # Tab exists but row 1 may be empty (user pre-created the tab without
    # typing a header). Write the expected header in that case - this never
    # overwrites existing data since we only act when row 1 is empty.
    if header and not ws.row_values(1):
        ws.update("A1", [header])
    return ws


def invalidate() -> None:
    """Clear all cached reads after a write."""
    st.cache_data.clear()


# ---------------------------------------------------------------------------
# Generic read/write
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def read_df(tab: str) -> pd.DataFrame:
    """Read an entire tab as a DataFrame. Empty tab returns empty df with headers."""
    ws = _ws(tab)
    records = ws.get_all_records()
    if records:
        return pd.DataFrame(records)
    headers = TAB_HEADERS.get(tab, [])
    return pd.DataFrame(columns=headers)


def overwrite_tab(tab: str, df: pd.DataFrame) -> None:
    """Replace the entire tab contents with `df` (header + rows)."""
    ws = _ws(tab)
    ws.clear()
    headers = TAB_HEADERS.get(tab, list(df.columns))
    # Reindex df to match expected header order so column drift can't desync.
    df = df.reindex(columns=headers, fill_value="")
    values = [headers] + df.astype(str).values.tolist()
    ws.update("A1", values)
    invalidate()


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

def active_players() -> pd.DataFrame:
    df = read_df("Players")
    if df.empty:
        return df
    # Normalise "Active" - accept TRUE/True/true/1/yes
    df["_active"] = df["Active"].astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "y"}
    )
    return df[df["_active"]].drop(columns=["_active"]).reset_index(drop=True)


def check_passcode(name: str, passcode: str) -> bool:
    df = active_players()
    if df.empty:
        return False
    row = df[df["Name"] == name]
    if row.empty:
        return False
    return str(row.iloc[0]["Passcode"]) == passcode


# ---------------------------------------------------------------------------
# Config (deadlines, admin passcode)
# ---------------------------------------------------------------------------

def config_dict() -> dict[str, str]:
    df = read_df("Config")
    if df.empty:
        return {}
    return {str(k): str(v) for k, v in zip(df["Key"], df["Value"])}


def predictions_deadline() -> datetime | None:
    """Return the single shared deadline for all predictions (or None if unset)."""
    return _parse_deadline(config_dict().get(DEADLINE_KEY, ""))


def _parse_deadline(raw: str) -> datetime | None:
    """Parse a deadline value entered in the Config tab.

    Accepts ISO-8601 ("2026-06-11T12:00") or "YYYY-MM-DD HH:MM".
    Naive values are assumed to be NZT (the configured display tz).
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    from config import DISPLAY_TZ
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=DISPLAY_TZ)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DISPLAY_TZ)
        return dt
    except ValueError:
        return None


def is_locked() -> bool:
    dl = predictions_deadline()
    if dl is None:
        return False
    return datetime.now(tz=timezone.utc) >= dl.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Predictions: upsert by (player, key)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def upsert_match_predictions(player: str, picks: dict[str, str]) -> None:
    """Replace this player's match picks. `picks` is {match_id: pick_value}."""
    df = read_df(TAB_PRED_MATCHES)
    # Drop existing rows for this player.
    if not df.empty:
        df = df[df["Player"] != player]
    new_rows = pd.DataFrame(
        [{"Player": player, "MatchID": mid, "Pick": pick, "UpdatedAt": _now_iso()}
         for mid, pick in picks.items() if pick],
    )
    out = pd.concat([df, new_rows], ignore_index=True) if not new_rows.empty else df
    overwrite_tab(TAB_PRED_MATCHES, out)


def upsert_bracket_picks(player: str, round_key: str, teams: list[str]) -> None:
    """Replace this player's picks for one bracket round."""
    df = read_df(TAB_PRED_BRACKET)
    if not df.empty:
        df = df[~((df["Player"] == player) & (df["Round"] == round_key))]
    new_rows = pd.DataFrame(
        [{"Player": player, "Round": round_key, "Team": t, "UpdatedAt": _now_iso()}
         for t in teams if t],
    )
    out = pd.concat([df, new_rows], ignore_index=True) if not new_rows.empty else df
    overwrite_tab(TAB_PRED_BRACKET, out)


def player_match_picks(player: str) -> dict[str, str]:
    df = read_df(TAB_PRED_MATCHES)
    if df.empty:
        return {}
    sub = df[df["Player"] == player]
    return {str(r["MatchID"]): str(r["Pick"]) for _, r in sub.iterrows()}


def player_bracket_picks(player: str) -> dict[str, list[str]]:
    """Returns {round_key: [team, ...]} for one player."""
    df = read_df(TAB_PRED_BRACKET)
    if df.empty:
        return {}
    sub = df[df["Player"] == player]
    out: dict[str, list[str]] = {}
    for _, r in sub.iterrows():
        out.setdefault(str(r["Round"]), []).append(str(r["Team"]))
    return out


# ---------------------------------------------------------------------------
# Actuals
# ---------------------------------------------------------------------------

def actual_match_results() -> dict[str, str]:
    df = read_df("MatchResults")
    if df.empty:
        return {}
    return {str(r["MatchID"]): str(r["Result"]) for _, r in df.iterrows() if str(r["Result"]).strip()}


def actual_standings() -> dict[str, dict[str, str]]:
    """Returns {group: {'First': team, 'Second': team, 'Third': team}}."""
    df = read_df("ActualGroupStandings")
    if df.empty:
        return {}
    out: dict[str, dict[str, str]] = {}
    for _, r in df.iterrows():
        g = str(r["Group"]).strip()
        if not g:
            continue
        out[g] = {
            "First":  str(r.get("First", "")).strip(),
            "Second": str(r.get("Second", "")).strip(),
            "Third":  str(r.get("Third", "")).strip(),
        }
    return out


def actual_bracket() -> dict[str, list[str]]:
    """Returns {round_key: [teams that actually advanced]}."""
    df = read_df("ActualBracket")
    if df.empty:
        return {}
    out: dict[str, list[str]] = {}
    for _, r in df.iterrows():
        rnd = str(r["Round"]).strip()
        team = str(r["Team"]).strip()
        if rnd and team:
            out.setdefault(rnd, []).append(team)
    return out


def write_actual_match_result(match_id: str, result: str) -> None:
    df = read_df("MatchResults")
    if df.empty:
        df = pd.DataFrame(columns=["MatchID", "Result"])
    df = df[df["MatchID"] != match_id]
    df = pd.concat([df, pd.DataFrame([{"MatchID": match_id, "Result": result}])], ignore_index=True)
    overwrite_tab("MatchResults", df)


def write_actual_standings(rows: list[dict[str, str]]) -> None:
    df = pd.DataFrame(rows, columns=["Group", "First", "Second", "Third"])
    overwrite_tab("ActualGroupStandings", df)


def write_actual_bracket_round(round_key: str, teams: list[str]) -> None:
    df = read_df("ActualBracket")
    if df.empty:
        df = pd.DataFrame(columns=["Round", "Team"])
    df = df[df["Round"] != round_key]
    new_rows = pd.DataFrame([{"Round": round_key, "Team": t} for t in teams if t])
    out = pd.concat([df, new_rows], ignore_index=True) if not new_rows.empty else df
    overwrite_tab("ActualBracket", out)
