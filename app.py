"""Streamlit entry point. Handles auth gating and sidebar navigation."""
import streamlit as st

from views import admin, leaderboard, login, predictions

st.set_page_config(page_title="World Cup 2026 Prediction League", page_icon="⚽", layout="wide")


def _sidebar() -> str:
    st.sidebar.title("⚽ WC 2026")
    st.sidebar.caption("Prediction League")
    st.sidebar.divider()
    player = st.session_state.get("player")
    if player:
        st.sidebar.markdown(f"Signed in as **{player}**")
        if st.sidebar.button("Sign out", use_container_width=True):
            for k in ("player", "admin_ok"):
                st.session_state.pop(k, None)
            st.rerun()
        st.sidebar.divider()
    page = st.sidebar.radio(
        "Navigate",
        ["Make Predictions", "Leaderboard", "Admin"],
        index=0,
    )
    return page


def main() -> None:
    if not st.session_state.get("player"):
        # Leaderboard and Admin should also be available without login? Spec implies
        # leaderboard is for everyone in the league, so they sign in to see it.
        login.render()
        return

    page = _sidebar()
    if page == "Make Predictions":
        predictions.render()
    elif page == "Leaderboard":
        leaderboard.render()
    elif page == "Admin":
        admin.render()


if __name__ == "__main__":
    main()
