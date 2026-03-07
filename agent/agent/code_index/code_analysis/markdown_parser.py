"""
Markdown parser that returns headers and section line ranges
This is a special case implementation that doesn't use tree-sitter
but is compatible with the parseFile function's capture processing
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Point:
    """Point information for a node"""

    row: int


@dataclass
class MockNode:
    """Interface to mimic tree-sitter node structure"""

    start_point: Point
    end_point: Point
    text: str
    parent: Optional["MockNode"] = None


@dataclass
class MockCapture:
    """Interface to mimic tree-sitter capture structure"""

    node: MockNode
    name: str
    pattern_index: int


def parse_markdown(content: bytes) -> dict[str, list[MockNode]]:
    """
    Parse a markdown file and extract headers and section line ranges

    Args:
        content: The content of the markdown file

    Returns:
        A list of mock captures compatible with tree-sitter captures
    """
    if not content or content.strip() == "":
        return {}

    lines = content.decode("utf-8").split("\n")
    captures: dict[str, list[MockNode]] = {}

    # Regular expressions for different header types
    atx_header_regex = re.compile(r"^(#{1,6})\s+(.+)$")
    # Setext headers must have at least 3 = or - characters
    setext_h1_regex = re.compile(r"^={3,}\s*$")
    setext_h2_regex = re.compile(r"^-{3,}\s*$")
    # Valid setext header text line should be plain text (not empty, not indented, not a special element)
    valid_setext_text_regex = re.compile(r"^\s*[^#<>!\[\]`\t]+[^\n]$")

    # Find all headers in the document
    for i, line in enumerate(lines):
        # Check for ATX headers (# Header)
        atx_match = atx_header_regex.match(line)
        if atx_match:
            level = len(atx_match.group(1))
            text = atx_match.group(2).strip()

            # Create a mock node for this header
            node = MockNode(start_point=Point(row=i), end_point=Point(row=i), text=text)

            # Append to list so multiple headers of same level are all kept
            captures.setdefault(f"name.definition.header.h{level}", []).append(node)
            captures.setdefault(f"definition.header.h{level}", []).append(node)

            continue

        # Check for setext headers (underlined headers)
        if i > 0:
            # Check for H1 (======)
            if setext_h1_regex.match(line) and valid_setext_text_regex.match(lines[i - 1]):
                text = lines[i - 1].strip()

                # Create a mock node for this header
                node = MockNode(start_point=Point(row=i - 1), end_point=Point(row=i), text=text)

                captures.setdefault("name.definition.header.h1", []).append(node)
                captures.setdefault("definition.header.h1", []).append(node)

                continue

            # Check for H2 (------)
            if setext_h2_regex.match(line) and valid_setext_text_regex.match(lines[i - 1]):
                text = lines[i - 1].strip()

                # Create a mock node for this header
                node = MockNode(start_point=Point(row=i - 1), end_point=Point(row=i), text=text)

                captures.setdefault("name.definition.header.h2", []).append(node)
                captures.setdefault("definition.header.h2", []).append(node)

                continue

    # Flatten to (name, node) and sort by node position so we can set section end = next header start - 1
    flat: list[tuple[str, MockNode]] = []
    for name, nodes in captures.items():
        for node in nodes:
            flat.append((name, node))
    flat.sort(key=lambda x: x[1].start_point.row)

    # Set each node's end_point to the line before the next header (or end of file)
    for idx, (_, node) in enumerate(flat):
        if idx + 1 < len(flat):
            node.end_point.row = flat[idx + 1][1].start_point.row - 1
        else:
            node.end_point.row = len(lines) - 1

    # Build dict expected by process_captures: name -> list of nodes
    header_captures: dict[str, list[MockNode]] = {}
    for name, node in flat:
        header_captures.setdefault(name, []).append(node)
    return header_captures


def format_markdown_captures(captures: List[MockCapture], min_section_lines: int = 4) -> Optional[str]:
    """
    Format markdown captures into the same string format as parseFile
    This is used for backward compatibility

    Args:
        captures: The list of query captures
        min_section_lines: Minimum number of lines for a section to be included

    Returns:
        A formatted string with headers and section line ranges
    """
    if len(captures) == 0:
        return None

    formatted_output = ""

    # Process only the definition captures (every other capture)
    for i in range(1, len(captures), 2):
        capture = captures[i]
        start_line = capture.node.start_point.row
        end_line = capture.node.end_point.row

        # Only include sections that span at least min_section_lines lines
        section_length = end_line - start_line + 1
        if section_length >= min_section_lines:
            # Extract header level from the name
            header_level = 1

            # Check if the name contains a header level (e.g., 'definition.header.h2')
            header_match = re.search(r"\.h(\d)$", capture.name)
            if header_match and header_match.group(1):
                header_level = int(header_match.group(1))

            header_prefix = "#" * header_level

            # Format: startLine--endLine | # Header Text
            formatted_output += f"{start_line}--{end_line} | {header_prefix} {capture.node.text}\n"

    return formatted_output if len(formatted_output) > 0 else None


# Example usage
if __name__ == "__main__":
    # Test markdown content
    test_content = """# Introduction

This is the introduction section with some content.

## Getting Started

Here's how to get started with this project.

### Prerequisites

You need the following tools installed.

## Installation

Follow these steps to install the software.

Alternative Header Style
========================

This is a setext-style H1 header.

Another Section
---------------

This is a setext-style H2 header.
"""

    # Parse the markdown
    captures = parse_markdown(test_content)

    # Format the output
    formatted = format_markdown_captures(captures)

    if formatted:
        print("Parsed markdown headers:")
        print(formatted)
    else:
        print("No headers found or sections too short.")
