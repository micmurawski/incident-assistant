import glob
import os
import re
import subprocess
from typing import Dict, Optional


class GoImportResolver:
    def __init__(self):
        self.module_cache: Dict[str, Optional[str]] = {}
        self.go_path = self._find_go_path()
        self.go_mod_cache = self._find_go_mod_cache()

    def _find_go_path(self) -> Optional[str]:
        """Find GOPATH from environment or default location"""
        gopath = os.environ.get('GOPATH')
        if gopath and os.path.exists(gopath):
            return gopath

        # Default GOPATH
        default_gopath = os.path.expanduser('~/go')
        if os.path.exists(default_gopath):
            return default_gopath
        return None

    def _find_go_mod_cache(self) -> Optional[str]:
        """Find Go module cache directory"""
        try:
            result = subprocess.run(['go', 'env', 'GOMODCACHE'],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                cache_path = result.stdout.strip()
                if os.path.exists(cache_path):
                    return cache_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback to default location
        default_cache = os.path.expanduser('~/go/pkg/mod')
        if os.path.exists(default_cache):
            return default_cache
        return None

    def clean_import_statement(self, import_statement: str) -> str:
        """Clean Go import statement"""
        import_path = import_statement.strip()
        # Remove quotes
        if import_path.startswith('"') and import_path.endswith('"'):
            import_path = import_path[1:-1]
        if import_path.startswith("'") and import_path.endswith("'"):
            import_path = import_path[1:-1]
        return import_path

    def find_go_mod_file(self, start_dir: str) -> Optional[str]:
        """Find go.mod file by walking up the directory tree"""
        current_dir = os.path.abspath(start_dir)
        while current_dir != os.path.dirname(current_dir):
            go_mod_path = os.path.join(current_dir, 'go.mod')
            if os.path.exists(go_mod_path):
                return go_mod_path
            current_dir = os.path.dirname(current_dir)
        return None

    def parse_go_mod(self, go_mod_path: str) -> Dict[str, str]:
        """Parse go.mod file to get module name and dependencies"""
        module_info = {}
        try:
            with open(go_mod_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract module name
            module_match = re.search(r'^module\s+(.+)$', content, re.MULTILINE)
            if module_match:
                module_info['module'] = module_match.group(1).strip()

            # Extract dependencies
            require_block = re.search(
                r'require\s*\((.*?)\)', content, re.DOTALL)
            if require_block:
                for line in require_block.group(1).split('\n'):
                    line = line.strip()
                    if line and not line.startswith('//'):
                        parts = line.split()
                        if len(parts) >= 2:
                            module_info[parts[0]] = parts[1]
        except Exception:
            pass
        return module_info

    def resolve_import(self, import_statement: str, project_root: Optional[str] = None) -> Optional[str]:
        """Resolve Go import to file path"""
        import_path = self.clean_import_statement(import_statement)

        if import_path in self.module_cache:
            return self.module_cache[import_path]

        result = self._resolve_import_internal(import_path, project_root)
        self.module_cache[import_path] = result
        return result

    def _resolve_import_internal(self, import_path: str, project_root: Optional[str] = None) -> Optional[str]:
        """Internal import resolution logic"""
        # Check if it's a standard library package
        if self._is_stdlib_package(import_path):
            return None  # Standard library, no source file needed

        # Try to resolve in project root first
        if project_root:
            go_mod_path = self.find_go_mod_file(project_root)
            if go_mod_path:
                module_info = self.parse_go_mod(go_mod_path)
                module_name = module_info.get('module', '')

                # Check if it's an internal import
                if import_path.startswith(module_name):
                    relative_path = import_path[len(module_name):].lstrip('/')
                    internal_path = os.path.join(
                        os.path.dirname(go_mod_path), relative_path)

                    # Look for Go files in the package directory
                    if os.path.isdir(internal_path):
                        for file in os.listdir(internal_path):
                            if file.endswith('.go') and not file.endswith('_test.go'):
                                return os.path.join(internal_path, file)

        # Try GOPATH/src
        if self.go_path:
            gopath_src = os.path.join(self.go_path, 'src', import_path)
            if os.path.isdir(gopath_src):
                for file in os.listdir(gopath_src):
                    if file.endswith('.go') and not file.endswith('_test.go'):
                        return os.path.join(gopath_src, file)

        # Try Go module cache
        if self.go_mod_cache:
            # Convert import path to module cache format
            cache_patterns = [
                os.path.join(self.go_mod_cache, import_path + '@*'),
                os.path.join(self.go_mod_cache,
                             import_path.replace('/', '!') + '@*')
            ]

            for pattern in cache_patterns:
                matches = glob.glob(pattern)
                if matches:
                    # Use the latest version
                    latest_match = max(matches)
                    if os.path.isdir(latest_match):
                        for file in os.listdir(latest_match):
                            if file.endswith('.go') and not file.endswith('_test.go'):
                                return os.path.join(latest_match, file)

        return None

    def _is_stdlib_package(self, import_path: str) -> bool:
        """Check if the import is a standard library package"""
        stdlib_packages = {
            'fmt', 'os', 'io', 'net', 'http', 'strings', 'strconv', 'time',
            'encoding/json', 'database/sql', 'context', 'sync', 'log',
            'errors', 'bufio', 'bytes', 'crypto', 'html', 'math', 'reflect',
            'regexp', 'sort', 'path', 'net/http', 'net/url', 'encoding/xml'
        }

        # Check if it's a known stdlib package or starts with a stdlib prefix
        if import_path in stdlib_packages:
            return True

        for stdlib_pkg in stdlib_packages:
            if import_path.startswith(stdlib_pkg + '/'):
                return True

        # Heuristic: if it doesn't contain a dot, it's likely stdlib
        return '.' not in import_path


def resolve_go_import(import_statement: str, project_root: Optional[str] = None) -> Optional[str]:
    resolver = GoImportResolver()
    return resolver.resolve_import(import_statement, project_root)


if __name__ == "__main__":
    # Test Go resolver
    print("=== Go Import Resolver ===")
    go_resolver = GoImportResolver()
    go_imports = [
        "fmt",
        "github.com/gin-gonic/gin",
        "encoding/json",
        "net/http"
    ]

    for imp in go_imports:
        result = go_resolver.resolve_import(imp, "./go-project")
        print(f"{imp} -> {result}")
