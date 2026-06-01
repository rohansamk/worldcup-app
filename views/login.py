"""Login view: name dropdown + passcode entry."""
import streamlit as st

from sheets_client import active_players, check_passcode


def render() -> None:
    st.title("World Cup 2026 — Prediction League")
    st.caption("Sign in with your name and the passcode the commissioner sent you.")

    players = active_players()
    if players.empty:
        st.error(
            "No active players found in the Google Sheet's `Players` tab. "
            "Add at least one row with `Active = TRUE` to get started."
        )
        return

    names = sorted(players["Name"].astype(str).tolist())
    with st.form("login"):
        name = st.selectbox("Your name", names, index=None, placeholder="Select your name…")
        passcode = st.text_input("Passcode", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if not submitted:
        return
    if not name:
        st.error("Pick your name from the dropdown.")
        return
    if not check_passcode(name, passcode):
        st.error("Wrong passcode for that name.")
        return

    st.session_state.player = name
    st.rerun()
