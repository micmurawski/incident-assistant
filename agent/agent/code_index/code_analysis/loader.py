import logging
import os
from typing import Any

from tree_sitter import Language, Parser, Query, QueryCursor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class TreeSitterLoader:
    @staticmethod
    def load_parser(ext: str) -> dict[str, Any] | None:
        match ext:
            case "py":
                from tree_sitter_python import language

                from .import_resolvers.python import PythonImportResolver as import_resolver_class
                from .queries.python import QUERY
            case "java":
                from tree_sitter_java import language

                from .import_resolvers.java import JavaImportResolver as import_resolver_class
                from .queries.java import QUERY
            case "js":
                from tree_sitter_javascript import language

                from .import_resolvers.js import JavaScriptImportResolver as import_resolver_class
                from .queries.javascript import QUERY
            case "ts":
                from tree_sitter_typescript import language_typescript as language

                from .import_resolvers.js import TypeScriptImportResolver as import_resolver_class
                from .queries.typescript import QUERY
            case "php":
                from tree_sitter_php import language_php as language

                from .import_resolvers.php import PHPImportResolver as import_resolver_class
                from .queries.php import QUERY
            case "go":
                from tree_sitter_go import language

                from .import_resolvers.go import GoImportResolver as import_resolver_class
                from .queries.go import QUERY
            case "toml":
                from tree_sitter_toml import language

                import_resolver_class = None
                from .queries.toml import QUERY
            case _:
                logging.error(f"Unsupported language: {ext}")
                return None
        lang_ptr = Language(language())
        parser = Parser(lang_ptr)
        query = Query(lang_ptr, QUERY)
        cursor = QueryCursor(query)
        return dict(parser=parser, cursor=cursor, import_resolver=import_resolver_class())


if __name__ == "__main__":
    loader = TreeSitterLoader()
    print(loader.load_parser("py"))
    print(loader.load_parser("java"))
    print(loader.load_parser("js"))
    print(loader.load_parser("ts"))
    print(loader.load_parser("php"))
    print(loader.load_parser("html"))
    print(loader.load_parser("css"))
    print(loader.load_parser("go"))
