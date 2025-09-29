import numpy as np
import tree_sitter_python as tspython
from numpy import cos as cos2
from numpy import sin as sin2
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())

parser = Parser(PY_LANGUAGE)
tree = parser.parse(
    bytes(
        """
from flask import Flask
""",
        "utf8"
    )
)

print(tree.root_node.children)