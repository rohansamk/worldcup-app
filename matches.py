"""Generate the 72 group-stage matches (round-robin within each group)."""
from itertools import combinations

from config import GROUPS


def generate_group_matches() -> list[dict[str, str]]:
    """Return all 72 group matches as dicts with MatchID/Group/Team1/Team2.

    MatchID format: "<GroupLetter>-<index>", e.g. "A-1" through "A-6".
    Match ordering within a group is stable (sorted by team order in GROUPS)
    but does not affect scoring.
    """
    matches: list[dict[str, str]] = []
    for group, teams in GROUPS.items():
        for i, (t1, t2) in enumerate(combinations(teams, 2), start=1):
            matches.append({
                "MatchID": f"{group}-{i}",
                "Group": group,
                "Team1": t1,
                "Team2": t2,
            })
    return matches
