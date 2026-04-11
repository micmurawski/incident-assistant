import glob
import os
import re
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def collect_jars_from_path(path_pattern: str, only_latest: bool = True) -> Dict[str, List[Tuple[str, str]]]:
    jar_files = glob.glob(path_pattern, recursive=True)
    artifacts = defaultdict(list)
    for jar_path in jar_files:
        path_parts = jar_path.split(os.sep)
        if len(path_parts) >= 4:
            artifact_id = path_parts[-3]
            version_str = path_parts[-2]
            filename = path_parts[-1]
            filename_match = re.search(f"{artifact_id}-([\\d.]+(?:-[\\w]+)?)\\.jar", filename)
            if filename_match:
                version_str = filename_match.group(1)
            artifacts[artifact_id].append((version_str, jar_path))

    if not only_latest:
        res = []
        for artifact_id, versions in artifacts.items():
            for version, path in versions:
                res.append(path)
        return res
    res = []
    for artifact_id, versions in artifacts.items():
        try:
            sorted_versions = sorted(versions, key=lambda x: version.parse(x[0]), reverse=True)
            latest_version, latest_path = sorted_versions[0]
            res.append(latest_path)
        except Exception as e:
            print(f"Error processing {artifact_id}: {e}")
            print(f"{artifact_id} (unknown version): {versions[0][1]}")
    return res


class JavaImportResolver:
    def __init__(self):
        self.source_cache: Dict[str, str] = {}
        self.jar_cache: Dict[str, List[str]] = {}
        self.jdk_paths = self._find_jdk_paths()

    def _find_jdk_paths(self) -> List[str]:
        paths = []

        mac_locations = [
            "/Library/Java/JavaVirtualMachines",
            f"{os.path.expanduser('~')}/Library/Java/JavaVirtualMachines",
            "/System/Library/Java/JavaVirtualMachines",
        ] + glob.glob("/Library/Java/JavaVirtualMachines/*/Contents/Home/lib/src.zip")

        linux_locations = ["/usr/lib/jvm", "/usr/java"]

        windows_locations = ["C:/Program Files/Java", "C:/Program Files (x86)/Java"]

        all_locations = mac_locations + linux_locations + windows_locations
        for location in all_locations:
            if os.path.exists(location):
                if os.path.isdir(location):
                    for root, dirs, files in os.walk(location):
                        for file in files:
                            if file == "src.zip":
                                paths.append(os.path.join(root, file))

                        if "src" in dirs:
                            paths.append(os.path.join(root, "src"))
        return paths

    def clean_import_statement(self, import_statement: str) -> Tuple[str, bool]:
        import_path = import_statement.strip()
        if import_path.startswith("import "):
            import_path = import_path[7:]
        if import_path.endswith(";"):
            import_path = import_path[:-1]  # Handle static imports
        if import_path.startswith("static "):
            import_path = import_path[7:]
        is_wildcard = import_path.endswith(".*")
        if is_wildcard:
            import_path = import_path[:-2]
        return import_path, is_wildcard

    def get_classpath_entries(self, project_root: Optional[str] = None) -> List[str]:
        classpath_entries = []
        if project_root:
            src_patterns = [
                os.path.join(project_root, "src/main/java"),
                os.path.join(project_root, "src/test/java"),
                os.path.join(project_root, "src"),
                os.path.join(project_root, "source"),
                project_root,
            ]

            for pattern in src_patterns:
                if os.path.isdir(pattern):
                    classpath_entries.append(pattern)

        if project_root:
            maven_repo = os.path.expanduser("~/.m2/repository")
            classpath_entries += collect_jars_from_path(os.path.join(maven_repo, "**/*.jar"), only_latest=False)
            # if os.path.isdir(maven_repo):
            #    for root, _, files in os.walk(maven_repo):
            #        for file in files:
            #            if file.endswith("-sources.jar"):
            #                classpath_entries.append(os.path.join(root, file))

            gradle_cache = os.path.expanduser("~/.gradle/caches")
            if os.path.isdir(gradle_cache):
                for root, _, files in os.walk(gradle_cache):
                    for file in files:
                        if file.endswith("-sources.jar"):
                            classpath_entries.append(os.path.join(root, file))

            lib_dirs = [
                os.path.join(project_root, "lib"),
                os.path.join(project_root, "libs"),
                os.path.join(project_root, "dependencies"),
            ]
            for lib_dir in lib_dirs:
                if os.path.isdir(lib_dir):
                    for file in os.listdir(lib_dir):
                        if file.endswith(".jar"):
                            classpath_entries.append(os.path.join(lib_dir, file))

        classpath_entries.extend(self.jdk_paths)
        return classpath_entries

    def find_in_directory(self, import_path: str, directory: str) -> Optional[str]:
        path_parts = import_path.split(".")
        class_name = path_parts[-1]
        package_parts = path_parts[:-1]

        rel_path = os.path.join(*package_parts, f"{class_name}.java")
        file_path = os.path.join(directory, rel_path)

        if os.path.isfile(file_path):
            return file_path

        if os.path.isdir(os.path.join(directory, *package_parts)):
            dir_path = os.path.join(directory, *package_parts)
            for file in os.listdir(dir_path):
                if file.lower() == f"{class_name.lower()}.java":
                    return os.path.join(dir_path, file)
        return None

    def find_in_jar(self, import_path: str, jar_path: str) -> Optional[str]:
        path_parts = import_path.split(".")
        class_name = path_parts[-1]
        package_parts = path_parts[:-1]
        rel_path = "/".join(package_parts) + "/" + class_name + ".java"

        if jar_path not in self.jar_cache:
            try:
                with zipfile.ZipFile(jar_path, "r") as jar:
                    self.jar_cache[jar_path] = jar.namelist()
            except zipfile.BadZipFile:
                self.jar_cache[jar_path] = []
                return None

        jar_contents = self.jar_cache[jar_path]

        if rel_path in jar_contents:
            with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as temp:
                with zipfile.ZipFile(jar_path, "r") as jar:
                    temp.write(jar.read(rel_path))
                return temp.name

        rel_path_lower = rel_path.lower()
        for jar_entry in jar_contents:
            if jar_entry.lower() == rel_path_lower:
                with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as temp:
                    with zipfile.ZipFile(jar_path, "r") as jar:
                        temp.write(jar.read(jar_entry))
                    return temp.name

        rel_path = os.path.join("java.base", rel_path)
        if rel_path in jar_contents:
            with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as temp:
                with zipfile.ZipFile(jar_path, "r") as jar:
                    temp.write(jar.read(rel_path))
                return temp.name

        rel_path_lower = rel_path.lower()
        jar_entry = os.path.join("java.base", jar_entry)
        for jar_entry in jar_contents:
            if jar_entry.lower() == rel_path_lower:
                with tempfile.NamedTemporaryFile(suffix=".java", delete=False) as temp:
                    with zipfile.ZipFile(jar_path, "r") as jar:
                        temp.write(jar.read(jar_entry))
                    return temp.name
        return None

    def resolve_import(self, import_statement: str, project_root: Optional[str] = None) -> Optional[str]:
        import_path, is_wildcard = self.clean_import_statement(import_statement)
        if is_wildcard:
            return None

        if import_path in self.source_cache:
            return self.source_cache[import_path]

        classpath_entries = self.get_classpath_entries(project_root)
        for entry in classpath_entries:
            if entry.endswith(".jar") or entry.endswith(".zip"):
                file_path = self.find_in_jar(import_path, entry)
            else:
                file_path = self.find_in_directory(import_path, entry)

            if file_path:
                self.source_cache[import_path] = file_path
                return file_path

        if project_root:
            found_path = self.search_recursively(import_path, project_root)
            if found_path:
                self.source_cache[import_path] = found_path
                return found_path

        return None

    def search_recursively(self, import_path: str, directory: str) -> Optional[str]:
        path_parts = import_path.split(".")
        class_name = path_parts[-1]
        file_pattern = f"**/{class_name}.java"

        matches = list(Path(directory).glob(file_pattern))

        for match in matches:
            if self.verify_class_in_file(str(match), class_name):
                return str(match)

        return None

    def verify_class_in_file(self, file_path: str, class_name: str) -> bool:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()

                class_pattern = re.compile(
                    r"(public|private|protected)?\s*(class|interface|enum)\s+" + re.escape(class_name) + r"\b"
                )

                return bool(class_pattern.search(content))
        except Exception:
            return False


def resolve_java_import(import_statement: str, source_root: Optional[str] = None) -> Optional[str]:
    resolver = JavaImportResolver()
    return resolver.resolve_import(import_statement, source_root)


# Example usage
if __name__ == "__main__":
    resolver = JavaImportResolver()
    from sme_agent.dependencies_analyzer.code_extractor import CodeExtractor
    from sme_agent.dependencies_analyzer.import_parser import ImportParser

    from agent.repo_paths import robot_shop_dir

    sample = (
        robot_shop_dir()
        / "shipping"
        / "src"
        / "main"
        / "java"
        / "com"
        / "instana"
        / "robotshop"
        / "shipping"
        / "ShippingServiceApplication.java"
    )
    file_content = open(sample, "r").read()
    for imp in ImportParser().parse_imports(file_content, "java"):
        name = imp["name"]
        res = resolve_java_import(name, "../services/robot-shop/shipping")
        print(imp["ref"], "->", res)
        if res:
            code_extractor = CodeExtractor().extract(imp["ref"], res)
            print(code_extractor)
