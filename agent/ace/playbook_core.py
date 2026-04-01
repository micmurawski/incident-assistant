"""Playbook model and apply_operations — no agent.tooling imports (safe for lightweight tests)."""

import glob
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Optional, TypedDict

import yaml

PLAYBOOK_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playbook_history")
os.makedirs(PLAYBOOK_HISTORY_DIR, exist_ok=True)


class PlaybookOperationError(Exception):
    pass


class Operation(TypedDict):
    action: Annotated[Literal["ADD", "UPDATE", "DELETE", "NONE"], "The action to perform on the playbook"]
    bullet_id: Annotated[
        Optional[str],
        "Bullet id — required for ADD, UPDATE, DELETE",
    ]
    section: Annotated[str, "The section of the playbook to perform the action on"]
    content: Annotated[str, "The content to perform the action on"]


class BulletTag(TypedDict):
    id: Annotated[str, "The id of the bulletpoint"]
    tag: Annotated[
        Literal["helpful", "harmful", "neutral"],
        "The tag for the bulletpoint",
    ]


@dataclass
class PlaybookSectionBullet:
    id: Annotated[str, "The id of the bulletpoint"]
    content: Annotated[str, "The content of the bulletpoint"]
    helpful: Annotated[int, "The score for the bulletpoint based on helpfulness feedback"] = 0
    harmful: Annotated[int, "The score for the bulletpoint based on harmfulness feedback"] = 0

    def to_dict(self, without_id: bool = False, without_points: bool = False) -> dict:
        data = {
            "id": self.id,
            "content": self.content,
            "harmful": self.harmful,
            "helpful": self.helpful,
        }
        if without_points:
            del data["harmful"]
            del data["helpful"]
        if without_id:
            del data["id"]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "PlaybookSectionBullet":
        return PlaybookSectionBullet(
            id=data["id"],
            content=data["content"],
            harmful=data.get("harmful", 0),
            helpful=data.get("helpful", 0),
        )

    def model_dump(self) -> dict:
        return self.to_dict()


@dataclass
class PlaybookSection:
    id: Annotated[str, "The id of the section"]
    bullets: Annotated[list[PlaybookSectionBullet], "The bullets in the section"]

    def to_dict(self, without_bullets_ids: bool = False, positive_only: bool = False, without_points: bool = False) -> dict:
        if positive_only:
            selected_bullets = list(filter(lambda b: (b.harmful - b.helpful) > 0, self.bullets))
        else:
            selected_bullets = self.bullets
        bullets_data = [bullet.to_dict(without_id=without_bullets_ids, without_points=without_points)
                        for bullet in selected_bullets]
        if without_bullets_ids and without_points:
            bullets_data = [bullet["content"] for bullet in bullets_data]
        return {
            self.id: bullets_data
        }

    def model_dump(self) -> dict:
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> "PlaybookSection":
        for _id, bullets in data.items():
            return PlaybookSection(
                id=_id,
                bullets=[PlaybookSectionBullet.from_dict(bullet) for bullet in bullets],
            )


@dataclass
class Playbook:
    playbook_id: Annotated[str, "The id of the playbook"]
    sections: Annotated[list[PlaybookSection], "The sections in the playbook"]
    number_of_revisions: Annotated[int, "The number of revisions of the playbook"]

    def _non_empty_sections(self) -> list[PlaybookSection]:
        return [section for section in self.sections if section.bullets]

    def _non_empty_section_data(self, without_bullets_ids: bool = False, positive_only: bool = False, without_points: bool = False) -> list[dict]:
        sections = []
        for section in self.sections:
            section_data = section.to_dict(without_bullets_ids, positive_only, without_points)
            _key = next(iter(section_data.keys()), None)
            if not _key:
                continue
            if section_data[_key]:
                sections.append({_key: section_data[_key]})
        return sections

    def to_dict(self, without_bullets_ids: bool = False, positive_only: bool = False, without_points: bool = False) -> dict:
        sections = self._non_empty_section_data(without_bullets_ids, positive_only, without_points)
        return {
            "playbook_id": self.playbook_id,
            "sections": sections,
        }

    def to_file(self, file_path: str):
        with open(file_path, "w") as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def from_dict(cls, data: dict, rev_number: int = 0) -> "Playbook":
        return Playbook(
            playbook_id=data["playbook_id"],
            sections=[PlaybookSection.from_dict(section) for section in data["sections"]],
            number_of_revisions=rev_number,
        )

    def save_revision(self):
        ts = str(datetime.now().timestamp()).replace(".", "")
        file_name = f"{self.playbook_id}-{ts}.json"
        file_path = os.path.join(PLAYBOOK_HISTORY_DIR, file_name)
        self.to_file(file_path)
        return file_path

    @classmethod
    def load_last_revision_of(cls, playbook_id: str):
        files = glob.glob(os.path.join(PLAYBOOK_HISTORY_DIR, f"{playbook_id}-*.json"))
        number_of_revs = len(files)
        if not files:
            playbook = cls(playbook_id=playbook_id, sections=[], number_of_revisions=0)
            playbook.save_revision()
            return playbook
        latest_file = max(files, key=lambda x: os.path.getctime(x))
        return cls.from_file(latest_file, rev_number=number_of_revs)

    def load_latest_revision(self):
        files = glob.glob(os.path.join(PLAYBOOK_HISTORY_DIR, f"{self.playbook_id}-*.json"))
        if not files:
            return None
        latest_file = max(files, key=lambda x: os.path.getctime(x))
        return self.from_file(latest_file)

    def to_yaml(self, without_bullets_ids: bool = False, positive_only: bool = False, without_points: bool = False) -> str:
        sections_data = self._non_empty_section_data(without_bullets_ids, positive_only, without_points)
        return yaml.dump(sections_data, indent=4, sort_keys=False)

    def to_markdown(self, without_bullets_ids: bool = False, positive_only: bool = False, without_points: bool = False) -> str:
        result = f"# Playbook (revision {self.number_of_revisions})\n\n"
        sections_data = self._non_empty_section_data(without_bullets_ids, positive_only, without_points)

        if len(sections_data) > 0:
            result += "## Sections\n\n"
        else:
            result += "NOTE: Playbook is empty. Add some sections and bullets to get started.\n"
        for section in sections_data:
            section_id = next(iter(section.keys()), None)
            if not section_id:
                continue
            result += f"### {section_id}\n\n"
            bullets = section[section_id]
            if without_bullets_ids:
                bullets_yaml = yaml.dump(bullets, indent=4, sort_keys=False)
                result += f"{bullets_yaml}\n"
            else:
                bullets_yaml = yaml.dump(bullets, indent=4, sort_keys=False)
                result += f"{bullets_yaml}\n"
            result += "\n"
        return result

    def model_dump(self) -> dict:
        sections = self._non_empty_sections()
        return {
            "playbook_id": self.playbook_id,
            "sections": [section.model_dump() for section in sections],
        }

    @classmethod
    def from_file(cls, file_path: str, rev_number: int = 0) -> "Playbook":
        with open(file_path, "r") as f:
            return cls.from_dict(json.load(f), rev_number=rev_number)

    def _section_by_id(self, section_id: str) -> "PlaybookSection":
        for s in self.sections:
            if s.id == section_id:
                return s
        raise PlaybookOperationError(f"Unknown section: {section_id!r}")

    def _section_by_id_or_create(self, section_id: str) -> "PlaybookSection":
        for s in self.sections:
            if s.id == section_id:
                return s
        section = PlaybookSection(id=section_id, bullets=[])
        self.sections.append(section)
        return section

    def _bullet_index(self, section: "PlaybookSection", bullet_id: str) -> int:
        for i, b in enumerate(section.bullets):
            if b.id == bullet_id:
                return i
        raise PlaybookOperationError(f"Unknown bullet id: {bullet_id!r} in section {section.id!r}")

    def apply_bullet_tags(self, bullet_tags: list[BulletTag]):
        bullet_by_id = {
            bullet.id: bullet
            for section in self.sections
            for bullet in section.bullets
        }
        for bullet_tag in bullet_tags:
            bullet_id = bullet_tag["id"]
            if bullet_id not in bullet_by_id:
                raise PlaybookOperationError(f"Unknown bullet id: {bullet_id!r}")
            tag = bullet_tag["tag"]
            if tag == "helpful":
                bullet_by_id[bullet_id].helpful += 1
            elif tag == "harmful":
                bullet_by_id[bullet_id].helpful -= 1
            elif tag == "neutral":
                continue
            else:
                raise PlaybookOperationError(f"Invalid bullet tag: {tag!r}")
        self.save_revision()

    def apply_operations(self, operations: list[Operation]):
        for operation in operations:
            action = operation["action"]
            if action == "NONE":
                continue
            if action == "ADD":
                section = self._section_by_id_or_create(operation["section"])
                bid = operation.get("bullet_id")
                if not bid:
                    raise PlaybookOperationError("ADD requires bullet_id")
                section.bullets.append(
                    PlaybookSectionBullet(id=bid, content=operation["content"])
                )
            elif action == "UPDATE":
                section = self._section_by_id(operation["section"])
                bid = operation.get("bullet_id")
                if not bid:
                    raise PlaybookOperationError("UPDATE requires bullet_id")
                i = self._bullet_index(section, bid)
                section.bullets[i].content = operation["content"]
            elif action == "DELETE":
                section = self._section_by_id(operation["section"])
                bid = operation.get("bullet_id")
                if not bid:
                    raise PlaybookOperationError("DELETE requires bullet_id")
                i = self._bullet_index(section, bid)
                section.bullets.pop(i)
                if not section.bullets:
                    self.sections = [s for s in self.sections if s.id != section.id]
            else:
                raise PlaybookOperationError(f"Invalid action: {action!r}")
        self.save_revision()
