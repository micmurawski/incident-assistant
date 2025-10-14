from typing import Any, Callable, Literal, TypedDict

XmlMatcherState = Literal["TEXT", "TAG_OPEN", "TAG_CLOSE"]


class XmlMatchResult(TypedDict):
    matched: bool
    data: str


class XmlMatcher:
    def __init__(
        self,
        tag_name: str,
        transform: Callable | None = None,
        position: int = 0,
    ):
        self.tag_name = tag_name
        self.transform = transform
        self.position = position
        self.matched = False
        self.chunks: list[XmlMatchResult] = []
        self.cached: list[str] = []
        self.state: XmlMatcherState = "TEXT"
        self.depth: int = 0
        self.pointer: int = 0
        self.index: int = 0  # ADD THIS - was missing!

    def _collect(self):
        if not self.cached:
            return

        last = self.chunks[-1] if self.chunks else None
        data = "".join(self.cached)
        matched = self.matched

        if last is not None and last["matched"] == matched:
            last["data"] += data
        else:
            self.chunks.append(
                XmlMatchResult(
                    data=data,
                    matched=matched,
                )
            )
        self.cached = []

    def _pop(self) -> Any:
        chunks = self.chunks
        self.chunks = []
        if not self.transform:
            return chunks
        return list(map(self.transform, chunks))

    def _update(self, chunk: str):
        for char in chunk:
            self.cached.append(char)
            self.pointer += 1

            if self.state == "TEXT":
                if char == "<" and (self.pointer <= self.position + 1 or self.matched):
                    self.state = "TAG_OPEN"
                    self.index = 0
                else:
                    self._collect()
            elif self.state == "TAG_OPEN":
                if char == ">" and self.index == len(self.tag_name):
                    self.state = "TEXT"
                    if not self.matched:
                        self.cached = []
                    self.depth += 1
                    self.matched = True
                elif self.index == 0 and char == "/":
                    self.state = "TAG_CLOSE"
                elif char == " " and (self.index == 0 or self.index == len(self.tag_name)):
                    continue
                elif self.index < len(self.tag_name) and self.tag_name[self.index] == char:
                    self.index += 1
                else:
                    self.state = "TEXT"
                    self._collect()
            elif self.state == "TAG_CLOSE":
                if char == ">" and self.index == len(self.tag_name):
                    self.state = "TEXT"
                    self.depth -= 1
                    self.matched = self.depth > 0
                    if not self.matched:
                        self.cached = []
                elif char == " " and (self.index == 0 or self.index == len(self.tag_name)):
                    continue
                elif self.index < len(self.tag_name) and self.tag_name[self.index] == char:
                    self.index += 1
                else:
                    self.state = "TEXT"
                    self._collect()

    def final(self, chunk: str | None = None) -> Any:
        if chunk:
            self._update(chunk)
        self._collect()
        return self._pop()

    def update(self, chunk: str) -> Any:
        self._update(chunk)
        return self._pop()
