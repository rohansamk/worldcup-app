"""Make Predictions - one continuous, editable flow.

All sections share one deadline (`deadline_group` in the Config tab). Until
that deadline the player can revise any section freely. After it, everything
on the page is read-only.

Flow (top to bottom):
  1. Group Matches      - pick winner/draw for each of the 72 matches
  2. Group Standings    - pick 1st / 2nd / 3rd for each group
  3. R32                - pick which 8 of your 12 third-placed teams advance
  4. R16                - pick 16 winners from your R32 set
  5. QF                 - pick 8 from your R16
  6. SF                 - pick 4 from your QF
  7. Final              - pick 2 from your SF
  8. Champion           - pick 1 from your Final

The "available options" for each knockout round come from the player's own
picks in the previous round - this is the cascade and it's enforced at edit
time AND at scoring time (see scoring.py).
"""
from __future__ import annotations

import streamlit as st

from config import ALL_TEAMS, DISPLAY_TZ, DISPLAY_TZ_LABEL, DRAW, GROUPS, TEAM_TO_GROUP
from matches import generate_group_matches
from sheets_client import (
    invalidate,
    is_locked,
    player_bracket_picks,
    player_match_picks,
    predictions_deadline,
    upsert_bracket_picks,
    upsert_match_predictions,
)


def render() -> None:
    player = st.session_state.player
    st.title(f"Your predictions, {player}")
    st.caption("Fill in every section. You can revise any pick until the deadline passes.")
    locked = is_locked()
    _deadline_header(locked)

    existing_bracket = player_bracket_picks(player)
    existing_matches = player_match_picks(player)

    # Effective cascade pools - mirrors scoring.py so what you see is what scores.
    # If an upstream change makes a downstream pick invalid, it falls out here.
    eff_r32 = sorted(
        set(existing_bracket.get("Group1st", []))
        | set(existing_bracket.get("Group2nd", []))
        | set(existing_bracket.get("ThirdPlaced", []))
    )
    eff_r16   = sorted(set(existing_bracket.get("R16",   [])) & set(eff_r32))
    eff_qf    = sorted(set(existing_bracket.get("QF",    [])) & set(eff_r16))
    eff_sf    = sorted(set(existing_bracket.get("SF",    [])) & set(eff_qf))
    eff_final = sorted(set(existing_bracket.get("Final", [])) & set(eff_sf))

    _section_group_matches(player, locked, existing_matches)
    st.divider()
    _section_group_standings(player, locked, existing_bracket)
    st.divider()
    _section_r32(player, locked, existing_bracket)
    st.divider()
    _section_knockout(player, locked, existing_bracket, stage="R16",   count=16, pool=eff_r32,  label="Round of 16",   prev_label="R32 set")
    st.divider()
    _section_knockout(player, locked, existing_bracket, stage="QF",    count=8,  pool=eff_r16,  label="Quarter-Finals", prev_label="R16 picks")
    st.divider()
    _section_knockout(player, locked, existing_bracket, stage="SF",    count=4,  pool=eff_qf,   label="Semi-Finals",    prev_label="QF picks")
    st.divider()
    _section_knockout(player, locked, existing_bracket, stage="Final", count=2,  pool=eff_sf,   label="Finalists",      prev_label="SF picks")
    st.divider()
    _section_champion(player, locked, existing_bracket, pool=eff_final)
    st.divider()
    _section_player_awards(player, locked, existing_bracket)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def _stale_hint(stored: list[str], pool: list[str], locked: bool) -> None:
    """If any of the player's saved picks fell out of the current pool, show a subtle note."""
    pool_set = set(pool)
    n = sum(1 for t in stored if t not in pool_set)
    if not n:
        return
    s = "s" if n > 1 else ""
    verb = "not being" if locked else "won't be"
    suffix = "" if locked else " Re-save to tidy up."
    st.caption(f"_{n} earlier pick{s} no longer match this round's options, {verb} scored.{suffix}_")


def _deadline_header(locked: bool) -> None:
    dl = predictions_deadline()
    shown = dl.astimezone(DISPLAY_TZ).strftime("%a %d %b %Y, %H:%M") if dl else "not set"
    if locked:
        st.error(f"🔒 Predictions are LOCKED. The deadline ({shown} {DISPLAY_TZ_LABEL}) has passed.")
    else:
        st.info(f"All sections editable until **{shown} {DISPLAY_TZ_LABEL}**. Save each section to persist your picks.")


# ---------------------------------------------------------------------------
# 1. Group Matches
# ---------------------------------------------------------------------------

def _section_group_matches(player: str, locked: bool, existing: dict[str, str]) -> None:
    st.header("1. Group Matches")
    st.caption("Pick the winning team, or Draw, for each of the 72 group matches. 1 pt each.")

    matches = generate_group_matches()
    new_picks: dict[str, str] = {}

    for group in GROUPS:
        group_matches = [m for m in matches if m["Group"] == group]
        with st.expander(f"Group {group} - {len(group_matches)} matches", expanded=False):
            for m in group_matches:
                options = [m["Team1"], DRAW, m["Team2"]]
                current = existing.get(m["MatchID"], "")
                idx = options.index(current) if current in options else None
                label = f"{m['Team1']} vs {m['Team2']}"
                if locked:
                    st.text(f"{label} → {current or '-'}")
                    new_picks[m["MatchID"]] = current
                else:
                    pick = st.selectbox(
                        label, options=options, index=idx,
                        key=f"match::{m['MatchID']}", placeholder="No pick",
                    )
                    if pick:
                        new_picks[m["MatchID"]] = pick

    if not locked and st.button("Save match picks", key="save_matches", type="primary"):
        upsert_match_predictions(player, new_picks)
        invalidate()
        st.success(f"Saved {len(new_picks)} match picks.")
        st.rerun()


# ---------------------------------------------------------------------------
# 2. Group Standings (1st / 2nd / 3rd per group)
# ---------------------------------------------------------------------------

def _section_group_standings(player: str, locked: bool, existing: dict[str, list[str]]) -> None:
    st.header("2. Group Standings")
    st.caption("Predict the final 1st, 2nd and 3rd of every group. 1st and 2nd auto-advance to R32. From the 12 3rd-placed teams you list here, you'll pick 8 to advance in the next section.")

    first_by_group  = {TEAM_TO_GROUP[t]: t for t in existing.get("Group1st", []) if t in TEAM_TO_GROUP}
    second_by_group = {TEAM_TO_GROUP[t]: t for t in existing.get("Group2nd", []) if t in TEAM_TO_GROUP}
    third_by_group  = {TEAM_TO_GROUP[t]: t for t in existing.get("Group3rd", []) if t in TEAM_TO_GROUP}

    new_first:  dict[str, str] = {}
    new_second: dict[str, str] = {}
    new_third:  dict[str, str] = {}

    for group, teams in GROUPS.items():
        with st.container(border=True):
            st.markdown(f"**Group {group}**")
            c1, c2, c3 = st.columns(3)

            if locked:
                c1.text(f"1st: {first_by_group.get(group, '-')}")
                c2.text(f"2nd: {second_by_group.get(group, '-')}")
                c3.text(f"3rd: {third_by_group.get(group, '-')}")
                if group in first_by_group:  new_first[group]  = first_by_group[group]
                if group in second_by_group: new_second[group] = second_by_group[group]
                if group in third_by_group:  new_third[group]  = third_by_group[group]
                continue

            default_first = first_by_group.get(group)
            f_idx = teams.index(default_first) if default_first in teams else None
            pick_1 = c1.selectbox(
                "1st", options=teams, index=f_idx,
                key=f"g1st::{group}", placeholder="Pick winner",
            )

            opts_2 = [t for t in teams if t != pick_1]
            default_second = second_by_group.get(group)
            s_idx = opts_2.index(default_second) if default_second in opts_2 else None
            pick_2 = c2.selectbox(
                "2nd", options=opts_2, index=s_idx,
                key=f"g2nd::{group}", placeholder="Pick runner-up",
            )

            opts_3 = [t for t in teams if t not in (pick_1, pick_2)]
            default_third = third_by_group.get(group)
            t_idx = opts_3.index(default_third) if default_third in opts_3 else None
            pick_3 = c3.selectbox(
                "3rd", options=opts_3, index=t_idx,
                key=f"g3rd::{group}", placeholder="Pick 3rd",
            )

            if pick_1: new_first[group]  = pick_1
            if pick_2: new_second[group] = pick_2
            if pick_3: new_third[group]  = pick_3

    if not locked and st.button("Save group standings", key="save_standings", type="primary"):
        upsert_bracket_picks(player, "Group1st", list(new_first.values()))
        upsert_bracket_picks(player, "Group2nd", list(new_second.values()))
        upsert_bracket_picks(player, "Group3rd", list(new_third.values()))
        invalidate()
        st.success(f"Saved {len(new_first)} winners, {len(new_second)} runners-up, {len(new_third)} third-place picks.")
        st.rerun()


# ---------------------------------------------------------------------------
# 3. R32 - pick 8 of your 12 third-placed picks to fill out the round of 32
# ---------------------------------------------------------------------------

def _section_r32(player: str, locked: bool, existing: dict[str, list[str]]) -> None:
    st.header("3. Round of 32")
    st.caption("Your 1st and 2nd picks (24 teams) auto-advance (already scored on the Group 1st / Group 2nd lines). Choose which 8 of your 12 third-placed picks join them in R32. 1 pt per correct third-placed pick, max 8.")

    third_pool = existing.get("Group3rd", [])
    stored = existing.get("ThirdPlaced", [])
    _stale_hint(stored, third_pool, locked)
    current = [t for t in stored if t in third_pool]

    if locked:
        st.text("Your 8 third-placed advancers: " + (", ".join(current) if current else "-"))
        return

    if len(third_pool) < 8:
        st.info(f"Fill in 3rd place for every group first (you have {len(third_pool)} so far).")
        return

    picks = st.multiselect(
        "Pick exactly 8",
        options=third_pool,
        default=current,
        max_selections=8,
        key="r32_third_placed",
    )
    if st.button("Save R32 picks", key="save_r32", type="primary"):
        if len(picks) != 8:
            st.error(f"You picked {len(picks)}, must be exactly 8.")
        else:
            upsert_bracket_picks(player, "ThirdPlaced", picks)
            invalidate()
            st.success("Saved.")
            st.rerun()


# ---------------------------------------------------------------------------
# 4-7. R16 / QF / SF / Final - cascading multiselect
# ---------------------------------------------------------------------------

_HEADER_NUMBER = {"R16": "4", "QF": "5", "SF": "6", "Final": "7"}


def _section_knockout(
    player: str,
    locked: bool,
    existing: dict[str, list[str]],
    *,
    stage: str,
    count: int,
    pool: list[str],
    label: str,
    prev_label: str,
) -> None:
    st.header(f"{_HEADER_NUMBER[stage]}. {label}")
    st.caption(f"Pick exactly {count} winners from your {prev_label}.")

    stored = existing.get(stage, [])
    _stale_hint(stored, pool, locked)
    current = [t for t in stored if t in pool]

    if locked:
        st.text("Your picks: " + (", ".join(current) if current else "-"))
        return

    if len(pool) < count:
        st.info(f"Save your {prev_label} first, you need at least {count} options here to proceed.")
        return

    picks = st.multiselect(
        f"Pick exactly {count}",
        options=pool,
        default=current,
        max_selections=count,
        key=f"knockout::{stage}",
    )
    if st.button(f"Save {label}", key=f"save_{stage}", type="primary"):
        if len(picks) != count:
            st.error(f"You picked {len(picks)}, must be exactly {count}.")
        else:
            upsert_bracket_picks(player, stage, picks)
            invalidate()
            st.success("Saved.")
            st.rerun()


# ---------------------------------------------------------------------------
# 8. Champion
# ---------------------------------------------------------------------------

def _section_player_awards(player: str, locked: bool, existing: dict[str, list[str]]) -> None:
    st.header("9. Player Awards")
    st.caption(
        "Type the player's name for each award. "
        "Matching is lenient - case, accents, and punctuation are ignored."
    )

    cur_boot = (existing.get("GoldenBoot") or [""])[0]
    cur_ball = (existing.get("GoldenBall") or [""])[0]

    if locked:
        c1, c2 = st.columns(2)
        c1.text(f"Golden Boot (top scorer): {cur_boot or '-'}")
        c2.text(f"Golden Ball (best player): {cur_ball or '-'}")
        return

    c1, c2 = st.columns(2)
    boot = c1.text_input("Golden Boot (top scorer)", value=cur_boot, key="award_boot", placeholder="e.g. Kylian Mbappé")
    ball = c2.text_input("Golden Ball (best player)", value=cur_ball, key="award_ball", placeholder="e.g. Lionel Messi")

    if st.button("Save awards", key="save_awards", type="primary"):
        upsert_bracket_picks(player, "GoldenBoot", [boot.strip()] if boot.strip() else [])
        upsert_bracket_picks(player, "GoldenBall", [ball.strip()] if ball.strip() else [])
        invalidate()
        st.success("Saved.")
        st.rerun()


def _section_champion(player: str, locked: bool, existing: dict[str, list[str]], *, pool: list[str]) -> None:
    st.header("8. Champion")
    st.caption("Pick one of your two finalists. 10 pts if you nail it.")

    stored = existing.get("Champion", [])
    _stale_hint(stored, pool, locked)
    current = stored[0] if stored and stored[0] in pool else None

    if locked:
        st.text(f"Your pick: {current or '-'}")
        return

    if not pool:
        st.info("Save your Finalists picks first.")
        return

    idx = pool.index(current) if current in pool else None
    pick = st.selectbox("Champion", options=pool, index=idx, key="champion_pick", placeholder="Pick one")
    if st.button("Save champion", key="save_champ", type="primary"):
        if not pick:
            st.error("Pick someone.")
        else:
            upsert_bracket_picks(player, "Champion", [pick])
            invalidate()
            st.success("Saved.")
            st.rerun()
