
import json
import os
import re
from typing import Dict, Optional


class PHPImportResolver:
    def __init__(self):
        self.module_cache: Dict[str, Optional[str]] = {}
        self.composer_cache: Dict[str, Dict] = {}

    def clean_import_statement(self, import_statement: str) -> str:
        """Clean PHP use/require statement"""
        import_path = import_statement.strip()

        # Handle use statements
        if import_path.startswith('use '):
            import_path = import_path[4:].strip()

        # Remove trailing semicolon
        if import_path.endswith(';'):
            import_path = import_path[:-1]

        # Remove quotes for require/include statements
        if import_path.startswith('"') and import_path.endswith('"'):
            import_path = import_path[1:-1]
        if import_path.startswith("'") and import_path.endswith("'"):
            import_path = import_path[1:-1]

        return import_path

    def find_composer_json(self, start_dir: str) -> Optional[str]:
        """Find composer.json by walking up the directory tree"""
        current_dir = os.path.abspath(start_dir)
        while current_dir != os.path.dirname(current_dir):
            composer_path = os.path.join(current_dir, 'composer.json')
            if os.path.exists(composer_path):
                return composer_path
            current_dir = os.path.dirname(current_dir)
        return None

    def parse_composer_json(self, composer_path: str) -> Dict:
        """Parse composer.json file"""
        if composer_path in self.composer_cache:
            return self.composer_cache[composer_path]

        try:
            with open(composer_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.composer_cache[composer_path] = data
                return data
        except Exception:
            return {}

    def resolve_psr4_autoload(self, class_name: str, composer_data: Dict, composer_dir: str) -> Optional[str]:
        """Resolve PSR-4 autoloading"""
        autoload = composer_data.get('autoload', {})
        psr4 = autoload.get('psr-4', {})

        for namespace_prefix, paths in psr4.items():
            namespace_prefix = namespace_prefix.rstrip('\\')
            class_namespace = class_name.rstrip('\\')

            if class_namespace.startswith(namespace_prefix):
                relative_path = class_namespace[len(
                    namespace_prefix):].lstrip('\\')
                file_path = relative_path.replace('\\', '/') + '.php'

                # paths can be a string or array
                if isinstance(paths, str):
                    paths = [paths]

                for path in paths:
                    full_path = os.path.join(composer_dir, path, file_path)
                    if os.path.exists(full_path):
                        return full_path

        return None

    def resolve_psr0_autoload(self, class_name: str, composer_data: Dict, composer_dir: str) -> Optional[str]:
        """Resolve PSR-0 autoloading"""
        autoload = composer_data.get('autoload', {})
        psr0 = autoload.get('psr-0', {})

        for namespace_prefix, paths in psr0.items():
            if class_name.startswith(namespace_prefix):
                file_path = class_name.replace(
                    '\\', '/').replace('_', '/') + '.php'

                if isinstance(paths, str):
                    paths = [paths]

                for path in paths:
                    full_path = os.path.join(composer_dir, path, file_path)
                    if os.path.exists(full_path):
                        return full_path

        return None

    def resolve_classmap(self, class_name: str, composer_data: Dict, composer_dir: str) -> Optional[str]:
        """Search in classmap directories"""
        autoload = composer_data.get('autoload', {})
        classmap = autoload.get('classmap', [])

        for path in classmap:
            search_dir = os.path.join(composer_dir, path)
            if os.path.isdir(search_dir):
                # Search for PHP files that might contain the class
                for root, _, files in os.walk(search_dir):
                    for file in files:
                        if file.endswith('.php'):
                            file_path = os.path.join(root, file)
                            if self.class_exists_in_file(file_path, class_name):
                                return file_path
            elif os.path.isfile(search_dir) and search_dir.endswith('.php'):
                if self.class_exists_in_file(search_dir, class_name):
                    return search_dir

        return None

    def class_exists_in_file(self, file_path: str, class_name: str) -> bool:
        """Check if a class exists in a PHP file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract just the class name without namespace
            simple_class_name = class_name.split('\\')[-1]

            # Look for class, interface, or trait declaration
            patterns = [
                r'class\s+' + re.escape(simple_class_name) + r'\b',
                r'interface\s+' + re.escape(simple_class_name) + r'\b',
                r'trait\s+' + re.escape(simple_class_name) + r'\b'
            ]

            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return True

            return False
        except Exception:
            return False

    def resolve_vendor_path(self, class_name: str, composer_dir: str) -> Optional[str]:
        """Try to resolve from vendor/composer/autoload_*.php files"""
        autoload_files = [
            'autoload_psr4.php',
            'autoload_classmap.php',
            'autoload_static.php'
        ]

        for autoload_file in autoload_files:
            autoload_path = os.path.join(
                composer_dir, 'vendor', 'composer', autoload_file)
            if os.path.exists(autoload_path):
                try:
                    # This is a simplified approach - in practice, you'd need to parse PHP arrays
                    with open(autoload_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Look for the class name in the file
                    if class_name in content:
                        # Extract file path (this is a simplified regex)
                        pattern = r"['\"]" + re.escape(class_name) + \
                            r"['\"].*?['\"]([^'\"]+\.php)['\"]"
                        match = re.search(pattern, content)
                        if match:
                            file_path = match.group(1)
                            full_path = os.path.join(
                                composer_dir, 'vendor', file_path)
                            if os.path.exists(full_path):
                                return full_path
                except Exception:
                    continue

        return None

    def resolve_relative_path(self, import_path: str, current_file_dir: str) -> Optional[str]:
        """Resolve relative require/include paths"""
        resolved_path = os.path.normpath(
            os.path.join(current_file_dir, import_path))

        if os.path.exists(resolved_path):
            return resolved_path

        # Try with .php extension if not present
        if not resolved_path.endswith('.php'):
            php_path = resolved_path + '.php'
            if os.path.exists(php_path):
                return php_path

        return None

    def resolve_import(self, import_statement: str, project_root: Optional[str] = None,
                       current_file: Optional[str] = None) -> Optional[str]:
        """Resolve PHP import/use statement to file path"""
        import_path = self.clean_import_statement(import_statement)

        cache_key = f"{import_path}:{project_root}:{current_file}"
        if cache_key in self.module_cache:
            return self.module_cache[cache_key]

        result = self._resolve_import_internal(
            import_path, project_root, current_file)
        self.module_cache[cache_key] = result
        return result

    def _resolve_import_internal(self, import_path: str, project_root: Optional[str] = None,
                                 current_file: Optional[str] = None) -> Optional[str]:
        """Internal PHP import resolution logic"""
        # Determine starting directory
        if current_file and os.path.exists(current_file):
            start_dir = os.path.dirname(current_file)
        elif project_root and os.path.exists(project_root):
            start_dir = project_root
        else:
            start_dir = os.getcwd()

        # Handle relative file paths (require/include)
        if ('/' in import_path or '\\' in import_path) and not import_path.startswith('\\'):
            relative_result = self.resolve_relative_path(
                import_path, start_dir)
            if relative_result:
                return relative_result

        # Find composer.json
        composer_path = self.find_composer_json(start_dir)
        if not composer_path:
            return None

        composer_data = self.parse_composer_json(composer_path)
        composer_dir = os.path.dirname(composer_path)

        # Try PSR-4 autoloading
        psr4_result = self.resolve_psr4_autoload(
            import_path, composer_data, composer_dir)
        if psr4_result:
            return psr4_result

        # Try PSR-0 autoloading
        psr0_result = self.resolve_psr0_autoload(
            import_path, composer_data, composer_dir)
        if psr0_result:
            return psr0_result

        # Try classmap
        classmap_result = self.resolve_classmap(
            import_path, composer_data, composer_dir)
        if classmap_result:
            return classmap_result

        # Try vendor autoload files
        vendor_result = self.resolve_vendor_path(import_path, composer_dir)
        if vendor_result:
            return vendor_result

        return None


def resolve_php_import(import_statement: str, project_root: Optional[str] = None,
                       current_file: Optional[str] = None) -> Optional[str]:
    resolver = PHPImportResolver()
    return resolver.resolve_import(import_statement, project_root, current_file)


if __name__ == "__main__":
    print("\n=== PHP Import Resolver ===")
    php_resolver = PHPImportResolver()
    php_imports = [
        "App\\Models\\User",
        "Illuminate\\Database\\Eloquent\\Model",
        "Symfony\\Component\\HttpFoundation\\Request",
        "./config/database.php",
        "Vendor\\Package\\SomeClass"
    ]

    for imp in php_imports:
        result = php_resolver.resolve_import(
            imp, "./php-project", "./php-project/src/Controller.php")
        print(f"{imp} -> {result}")
