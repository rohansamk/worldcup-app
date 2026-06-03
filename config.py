"""Static configuration for the World Cup 2026 prediction app.

All scoring weights, group definitions, and sheet schema live here.
Per-round deadlines live in the Google Sheet's Config tab so an admin
can change them without a code deploy.
"""
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Pacific/Auckland")
DISPLAY_TZ_LABEL = "NZT (UTC+12)"

# Google Sheet ID (from the URL between /d/ and /edit). Hardcoded for this
# league. Can be overridden via st.secrets["sheet_id"] if you ever fork it.
SHEET_ID = "1Um-vLb76XRsCGFpBQ7wgbSQ-Wi6Cj4mWZ1Mk7isqsdM"

GROUPS: dict[str, list[str]] = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia-Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["USA", "Paraguay", "Australia", "Turkiye"],
    "E": ["Germany", "Curacao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

ALL_TEAMS: list[str] = [t for teams in GROUPS.values() for t in teams]
TEAM_TO_GROUP: dict[str, str] = {
    team: group for group, teams in GROUPS.items() for team in teams
}

DRAW = "Draw"

GOLDEN_BOOT_POINTS = 5
GOLDEN_BALL_POINTS = 5

SCORING: dict[str, int] = {
    "group_match": 1,
    "group_first": 2,
    "group_second": 1,
    "r32": 1,
    "r16": 3,
    "qf": 4,
    "sf": 5,
    "final": 7,
    "champion": 10,
    "golden_boot": GOLDEN_BOOT_POINTS,
    "golden_ball": GOLDEN_BALL_POINTS,
}

# All predictions share one deadline. Once it passes, the whole predictions
# page locks (group matches, standings, and the entire knockout cascade).
DEADLINE_KEY = "deadline_group"

# Sheet tab names
TAB_PLAYERS          = "Players"
TAB_CONFIG           = "Config"
TAB_MATCHES          = "Matches"
TAB_MATCH_RESULTS    = "MatchResults"
TAB_ACTUAL_STANDINGS = "ActualGroupStandings"
TAB_ACTUAL_BRACKET   = "ActualBracket"
TAB_PRED_MATCHES     = "PredictionsMatches"
TAB_PRED_BRACKET     = "PredictionsBracket"

# Header rows for each tab (used when seeding empty tabs).
TAB_HEADERS: dict[str, list[str]] = {
    TAB_PLAYERS:          ["Name", "Passcode", "Active"],
    TAB_CONFIG:           ["Key", "Value"],
    TAB_MATCHES:          ["MatchID", "Group", "Team1", "Team2"],
    TAB_MATCH_RESULTS:    ["MatchID", "Result"],
    TAB_ACTUAL_STANDINGS: ["Group", "First", "Second", "Third"],
    TAB_ACTUAL_BRACKET:   ["Round", "Team"],
    TAB_PRED_MATCHES:     ["Player", "MatchID", "Pick", "UpdatedAt"],
    TAB_PRED_BRACKET:     ["Player", "Round", "Team", "UpdatedAt"],
}

ADMIN_PASSCODE_KEY = "admin_passcode"
