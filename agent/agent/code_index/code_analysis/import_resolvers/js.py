import json
import os
import re
from typing import Dict, Optional


class JavaScriptImportResolver:
    def __init__(self):
        self.module_cache: Dict[str, Optional[str]] = {}
        self.package_json_cache: Dict[str, Dict] = {}

    def clean_import_statement(self, import_statement: str) -> str:
        """Clean JavaScript import statement"""
        import_path = import_statement.strip()
        # Remove quotes
        if import_path.startswith('"') and import_path.endswith('"'):
            import_path = import_path[1:-1]
        if import_path.startswith("'") and import_path.endswith("'"):
            import_path = import_path[1:-1]
        if import_path.startswith("`") and import_path.endswith("`"):
            import_path = import_path[1:-1]
        return import_path

    def find_package_json(self, start_dir: str) -> Optional[str]:
        """Find package.json by walking up the directory tree"""
        current_dir = os.path.abspath(start_dir)
        while current_dir != os.path.dirname(current_dir):
            package_json_path = os.path.join(current_dir, "package.json")
            if os.path.exists(package_json_path):
                return package_json_path
            current_dir = os.path.dirname(current_dir)
        return None

    def parse_package_json(self, package_json_path: str) -> Dict:
        """Parse package.json file"""
        if package_json_path in self.package_json_cache:
            return self.package_json_cache[package_json_path]

        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.package_json_cache[package_json_path] = data
                return data
        except Exception:
            return {}

    def resolve_node_modules(self, import_path: str, start_dir: str) -> Optional[str]:
        """Resolve import from node_modules"""
        current_dir = os.path.abspath(start_dir)

        while current_dir != os.path.dirname(current_dir):
            node_modules_path = os.path.join(current_dir, "node_modules", import_path)

            # Check if it's a directory with package.json
            if os.path.isdir(node_modules_path):
                package_json_path = os.path.join(node_modules_path, "package.json")
                if os.path.exists(package_json_path):
                    package_data = self.parse_package_json(package_json_path)
                    main_file = package_data.get("main", "index.js")
                    main_path = os.path.join(node_modules_path, main_file)

                    if os.path.exists(main_path):
                        return main_path

                    # Try index.js as fallback
                    index_path = os.path.join(node_modules_path, "index.js")
                    if os.path.exists(index_path):
                        return index_path

            # Check if it's a direct file
            for ext in [".js", ".mjs", ".cjs"]:
                file_path = node_modules_path + ext
                if os.path.exists(file_path):
                    return file_path

            current_dir = os.path.dirname(current_dir)

        return None

    def resolve_relative_import(self, import_path: str, current_file_dir: str) -> Optional[str]:
        """Resolve relative imports (./, ../)"""
        if not (import_path.startswith("./") or import_path.startswith("../")):
            return None

        resolved_path = os.path.normpath(os.path.join(current_file_dir, import_path))

        # Try different extensions
        extensions = [".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"]

        # Check if it's a direct file
        if os.path.exists(resolved_path):
            return resolved_path

        # Try with extensions
        for ext in extensions:
            file_path = resolved_path + ext
            if os.path.exists(file_path):
                return file_path

        # Try index files in directory
        if os.path.isdir(resolved_path):
            for ext in extensions:
                index_path = os.path.join(resolved_path, f"index{ext}")
                if os.path.exists(index_path):
                    return index_path

        return None

    def resolve_import(
        self, import_statement: str, project_root: Optional[str] = None, current_file: Optional[str] = None
    ) -> Optional[str]:
        """Resolve JavaScript import to file path"""
        import_path = self.clean_import_statement(import_statement)

        cache_key = f"{import_path}:{project_root}:{current_file}"
        if cache_key in self.module_cache:
            return self.module_cache[cache_key]

        result = self._resolve_import_internal(import_path, project_root, current_file)
        self.module_cache[cache_key] = result
        return result

    def _resolve_import_internal(
        self, import_path: str, project_root: Optional[str] = None, current_file: Optional[str] = None
    ) -> Optional[str]:
        """Internal import resolution logic"""
        # Determine starting directory
        if current_file and os.path.exists(current_file):
            start_dir = os.path.dirname(current_file)
        elif project_root and os.path.exists(project_root):
            start_dir = project_root
        else:
            start_dir = os.getcwd()

        # Try relative imports first
        if import_path.startswith("./") or import_path.startswith("../"):
            return self.resolve_relative_import(import_path, start_dir)

        # Try absolute imports from project root
        if project_root:
            abs_path = os.path.join(project_root, import_path)
            extensions = [".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"]

            for ext in extensions:
                file_path = abs_path + ext
                if os.path.exists(file_path):
                    return file_path

            if os.path.isdir(abs_path):
                for ext in extensions:
                    index_path = os.path.join(abs_path, f"index{ext}")
                    if os.path.exists(index_path):
                        return index_path

        # Try node_modules resolution
        return self.resolve_node_modules(import_path, start_dir)


class TypeScriptImportResolver(JavaScriptImportResolver):
    def __init__(self):
        super().__init__()
        self.tsconfig_cache: Dict[str, Dict] = {}

    def find_tsconfig(self, start_dir: str) -> Optional[str]:
        """Find tsconfig.json by walking up the directory tree"""
        current_dir = os.path.abspath(start_dir)
        while current_dir != os.path.dirname(current_dir):
            for filename in ["tsconfig.json", "jsconfig.json"]:
                config_path = os.path.join(current_dir, filename)
                if os.path.exists(config_path):
                    return config_path
            current_dir = os.path.dirname(current_dir)
        return None

    def parse_tsconfig(self, tsconfig_path: str) -> Dict:
        """Parse tsconfig.json file"""
        if tsconfig_path in self.tsconfig_cache:
            return self.tsconfig_cache[tsconfig_path]

        try:
            with open(tsconfig_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Remove comments (basic implementation)
                content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
                content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
                data = json.loads(content)
                self.tsconfig_cache[tsconfig_path] = data
                return data
        except Exception:
            return {}

    def resolve_path_mapping(self, import_path: str, tsconfig_data: Dict, tsconfig_dir: str) -> Optional[str]:
        """Resolve TypeScript path mappings"""
        compiler_options = tsconfig_data.get("compilerOptions", {})
        paths = compiler_options.get("paths", {})
        base_url = compiler_options.get("baseUrl", ".")

        for pattern, mappings in paths.items():
            # Simple pattern matching (supports * wildcard)
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                if import_path.startswith(prefix):
                    suffix = import_path[len(prefix) :]
                    for mapping in mappings:
                        if mapping.endswith("*"):
                            mapped_path = mapping[:-1] + suffix
                        else:
                            mapped_path = mapping

                        full_path = os.path.normpath(os.path.join(tsconfig_dir, base_url, mapped_path))

                        # Try different extensions
                        extensions = [".ts", ".tsx", ".js", ".jsx", ".d.ts"]

                        if os.path.exists(full_path):
                            return full_path

                        for ext in extensions:
                            file_path = full_path + ext
                            if os.path.exists(file_path):
                                return file_path

                        # Try index files
                        if os.path.isdir(full_path):
                            for ext in extensions:
                                index_path = os.path.join(full_path, f"index{ext}")
                                if os.path.exists(index_path):
                                    return index_path
            else:
                # Exact match
                if import_path == pattern:
                    for mapping in mappings:
                        full_path = os.path.normpath(os.path.join(tsconfig_dir, base_url, mapping))
                        if os.path.exists(full_path):
                            return full_path

        return None

    def _resolve_import_internal(
        self, import_path: str, project_root: Optional[str] = None, current_file: Optional[str] = None
    ) -> Optional[str]:
        """Internal TypeScript import resolution logic"""
        # Determine starting directory
        if current_file and os.path.exists(current_file):
            start_dir = os.path.dirname(current_file)
        elif project_root and os.path.exists(project_root):
            start_dir = project_root
        else:
            start_dir = os.getcwd()

        # Find and parse tsconfig.json
        tsconfig_path = self.find_tsconfig(start_dir)
        if tsconfig_path:
            tsconfig_data = self.parse_tsconfig(tsconfig_path)
            tsconfig_dir = os.path.dirname(tsconfig_path)

            # Try path mappings first
            mapped_path = self.resolve_path_mapping(import_path, tsconfig_data, tsconfig_dir)
            if mapped_path:
                return mapped_path

        # Try relative imports with TypeScript extensions
        if import_path.startswith("./") or import_path.startswith("../"):
            resolved_path = os.path.normpath(os.path.join(start_dir, import_path))
            extensions = [".ts", ".tsx", ".d.ts", ".js", ".jsx"]

            if os.path.exists(resolved_path):
                return resolved_path

            for ext in extensions:
                file_path = resolved_path + ext
                if os.path.exists(file_path):
                    return file_path

            if os.path.isdir(resolved_path):
                for ext in extensions:
                    index_path = os.path.join(resolved_path, f"index{ext}")
                    if os.path.exists(index_path):
                        return index_path

        # Fall back to JavaScript resolution
        return super()._resolve_import_internal(import_path, project_root, current_file)


# Convenience functions


def resolve_javascript_import(
    import_statement: str, project_root: Optional[str] = None, current_file: Optional[str] = None
) -> Optional[str]:
    resolver = JavaScriptImportResolver()
    return resolver.resolve_import(import_statement, project_root, current_file)


def resolve_typescript_import(
    import_statement: str, project_root: Optional[str] = None, current_file: Optional[str] = None
) -> Optional[str]:
    resolver = TypeScriptImportResolver()
    return resolver.resolve_import(import_statement, project_root, current_file)


# Example usage and testing
if __name__ == "__main__":
    print("\n=== JavaScript Import Resolver ===")
    js_resolver = JavaScriptImportResolver()
    js_imports = ["react", "./components/Header", "../utils/helpers", "lodash", "@types/node"]

    for imp in js_imports:
        result = js_resolver.resolve_import(imp, "./js-project", "./js-project/src/index.js")
        print(f"{imp} -> {result}")

    print("\n=== TypeScript Import Resolver ===")
    ts_resolver = TypeScriptImportResolver()
    ts_imports = ["react", "./types/User", "@/components/Button", "../services/api", "typescript"]

    for imp in ts_imports:
        result = ts_resolver.resolve_import(imp, "./ts-project", "./ts-project/src/main.ts")
        print(f"{imp} -> {result}")
