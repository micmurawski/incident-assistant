"""Playbook model and apply_operations — no agent.tooling imports (safe for lightweight tests)."""

import glob
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Optional, TypedDict

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
    tag: Annotated[Literal["helpful", "harmful", "neutral"], "The tag for the bulletpoint"]


@dataclass
class PlaybookSectionBullet:
    id: Annotated[str, "The id of the bulletpoint"]
    content: Annotated[str, "The content of the bulletpoint"]

    def to_dict(self, without_id: bool = False) -> dict:
        if without_id:
            return {
                "content": self.content,
            }
        return {
            "id": self.id,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlaybookSectionBullet":
        return PlaybookSectionBullet(
            id=data["id"],
            content=data["content"],
        )


@dataclass
class PlaybookSection:
    id: Annotated[str, "The id of the section"]
    bullets: Annotated[list[PlaybookSectionBullet], "The bullets in the section"]

    def to_dict(self, without_bullets_ids: bool = False) -> dict:
        if without_bullets_ids:
            return {
                self.id: [bullet.to_dict(without_id=True)["content"] for bullet in self.bullets]
            }
        return {
            self.id: [bullet.to_dict(without_id=without_bullets_ids) for bullet in self.bullets]
        }

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

    def to_dict(self, without_bullets_ids: bool = False) -> dict:
        return {
            "playbook_id": self.playbook_id,
            "sections": [section.to_dict(without_bullets_ids=without_bullets_ids) for section in self.sections],
        }

    def to_file(self, file_path: str):
        with open(file_path, "w") as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def from_dict(cls, data: dict) -> "Playbook":
        return Playbook(
            playbook_id=data["playbook_id"],
            sections=[PlaybookSection.from_dict(section) for section in data["sections"]],
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
        if not files:
            playbook = cls(playbook_id=playbook_id, sections=[])
            playbook.save_revision()
            return playbook
        latest_file = max(files, key=lambda x: os.path.getctime(x))
        return cls.from_file(latest_file)

    def load_latest_revision(self):
        files = glob.glob(os.path.join(PLAYBOOK_HISTORY_DIR, f"{self.playbook_id}-*.json"))
        if not files:
            return None
        latest_file = max(files, key=lambda x: os.path.getctime(x))
        return self.from_file(latest_file)

    def to_markdown(self) -> str:
        result = ""
        for section in self.sections:
            result += f"## {section.id}\n\n"
            for bullet in section.bullets:
                result += f"- {bullet.content}\n"
            result += "\n"
        return result

    def from_file(self, file_path: str) -> "Playbook":
        with open(file_path, "r") as f:
            return self.from_dict(json.load(f))

    def _section_by_id(self, section_id: str) -> "PlaybookSection":
        for s in self.sections:
            if s.id == section_id:
                return s
        raise PlaybookOperationError(f"Unknown section: {section_id!r}")

    def _bullet_index(self, section: "PlaybookSection", bullet_id: str) -> int:
        for i, b in enumerate(section.bullets):
            if b.id == bullet_id:
                return i
        raise PlaybookOperationError(f"Unknown bullet id: {bullet_id!r} in section {section.id!r}")

    def apply_operations(self, operations: list[Operation]):
        for operation in operations:
            action = operation["action"]
            if action == "NONE":
                continue
            section = self._section_by_id(operation["section"])
            if action == "ADD":
                bid = operation.get("bullet_id")
                if not bid:
                    raise PlaybookOperationError("ADD requires bullet_id")
                section.bullets.append(
                    PlaybookSectionBullet(id=bid, content=operation["content"])
                )
            elif action == "UPDATE":
                bid = operation.get("bullet_id")
                if not bid:
                    raise PlaybookOperationError("UPDATE requires bullet_id")
                i = self._bullet_index(section, bid)
                section.bullets[i].content = operation["content"]
            elif action == "DELETE":
                bid = operation.get("bullet_id")
                if not bid:
                    raise PlaybookOperationError("DELETE requires bullet_id")
                i = self._bullet_index(section, bid)
                section.bullets.pop(i)
            else:
                raise PlaybookOperationError(f"Invalid action: {action!r}")
