"""Leaderboard view: ranked table with per-category point breakdown."""
import streamlit as st

from scoring import CATEGORY_COLUMNS, compute_scores
from sheets_client import invalidate


def render() -> None:
    st.title("Leaderboard")
    c1, c2 = st.columns([1, 6])
    if c1.button("Refresh"):
        invalidate()
        st.rerun()
    c2.caption("Live scores based on results entered by the admin. Refresh to pull the latest from Google Sheets.")

    df = compute_scores()
    if df.empty:
        st.info("No active players yet — add some to the Google Sheet's Players tab.")
        return

    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Rank":   st.column_config.NumberColumn(width="small"),
            "Player": st.column_config.TextColumn(width="medium"),
            "Total":  st.column_config.NumberColumn(width="small", help="Sum of all category points"),
            **{c: st.column_config.NumberColumn(width="small") for c in CATEGORY_COLUMNS},
        },
    )

    with st.expander("How scoring works", expanded=False):
        from config import SCORING
        st.markdown(
            f"""
- Correct group match result: **{SCORING['group_match']} pt**
- Correct group winner (1st): **{SCORING['group_first']} pts**
- Correct group runner-up (2nd): **{SCORING['group_second']} pt**
- Correct R32 advancement (per team): **{SCORING['r32']} pts**
- Correct R16 advancement (per team): **{SCORING['r16']} pts**
- Correct QF advancement (per team): **{SCORING['qf']} pts**
- Correct SF advancement (per team): **{SCORING['sf']} pts**
- Correct finalist (per team): **{SCORING['final']} pts**
- Correct champion: **{SCORING['champion']} pts**
"""
        )
