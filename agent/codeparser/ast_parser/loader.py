import os
from tree_sitter import Language, Parser, QueryCursor, Query


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class TreeSitterLoader:
    @staticmethod
    def load_parser(ext: str):

        match ext:
            case "py":
                from .queries.python import QUERY
                from tree_sitter_python import language
            case "java":
                from .queries.java import QUERY
                from tree_sitter_java import language
            case "js":
                from .queries.javascript import QUERY
                from tree_sitter_javascript import language
            case "ts":
                from .queries.typescript import QUERY
                from tree_sitter_typescript import language_typescript as language
            case "php":
                from .queries.php import QUERY
                from tree_sitter_php import language_php as language
            case _:
                raise ValueError(f"Unsupported language: {ext}")
        lang_ptr = Language(language())
        parser = Parser(lang_ptr)
        query = Query(lang_ptr, QUERY)
        cursor = QueryCursor(query)
        return dict(parser=parser, cursor=cursor)


if __name__ == "__main__":
    loader = TreeSitterLoader()
    print(loader.load_parser('py'))
    print(loader.load_parser('java'))
    print(loader.load_parser('js'))
    print(loader.load_parser('ts'))
    print(loader.load_parser('php'))
    print(loader.load_parser('html'))
    print(loader.load_parser('css'))
    print(loader.load_parser('go'))
