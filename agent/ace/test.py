

from ace.playbook_core import Playbook

data: dict[str, list[dict]] = {}


async def _demo():
    playbook = Playbook.load_last_revision_of("incident_commander")
    print(playbook.to_markdown(without_bullets_ids=True, positive_only=False, without_points=True))
if __name__ == "__main__":
    import asyncio
    asyncio.run(_demo())
