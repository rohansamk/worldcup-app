"""Scoring engine. Pure functions: predictions in, points out."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

from config import GROUPS, SCORING, TAB_PRED_BRACKET, TAB_PRED_MATCHES
from sheets_client import (
    actual_bracket,
    actual_match_results,
    actual_standings,
    active_players,
    read_df,
)

CATEGORY_COLUMNS = [
    "Matches", "Group 1st", "Group 2nd", "R32",
    "R16", "QF", "SF", "Final", "Champion",
    "Golden Boot", "Golden Ball",
]


def _normalise(s: str) -> str:
    """Lowercase, strip accents, drop punctuation, collapse and trim whitespace.

    "Mbappé", "mbappe", "MBAPPE " all collapse to "mbappe".
    Returns "" for None/empty/whitespace-only input.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def _score_award(player_pick: str, actual: str, points: int) -> int:
    p = _normalise(player_pick or "")
    a = _normalise(actual or "")
    return points if p and a and p == a else 0


def _player_matches_score(player_picks: dict[str, str], results: dict[str, str]) -> int:
    pts = 0
    for mid, pick in player_picks.items():
        if not pick:
            continue
        if results.get(mid) == pick:
            pts += SCORING["group_match"]
    return pts


def _player_group_advancement(
    player_bracket: dict[str, list[str]],
    standings: dict[str, dict[str, str]],
) -> tuple[int, int]:
    """Return (group_first_points, group_second_points)."""
    first_pts = second_pts = 0
    # Player's Group1st rows are 12 teams; we don't know which group they intended
    # without inferring from TEAM_TO_GROUP. Use that mapping.
    from config import TEAM_TO_GROUP
    for team in player_bracket.get("Group1st", []):
        grp = TEAM_TO_GROUP.get(team)
        if grp and standings.get(grp, {}).get("First") == team:
            first_pts += SCORING["group_first"]
    for team in player_bracket.get("Group2nd", []):
        grp = TEAM_TO_GROUP.get(team)
        if grp and standings.get(grp, {}).get("Second") == team:
            second_pts += SCORING["group_second"]
    return first_pts, second_pts


def _player_r32_set(player_bracket: dict[str, list[str]]) -> set[str]:
    teams: set[str] = set()
    for key in ("Group1st", "Group2nd", "ThirdPlaced"):
        for t in player_bracket.get(key, []):
            if t:
                teams.add(t)
    return teams


def _intersect_score(predicted: set[str] | list[str], actual: set[str] | list[str], pts: int) -> int:
    return len(set(predicted) & set(actual)) * pts


def compute_scores() -> pd.DataFrame:
    """Return a DataFrame with one row per active player and category columns + Total."""
    players = active_players()
    if players.empty:
        return pd.DataFrame(columns=["Player"] + CATEGORY_COLUMNS + ["Total"])

    match_results = actual_match_results()
    standings = actual_standings()
    bracket = actual_bracket()

    pred_matches = read_df(TAB_PRED_MATCHES)
    pred_bracket = read_df(TAB_PRED_BRACKET)

    rows = []
    for _, p in players.iterrows():
        name = str(p["Name"])

        # Match picks
        pm = pred_matches[pred_matches["Player"] == name] if not pred_matches.empty else pred_matches
        picks = {str(r["MatchID"]): str(r["Pick"]) for _, r in pm.iterrows()} if not pm.empty else {}
        matches_pts = _player_matches_score(picks, match_results)

        # Bracket picks
        pb = pred_bracket[pred_bracket["Player"] == name] if not pred_bracket.empty else pred_bracket
        player_b: dict[str, list[str]] = {}
        if not pb.empty:
            for _, r in pb.iterrows():
                player_b.setdefault(str(r["Round"]), []).append(str(r["Team"]))

        first_pts, second_pts = _player_group_advancement(player_b, standings)

        # Cascade-filter each downstream round through the previous effective
        # set so stale picks from upstream changes are ignored at scoring time.
        # eff_r32 is the 32-team set used as the R16 cascade pool; it is NOT
        # used to score the R32 line (group winners and runners-up are already
        # credited on their own lines, so re-scoring them here would double-count).
        eff_r32   = _player_r32_set(player_b)
        eff_r16   = set(player_b.get("R16",   [])) & eff_r32
        eff_qf    = set(player_b.get("QF",    [])) & eff_r16
        eff_sf    = set(player_b.get("SF",    [])) & eff_qf
        eff_final = set(player_b.get("Final", [])) & eff_sf

        # R32 line: score ONLY the 8 ThirdPlaced picks that turned out to be
        # actual third-placed advancers. Max 8 points from this line.
        r32_pts   = _intersect_score(
            player_b.get("ThirdPlaced", []),
            bracket.get("ThirdPlaced", []),
            SCORING["r32"],
        )
        r16_pts   = _intersect_score(eff_r16,   bracket.get("R16",   []),  SCORING["r16"])
        qf_pts    = _intersect_score(eff_qf,    bracket.get("QF",    []),  SCORING["qf"])
        sf_pts    = _intersect_score(eff_sf,    bracket.get("SF",    []),  SCORING["sf"])
        final_pts = _intersect_score(eff_final, bracket.get("Final", []),  SCORING["final"])

        champion_pts = 0
        actual_champ = bracket.get("Champion", [])
        player_champ_list = player_b.get("Champion", [])
        player_champ = player_champ_list[0] if player_champ_list else None
        if player_champ and player_champ in eff_final and actual_champ and actual_champ[0] == player_champ:
            champion_pts = SCORING["champion"]

        pb_boot = (player_b.get("GoldenBoot") or [""])[0]
        pb_ball = (player_b.get("GoldenBall") or [""])[0]
        ab_boot = (bracket.get("GoldenBoot")  or [""])[0]
        ab_ball = (bracket.get("GoldenBall")  or [""])[0]
        boot_pts = _score_award(pb_boot, ab_boot, SCORING["golden_boot"])
        ball_pts = _score_award(pb_ball, ab_ball, SCORING["golden_ball"])

        total = (
            matches_pts + first_pts + second_pts
            + r32_pts + r16_pts + qf_pts + sf_pts + final_pts + champion_pts
            + boot_pts + ball_pts
        )

        rows.append({
            "Player":      name,
            "Matches":     matches_pts,
            "Group 1st":   first_pts,
            "Group 2nd":   second_pts,
            "R32":         r32_pts,
            "R16":         r16_pts,
            "QF":          qf_pts,
            "SF":          sf_pts,
            "Final":       final_pts,
            "Champion":    champion_pts,
            "Golden Boot": boot_pts,
            "Golden Ball": ball_pts,
            "Total":       total,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("Total", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", df["Total"].rank(method="min", ascending=False).astype(int))
    return df
