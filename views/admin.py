"""Admin view: passcode-gated. Seed matches, enter actual results."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config import ADMIN_PASSCODE_KEY, ALL_TEAMS, DRAW, GROUPS, TAB_MATCHES
from matches import generate_group_matches
from sheets_client import (
    actual_bracket,
    actual_match_results,
    actual_standings,
    config_dict,
    invalidate,
    overwrite_tab,
    read_df,
    write_actual_bracket_round,
    write_actual_match_result,
    write_actual_standings,
)

MATCH_COLS = {"MatchID", "Group", "Team1", "Team2"}


def render() -> None:
    st.title("Admin")
    st.caption("Seed matches once, then enter results as the tournament unfolds. Players can't see this page.")
    if not _auth_gate():
        return

    st.divider()
    tabs = st.tabs(["Setup", "Match results", "Group standings", "Knockout actuals"])
    with tabs[0]: _setup_section()
    with tabs[1]: _match_results_section()
    with tabs[2]: _standings_section()
    with tabs[3]: _knockout_section()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _auth_gate() -> bool:
    if st.session_state.get("admin_ok"):
        if st.sidebar.button("Sign out of admin"):
            st.session_state.admin_ok = False
            st.rerun()
        return True

    cfg = config_dict()
    expected = cfg.get(ADMIN_PASSCODE_KEY, "")
    if not expected:
        st.error(
            f"No `{ADMIN_PASSCODE_KEY}` set in the Google Sheet's Config tab. "
            "Add a row with Key=`admin_passcode` and a value, then reload."
        )
        return False

    with st.form("admin_login"):
        pc = st.text_input("Admin passcode", type="password")
        ok = st.form_submit_button("Unlock", type="primary")
    if ok:
        if pc == expected:
            st.session_state.admin_ok = True
            st.rerun()
        else:
            st.error("Wrong passcode.")
    return False


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _setup_section() -> None:
    st.subheader("Initial setup")
    df = read_df(TAB_MATCHES)
    healthy = MATCH_COLS.issubset(set(df.columns))

    if df.empty:
        st.write("Matches tab is empty.")
        button_label = "Seed all 72 group matches"
    elif not healthy:
        st.warning(
            f"Matches tab has {len(df)} rows but no proper header row "
            f"(expected columns: {', '.join(sorted(MATCH_COLS))}). "
            "Re-seeding will overwrite the rows with a header + 72 matches."
        )
        button_label = "Re-seed matches (overwrite existing rows)"
    else:
        st.write(f"Matches tab has **{len(df)}** matches seeded with proper headers.")
        button_label = "Re-seed matches (overwrite existing rows)"

    if st.button(button_label, type="primary"):
        matches = generate_group_matches()
        df_out = pd.DataFrame(matches, columns=["MatchID", "Group", "Team1", "Team2"])
        overwrite_tab(TAB_MATCHES, df_out)
        st.success(f"Wrote header + {len(matches)} matches.")
        st.rerun()


# ---------------------------------------------------------------------------
# Match results
# ---------------------------------------------------------------------------

def _match_results_section() -> None:
    st.subheader("Enter actual match results")
    matches_df = read_df(TAB_MATCHES)
    if matches_df.empty:
        st.info("No matches yet, go to Setup and seed the matches first.")
        return
    if not MATCH_COLS.issubset(set(matches_df.columns)):
        st.error(
            f"Matches tab is missing its header row (expected: {', '.join(sorted(MATCH_COLS))}). "
            "Open the Setup tab and click *Re-seed matches*."
        )
        return

    results = actual_match_results()
    for group in GROUPS:
        group_matches = matches_df[matches_df["Group"] == group]
        with st.expander(f"Group {group}", expanded=False):
            for _, m in group_matches.iterrows():
                mid = str(m["MatchID"])
                options = [str(m["Team1"]), DRAW, str(m["Team2"])]
                current = results.get(mid, "")
                idx = options.index(current) if current in options else None
                label = f"{m['Team1']} vs {m['Team2']}  ({mid})"
                c1, c2 = st.columns([4, 1])
                pick = c1.selectbox(label, options=options, index=idx, key=f"admin_match::{mid}", placeholder="No result yet")
                if c2.button("Save", key=f"admin_save::{mid}"):
                    write_actual_match_result(mid, pick or "")
                    invalidate()
                    st.toast(f"Saved {mid}: {pick}")
                    st.rerun()


# ---------------------------------------------------------------------------
# Group standings
# ---------------------------------------------------------------------------

def _standings_section() -> None:
    st.subheader("Actual group standings (1st / 2nd / 3rd)")
    st.caption("Used for scoring group advancement picks and to build the actual R32 set (1st + 2nd of each group + 8 third-placed entered in the Knockout tab).")
    standings = actual_standings()

    rows: list[dict[str, str]] = []
    for group, teams in GROUPS.items():
        cur = standings.get(group, {})
        with st.container(border=True):
            st.markdown(f"**Group {group}**")
            c1, c2, c3 = st.columns(3)
            first_idx  = teams.index(cur.get("First"))  if cur.get("First")  in teams else None
            f = c1.selectbox("1st",   options=teams, index=first_idx,  key=f"std1::{group}", placeholder="-")
            opts_2 = [t for t in teams if t != f]
            second_idx = opts_2.index(cur.get("Second")) if cur.get("Second") in opts_2 else None
            s = c2.selectbox("2nd",   options=opts_2, index=second_idx, key=f"std2::{group}", placeholder="-")
            opts_3 = [t for t in teams if t not in (f, s)]
            third_idx  = opts_3.index(cur.get("Third"))  if cur.get("Third")  in opts_3 else None
            t = c3.selectbox("3rd",   options=opts_3, index=third_idx,  key=f"std3::{group}", placeholder="-")
            rows.append({"Group": group, "First": f or "", "Second": s or "", "Third": t or ""})

    if st.button("Save all standings", type="primary"):
        write_actual_standings(rows)
        invalidate()
        st.success("Saved standings.")
        st.rerun()


# ---------------------------------------------------------------------------
# Knockout actuals
# ---------------------------------------------------------------------------

def _knockout_section() -> None:
    st.subheader("Knockout actuals")
    st.caption(
        "Enter who actually advanced at each stage. ThirdPlaced is the 8 best third-placed teams used to complete the R32. "
        "You can save a partial set as teams qualify over several days and add more later - you just can't enter more than the round's max."
    )
    bracket = actual_bracket()
    standings = actual_standings()

    advancers = set()
    for g in GROUPS:
        for k in ("First", "Second"):
            v = standings.get(g, {}).get(k, "")
            if v: advancers.add(v)

    third_pool = sorted([t for t in ALL_TEAMS if t not in advancers])
    _editable_multiselect("ThirdPlaced", "Best 8 third-placed (to R32)", third_pool, 8, bracket)

    # Subsequent rounds: pool is the actual previous round's set
    r32_set = sorted(advancers | set(bracket.get("ThirdPlaced", [])))
    _editable_multiselect("R16", "R16 advancers", r32_set, 16, bracket)
    _editable_multiselect("QF",  "QF advancers",  sorted(bracket.get("R16", [])),  8, bracket)
    _editable_multiselect("SF",  "SF advancers",  sorted(bracket.get("QF", [])),   4, bracket)
    _editable_multiselect("Final", "Finalists",   sorted(bracket.get("SF", [])),   2, bracket)

    finalists = bracket.get("Final", [])
    champ_current_list = bracket.get("Champion", [])
    champ_current = champ_current_list[0] if champ_current_list else None
    st.markdown("**Champion**")
    if not finalists:
        st.info("Enter finalists first.")
    else:
        idx = finalists.index(champ_current) if champ_current in finalists else None
        pick = st.selectbox("Actual champion", options=finalists, index=idx, key="admin_champ", placeholder="-")
        if st.button("Save champion", key="admin_save_champ", type="primary"):
            if pick:
                write_actual_bracket_round("Champion", [pick])
                invalidate()
                st.success("Saved.")
                st.rerun()

    st.divider()
    st.markdown("**Player Awards**")
    cur_boot = (bracket.get("GoldenBoot") or [""])[0]
    cur_ball = (bracket.get("GoldenBall") or [""])[0]
    c1, c2 = st.columns(2)
    new_boot = c1.text_input("Golden Boot (top scorer)", value=cur_boot, key="admin_award_boot")
    new_ball = c2.text_input("Golden Ball (best player)", value=cur_ball, key="admin_award_ball")
    if st.button("Save awards", key="admin_save_awards", type="primary"):
        write_actual_bracket_round("GoldenBoot", [new_boot.strip()] if new_boot.strip() else [])
        write_actual_bracket_round("GoldenBall", [new_ball.strip()] if new_ball.strip() else [])
        invalidate()
        st.success("Saved awards.")
        st.rerun()


def _editable_multiselect(round_key: str, label: str, pool: list[str], count: int, bracket: dict[str, list[str]]) -> None:
    st.markdown(f"**{label}** (up to {count} teams)")
    if not pool:
        st.info(f"Fill in the previous round first to populate the pool.")
        return
    current = [t for t in bracket.get(round_key, []) if t in pool]
    picks = st.multiselect(
        f"Pick up to {count} (save fewer now, add more later)",
        options=pool, default=current, max_selections=count,
        key=f"admin_round::{round_key}", label_visibility="collapsed",
    )
    if st.button(f"Save {round_key}", key=f"admin_save_round::{round_key}", type="primary"):
        # Allow saving a partial set (teams qualify over several days), but never
        # more than the round's max. max_selections already caps the widget; this
        # guard is the explicit, clearly-messaged backstop.
        if len(picks) > count:
            st.error(f"You selected {len(picks)}, but {round_key} can hold at most {count}. Remove some and save again.")
        else:
            write_actual_bracket_round(round_key, picks)
            invalidate()
            st.success(f"Saved {len(picks)} of up to {count} {round_key} team(s).")
            st.rerun()
