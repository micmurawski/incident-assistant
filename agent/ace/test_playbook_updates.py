"""Tests for Playbook.apply_operations (ADD / UPDATE / DELETE / NONE)."""

import glob
import os
import tempfile
import unittest
from unittest.mock import patch

from ace.playbook_core import (Playbook, PlaybookOperationError,
                               PlaybookSection, PlaybookSectionBullet)


def _sample_playbook() -> Playbook:
    return Playbook(
        playbook_id="p1",
        sections={
            "sec_a": PlaybookSection(
                id="sec_a",
                bullets=[
                    PlaybookSectionBullet(id="b1", content="one"),
                    PlaybookSectionBullet(id="b2", content="two"),
                ],
            ),
            "sec_b": PlaybookSection(id="sec_b", bullets=[]),
        },
        number_of_revisions=0,
    )


class TestPlaybookUpdates(unittest.TestCase):
    def test_add_appends_bullet(self):
        pb = _sample_playbook()
        pb.apply_operations(
            [
                {
                    "action": "ADD",
                    "section": "sec_b",
                    "bullet_id": "nb",
                    "content": "new line",
                }
            ]
        )
        self.assertEqual(len(pb.sections["sec_b"].bullets), 1)
        self.assertTrue(pb.sections["sec_b"].bullets[0].id.startswith("nb-"))
        self.assertEqual(pb.sections["sec_b"].bullets[0].content, "new line")

    def test_update_changes_content(self):
        pb = _sample_playbook()
        pb.apply_operations(
            [
                {
                    "action": "UPDATE",
                    "section": "sec_a",
                    "bullet_id": "b1",
                    "content": "updated",
                }
            ]
        )
        self.assertEqual(pb.sections["sec_a"].bullets[0].content, "updated")
        self.assertEqual(pb.sections["sec_a"].bullets[0].id, "b1")

    def test_delete_removes_bullet(self):
        pb = _sample_playbook()
        pb.apply_operations(
            [
                {
                    "action": "DELETE",
                    "section": "sec_a",
                    "bullet_id": "b1",
                    "content": "",
                }
            ]
        )
        self.assertEqual(len(pb.sections["sec_a"].bullets), 1)
        self.assertEqual(pb.sections["sec_a"].bullets[0].id, "b2")

    def test_none_is_noop(self):
        pb = _sample_playbook()
        before = pb.to_dict()
        pb.apply_operations([{"action": "NONE", "section": "sec_a", "content": ""}])
        self.assertEqual(pb.to_dict(), before)

    def test_add_requires_bullet_id(self):
        pb = _sample_playbook()
        with self.assertRaises(PlaybookOperationError) as ctx:
            pb.apply_operations(
                [
                    {
                        "action": "ADD",
                        "section": "sec_b",
                        "bullet_id": None,
                        "content": "x",
                    }
                ]
            )
        self.assertIn("bullet_id", str(ctx.exception))

    def test_unknown_section(self):
        pb = _sample_playbook()
        with self.assertRaises(PlaybookOperationError) as ctx:
            pb.apply_operations(
                [
                    {
                        "action": "UPDATE",
                        "section": "nope",
                        "bullet_id": "x",
                        "content": "y",
                    }
                ]
            )
        self.assertIn("Unknown section", str(ctx.exception))

    def test_unknown_bullet_on_update(self):
        pb = _sample_playbook()
        with self.assertRaises(PlaybookOperationError) as ctx:
            pb.apply_operations(
                [
                    {
                        "action": "UPDATE",
                        "section": "sec_a",
                        "bullet_id": "missing",
                        "content": "z",
                    }
                ]
            )
        self.assertIn("Unknown bullet", str(ctx.exception))
        self.assertIn("does not exist in the playbook", str(ctx.exception))

    def test_unknown_bullet_on_update_reports_actual_section_hint(self):
        pb = _sample_playbook()
        with self.assertRaises(PlaybookOperationError) as ctx:
            pb.apply_operations(
                [
                    {
                        "action": "UPDATE",
                        "section": "sec_b",
                        "bullet_id": "b1",
                        "content": "z",
                    }
                ]
            )
        self.assertIn("Unknown bullet id", str(ctx.exception))
        self.assertIn("exists in section(s): 'sec_a'", str(ctx.exception))

    def test_unknown_bullet_on_delete_reports_actual_section_hint(self):
        pb = _sample_playbook()
        with self.assertRaises(PlaybookOperationError) as ctx:
            pb.apply_operations(
                [
                    {
                        "action": "DELETE",
                        "section": "sec_b",
                        "bullet_id": "b2",
                        "content": "",
                    }
                ]
            )
        self.assertIn("Unknown bullet id", str(ctx.exception))
        self.assertIn("exists in section(s): 'sec_a'", str(ctx.exception))

    def test_add_creates_missing_section(self):
        pb = _sample_playbook()
        pb.apply_operations(
            [
                {
                    "action": "ADD",
                    "section": "new_section",
                    "bullet_id": "b9",
                    "content": "new content",
                }
            ]
        )
        self.assertEqual(pb.sections["new_section"].id, "new_section")
        self.assertEqual(len(pb.sections["new_section"].bullets), 1)
        self.assertTrue(pb.sections["new_section"].bullets[0].id.startswith("b9-"))
        self.assertEqual(pb.sections["new_section"].bullets[0].content, "new content")

    def test_add_normalizes_existing_short_suffix(self):
        pb = _sample_playbook()
        pb.apply_operations(
            [
                {
                    "action": "ADD",
                    "section": "sec_b",
                    "bullet_id": "diagnose-missing-text-index-e4f1",
                    "content": "new content",
                }
            ]
        )
        added_id = pb.sections["sec_b"].bullets[0].id
        self.assertRegex(added_id, r"^diagnose-missing-text-index-[0-9a-f]{4}$")
        self.assertNotRegex(added_id, r"^diagnose-missing-text-index-e4f1-[0-9a-f]{4}$")

    def test_delete_removes_section_when_empty(self):
        pb = _sample_playbook()
        pb.apply_operations(
            [
                {
                    "action": "DELETE",
                    "section": "sec_a",
                    "bullet_id": "b1",
                    "content": "",
                },
                {
                    "action": "DELETE",
                    "section": "sec_a",
                    "bullet_id": "b2",
                    "content": "",
                },
            ]
        )
        self.assertTrue(all(section.id != "sec_a" for section in pb.sections.values()))

    def test_to_dict_excludes_empty_sections(self):
        pb = _sample_playbook()
        payload = pb.to_dict()
        self.assertEqual(len(payload["sections"]), 1)
        self.assertIn("sec_a", payload["sections"])

    def test_to_markdown_excludes_empty_sections(self):
        pb = _sample_playbook()
        md = pb.to_markdown()
        self.assertIn("### sec_a", md)
        self.assertNotIn("### sec_b", md)

    def test_apply_bullet_tags_helpful_adds_helpful_point(self):
        pb = _sample_playbook()
        self.assertEqual(pb.sections["sec_a"].bullets[0].helpful, 0)
        pb.apply_bullet_tags([{"id": "b1", "tag": "helpful"}])
        self.assertEqual(pb.sections["sec_a"].bullets[0].helpful, 1)

    def test_apply_bullet_tags_harmful_increments_harmful_point(self):
        pb = _sample_playbook()
        self.assertEqual(pb.sections["sec_a"].bullets[0].harmful, 0)
        pb.apply_bullet_tags([{"id": "b1", "tag": "harmful"}])
        self.assertEqual(pb.sections["sec_a"].bullets[0].harmful, 1)

    def test_apply_bullet_tags_unknown_bullet_raises(self):
        pb = _sample_playbook()
        with self.assertRaises(PlaybookOperationError) as ctx:
            pb.apply_bullet_tags([{"id": "missing", "tag": "helpful"}])
        self.assertIn("Unknown bullet id", str(ctx.exception))


class TestPlaybookDraftCommit(unittest.TestCase):
    def _history_glob(self, history_dir: str, playbook_id: str) -> list[str]:
        return glob.glob(os.path.join(history_dir, f"{playbook_id}-*.json"))

    def test_apply_operations_auto_save_false_skips_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("ace.playbook_core.PLAYBOOK_HISTORY_DIR", tmp):
                pb = _sample_playbook()
                pb.playbook_id = "draft_ops"
                pb.auto_save = False
                pb.apply_operations(
                    [
                        {
                            "action": "ADD",
                            "section": "sec_b",
                            "bullet_id": "nb",
                            "content": "new line",
                        }
                    ]
                )
                self.assertEqual(self._history_glob(tmp, "draft_ops"), [])

    def test_apply_bullet_tags_auto_save_false_skips_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("ace.playbook_core.PLAYBOOK_HISTORY_DIR", tmp):
                pb = _sample_playbook()
                pb.playbook_id = "draft_tags"
                pb.auto_save = False
                pb.apply_bullet_tags([{"id": "b1", "tag": "helpful"}])
                self.assertEqual(self._history_glob(tmp, "draft_tags"), [])
                self.assertEqual(pb.sections["sec_a"].bullets[0].helpful, 1)

    def test_commit_persists_and_sets_auto_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("ace.playbook_core.PLAYBOOK_HISTORY_DIR", tmp):
                pb = _sample_playbook()
                pb.playbook_id = "commit_test"
                pb.auto_save = False
                pb.apply_bullet_tags([{"id": "b1", "tag": "helpful"}])
                path = pb.commit()
                self.assertTrue(pb.auto_save)
                self.assertEqual(len(self._history_glob(tmp, "commit_test")), 1)
                self.assertTrue(os.path.isfile(path))
                loaded = Playbook.from_file(path)
                self.assertEqual(loaded.sections["sec_a"].bullets[0].helpful, 1)

    def test_snapshot_roundtrip_for_pipeline(self):
        pb = _sample_playbook()
        pb.playbook_id = "snap_r"
        pb.auto_save = False
        pb.apply_bullet_tags([{"id": "b1", "tag": "harmful"}])
        snap = pb.to_dict()
        rev = pb.number_of_revisions
        restored = Playbook.from_dict(snap, rev_number=rev, auto_save=False)
        self.assertEqual(restored.sections["sec_a"].bullets[0].harmful, 1)
        self.assertFalse(restored.auto_save)


if __name__ == "__main__":
    unittest.main()
