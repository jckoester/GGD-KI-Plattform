from app.litellm.client import LiteLLMClient
from app.litellm.teams import is_phase1_team


async def reconcile_user_team(
    client: LiteLLMClient,
    pseudonym: str,
    target_team_id: str,
    current_team_ids: set[str],
) -> dict:
    """
    Synchronisiert Phase-1 Team-Membership auf genau ein Zielteam.
    Fremdteams (nicht Phase-1) werden nicht verändert.
    """
    current_phase1 = {team for team in current_team_ids if is_phase1_team(team)}
    to_remove = sorted(current_phase1 - {target_team_id})
    to_add = [] if target_team_id in current_phase1 else [target_team_id]

    for team_id in to_remove:
        await client.remove_team_member(team_id, pseudonym)
    for team_id in to_add:
        await client.add_team_member(team_id, pseudonym)

    return {
        "added": to_add,
        "removed": to_remove,
        "unchanged": not to_remove and not to_add,
    }

