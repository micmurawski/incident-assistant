import os
import json
from pathlib import Path
from tree_sitter import Language, Parser, Tree
import subprocess
import glob

import tree_sitter_typescript
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_java


class CodeStructureAnalyzer:
    def __init__(self):

        self.languages = {
            'javascript': {
                'extensions': ['.js'],
                'class_types': ['class_declaration'],
                'method_types': ['method_definition'],
                'function_types': ['function_declaration', 'function', 'arrow_function'],
                'constructor_identifier': 'constructor',
                'reference_types': ['identifier', 'property_identifier', 'member_expression'],
                'import_types': ['import_statement', 'import_declaration', 'call_expression'],
                'import_name_field': 'source',
                'import_alias_field': 'name',
                'require_function': 'require'
            },
            'typescript': {
                'extensions': ['.ts', '.tsx'],
                'class_types': ['class_declaration'],
                'method_types': ['method_definition'],
                'function_types': ['function_declaration', 'function', 'arrow_function'],
                'constructor_identifier': 'constructor',
                'reference_types': ['identifier', 'property_identifier', 'member_expression'],
                'import_types': ['import_statement', 'import_declaration'],
                'import_name_field': 'source',
                'import_alias_field': 'name'
            },
            'python': {
                'extensions': ['.py'],
                'class_types': ['class_definition'],
                'method_types': ['function_definition'],
                'function_types': ['function_definition'],
                'constructor_identifier': '__init__',
                'reference_types': ['identifier', 'attribute', 'call'],
                'import_types': ['import_statement', 'import_from_statement'],
                'import_name_field': 'module',
                'import_alias_field': 'name'
            },
            'java': {
                'extensions': ['.java'],
                'class_types': ['class_declaration', 'interface_declaration'],
                'method_types': ['method_declaration'],
                'function_types': [],#['method_declaration'],
                'constructor_identifier': None,
                'reference_types': ['identifier', 'method_invocation', 'object_creation_expression', 'field_declaration', 'variable_declarator', 'type_identifier', 'scoped_identifier', 'type_parameter', 'type_arguments', 'type_bound'],
                'import_types': ['import_declaration'],
                'import_name_field': 'name',
                'import_alias_field': None
            }
        }

        self.REFERENCE_IDENTIFIERS = {
            "python": {
                "class": "identifier",
                "method": "call",
                "child_field_name": "function",
                "field": "attribute",
                "variable": "identifier"
            },
            "java": {
                "class": "type_identifier",
                "method": "method_invocation",
                "child_field_name": "name",
                "field": "field_declaration",
                "variable": "variable_declarator",
                "parameter": "formal_parameter",
                "return_type": "type"
            },
            "javascript": {
                "class": "identifier",
                "method": "call_expression",
                "child_field_name": "function",
                "field": "property_identifier",
                "variable": "identifier"
            },
            "typescript": {
                "class": "identifier",
                "method": "call_expression",
                "child_field_name": "function",
                "field": "property_identifier",
                "variable": "identifier"
            }
        }

        self.parsers = {}
        self.setup_languages()
        self.parsed_files_cache = {}

    def setup_languages(self):
        for lang_name in self.languages:
            if lang_name == 'typescript':
                lang_obj = Language(
                    tree_sitter_typescript.language_typescript())
                self.parsers[lang_name] = Parser(lang_obj)

                # Also set up TSX parser if needed
                if '.tsx' in self.languages[lang_name]['extensions']:
                    lang_obj_tsx = Language(
                        tree_sitter_typescript.language_tsx())
                    self.parsers['tsx'] = Parser(lang_obj_tsx)
            elif lang_name == 'javascript':
                lang_obj = Language(
                    tree_sitter_javascript.language())
                self.parsers[lang_name] = Parser(lang_obj)
            elif lang_name == 'python':
                lang_obj = Language(tree_sitter_python.language())
                self.parsers[lang_name] = Parser(lang_obj)
            elif lang_name == 'java':
                lang_obj = Language(tree_sitter_java.language())
                self.parsers[lang_name] = Parser(lang_obj)
            else:
                raise ValueError(f"Unsupported language: {lang_name}")

    def get_language_for_file(self, file_path):
        """Determine the language based on file extension."""
        extension = os.path.splitext(file_path)[1].lower()
        for lang_name, config in self.languages.items():
            if extension in config['extensions']:
                if extension == '.tsx':
                    return 'tsx'
                return lang_name
        return None

    @classmethod
    def _get_node_text(cls, node, code_bytes):
        """Extract text content from a node."""
        return code_bytes[node.start_byte:node.end_byte].decode('utf8')

    def _find_name_node(self, node, lang_name):
        """Find the name node for a class, method, or function."""
        if lang_name in ['javascript', 'typescript', 'tsx']:
            # For JS/TS classes and functions
            for child in node.children:
                if child.type == 'identifier' or child.type == 'property_identifier':
                    return child

        elif lang_name == 'python':
            # For Python classes and functions
            for child in node.children:
                if child.type == 'identifier':
                    return child

        elif lang_name == 'java':
            # For Java classes and methods
            for child in node.children:
                if child.type == 'identifier':
                    return child

        # Deeper search if not found directly
        for child in node.children:
            if 'name' in child.type or 'identifier' in child.type:
                return child

        return None

    def _get_node_name(self, node, code_bytes, lang_name):
        """Get the name of a class, method, or function node."""
        name_node = self._find_name_node(node, lang_name)
        if name_node:
            return self._get_node_text(name_node, code_bytes)
        return None

    def _is_constructor(self, method_node, class_name, code_bytes, lang_name):
        """Check if a method is a constructor."""
        method_name = self._get_node_name(method_node, code_bytes, lang_name)
        if not method_name:
            return False

        lang_config = self.languages[lang_name.replace('tsx', 'typescript')]
        constructor_id = lang_config['constructor_identifier']

        # For languages with explicit constructor name like JS/TS
        if constructor_id and method_name == constructor_id:
            return True

        # For Java, constructor has same name as class
        if lang_name == 'java' and method_name == class_name:
            return True

        return False

    def _extract_docstring(self, node, code_bytes, lang_name):
        """Extract docstring from a node based on language."""
        docstring = None

        if lang_name == 'python':
            # In Python, docstring is usually the first string expression in the body
            body_node = None

            # Find the body node
            for child in node.children:
                if child.type == 'block':
                    body_node = child
                    break

            if body_node:
                # Look for the first expression/string node
                for child in body_node.children:
                    # Check for expression statements containing strings
                    if child.type == 'expression_statement':
                        for expr_child in child.children:
                            if expr_child.type in ['string', 'string_content']:
                                docstring = self._get_node_text(
                                    child, code_bytes)
                                # Clean up the docstring
                                docstring = docstring.strip().strip('"\'').strip()
                                return docstring

        elif lang_name in ['javascript', 'typescript', 'tsx']:
            # In JS/TS, look for JSDoc comments above the node
            if node.prev_sibling and node.prev_sibling.type == 'comment':
                comment_text = self._get_node_text(
                    node.prev_sibling, code_bytes)
                if comment_text.startswith('/**') and comment_text.endswith('*/'):
                    # Clean up the JSDoc comment
                    lines = comment_text.split('\n')
                    cleaned_lines = []
                    for line in lines:
                        line = line.strip().lstrip('/*').lstrip('*').rstrip('*/').strip()
                        if line:
                            cleaned_lines.append(line)
                    docstring = '\n'.join(cleaned_lines)

        elif lang_name == 'java':
            # In Java, also look for Javadoc comments above the node
            if node.prev_sibling and node.prev_sibling.type == 'comment':
                comment_text = self._get_node_text(
                    node.prev_sibling, code_bytes)
                if comment_text.startswith('/**') and comment_text.endswith('*/'):
                    # Clean up the Javadoc comment
                    lines = comment_text.split('\n')
                    cleaned_lines = []
                    for line in lines:
                        line = line.strip().lstrip('/*').lstrip('*').rstrip('*/').strip()
                        if line:
                            cleaned_lines.append(line)
                    docstring = '\n'.join(cleaned_lines)

        return docstring

    def _extract_method_data(self, method_node, code_bytes, lang_name):
        """Extract data from a method node."""
        method_name = self._get_node_name(method_node, code_bytes, lang_name)
        if not method_name:
            method_name = "<anonymous>"

        # Extract docstring
        docstring = self._extract_docstring(method_node, code_bytes, lang_name)

        method_data = {
            "method_name": method_name,
            "start_line": method_node.start_point[0] + 1,
            "end_line": method_node.end_point[0] + 1,
            "start_column": method_node.start_point[1],
            "end_column": method_node.end_point[1],
            # "source_code": self._get_node_text(method_node, code_bytes)
        }

        # Add docstring if found
        if docstring:
            method_data["doc_string"] = docstring

        return method_data

    def _find_class_methods(self, class_node, code_bytes, lang_name):
        """Find all methods within a class node."""
        methods = []
        constructor = None

        # Get class name for constructor identification
        class_name = self._get_node_name(class_node, code_bytes, lang_name)

        # Different languages store methods differently
        if lang_name in ['javascript', 'typescript', 'tsx']:
            # For JS/TS, methods are in class_body
            for child in class_node.children:
                if child.type == 'class_body':
                    for body_item in child.children:
                        if body_item.type in self.languages[lang_name.replace('tsx', 'typescript')]['method_types']:
                            method_data = self._extract_method_data(
                                body_item, code_bytes, lang_name)

                            # Check if it's a constructor
                            if self._is_constructor(body_item, class_name, code_bytes, lang_name):
                                constructor = method_data
                            else:
                                methods.append(method_data)

        elif lang_name == 'python':
            # For Python, methods are functions in the class block
            for child in class_node.children:
                if child.type == 'block':
                    for body_item in child.children:
                        if body_item.type in self.languages[lang_name]['method_types']:
                            method_data = self._extract_method_data(
                                body_item, code_bytes, lang_name)

                            # Check if it's a constructor
                            if self._is_constructor(body_item, class_name, code_bytes, lang_name):
                                constructor = method_data
                            else:
                                methods.append(method_data)

        elif lang_name == 'java':
            # For Java, methods are in the class_body
            for child in class_node.children:
                if child.type == 'class_body':
                    for body_item in child.children:
                        if body_item.type in self.languages[lang_name]['method_types']:
                            method_data = self._extract_method_data(
                                body_item, code_bytes, lang_name)

                            # Check if it's a constructor
                            if self._is_constructor(body_item, class_name, code_bytes, lang_name):
                                constructor = method_data
                            else:
                                methods.append(method_data)

        return methods, constructor

    def _find_classes_and_functions(self, root_node, code_bytes, file_path, lang_name):
        """
        Recursively find all classes and functions in a parsed file.

        Returns:
            tuple: (classes_data, functions_data)
        """
        classes_data = []
        functions_data = []

        # Handle TypeScript variants
        lang_config_name = lang_name.replace('tsx', 'typescript')

        def traverse(node, parent=None):
            """Recursively traverse the syntax tree."""
            # Check if this node is a class
            if node.type in self.languages[lang_config_name]['class_types']:
                class_name = self._get_node_name(node, code_bytes, lang_name)
                if class_name:
                    # Find methods and constructor
                    methods, constructor = self._find_class_methods(
                        node, code_bytes, lang_name)

                    # Extract class docstring
                    class_docstring = self._extract_docstring(
                        node, code_bytes, lang_name)

                    # Create class data dictionary
                    class_data = {
                        "class_name": class_name,
                        "constructor_declaration": constructor,
                        "method_declarations": methods,
                        "file_path": file_path,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "start_column": node.start_point[1],
                        "end_column": node.end_point[1],
                        # "source_code": self._get_node_text(node, code_bytes)
                    }

                    # Add docstring if found
                    if class_docstring:
                        class_data["doc_string"] = class_docstring

                    # Add class to results
                    classes_data.append(class_data)

            # Check if this node is a standalone function (not inside a class)
            elif (node.type in self.languages[lang_config_name]['function_types'] and
                  (not parent or parent.type not in self.languages[lang_config_name]['class_types'])):
                function_name = self._get_node_name(
                    node, code_bytes, lang_name)
                if function_name:
                    # Extract function docstring
                    function_docstring = self._extract_docstring(
                        node, code_bytes, lang_name)

                    # Create function data dictionary
                    function_data = {
                        "function_name": function_name,
                        "file_path": file_path,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "start_column": node.start_point[1],
                        "end_column": node.end_point[1],
                        # "source_code": self._get_node_text(node, code_bytes)
                    }

                    # Add docstring if found
                    if function_docstring:
                        function_data["doc_string"] = function_docstring

                    # Add function to results
                    functions_data.append(function_data)

            # Continue traversing the tree
            for child in node.children:
                traverse(child, node)

        # Start traversal from the root
        traverse(root_node)

        return classes_data, functions_data

    @classmethod
    def _is_require_statement(cls, node: Tree, code_bytes: bytes, lang_name: str) -> bool:
        """Check if a node is a require statement in JavaScript."""
        if lang_name != 'javascript':
            return False

        if node.type != 'call_expression':
            return False

        # Get the function name
        function_node = node.child_by_field_name('function')
        if not function_node:
            return False

        function_name = cls._get_node_text(function_node, code_bytes)
        return function_name == 'require'

    @classmethod
    def _extract_require_import(cls, node: Tree, code_bytes: bytes) -> dict:
        """Extract import information from a require statement."""
        # Get the argument node (the string literal with the module name)
        arguments = node.child_by_field_name('arguments')
        if not arguments or not arguments.children:
            return None

        module_node = arguments.children[0]
        if module_node.type != 'string':
            return None

        module_name = cls._get_node_text(module_node, code_bytes).strip('"\'')

        # Get the variable name if it's assigned
        parent = node.parent
        if parent and parent.type == 'variable_declarator':
            name_node = parent.child_by_field_name('name')
            if name_node:
                ref_name = cls._get_node_text(name_node, code_bytes)
            else:
                ref_name = module_name
        else:
            ref_name = module_name

        return {
            'name': module_name,
            'ref_name': ref_name
        }

    def analyze_file(self, file_path: str) -> tuple[list, list, list]:
        """
        Analyze a single file and extract class, function, and import data.

        Args:
            file_path: Path to the file to analyze

        Returns:
            tuple: (classes_data, functions_data, imports_data)
        """
        # Determine the language
        lang_name = self.get_language_for_file(file_path)
        if not lang_name:
            print(f"Skipping unsupported file: {file_path}")
            return [], [], []

        try:
            # Read the file content
            with open(file_path, 'rb') as f:
                code_bytes = f.read()

            # Parse the file
            tree = self.parsers[lang_name].parse(code_bytes)
            
            # TODO: find used dependencies
            #self._find_name_node(tree.root_node, lang_name)

            # Extract classes, functions, and imports
            classes_data, functions_data = self._find_classes_and_functions(
                tree.root_node, code_bytes, file_path, lang_name)
            imports_data = []

            return classes_data, functions_data, imports_data

        except Exception as e:
            print(f"Error analyzing file {file_path}: {str(e)}")
            raise
            return [], [], []

    @staticmethod
    def deduplicate_references(references):
        seen = set()
        unique_references = []

        for ref in references:
            key = (ref['start_line'], ref['end_line'], ref['file_path'])

            if key not in seen:
                seen.add(key)
                unique_references.append(ref)

        return unique_references

    def _find_references_in_file(self, root_node, code_bytes, file_path, lang_name, identifier):
        """
        Find all references to a specific identifier in a file.

        Args:
            root_node: The root node of the parsed file
            code_bytes: The file content as bytes
            file_path: Path to the file
            lang_name: Language of the file
            identifier: The identifier name to look for

        Returns:
            list: List of reference locations (dicts with file_path, start_line, end_line)
        """
        references = []
        lang_config_name = lang_name.replace('tsx', 'typescript')
        ref_config = self.REFERENCE_IDENTIFIERS[lang_config_name]

        def add_reference(node):
            """Add a reference to the list if the node matches the identifier."""
            references.append({
                "file_path": file_path,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

        def is_declaration(node, parent):
            """Check if a node is a declaration rather than a reference."""
            if not parent:
                return False
            
            if lang_name in ['javascript', 'typescript', 'tsx']:
                return (parent.type == 'class_declaration' and node == parent.child_by_field_name('name')) or \
                       (parent.type == 'method_definition' and node == parent.child_by_field_name('name')) or \
                       (parent.type == 'function_declaration' and node == parent.child_by_field_name('name'))
            elif lang_name == 'python':
                return parent.type in ['class_definition', 'function_definition']
            elif lang_name == 'java':
                return (parent.type == 'class_declaration' and node == parent.child_by_field_name('name')) or \
                       (parent.type == 'method_declaration' and node == parent.child_by_field_name('name')) or \
                       (parent.type == ref_config["field"] and node == parent.child_by_field_name('name')) or \
                       (parent.type == ref_config["variable"] and node == parent.child_by_field_name('name'))
            return False

        def check_type_node(type_node):
            """Check a type node for references to the identifier."""
            if not type_node:
                return

            for child in type_node.children:
                if child.type == ref_config["class"]:
                    type_name = self._get_node_text(child, code_bytes)
                    if type_name == identifier:
                        add_reference(child)
                elif child.type == 'scoped_identifier':
                    for subchild in child.children:
                        if subchild.type == ref_config["class"]:
                            type_name = self._get_node_text(subchild, code_bytes)
                            if type_name == identifier:
                                add_reference(subchild)

        def traverse(node):
            """Recursively traverse the AST looking for references."""
            # Check if this node could be a reference
            if node.type in self.languages[lang_config_name]['reference_types']:
                # Handle different reference patterns by language
                if lang_name in ['javascript', 'typescript', 'tsx']:
                    # For direct identifiers
                    if node.type == ref_config["class"]:
                        node_text = self._get_node_text(node, code_bytes)
                        if node_text == identifier and not is_declaration(node, node.parent):
                            add_reference(node)

                    # For method calls
                    elif node.type == ref_config["method"]:
                        function_node = node.child_by_field_name(ref_config["child_field_name"])
                        if function_node:
                            function_name = self._get_node_text(function_node, code_bytes)
                            if function_name == identifier:
                                add_reference(node)

                elif lang_name == 'python':
                    # For direct identifiers in Python
                    if node.type == ref_config["class"]:
                        node_text = self._get_node_text(node, code_bytes)
                        if node_text == identifier and not is_declaration(node, node.parent):
                            add_reference(node)

                    # For method calls in Python
                    elif node.type == ref_config["method"]:
                        function_node = node.child_by_field_name(ref_config["child_field_name"])
                        if function_node and function_node.type == ref_config["class"]:
                            function_name = self._get_node_text(function_node, code_bytes)
                            if function_name == identifier:
                                add_reference(node)

                elif lang_name == 'java':
                    # For direct identifiers in Java
                    if node.type == ref_config["class"]:
                        node_text = self._get_node_text(node, code_bytes)
                        if node_text == identifier and not is_declaration(node, node.parent):
                            add_reference(node)

                    # For field declarations in Java
                    elif node.type == ref_config["field"]:
                        check_type_node(node.child_by_field_name(ref_config["return_type"]))

                    # For variable declarations in Java
                    elif node.type == ref_config["variable"]:
                        parent = node.parent
                        if parent and parent.type == 'local_variable_declaration':
                            check_type_node(parent.child_by_field_name(ref_config["return_type"]))

                    # For method declarations in Java
                    elif node.type == 'method_declaration':
                        # Check return type
                        check_type_node(node.child_by_field_name(ref_config["return_type"]))

                        # Check parameters
                        parameters = node.child_by_field_name('parameters')
                        if parameters:
                            for param in parameters.children:
                                if param.type == ref_config["parameter"]:
                                    check_type_node(param.child_by_field_name(ref_config["return_type"]))

            # Continue traversing children
            for child in node.children:
                traverse(child)

        # Start traversal
        traverse(root_node)
        return self.deduplicate_references(references)

    def _get_file_parse_cache(self, file_paths):
        """
        Parse all specified files and cache the results.

        Args:
            file_paths: List of file paths to parse

        Returns:
            dict: Mapping of file paths to (tree, code_bytes, lang_name) tuples
        """
        # Parse files not in cache
        for file_path in file_paths:
            if file_path not in self.parsed_files_cache:
                # Determine the language
                lang_name = self.get_language_for_file(file_path)
                if not lang_name:
                    continue

                try:
                    # Read the file content
                    with open(file_path, 'rb') as f:
                        code_bytes = f.read()

                    # Parse the file
                    tree = self.parsers[lang_name].parse(code_bytes)

                    # Cache the results
                    self.parsed_files_cache[file_path] = (
                        tree, code_bytes, lang_name)

                except Exception as e:
                    print(f"Error parsing file {file_path}: {str(e)}")
                    continue

        return self.parsed_files_cache

    def _find_all_references(self, all_file_paths, elements_with_ids):
        """
        Find all references to the specified elements across all files.

        Args:
            all_file_paths: List of all file paths to search in
            elements_with_ids: List of (element, identifier, source_language) tuples where:
                - element is a dict to update with references
                - identifier is the name to search for
                - source_language is the language of the declaration (to match only in compatible files)
        """
        # Parse all files first
        file_cache = self._get_file_parse_cache(all_file_paths)

        # Group files by language for more efficient processing
        files_by_language = {}
        for file_path, (tree, code_bytes, lang_name) in file_cache.items():
            base_lang = lang_name.replace('tsx', 'typescript')
            if base_lang not in files_by_language:
                files_by_language[base_lang] = []
            files_by_language[base_lang].append(
                (file_path, tree, code_bytes, lang_name))

        # For each element, search for references in files of the same language
        for element, identifier, source_language in elements_with_ids:
            element['references'] = []

            # Only search in files of the same language
            base_source_lang = source_language.replace('tsx', 'typescript')

            # Skip if this language has no files
            if base_source_lang not in files_by_language:
                continue

            for file_path, tree, code_bytes, lang_name in files_by_language[base_source_lang]:
                # Skip the declaration file to avoid duplicate references
                if 'file_path' in element and file_path == element['file_path']:
                    continue

                # Find references in this file
                refs = self._find_references_in_file(
                    tree.root_node, code_bytes, file_path, lang_name, identifier
                )

                # Add to the element
                element['references'].extend(refs)

    def analyze_directory(self, directory_path, recursive=True, find_references=True) -> dict:
        """
        Analyze all supported code files in a directory.

        Args:
            directory_path: Directory to analyze
            recursive: Whether to recursively analyze subdirectories
            find_references: Whether to find references to classes, methods, and functions

        Returns:
            tuple: (all_classes_data, all_functions_data, all_imports_data)
        """
        all_classes_data = []
        all_functions_data = []
        all_imports_data = []

        # Collect all supported file extensions
        all_extensions = []
        for lang_config in self.languages.values():
            all_extensions.extend(lang_config['extensions'])

        # Convert to set for faster lookups
        supported_extensions = set(all_extensions)

        # Build the pattern for glob search
        pattern = os.path.join(directory_path, '**' if recursive else '', '*')

        # Find all files
        all_file_paths = []
        for file_path in glob.glob(pattern, recursive=recursive):
            if os.path.isfile(file_path):
                # Check if the file has a supported extension
                extension = os.path.splitext(file_path)[1].lower()
                if extension in supported_extensions:
                    all_file_paths.append(file_path)

        # First pass: collect all classes, functions, and imports
        for file_path in all_file_paths:
            print(f"Analyzing file: {file_path}")
            classes_data, functions_data, imports_data = self.analyze_file(
                file_path)
            all_classes_data.extend(classes_data)
            all_functions_data.extend(functions_data)
            all_imports_data.extend(imports_data)

        # Second pass: find references if requested
        if find_references:
            print("\nFinding references...")

            # Prepare list of elements with their identifiers and source language
            elements_with_ids = []

            # Add classes
            for class_data in all_classes_data:
                # Get the source language from the file extension
                file_path = class_data['file_path']
                source_language = self.get_language_for_file(file_path)

                elements_with_ids.append(
                    (class_data, class_data['class_name'], source_language))

                # Add methods
                for method_data in class_data.get('method_declarations', []):
                    elements_with_ids.append(
                        (method_data, method_data['method_name'], source_language))

                # Add constructor if present
                if class_data.get('constructor_declaration'):
                    elements_with_ids.append(
                        (class_data['constructor_declaration'],
                         class_data['constructor_declaration']['method_name'],
                         source_language)
                    )

            # Add functions
            for function_data in all_functions_data:
                # Get the source language from the file extension
                file_path = function_data['file_path']
                source_language = self.get_language_for_file(file_path)

                elements_with_ids.append(
                    (function_data, function_data['function_name'], source_language))

            # Find references for all elements
            self._find_all_references(all_file_paths, elements_with_ids)

        results = {
            "class_data": all_classes_data,
            "functions_data": all_functions_data,
            "imports_data": all_imports_data
        }

        return results

    def save_results_to_json(self, output_file, data: dict):
        """Save the analysis results to a JSON file."""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        print(f"Results saved to {output_file}")
        print(
            f"Found {len(data['class_data'])} classes, {len(data['functions_data'])} functions, and {len(data['imports_data'])} imports")


# Example usage
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze code structure in a directory")
    parser.add_argument("directory", help="Directory to analyze")
    parser.add_argument(
        "--output", "-o", default="code_structure.json", help="Output JSON file")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Recursively analyze subdirectories")
    parser.add_argument("--no-references", action="store_true",
                        help="Skip finding references (faster)")

    args = parser.parse_args()

    analyzer = CodeStructureAnalyzer()
    data = analyzer.analyze_directory(
        args.directory,
        args.recursive,
        find_references=not args.no_references
    )
    analyzer.save_results_to_json(args.output, data)
