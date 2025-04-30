#!/usr/bin/env python3
"""
TypeScript Error Log Analyzer for LLMs

This script processes TypeScript error logs and extracts structured information to help
LLMs debug TypeScript problems more effectively. It handles both compilation errors and
runtime errors, providing detailed type information and suggestions for common TS issues.
"""

import re
import json
import sys
import os
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

class TypeScriptErrorLogAnalyzer:
    """Analyzes TypeScript error logs and extracts structured information."""
    
    # Patterns for extracting information from TypeScript logs
    
    # TypeScript compiler error pattern
    # Example: error TS2322: Type 'string' is not assignable to type 'number'.
    TS_COMPILER_ERROR_PATTERN = re.compile(
        r'(?:^|\n)(?:ERROR|Error|error)\s+TS(\d+):\s+(.+?)(?=\n|$)',
        re.MULTILINE
    )
    
    # TypeScript file location pattern
    # Example: src/app.ts:42:10
    TS_FILE_LOCATION_PATTERN = re.compile(
        r'((?:[a-zA-Z]:)?[\\/]?[\w\-./\\]+\.(?:ts|tsx))(?::(\d+))?(?::(\d+))?',
        re.MULTILINE
    )
    
    # Runtime error patterns (similar to JavaScript)
    RUNTIME_ERROR_PATTERN = re.compile(
        r'(?:^|\n)(?:Uncaught )?(\w+(?:Error|Exception))(?:: (.+?))?(?=\n\s+at|\n|$)',
        re.MULTILINE | re.DOTALL
    )
    
    # Stack trace patterns (for runtime errors)
    BROWSER_FRAME_PATTERN = re.compile(r'\s+at\s+(?:(.+?)\s+)?\(?(.+?):(\d+):(\d+)\)?')
    NODE_FRAME_PATTERN = re.compile(r'\s+at\s+(?:(.+?)\s+\()?(.+?):(\d+):(\d+)(?:\))?')
    
    # Extract additional context
    TYPE_INFORMATION_PATTERN = re.compile(r'Type\s+\'([^\']+)\'\s+is\s+(?:not\s+)?(.+?)(\'[^\']+\')?')
    EXPECTED_TYPE_PATTERN = re.compile(r'Expected\s+(?:type\s+)?\'([^\']+)\'')
    
    # Common TypeScript error codes and their descriptions
    TS_ERROR_DESCRIPTIONS = {
        # Type errors
        "2322": "Type assignment error - value doesn't match the expected type",
        "2345": "Argument type error - argument doesn't match parameter type",
        "2339": "Property does not exist on type - trying to access undefined property",
        "2531": "Object is possibly null - attempting to use an object that might be null",
        "2532": "Object is possibly undefined - accessing properties on potentially undefined object",
        "2307": "Cannot find module - module import failed",
        "2304": "Cannot find name - identifier not found in current scope",
        "2454": "Variable is used before being assigned",
        "2366": "Function lacks return statement and doesn't return void",
        "2362": "Null/undefined is not assignable to this type",
        "2741": "Property is missing in type but required in another type",
        "7006": "Parameter has implicit 'any' type",
        "7031": "Binding element has implicit 'any' type",
        # Syntax errors
        "1005": "Syntax error with unexpected token",
        "1068": "Unexpected token - possible syntax error",
        "1003": "Identifier expected - syntax error in declaration",
        "1136": "Property assignment expected - invalid object literal format",
        # Configuration errors
        "2307": "Cannot find module - module import error or configuration issue",
        "18003": "No inputs were found in config file",
        "5023": "Unknown compiler option",
        # Generic
        "0": "Unknown TypeScript error"
    }
    
    # Common TypeScript error suggestions
    TS_ERROR_SUGGESTIONS = {
        # Type errors
        "2322": [
            "Check the variable type and ensure it matches the declared type",
            "Use type assertion if you're sure about the type (e.g., value as Type)",
            "Create a proper type guard if needed",
            "Modify the variable declaration to match the actual type you're using"
        ],
        "2345": [
            "Verify function parameter types match the function signature",
            "Make sure you're passing the correct arguments to functions",
            "Consider using optional parameters or default values",
            "Look at the function definition to understand expected types"
        ],
        "2339": [
            "Check if the property exists on the object type",
            "Use optional chaining (obj?.prop) for potentially undefined properties",
            "Extend the interface/type to include the property",
            "Use type guards to narrow down the type before accessing properties"
        ],
        "2531": [
            "Add null checks before accessing properties",
            "Use the non-null assertion operator (!) if you're sure it's not null",
            "Use optional chaining (obj?.prop) to safely access properties",
            "Fix the code logic to ensure the object is not null at this point"
        ],
        "2532": [
            "Add undefined checks before accessing properties",
            "Use optional chaining (obj?.prop) for safer property access",
            "Use nullish coalescing operator (??) to provide fallback values",
            "Initialize the variable properly before using it"
        ],
        "2307": [
            "Check if the module is installed (npm install or yarn add)",
            "Verify the import path is correct",
            "Check tsconfig.json for proper module resolution settings",
            "Make sure the module has type definitions (@types/package-name)"
        ],
        "2304": [
            "Import or declare the identifier before using it",
            "Check for typos in the variable or function name",
            "Ensure the variable is in scope where you're trying to use it",
            "If it's a global variable, add appropriate declaration file"
        ],
        "2454": [
            "Initialize the variable before using it",
            "Use definite assignment assertion (variable!: Type) if appropriate",
            "Make sure control flow guarantees assignment before use"
        ],
        # Syntax errors
        "1005": [
            "Check for syntax errors like missing brackets, parentheses, or semicolons",
            "Ensure proper JSX/TSX syntax if using React components",
            "Look for mismatched quotes or template literals"
        ],
        "1068": [
            "Fix the unexpected syntax token",
            "Check for typos or incorrect punctuation",
            "Verify class, function, and object literal syntax"
        ],
        # Configuration errors
        "18003": [
            "Check tsconfig.json for proper 'include' and 'files' settings",
            "Verify file paths in the configuration",
            "Make sure TypeScript files exist at the specified locations"
        ],
        "5023": [
            "Correct the unknown compiler option in tsconfig.json",
            "Check for typos in compiler options",
            "Refer to TypeScript documentation for valid compiler options"
        ]
    }
    
    # Common JavaScript/Runtime error types and their descriptions (for runtime errors)
    RUNTIME_ERROR_DESCRIPTIONS = {
        "TypeError": "Operation on a value of the wrong type",
        "ReferenceError": "Reference to a variable/function that doesn't exist",
        "SyntaxError": "Code contains syntax that cannot be parsed",
        "RangeError": "Numeric value outside of acceptable range",
        "URIError": "Incorrect use of URI functions",
        "EvalError": "Error in the eval() function",
        "InternalError": "Error in the JavaScript engine",
        "Error": "Generic error object"
    }
    
    # Common JavaScript/Runtime error suggestions
    RUNTIME_ERROR_SUGGESTIONS = {
        "TypeError": [
            "Check types before performing operations",
            "Use type guards to ensure variables are of the expected type",
            "Add null/undefined checks before accessing properties",
            "Verify that objects and functions exist before using them"
        ],
        "ReferenceError": [
            "Make sure the variable or function is defined before use",
            "Check for typos in variable/function names",
            "Verify variable scope - it might be defined in a different scope",
            "Check import statements if using modules"
        ],
        "SyntaxError": [
            "Check for syntax errors in your TypeScript code",
            "Verify correct use of TypeScript-specific syntax",
            "Look for mismatched brackets, parentheses, or quotes",
            "Ensure proper use of generics, interfaces, and types"
        ],
        "RangeError": [
            "Check array indices to ensure they're within bounds",
            "Verify numeric parameters are within valid ranges",
            "Check for infinite recursion or excessive loop iterations"
        ]
    }
    
    def __init__(self, log_content: str):
        """Initialize with the content of the error log."""
        self.log_content = log_content
        self.parsed_errors = []
    
    def parse(self) -> List[Dict[str, Any]]:
        """Parse the error log and extract structured information about TypeScript errors."""
        # First try to match TypeScript compiler errors
        compiler_errors = list(self.TS_COMPILER_ERROR_PATTERN.finditer(self.log_content))
        
        if compiler_errors:
            for match in compiler_errors:
                error_code = match.group(1)
                error_message = match.group(2).strip()
                
                # Extract file location information before or after the error message
                # Look in surrounding context (up to 3 lines before and after)
                error_pos = match.start()
                context_start = max(0, error_pos - 200)
                context_end = min(len(self.log_content), error_pos + 200)
                context = self.log_content[context_start:context_end]
                
                file_match = self.TS_FILE_LOCATION_PATTERN.search(context)
                
                file_path = line_num = column_num = None
                if file_match:
                    file_path = file_match.group(1)
                    line_num = int(file_match.group(2)) if file_match.group(2) else None
                    column_num = int(file_match.group(3)) if file_match.group(3) else None
                
                error_info = self._parse_compiler_error(error_code, error_message, file_path, line_num, column_num)
                if error_info:
                    self.parsed_errors.append(error_info)
        
        # Then try to match runtime errors
        runtime_errors = list(self.RUNTIME_ERROR_PATTERN.finditer(self.log_content))
        
        if runtime_errors:
            for match in runtime_errors:
                # Get the start position of this error in the log
                start_pos = match.start()
                
                # Get the next error's start position if any
                next_error_pos = None
                for next_match in runtime_errors:
                    if next_match.start() > start_pos:
                        next_error_pos = next_match.start()
                        break
                
                # Extract the full error including the stack trace
                if next_error_pos:
                    error_text = self.log_content[start_pos:next_error_pos]
                else:
                    error_text = self.log_content[start_pos:]
                
                # Parse this runtime error
                error_info = self._parse_runtime_error(error_text, match.group(1), match.group(2))
                if error_info:
                    self.parsed_errors.append(error_info)
        
        # If no errors found but log contains 'error' and 'TS', try to extract what we can
        if not self.parsed_errors and 'error' in self.log_content.lower() and 'TS' in self.log_content:
            fallback_error = self._parse_unstructured_ts_error()
            if fallback_error:
                self.parsed_errors.append(fallback_error)
        
        return self.parsed_errors
    
    def _parse_compiler_error(self, error_code: str, error_message: str, 
                              file_path: Optional[str], line_num: Optional[int], 
                              column_num: Optional[int]) -> Dict[str, Any]:
        """Parse a TypeScript compiler error and extract its information."""
        # Get error description and suggestions
        error_description = self.TS_ERROR_DESCRIPTIONS.get(error_code, "Unrecognized TypeScript error code")
        suggestions = self.TS_ERROR_SUGGESTIONS.get(error_code, ["No specific suggestions available for this error type"])
        
        # Extract type information if present
        type_info = {}
        type_match = self.TYPE_INFORMATION_PATTERN.search(error_message)
        if type_match:
            type_info["actual_type"] = type_match.group(1)
            type_info["relation"] = type_match.group(2).strip()
            type_info["expected_type"] = type_match.group(3).strip("'") if type_match.group(3) else None
        
        expected_match = self.EXPECTED_TYPE_PATTERN.search(error_message)
        if expected_match and "expected_type" not in type_info:
            type_info["expected_type"] = expected_match.group(1)
        
        # Create stack frames if we have file location
        stack_frames = []
        if file_path:
            stack_frames.append({
                "file": file_path,
                "line": line_num or 0,
                "column": column_num or 0,
                "is_framework_code": False,
                "is_error_location": True
            })
        
        return {
            "error_type": "TSCompilerError",
            "error_code": f"TS{error_code}",
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions,
            "type_info": type_info
        }
    
    def _parse_runtime_error(self, error_text: str, error_type: str, error_message: Optional[str]) -> Dict[str, Any]:
        """Parse a TypeScript runtime error and extract its information."""
        error_type = error_type.strip() if error_type else "UnknownError"
        error_message = error_message.strip() if error_message else ""
        
        # Extract the stack frames
        stack_frames = []
        
        # Try different frame patterns (browser, node)
        frame_matches = list(self.BROWSER_FRAME_PATTERN.finditer(error_text))
        if not frame_matches:
            frame_matches = list(self.NODE_FRAME_PATTERN.finditer(error_text))
        
        for i, frame_match in enumerate(frame_matches):
            function_name, file_path, line_num, col_num = frame_match.groups()
            function_name = function_name.strip() if function_name else "<anonymous>"
            
            # Look for .ts or .tsx files in the path to identify TypeScript source files
            is_ts_source = file_path and (file_path.endswith('.ts') or file_path.endswith('.tsx'))
            
            # Detect if this is likely framework code vs. user code
            is_framework_code = (
                "node_modules" in file_path or
                file_path.startswith("webpack:") or
                file_path.startswith("http://localhost") or
                "vendor" in file_path or
                any(fw in file_path.lower() for fw in [
                    "react", "angular", "vue", "jquery", "lodash", "axios", 
                    "express", "next", "nuxt", "ember"
                ])
            )
            
            # Mark the first user code frame as the error location
            is_error_location = False
            if i == 0 or (not any(frame.get("is_error_location") for frame in stack_frames) and not is_framework_code):
                is_error_location = True
            
            stack_frames.append({
                "function": function_name,
                "file": file_path,
                "line": int(line_num),
                "column": int(col_num),
                "is_framework_code": is_framework_code,
                "is_ts_source": is_ts_source,
                "is_error_location": is_error_location
            })
        
        # Get error description and suggestions
        error_description = self.RUNTIME_ERROR_DESCRIPTIONS.get(error_type, "Unrecognized runtime error type")
        suggestions = self.RUNTIME_ERROR_SUGGESTIONS.get(error_type, ["No specific suggestions available for this error type"])
        
        return {
            "error_type": f"Runtime{error_type}",
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions
        }
    
    def _parse_unstructured_ts_error(self) -> Optional[Dict[str, Any]]:
        """Attempt to extract TypeScript error information from unstructured text."""
        lines = self.log_content.splitlines()
        
        # Look for TS error codes
        ts_code_match = re.search(r'TS(\d+)', self.log_content)
        error_code = ts_code_match.group(1) if ts_code_match else "0000"
        
        # Extract an error message - take the first line that has "error" in it
        error_message = "Unknown TypeScript error"
        for line in lines:
            if 'error' in line.lower() and len(line.strip()) > 10:
                error_message = line.strip()
                break
        
        # Look for file and line information
        file_match = self.TS_FILE_LOCATION_PATTERN.search(self.log_content)
        
        stack_frames = []
        if file_match:
            file_path = file_match.group(1)
            line_num = int(file_match.group(2)) if file_match.group(2) else 0
            column_num = int(file_match.group(3)) if file_match.group(3) else 0
            
            stack_frames.append({
                "file": file_path,
                "line": line_num,
                "column": column_num,
                "is_framework_code": False,
                "is_error_location": True
            })
        
        # Get error description and suggestions
        error_description = self.TS_ERROR_DESCRIPTIONS.get(error_code, "Unrecognized TypeScript error")
        suggestions = self.TS_ERROR_SUGGESTIONS.get(error_code, ["No specific suggestions available for this error type"])
        
        return {
            "error_type": "TSCompilerError",
            "error_code": f"TS{error_code}",
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions,
            "type_info": {}
        }
    
    def summarize(self) -> Dict[str, Any]:
        """Provide a summary of the errors found in the log."""
        if not self.parsed_errors:
            self.parse()
            
        if not self.parsed_errors:
            return {"status": "No TypeScript errors found in the log"}
            
        error_counts = defaultdict(int)
        compiler_error_counts = defaultdict(int)
        runtime_error_counts = defaultdict(int)
        
        for error in self.parsed_errors:
            if error["error_type"] == "TSCompilerError":
                error_counts["TSCompilerError"] += 1
                compiler_error_counts[error["error_code"]] += 1
            else:
                error_counts[error["error_type"]] += 1
                runtime_error_counts[error["error_type"]] += 1
            
        return {
            "status": f"Found {len(self.parsed_errors)} error(s) in the log",
            "error_counts": dict(error_counts),
            "compiler_error_counts": dict(compiler_error_counts),
            "runtime_error_counts": dict(runtime_error_counts),
            "errors": self.parsed_errors
        }
    
    def format_for_llm(self) -> str:
        """Format the parsed errors in a way that's helpful for LLMs."""
        summary = self.summarize()
        
        if summary.get("status") == "No TypeScript errors found in the log":
            return "No TypeScript errors found in the log file."
            
        result = [f"# TypeScript Error Log Analysis\n"]
        result.append(f"Found {len(self.parsed_errors)} error(s) in the log.\n")
        
        # Add error type distribution
        result.append("## Error Distribution")
        for error_type, count in summary["error_counts"].items():
            result.append(f"- {error_type}: {count} occurrence(s)")
        
        # Add compiler error code distribution if any
        if summary["compiler_error_counts"]:
            result.append("\n### TypeScript Compiler Error Codes")
            for error_code, count in summary["compiler_error_counts"].items():
                result.append(f"- {error_code}: {count} occurrence(s)")
        
        result.append("")
        
        # Add detailed analysis of each error
        result.append("## Detailed Error Analysis")
        
        for i, error in enumerate(self.parsed_errors, 1):
            if error["error_type"] == "TSCompilerError":
                result.append(f"\n### Error {i}: TypeScript Compiler Error {error['error_code']}")
                result.append(f"**Message:** {error['message']}")
                result.append(f"**Description:** {error['description']}")
                
                # Add type information if available
                if error["type_info"]:
                    result.append("\n**Type Information:**")
                    if "actual_type" in error["type_info"]:
                        result.append(f"- Actual Type: `{error['type_info']['actual_type']}`")
                    if "expected_type" in error["type_info"]:
                        result.append(f"- Expected Type: `{error['type_info']['expected_type']}`")
                    if "relation" in error["type_info"]:
                        result.append(f"- Issue: {error['type_info']['relation']}")
            else:
                result.append(f"\n### Error {i}: Runtime {error['error_type']}")
                result.append(f"**Message:** {error['message']}")
                result.append(f"**Description:** {error['description']}")
            
            # Add error location
            error_location = next((frame for frame in error["stack_frames"] if frame.get("is_error_location")), None)
            if error_location:
                result.append(f"\n**Error Location:**")
                if "function" in error_location:
                    result.append(f"- Function: {error_location['function']}")
                result.append(f"- File: {error_location['file']}")
                result.append(f"- Line: {error_location['line']}")
                result.append(f"- Column: {error_location['column']}")
                if error_location.get("is_ts_source"):
                    result.append("- *This is a TypeScript source file*")
            
            # Add stack trace (condensed) for runtime errors
            if error["error_type"] != "TSCompilerError" and error["stack_frames"]:
                result.append(f"\n**Stack Trace:**")
                for frame in error["stack_frames"][:5]:  # Show only top 5 frames to keep it manageable
                    is_app_code = not frame.get("is_framework_code", False)
                    result.append(f"- {frame.get('function', '<anonymous>')} ({frame['file']}:{frame['line']}:{frame['column']}) {'[Your Code]' if is_app_code else ''}")
            
            # Add suggestions
            result.append(f"\n**Possible Fixes:**")
            for suggestion in error["suggestions"]:
                result.append(f"- {suggestion}")
        
        return "\n".join(result)
    
    def to_json(self) -> str:
        """Export the parsed errors as JSON."""
        if not self.parsed_errors:
            self.parse()
        return json.dumps(self.summarize(), indent=2)


def analyze_file(file_path: str, format_type: str = "text") -> str:
    """
    Analyze a TypeScript error log file and return formatted results.
    
    Args:
        file_path: Path to the error log file
        format_type: Output format ('text', 'json', or 'llm')
    
    Returns:
        Formatted analysis as a string
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            log_content = f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"
    
    analyzer = TypeScriptErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No TypeScript errors found in the log":
            return "No TypeScript errors found in the log file."
        
        return f"Found {len(analyzer.parsed_errors)} errors in the log file. Use --format json or --format llm for detailed output."


def analyze_text(log_content: str, format_type: str = "llm") -> str:
    """
    Analyze TypeScript error log content provided as a string.
    
    Args:
        log_content: The error log content as a string
        format_type: Output format ('text', 'json', or 'llm')
    
    Returns:
        Formatted analysis as a string
    """
    analyzer = TypeScriptErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No TypeScript errors found in the log":
            return "No TypeScript errors found in the log."
        
        return f"Found {len(analyzer.parsed_errors)} errors in the log. Use format='json' or format='llm' for detailed output."


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TypeScript Error Log Analyzer for LLMs")
    parser.add_argument("file", nargs="?", help="Path to the error log file")
    parser.add_argument("--format", choices=["text", "json", "llm"], default="llm", 
                        help="Output format (default: llm)")
    
    args = parser.parse_args()
    
    if args.file:
        print(analyze_file(args.file, args.format))
    elif not sys.stdin.isatty():
        # Read from stdin if available
        log_content = sys.stdin.read()
        print(analyze_text(log_content, args.format))
    else:
        parser.print_help()


# Example usage:
"""
# As a command-line tool
python typescript_error_analyzer.py error_log.txt --format llm

# As a library
from typescript_error_analyzer import analyze_text

ts_error_log = '''
error TS2322: Type 'string' is not assignable to type 'number'.
  src/components/Counter.tsx:15:10
'''

formatted_analysis = analyze_text(ts_error_log)
print(formatted_analysis)
"""