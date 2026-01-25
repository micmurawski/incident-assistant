import hashlib
import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from tree_sitter import Node, Parser, QueryCursor, Tree

from agent.code_index.code_analysis.import_resolvers.base import DepInfo
from agent.code_index.code_analysis.loader import TreeSitterLoader
from agent.code_index.code_analysis.markdown_parser import parse_markdown
from agent.constants import (EXTENSIONS, FALLBACK_EXTENSION, MAX_BLOCK_CHARS,
                             MAX_CHARS_TOLERANCE_FACTOR, MIN_BLOCK_CHARS,
                             MIN_CHUNK_REMAINDER_CHARS)

Options = Optional[Dict[str, Any]]


def read_lines(filepath: str, start: int, end: int) -> list[str]:
    if start < 1 or end < 1:
        raise ValueError("Line numbers must be positive integers")

    if start > end:
        raise ValueError("Start line number cannot be greater than end line number")

    lines = []

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            for current_line_num, line in enumerate(file, 1):
                if current_line_num >= start and current_line_num <= end:
                    lines.append(line.rstrip("\n\r"))
                elif current_line_num > end:
                    break  # Stop reading once we've passed the end line

    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")

    return lines


@dataclass
class CodeBlock:
    file_path: str
    type: str
    start_line: int
    end_line: int
    content: bytes
    file_hash: str
    segment_hash: str
    identifier: Optional[str] = None
    dep_infos: Optional[List[DepInfo]] = field(default_factory=list)

    def to_file(self):
        path = os.path.join("store", f"{self.file_hash}-{self.segment_hash}")
        with open(path, "w") as f:
            f.write(f"FILE_PATH: {self.file_path}\n")
            f.write(f"TYPE: {self.type}\n")
            f.write(f"IDENTIFIER: {self.identifier}\n")
            f.write(f"START_LINE: {self.start_line}\n")
            f.write(f"END_LINE: {self.end_line}\n\n")
            f.write(f"DEP_INFOS: {self.dep_infos}\n")

            f.write(self.content.decode("utf-8"))


class CodeParser:
    """
    CodeParser is a class that parses code files and returns a list of CodeBlock objects.
    """

    loaded_parsers: Dict[str, Any] = {}

    def is_supported_extension(self, ext: str) -> bool:
        return ext in EXTENSIONS

    @staticmethod
    def create_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def parse_file(
        self, work_dir: str, file_path: str, options: Options = None
    ) -> Coroutine[Any, Any, List[CodeBlock]]:
        options = options or {}

        ext = Path(file_path).suffix.lower()
        if not self.is_supported_extension(ext):
            return []

        content: str
        file_hash: str

        if "content" in options:
            content = options["content"]
            file_hash = options["file_hash"] or self.create_hash(content)
        else:
            try:
                content = open(file_path, "rb").read()
                file_hash = self.create_hash(content)
            except Exception as e:
                # add error logs
                print(f"Error parsing file {file_path}: {str(e)}")
                return []

        return await self.parse_content(work_dir, file_path, content, file_hash)

    async def parse_content(
        self, work_dir: str, file_path: str, content: bytes, file_hash: str
    ) -> Coroutine[Any, Any, List[CodeBlock]]:
        ext = Path(file_path).suffix.lower()[1:]
        seen_segment_hashes: set[str] = set()

        if ext in ["md", "markdown"]:
            return self.parse_markdown(file_path, content, file_hash, seen_segment_hashes)

        if f".{ext}" in FALLBACK_EXTENSION:
            raise Exception(f"Unsupported file type: {file_path}")

        # TODO: Add loading of parsers
        if ext not in self.loaded_parsers:
            parser = TreeSitterLoader.load_parser(ext)
            if parser is None:
                return self.parse_markdown(file_path, content, file_hash, seen_segment_hashes)
            self.loaded_parsers[ext] = parser

        language: dict[str, Any] = self.loaded_parsers[ext]
        cursor: QueryCursor = language["cursor"]
        parser: Parser = language["parser"]
        tree: Tree = parser.parse(content)
        captures = cursor.captures(tree.root_node) if tree else []

        if len(captures) == 0:
            if len(content) >= MIN_BLOCK_CHARS:
                blocks = self.perform_fallback_chunking(content, file_path, file_hash, seen_segment_hashes)
                return blocks
            else:
                return []

        results: List[CodeBlock] = []
        q = deque()

        for capture in captures.values():
            for node in capture:
                q.appendleft(node)

        while q:
            current_node: Node = q.popleft()
            if len(current_node.text) >= MIN_BLOCK_CHARS:
                if len(current_node.text) > MAX_BLOCK_CHARS * MAX_CHARS_TOLERANCE_FACTOR:
                    for child in current_node.children:
                        if child:
                            q.appendleft(child)
                else:
                    chunked_blocks = self.chunk_leaf_node_by_lines(
                        current_node, file_path, file_hash, seen_segment_hashes
                    )
                    if chunked_blocks:
                        results.extend(chunked_blocks)
            else:
                attr1 = current_node.child_by_field_name("name")
                attr2 = next(filter(lambda x: x.type == "identifier", current_node.children), None)
                _id = attr1.text.decode("utf8") if attr1 else (attr2.text.decode("utf8") if attr2 else None)

                _type = current_node.type
                if _type == "identifier" and _id is None:
                    _id = current_node.text.decode("utf8")

                start_line = current_node.start_point[0] + 1
                end_line = current_node.end_point[0] + 1
                content = current_node.text
                content_preview = current_node.text[:100]

                segment_hash = self.create_hash(
                    f"{file_path}-{start_line}-{end_line}-{len(content)}-{content_preview}".encode("utf-8")
                )

                if segment_hash not in seen_segment_hashes:
                    seen_segment_hashes.add(segment_hash)

                    dep_infos = []
                    # TODO: Add import analysis
                    # if _type in ["import_from_statement", "import_statement"] and self.loaded_parsers[ext]["import_resolver"]:
                    #    dep_infos = self.loaded_parsers[ext]["import_resolver"].resolve_import(
                    #        work_dir,
                    #        file_path,
                    #        content.decode('utf-8'),
                    #    )
                    results.append(
                        CodeBlock(
                            identifier=_id,
                            file_path=file_path,
                            type=_type,
                            start_line=start_line,
                            end_line=end_line,
                            content=content,
                            file_hash=file_hash,
                            segment_hash=segment_hash,
                            dep_infos=dep_infos,
                        )
                    )
                    # results[-1].to_file()

        return results

    @classmethod
    def chunk_leaf_node_by_lines(
        cls, node: Node, file_path: str, file_hash: str, seen_segment_hashes: set[str]
    ) -> List[CodeBlock]:
        lines = node.text.split(b"\n")
        base_start_line = node.start_point.row + 1
        return cls.chunk_text_by_lines(lines, file_path, file_hash, node.type, seen_segment_hashes, base_start_line)

    @classmethod
    def chunk_text_by_lines(
        cls,
        lines: list[bytes],
        file_path: str,
        file_hash: str,
        chunk_type: str,
        seen_segment_hashes: set[str],
        base_start_line: int = 1,
    ) -> List[CodeBlock]:
        chunks: List[CodeBlock] = []
        current_chunk_lines: List[str] = []
        current_chunk_length: int = 0
        chunk_start_line_index: int = 0
        effective_max_chars: int = MAX_BLOCK_CHARS * MAX_CHARS_TOLERANCE_FACTOR

        def finalize_chunk(end_line_index: int):
            nonlocal current_chunk_lines, current_chunk_length, chunk_start_line_index
            if current_chunk_length >= MIN_BLOCK_CHARS and current_chunk_length > 0:
                chunk_content = b"\n".join(current_chunk_lines)
                start_line = base_start_line + chunk_start_line_index
                end_line = base_start_line + end_line_index
                content_preview = chunk_content[:100]
                segment_hash = cls.create_hash(
                    f"{file_path}-{start_line}-{end_line}-{len(chunk_content)}-{content_preview}".encode("utf-8")
                )

                if segment_hash not in seen_segment_hashes:
                    seen_segment_hashes.add(segment_hash)
                    chunks.append(
                        CodeBlock(
                            identifier=None,
                            file_path=file_path,
                            content=chunk_content,
                            type=chunk_type,
                            start_line=start_line,
                            end_line=end_line,
                            file_hash=file_hash,
                            segment_hash=segment_hash,
                        )
                    )
                    # chunks[-1].to_file()
                current_chunk_lines = []
                current_chunk_length = 0
                chunk_start_line_index = end_line_index + 1

        def create_segment_block(segment: str, original_line_number: int, start_char_index: int):
            nonlocal current_chunk_lines, current_chunk_length, chunk_start_line_index
            segment_preview = segment[:100]
            segment_hash = f"{file_path}-{original_line_number}-{start_char_index}-{len(segment)}-{segment_preview}"

            if segment_hash not in seen_segment_hashes:
                seen_segment_hashes.add(segment_hash)
                chunks.append(
                    CodeBlock(
                        identifier=None,
                        file_path=file_path,
                        content=segment,
                        type=f"{chunk_type}_segment",
                        start_line=original_line_number,
                        end_line=original_line_number,
                        file_hash=file_hash,
                        segment_hash=segment_hash,
                    )
                )
                # chunks[-1].to_file()

        for i in range(len(lines)):
            line = lines[i]
            line_len = len(line) + (1 if i < len(lines) - 1 else 0)
            original_line_number = base_start_line + i
            if line_len > effective_max_chars:
                if len(current_chunk_lines) > 0:
                    finalize_chunk(i - 1)

                remaining_line_content = line
                current_segment_start_char = 0

                while len(remaining_line_content) > 0:
                    segment = remaining_line_content[:MAX_BLOCK_CHARS]
                    remaining_line_content = remaining_line_content[MAX_BLOCK_CHARS:]
                    create_segment_block(segment, original_line_number, current_segment_start_char)
                    current_segment_start_char += MAX_BLOCK_CHARS

                chunk_start_line_index = i + 1
                continue

            if current_chunk_length > 0 and current_chunk_length + line_len > effective_max_chars:
                split_index = i - 1
                remainder_length = 0
                for j in range(i, len(lines)):
                    remainder_length += len(lines[j]) + (1 if len(lines[j]) - 1 > j else 0)

                if (
                    (current_chunk_length >= MIN_BLOCK_CHARS)
                    and (remainder_length < MIN_CHUNK_REMAINDER_CHARS)
                    and (len(current_chunk_lines) > 1)
                ):
                    for k in range(i - 2, chunk_start_line_index + 1, -1):
                        potential_chink_lines = lines[chunk_start_line_index : k + 1]
                        potential_chunk_length = len("\n".join(potential_chink_lines)) + 1
                        potential_next_chunk_lines = lines[k + 1 :]
                        potential_next_chunk_length = len("\n".join(potential_next_chunk_lines)) + 1
                        if (
                            potential_chunk_length >= MIN_BLOCK_CHARS
                            and potential_next_chunk_length >= MIN_CHUNK_REMAINDER_CHARS
                        ):
                            split_index = k
                            break

                finalize_chunk(split_index)

                if i >= chunk_start_line_index:
                    current_chunk_lines.append(line)
                    current_chunk_length += line_len
                else:
                    i = chunk_start_line_index - 1
                    continue
            else:
                current_chunk_lines.append(line)
                current_chunk_length += line_len

        if len(current_chunk_lines) > 0:
            finalize_chunk(len(lines) - 1)

        return chunks

    @classmethod
    def parse_markdown(
        cls, file_path: str, content: str, file_hash: str, seen_segment_hashes: set[str]
    ) -> Coroutine[Any, Any, List[CodeBlock]]:
        lines = content.split(b"\n")
        markdown_captures = parse_markdown(content) or []

        if len(markdown_captures) == 0:
            return cls.process_markdown_section(lines, file_path, file_hash, "markdown_content", seen_segment_hashes, 1)

        results: List[CodeBlock] = []
        last_processed_line = 0

        if len(markdown_captures) > 0:
            first_header_line = markdown_captures[0].node.start_position.row
            if first_header_line > 0:
                pre_header_lines = lines[:first_header_line]
                pre_header_blocks = cls.process_markdown_section(
                    pre_header_lines, file_path, file_hash, "markdown_content", seen_segment_hashes, 1
                )
                results.extend(pre_header_blocks)

        for i in range(len(markdown_captures), 2):
            name_capture = markdown_captures[i]
            if i + 1 >= len(markdown_captures):
                break
            definition_capture = markdown_captures[i + 1]

            if not definition_capture:
                continue

            start_line = name_capture.node.start_position.row + 1
            end_line = definition_capture.node.end_position.row + 1
            section_lines = lines[start_line - 1 : end_line]
            header_match = name_capture.name.match(r"definition\.header\.h(\d)")
            header_level = int(header_match[1]) if header_match else 1
            header_text = name_capture.node.text

            section_blocks = cls.process_markdown_section(
                section_lines,
                file_path,
                file_hash,
                f"markdown_header_h{header_level}",
                seen_segment_hashes,
                start_line,
                header_text,
            )
            results.extend(section_blocks)
            last_processed_line = end_line

        if last_processed_line < len(lines):
            remaining_lines = lines[last_processed_line:]
            remaining_blocks = cls.process_markdown_section(
                remaining_lines, file_path, file_hash, "markdown_content", seen_segment_hashes, last_processed_line + 1
            )
            results.extend(remaining_blocks)

        return results

    @classmethod
    def process_markdown_section(
        cls,
        lines: list[bytes],
        file_path: str,
        file_hash: str,
        _type: str,
        seen_segment_hashes: set[str],
        start_line: int,
        identifier: str | None = None,
    ) -> Coroutine[Any, Any, List[CodeBlock]]:
        content = b"\n".join(lines)
        if len(content.strip()) < MIN_BLOCK_CHARS:
            return []

        needs_chunking = len(content) > MAX_BLOCK_CHARS * MAX_CHARS_TOLERANCE_FACTOR or any(
            map(lambda line: len(line) > MAX_BLOCK_CHARS * MAX_CHARS_TOLERANCE_FACTOR, lines)
        )
        if needs_chunking:
            chunks = cls.chunk_text_by_lines(
                lines, file_path, file_hash, "markdown_content", seen_segment_hashes, start_line
            )
            if identifier:
                for chunk in chunks:
                    chunk.identifier = identifier
            return chunks
        end_line = start_line + len(lines) - 1
        content_preview = content[:100]
        segment_hash = cls.create_hash(
            f"{file_path}-{start_line}-{end_line}-{len(content)}-{content_preview}".encode("utf-8")
        )
        if segment_hash not in seen_segment_hashes:
            seen_segment_hashes.add(segment_hash)
            res = [
                CodeBlock(
                    file_path=file_path,
                    content=content,
                    type="markdown_content",
                    start_line=start_line,
                    end_line=end_line,
                    file_hash=file_hash,
                    segment_hash=segment_hash,
                    identifier=identifier,
                )
            ]
            # res[-1].to_file()
            return res

    def perform_fallback_chunking(
        self, content: bytes, file_path: str, file_hash: str, seen_segment_hashes: set[str]
    ) -> List[CodeBlock]:
        lines = content.split(b"\n")
        return self.chunk_text_by_lines(lines, file_path, file_hash, "fallback_chunking", seen_segment_hashes)


class IDirectoryScanner:
    def scan_directory(
        self,
        directory_path: str,
        on_error: Callable[[Exception], None],
        on_blocks_indexed: Callable[[int], None],
        on_files_parsed: Callable[[int], None],
    ) -> list[CodeBlock]:
        raise NotImplementedError


async def main():
    code_parser = CodeParser()
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(BASE_DIR, "example.py")
    # file_path = os.path.join(BASE_DIR, "README.md")
    code_blocks = await code_parser.parse_file(file_path)
    for code_block in sorted(code_blocks, key=lambda x: x.start_line):
        print(
            "TYPE:",
            code_block.type,
            "IDENTIFIER:",
            code_block.identifier,
            code_block.start_line,
            code_block.segment_hash,
        )
        print()
        print(code_block.content.decode("utf-8"))
        # print("\n".join(read_lines(code_block.file_path,
        #      code_block.start_line, code_block.end_line)))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
