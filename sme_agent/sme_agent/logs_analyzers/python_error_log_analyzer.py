#!/usr/bin/env python3
"""
Python Error Log Analyzer for LLMs

This script processes Python error logs and extracts structured information to help
LLMs debug problems more effectively. It handles multiple error tracebacks in a single log,
extracts code context, categorizes errors, and provides suggestions for common error types.
"""

import re
import json
import sys
import os
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

class ErrorLogAnalyzer:
    """Analyzes Python error logs and extracts structured information."""
    
    # Patterns for extracting information from error logs
    TRACEBACK_PATTERN = re.compile(r'Traceback \(most recent call last\):(?:.+?)(?:^\w+(?:Error|Exception|Warning).*?)(?=\n\s*Traceback|\Z)', 
                                   re.MULTILINE | re.DOTALL)
    ERROR_LINE_PATTERN = re.compile(r'^(\w+(?:Error|Exception|Warning)[^:\n]*)(:.+)?$', re.MULTILINE)
    FILE_LINE_PATTERN = re.compile(r'  File "([^"]+)", line (\d+), in (.+)')
    CODE_LINE_PATTERN = re.compile(r'    (.+)')
    
    # Common error types and their descriptions
    ERROR_DESCRIPTIONS = {
        "SyntaxError": "Code contains syntax that Python cannot parse",
        "NameError": "Using a variable or function name that hasn't been defined",
        "TypeError": "Operation applied to inappropriate type or function called with wrong type of arguments",
        "ValueError": "Function receives an argument of the right type but inappropriate value",
        "IndexError": "Trying to access an index that doesn't exist in a sequence",
        "KeyError": "Trying to access a key that doesn't exist in a dictionary",
        "AttributeError": "Trying to access an attribute that doesn't exist on an object",
        "ImportError": "Unable to import a module",
        "ModuleNotFoundError": "Module not found when importing",
        "FileNotFoundError": "Attempting to open a file that doesn't exist",
        "ZeroDivisionError": "Attempting to divide by zero",
        "RuntimeError": "Error that occurs during program execution",
        "PermissionError": "Lack of permissions to perform an operation",
        "MemoryError": "Running out of memory",
        "RecursionError": "Maximum recursion depth exceeded"
    }
    
    # Common error causes and potential fixes
    ERROR_SUGGESTIONS = {
        "SyntaxError": [
            "Check for missing or extra parentheses, brackets, or braces",
            "Verify indentation is consistent",
            "Look for missing colons after if/for/while statements",
            "Check for invalid character encodings"
        ],
        "NameError": [
            "Check for typos in variable or function names",
            "Make sure the variable is defined before it's used",
            "Verify the variable is in scope where it's being used",
            "Check if you need to import a module"
        ],
        "TypeError": [
            "Verify the types of operands in expressions",
            "Check function parameters match expected types",
            "Consider using type conversion functions",
            "Use isinstance() to check object types if needed"
        ],
        "ValueError": [
            "Validate input data before processing",
            "Check format of strings passed to conversion functions",
            "Verify numeric values are in expected ranges"
        ],
        "IndexError": [
            "Check array/list indices against their lengths",
            "Verify loops that access elements don't exceed bounds",
            "Use appropriate conditional checks before accessing elements"
        ],
        "KeyError": [
            "Use dict.get(key, default) instead of dict[key] when appropriate",
            "Check if keys exist with 'key in dict' before accessing",
            "Verify dictionary keys are what you expect"
        ],
        "AttributeError": [
            "Check for typos in attribute names",
            "Verify object type to ensure it has the expected attributes",
            "Check if the object is properly initialized"
        ],
        "ImportError": [
            "Verify the module is installed (pip list)",
            "Check if the module name is spelled correctly",
            "Make sure you're importing from the correct path or package"
        ],
        "ModuleNotFoundError": [
            "Install the missing module with pip",
            "Check your Python environment/virtual environment",
            "Verify the module name spelling"
        ],
        "FileNotFoundError": [
            "Verify file path is correct and file exists",
            "Check working directory with os.getcwd()",
            "Use absolute paths instead of relative paths if necessary"
        ],
        "ZeroDivisionError": [
            "Add conditional checks before division operations",
            "Use try/except to handle potential division by zero",
            "Validate denominator values"
        ]
    }
    
    def __init__(self, log_content: str):
        """Initialize with the content of the error log."""
        self.log_content = log_content
        self.parsed_errors = []
    
    def parse(self) -> List[Dict[str, Any]]:
        """Parse the error log and extract structured information about errors."""
        # Find all tracebacks in the log
        tracebacks = self.TRACEBACK_PATTERN.findall(self.log_content)
        
        if not tracebacks:
            # Try to handle logs that might not match the traceback pattern exactly
            if "Error" in self.log_content or "Exception" in self.log_content:
                tracebacks = [self.log_content]
            else:
                return []
        
        for traceback_text in tracebacks:
            error_info = self._parse_traceback(traceback_text)
            if error_info:
                self.parsed_errors.append(error_info)
                
        return self.parsed_errors
    
    def _parse_traceback(self, traceback_text: str) -> Optional[Dict[str, Any]]:
        """Parse a single traceback and extract its information."""
        # Extract error type and message
        error_match = self.ERROR_LINE_PATTERN.search(traceback_text)
        if not error_match:
            return None
            
        error_type = error_match.group(1).strip()
        error_message = error_match.group(2).strip(': \n') if error_match.group(2) else ""
        
        # Extract the error class (without additional qualifiers)
        error_class = error_type.split('.')[-1]
        
        # Extract stack frames
        stack_frames = []
        file_matches = self.FILE_LINE_PATTERN.findall(traceback_text)
        
        # Split the traceback into lines for better parsing
        lines = traceback_text.split('\n')
        current_frame = None
        code_lines = []
        highlighting_lines = []
        
        for line in lines:
            # Check if this is a file line
            file_match = self.FILE_LINE_PATTERN.match(line)
            if file_match:
                # If we have a previous frame, add it with its code
                if current_frame:
                    current_frame['code'] = '\n'.join(code_lines) if code_lines else None
                    current_frame['highlighting'] = '\n'.join(highlighting_lines) if highlighting_lines else None
                    stack_frames.append(current_frame)
                    code_lines = []
                    highlighting_lines = []
                
                # Start new frame
                current_frame = {
                    "file": file_match.group(1),
                    "line": int(file_match.group(2)),
                    "function": file_match.group(3),
                    "is_error_location": False
                }
            # Check if this is a code line (starts with 4 spaces)
            elif line.startswith('    ') and current_frame:
                # Check if this line contains only highlighting (carets or other indicators)
                if all(c in '^~* ' for c in line[4:]):
                    highlighting_lines.append(line[4:])
                else:
                    code_lines.append(line[4:])
        
        # Add the last frame if exists
        if current_frame:
            current_frame['code'] = '\n'.join(code_lines) if code_lines else None
            current_frame['highlighting'] = '\n'.join(highlighting_lines) if highlighting_lines else None
            stack_frames.append(current_frame)
        
        # Mark the last frame as error location
        if stack_frames:
            stack_frames[-1]['is_error_location'] = True
        
        # Get error description and suggestions
        error_description = self.ERROR_DESCRIPTIONS.get(error_class, "Unrecognized error type")
        suggestions = self.ERROR_SUGGESTIONS.get(error_class, ["No specific suggestions available for this error type"])
        
        return {
            "error_type": error_type,
            "error_class": error_class,
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions
        }
    
    def summarize(self) -> Dict[str, Any]:
        """Provide a summary of the errors found in the log."""
        if not self.parsed_errors:
            self.parse()
            
        if not self.parsed_errors:
            return {"status": "No Python errors found in the log"}
            
        error_counts = defaultdict(int)
        for error in self.parsed_errors:
            error_counts[error["error_class"]] += 1
            
        return {
            "status": f"Found {len(self.parsed_errors)} error(s) in the log",
            "error_counts": dict(error_counts),
            "errors": self.parsed_errors
        }
    
    def format_for_llm(self) -> str:
        """Format the parsed errors in a way that's helpful for LLMs."""
        summary = self.summarize()
        
        if summary.get("status") == "No Python errors found in the log":
            return "No Python errors found in the log file."
            
        result = [f"# Python Error Log Analysis\n"]
        result.append(f"Found {len(self.parsed_errors)} error(s) in the log.\n")
        
        # Add error type distribution
        result.append("## Error Distribution")
        for error_type, count in summary["error_counts"].items():
            result.append(f"- {error_type}: {count} occurrence(s)")
        result.append("")
        
        # Add detailed analysis of each error
        result.append("## Detailed Error Analysis")
        
        for i, error in enumerate(self.parsed_errors, 1):
            result.append(f"\n### Error {i}: {error['error_type']}")
            result.append(f"**Message:** {error['message']}")
            result.append(f"**Description:** {error['description']}")
            
            # Add error location
            error_location = next((frame for frame in error["stack_frames"] if frame["is_error_location"]), None)
            if error_location:
                result.append(f"\n**Error Location:**")
                result.append(f"- File: {error_location['file']}")
                result.append(f"- Line: {error_location['line']}")
                result.append(f"- Function: {error_location['function']}")
                if error_location["code"]:
                    result.append(f"- Code: `{error_location['code']}`")
            
            # Add stack trace (condensed)
            result.append(f"\n**Stack Trace (most recent call last):**")
            for frame in reversed(error["stack_frames"]):
                result.append(f"- {frame['file']}:{frame['line']} in {frame['function']}")
                if frame["code"]:
                    result.append(f"  Code: `{frame['code']}`")
            
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
    Analyze a Python error log file and return formatted results.
    
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
    
    analyzer = ErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No Python errors found in the log":
            return "No Python errors found in the log file."
        
        return f"Found {len(analyzer.parsed_errors)} errors in the log file. Use --format json or --format llm for detailed output."


def analyze_text(log_content: str, format_type: str = "llm") -> str:
    """
    Analyze Python error log content provided as a string.
    
    Args:
        log_content: The error log content as a string
        format_type: Output format ('text', 'json', or 'llm')
    
    Returns:
        Formatted analysis as a string
    """
    analyzer = ErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No Python errors found in the log":
            return "No Python errors found in the log."
        
        return f"Found {len(analyzer.parsed_errors)} errors in the log. Use format='json' or format='llm' for detailed output."


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Python Error Log Analyzer for LLMs")
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
python error_analyzer.py error_log.txt --format llm

# As a library
from error_analyzer import analyze_text

error_log = '''
Traceback (most recent call last):
  File "app.py", line 25, in process_data
    result = calculate_total(data)
  File "app.py", line 10, in calculate_total
    return sum(values) / len(values)
ZeroDivisionError: division by zero
'''

formatted_analysis = analyze_text(error_log)
print(formatted_analysis)
"""