"""Tests for Playbook.apply_operations (ADD / UPDATE / DELETE / NONE)."""

import unittest

from ace import (Playbook, PlaybookOperationError, PlaybookSection,
                 PlaybookSectionBullet)


def _sample_playbook() -> Playbook:
    return Playbook(
        playbook_id="p1",
        sections=[
            PlaybookSection(
                id="sec_a",
                bullets=[
                    PlaybookSectionBullet(id="b1", content="one"),
                    PlaybookSectionBullet(id="b2", content="two"),
                ],
            ),
            PlaybookSection(id="sec_b", bullets=[]),
        ],
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
        self.assertEqual(len(pb.sections[1].bullets), 1)
        self.assertEqual(pb.sections[1].bullets[0].id, "nb")
        self.assertEqual(pb.sections[1].bullets[0].content, "new line")

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
        self.assertEqual(pb.sections[0].bullets[0].content, "updated")
        self.assertEqual(pb.sections[0].bullets[0].id, "b1")

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
        self.assertEqual(len(pb.sections[0].bullets), 1)
        self.assertEqual(pb.sections[0].bullets[0].id, "b2")

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
        self.assertEqual(pb.sections[-1].id, "new_section")
        self.assertEqual(len(pb.sections[-1].bullets), 1)
        self.assertEqual(pb.sections[-1].bullets[0].id, "b9")
        self.assertEqual(pb.sections[-1].bullets[0].content, "new content")

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
        self.assertTrue(all(section.id != "sec_a" for section in pb.sections))

    def test_to_dict_excludes_empty_sections(self):
        pb = _sample_playbook()
        payload = pb.to_dict()
        self.assertEqual(len(payload["sections"]), 1)
        self.assertIn("sec_a", payload["sections"][0])

    def test_to_markdown_excludes_empty_sections(self):
        pb = _sample_playbook()
        md = pb.to_markdown()
        self.assertIn("### sec_a", md)
        self.assertNotIn("### sec_b", md)

    def test_apply_bullet_tags_helpful_adds_helpful_point(self):
        pb = _sample_playbook()
        self.assertEqual(pb.sections[0].bullets[0].useful, 0)
        self.assertEqual(pb.sections[0].bullets[0].helpful, 0)
        pb.apply_bullet_tags([{"id": "b1", "tag": "helpful"}])
        self.assertEqual(pb.sections[0].bullets[0].useful, 0)
        self.assertEqual(pb.sections[0].bullets[0].helpful, 1)

    def test_apply_bullet_tags_harmful_decrements_helpful_point(self):
        pb = _sample_playbook()
        self.assertEqual(pb.sections[0].bullets[0].useful, 0)
        self.assertEqual(pb.sections[0].bullets[0].helpful, 0)
        pb.apply_bullet_tags([{"id": "b1", "tag": "harmful"}])
        self.assertEqual(pb.sections[0].bullets[0].useful, 0)
        self.assertEqual(pb.sections[0].bullets[0].helpful, -1)

    def test_apply_bullet_tags_unknown_bullet_raises(self):
        pb = _sample_playbook()
        with self.assertRaises(PlaybookOperationError) as ctx:
            pb.apply_bullet_tags([{"id": "missing", "tag": "helpful"}])
        self.assertIn("Unknown bullet id", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
