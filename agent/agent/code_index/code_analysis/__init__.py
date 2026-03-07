import logging
import os
import re
from typing import Any

from tree_sitter import Node, Parser, QueryCursor

from agent.code_index.code_analysis.loader import TreeSitterLoader
from agent.code_index.code_analysis.markdown_parser import (MockNode,
                                                            parse_markdown)
from agent.constants import DEFAULT_MIN_COMPONENT_LINES_VALUE, EXTENSIONS


def process_captures(captures: dict[str, list[Node | MockNode]], lines: list[str], language: str) -> str:
    needs_html_filtering = language in ["jsx", "tsx"]

    def is_not_html_element(line: str) -> bool:
        if not needs_html_filtering:
            return True
        # Common HTML elements pattern
        HTML_ELEMENTS = re.compile(r"^[^A-Z]*<\/?(?:div|span|button|input|h[1-6]|p|a|img|ul|li|form)\b")
        trimmed_line = line.strip()
        return not HTML_ELEMENTS.match(trimmed_line)

    if not captures:
        return None

    formatted_output = ""

    captures = sorted([(name, nodes) for name, nodes in captures.items()], key=lambda x: x[1][0].start_point.row)
    processed_lines: set[str] = set()
    nodes: list[Node | MockNode]
    name: str
    for name, nodes in captures:
        if "definition" not in name and "name" not in name:
            continue
        for node in nodes:
            definition_capture = node.parent if "name" in name else node

            if not definition_capture:
                continue

            start_line = definition_capture.start_point.row
            end_line = definition_capture.end_point.row
            line_count = end_line - start_line + 1

            min_lines = 1 if language == "markdown" else DEFAULT_MIN_COMPONENT_LINES_VALUE
            if line_count < min_lines:
                continue

            line_key = f"{start_line}--{end_line}"

            if line_key in processed_lines:
                continue

            start_line_content = lines[start_line].strip()
            if "name.definition" in name:
                component_name = node.text

                if line_key not in processed_lines and component_name:
                    formatted_output += f"{start_line + 1}--{end_line + 1} | {lines[start_line]}\n"
                    processed_lines.add(line_key)

            elif "name.definition" not in name and is_not_html_element(start_line_content):
                formatted_output += f"{start_line + 1}--{end_line + 1} | {lines[start_line]}\n"
                processed_lines.add(line_key)
                if node.parent and len(node.parent.children) > 0:
                    context_end = node.parent.children[-1].end_point.row

            elif is_not_html_element(start_line_content):
                formatted_output += f"{start_line + 1}--{end_line + 1} | {lines[start_line]}\n"
                processed_lines.add(line_key)
                if node.parent and node.parent.last_child:
                    context_end = node.parent.last_child.end_point.row
                    context_span = context_end - node.start_point.row + 1
                    if context_span >= DEFAULT_MIN_COMPONENT_LINES_VALUE:
                        range_key = f"{node.start_point.row}--{context_end}"
                        if range_key not in processed_lines:
                            formatted_output += f"{node.parent.start_point.row + 1}--{context_end + 1} | {lines[node.parent.start_point.row]}\n"
                            processed_lines.add(range_key)
    if formatted_output:
        return formatted_output
    return None


def parse_source_code_definitions(file_path: str) -> str:
    file_exists = os.path.exists(file_path)
    if not file_exists:
        raise FileNotFoundError(f"File not found: {file_path}")
    if os.path.isdir(file_path):
        content = ""
        for file in os.listdir(file_path):
            res = parse_source_code_definitions(os.path.join(file_path, file))
            if res:
                content += res + "\n"
        if content != "":
            content = "# Directory: " + file_path + "\n" + content
        return content
    ext = os.path.splitext(file_path)[1]

    if ext not in EXTENSIONS:
        return None

    if ext == ".md" or ext == ".markdown":
        content = open(file_path, "rb").read()
        markdown_captures = parse_markdown(content)
        lines = content.decode("utf-8").split("\n")
        markdown_definitions = process_captures(markdown_captures, lines, "markdown")
        if markdown_definitions:
            return f"# {os.path.basename(file_path)}\n{markdown_definitions}"
        return None

    lang = ext[1:]
    
    parsers = TreeSitterLoader.load_parser(lang)
    if parsers is None:
        return f"Unsupported file type: {file_path}"
    
    definitions = parse_file(file_path, parsers, lang)
    if definitions:
        return f"# {os.path.basename(file_path)}\n{definitions}"
    return None


def parse_file(file_path: str, parsers: dict[str, Any], lang: str) -> str:
    content = open(file_path, "rb").read()
    cursor: QueryCursor = parsers["cursor"]
    parser: Parser = parsers["parser"]
    try:
        tree = parser.parse(content)
        captures: dict[str, list[Node]] = cursor.captures(tree.root_node) if tree else {}
        lines = content.decode("utf-8").split("\n")
        return process_captures(captures, lines, lang)
    except Exception as e:
        logging.error(f"Error parsing file {file_path}: {str(e)}")
        return None
