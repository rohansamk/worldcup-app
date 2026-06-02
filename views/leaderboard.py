"""Leaderboard view: ranked table with per-category point breakdown."""
import streamlit as st

from config import SCORING
from scoring import CATEGORY_COLUMNS, compute_scores
from sheets_client import invalidate


def render() -> None:
    title_col, btn_col = st.columns([6, 1])
    with title_col:
        st.title("Leaderboard")
        st.caption("Live scores based on results entered by the admin.")
    with btn_col:
        st.write("")
        if st.button("Refresh", use_container_width=True):
            invalidate()
            st.rerun()

    df = compute_scores()
    if df.empty:
        st.info("No active players yet — add some to the Google Sheet's Players tab.")
        return

    st.divider()
    st.subheader("Podium")
    podium_cols = st.columns(3)
    podium_labels = ["1st", "2nd", "3rd"]
    for i, (col, label) in enumerate(zip(podium_cols, podium_labels)):
        if i < len(df):
            row = df.iloc[i]
            col.metric(label=label, value=str(row["Player"]), delta=f"{int(row['Total'])} pts", delta_color="off")
        else:
            col.metric(label=label, value="—", delta="0 pts", delta_color="off")

    st.divider()
    st.subheader("Full standings")
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
