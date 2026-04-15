import unittest
from contextlib import contextmanager
from unittest.mock import patch

from ace.pipeline import reflect_on_tasks
from ace.playbook_core import Playbook, PlaybookSection, PlaybookSectionBullet


def _sample_playbook(playbook_id: str) -> Playbook:
    return Playbook(
        playbook_id=playbook_id,
        sections={
            "sec_a": PlaybookSection(
                id="sec_a",
                bullets=[PlaybookSectionBullet(id="b1", content="one")],
            ),
        },
        number_of_revisions=3,
    )


class _FakeReflectorAgent:
    def __init__(self, assignee: str, playbooks: dict[str, Playbook]):
        self.assignee = assignee
        self.playbooks = playbooks

    async def call(self, shared: dict):
        self.playbooks[self.assignee].apply_bullet_tags([{"id": "b1", "tag": "helpful"}])
        shared["messages"].append({"role": "assistant", "content": []})


@contextmanager
def _create_reflector_agent_stub(assignee, task, playbooks):
    del task
    yield _FakeReflectorAgent(assignee, playbooks)


class TestReflectPipelineSnapshots(unittest.IsolatedAsyncioTestCase):
    async def test_reflect_on_tasks_snapshot_includes_updated_bullet_scores(self):
        playbook = _sample_playbook("coder_agent")
        tasks_map = {"coder_agent": [object()]}

        with patch("ace.pipeline.Playbook.load_last_revision_of", return_value=playbook):
            with patch("ace.pipeline.create_reflector_agent", side_effect=_create_reflector_agent_stub):
                with patch("ace.pipeline.get_reflections", return_value=[{"assignee": "coder_agent"}]):
                    result = await reflect_on_tasks.exec_async({"tasks_map": tasks_map})

        snapshot = result["reflections_by_assignee"]["coder_agent"]["playbook_snapshot"]
        self.assertEqual(snapshot["sections"]["sec_a"][0]["helpful"], 1)
        self.assertEqual(snapshot["sections"]["sec_a"][0]["harmful"], 0)


if __name__ == "__main__":
    unittest.main()
