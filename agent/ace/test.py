from ace.playbook_core import Playbook, PlaybookSection, PlaybookSectionBullet


async def _demo():
    playbook = Playbook(
        playbook_id="test",
        sections=[PlaybookSection(id="test", bullets=[PlaybookSectionBullet(id="test", content="test")])],
    )
    playbook.to_file("test.json")
    loaded = playbook.from_file("test.json")
    print(loaded.to_dict())
    print(loaded.to_markdown())
    print(loaded.save_revision())
    print(loaded.load_latest_revision())
    loaded.apply_operations(
        [
            {
                "action": "ADD",
                "section": "test",
                "bullet_id": "b2",
                "content": "second bullet",
            }
        ]
    )
    print("after ADD:", loaded.to_dict())


if __name__ == "__main__":
    import asyncio

    asyncio.run(_demo())
