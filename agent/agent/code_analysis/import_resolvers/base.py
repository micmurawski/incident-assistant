from dataclasses import dataclass
from typing import Optional


@dataclass
class DepInfo:
    file_path: str
    import_path: str
    ref: str
    resolved_path: Optional[str] = None
    is_builtin: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "DepInfo":
        return cls(
            file_path=data['file_path'],
            import_path=data['import_path'],
            ref=data['ref'],
            resolved_path=data['resolved_path'],
            is_builtin=data.get('is_builtin', False)
        )
