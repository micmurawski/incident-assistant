import ast
import importlib
import importlib.util
import os
import re
import site
from typing import Dict, List, Optional, Set

from .base import DepInfo


class PythonImportResolver:
    def __init__(self):
        # self._visited_modules: Set[str] = set()
        self._module_cache: Dict[str, dict[str, str]] = {}

    def resolve_import(
        self,
        work_dir: str,
        file_path: str,
        import_statement: str,
    ) -> list[DepInfo]:
        """
        Resolve a Python import statement to its actual file path and alias/ref.

        Args:
            work_dir: The working directory to resolve relative imports.
            import_statement: The import statement to resolve (e.g., 'numpy' or 'package.module')

        Returns:
            A list of dicts with keys: module_path, ref (alias or imported name), and resolved_path.
        """
        stmt = import_statement.strip()
        source_root = site.getsitepackages()[0]
        results = []
        # Patterns for different import forms
        # 1. import numpy as np
        m = re.match(r"^import\s+([a-zA-Z0-9_.]+)\s+as\s+([a-zA-Z0-9_]+)$", stmt)
        if m:
            module_path = m.group(1)
            ref = m.group(2)
            key = f"{work_dir}:{file_path}:{module_path}:{source_root}"
            if key in self._module_cache:
                dep_info = self._module_cache[key]
            else:
                dep_info = self._resolve_import_internal(work_dir, file_path, module_path, source_root)
                self._module_cache[key] = dep_info
                dep_info["ref"] = ref
            results.append(DepInfo.from_dict(dep_info))
            return results

        # 2. import numpy
        m = re.match(r"^import\s+([a-zA-Z0-9_.]+)$", stmt)
        if m:
            module_path = m.group(1)
            ref = module_path.split(".")[0]
            key = f"{work_dir}:{file_path}:{module_path}:{source_root}"
            if key in self._module_cache:
                dep_info = self._module_cache[key]
            else:
                dep_info = self._resolve_import_internal(work_dir, file_path, module_path, source_root)
                self._module_cache[key] = dep_info
                dep_info["ref"] = ref
            results.append(DepInfo.from_dict(dep_info))
            return results

        # 3. from numpy import sin as sin2, cos as cos2
        m = re.match(r"^from\s+([a-zA-Z0-9_.]+)\s+import\s+(.+)$", stmt)
        if m:
            base_module = m.group(1)
            import_section = m.group(2).strip()
            # Handle parenthesized multi-import: from numpy import (sin as sin2, cos as cos2)
            if import_section.startswith("(") and import_section.endswith(")"):
                import_section = import_section[1:-1].strip()
            # Split by comma, handle as/as2
            for part in [p.strip() for p in import_section.split(",") if p.strip()]:
                as_match = re.match(r"^([a-zA-Z0-9_]+)\s+as\s+([a-zA-Z0-9_]+)$", part)
                if as_match:
                    imported = as_match.group(1)
                    ref = as_match.group(2)
                else:
                    imported = part
                    ref = imported
                module_path = f"{base_module}.{imported}"
                key = f"{work_dir}:{file_path}:{module_path}:{source_root}"
                if key in self._module_cache:
                    dep_info = self._module_cache[key]
                else:
                    dep_info = self._resolve_import_internal(work_dir, file_path, module_path, source_root)
                    self._module_cache[key] = dep_info
                    dep_info["ref"] = ref
                results.append(DepInfo.from_dict(dep_info))
            return results

        # 4. fallback: bare module path (e.g., just "flask" or "flask.app")
        bare = stmt.split()[0]
        if bare:
            module_path = bare
            ref = bare.split(".")[0]
            key = f"{work_dir}:{file_path}:{module_path}:{source_root}"
            if key in self._module_cache:
                dep_info = self._module_cache[key]
            else:
                dep_info = self._resolve_import_internal(work_dir, file_path, module_path, source_root)
                self._module_cache[key] = dep_info
                dep_info["ref"] = ref
            results.append(DepInfo.from_dict(dep_info))
            return results

        return []

    def _resolve_import_internal(
        self, work_dir: str, file_path: str, module_path: str, source_root: Optional[str] = None
    ) -> dict[str, str]:
        """
        Internal method to resolve imports recursively.
        """

        result = {"import_path": module_path, "is_builtin": False, "resolved_path": None, "file_path": file_path}

        try:
            spec = importlib.util.find_spec(module_path)
            if spec is not None and spec.origin is not None:
                if spec.origin == "built-in":
                    result["is_builtin"] = True
                    return result
                result["resolved_path"] = spec.origin
                return result
        except (ImportError, ModuleNotFoundError):
            pass
        # If not found in standard paths, try source_root
        if source_root:
            # Convert import statement to potential file path

            file_path_parts = list(os.path.split(file_path))
            file_path_parts[-1] = file_path_parts[-1].replace(".py", "")

            if module_path.startswith("."):
                parts = module_path[1:].split(".")
                potential_paths = [
                    os.path.join(work_dir, *parts[:-1]) + ".py",
                    os.path.join(work_dir, *parts[:-1], "__init__.py"),
                    os.path.join(source_root, *parts) + ".py",
                    os.path.join(source_root, *parts[:-1], "__init__.py"),
                ]
                if file_path_parts:
                    # print(work_dir, file_path_parts, parts)
                    potential_paths.append(os.path.join(work_dir, *file_path_parts[:-1], *parts[:-1]) + ".py")
                    potential_paths.append(os.path.join(work_dir, *file_path_parts[:-1], *parts[:-1], "__init__.py"))
                    # for path in potential_paths:
                    #    print(f"path: {path}")
            else:
                parts = module_path.split(".")
                potential_paths = [
                    os.path.join(work_dir, *parts) + ".py",
                    os.path.join(work_dir, *parts[:-1], "__init__.py"),
                    os.path.join(work_dir, *parts) + ".py",
                    os.path.join(source_root, *parts) + ".py",
                    os.path.join(source_root, *parts[:-1], "__init__.py"),
                ]

            for path in potential_paths:
                if os.path.exists(path):
                    result["resolved_path"] = os.path.abspath(path)
                    return result

        return result

    def resolve_import_chain(self, import_statement: str, source_root: Optional[str] = None) -> List[str]:
        """
        Resolve an import statement and all its dependencies recursively.

        Args:
            import_statement: The import statement to resolve
            source_root: Optional root directory to search for local modules

        Returns:
            List of file paths for the module and all its dependencies
        """
        result = set()
        self._resolve_import_chain_internal(import_statement, source_root, result)
        return list(result)

    def _resolve_import_chain_internal(
        self, import_statement: str, source_root: Optional[str], resolved_paths: Set[str]
    ) -> None:
        """
        Internal method to recursively resolve import chains.
        """
        if import_statement in self._visited_modules:
            return

        self._visited_modules.add(import_statement)

        # Resolve the current import
        file_path = self._resolve_import_internal(import_statement, source_root)
        if file_path:
            resolved_paths.add(file_path)

            # Parse the file to find its imports
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Parse the AST to find imports
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        if isinstance(node, ast.Import):
                            for name in node.names:
                                self._resolve_import_chain_internal(name.name, source_root, resolved_paths)
                        else:  # ImportFrom
                            if node.module:
                                self._resolve_import_chain_internal(node.module, source_root, resolved_paths)
            except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
                pass


def resolve_python_import(import_statement: str, source_root: Optional[str] = None) -> Optional[str]:
    resolver = PythonImportResolver()
    return resolver.resolve_import(import_statement, source_root)


# Example usage
if __name__ == "__main__":
    from sme_agent.dependencies_analyzer.import_parser import ImportParser

    import_parser = ImportParser()
    file_path = "./services/robot-shop/payment/payment.py"
    content = open(file_path, "r").read()
    imports = import_parser.parse_imports(content, "python")

    resolver = PythonImportResolver()

    for imp in imports:
        is_from = imp.get("from", False)
        if is_from:
            module = f"{imp['name']}.{imp['ref']}"
        else:
            module = imp["ref"]

        # Get the direct import resolution
        res = resolver.resolve_import(module, ".venv/lib/python3.12/site-packages")
        print(f"{module} -> {res}")
        import inspect

        from flask import Flask

        print(inspect.getfile(Flask))
        # Get the full import chain
        # chain = resolver.resolve_import_chain(module, "./venv")
        # print(f"Import chain for {module}:")
        # for path in chain:
        #    print(f"  - {path}")
