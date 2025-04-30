#!/usr/bin/env python3
"""
JavaScript Error Log Analyzer for LLMs

This script processes JavaScript error logs and extracts structured information to help
LLMs debug JavaScript problems more effectively. It handles browser console errors,
Node.js errors, framework-specific errors, and provides suggestions for common JS issues.
"""

import re
import json
import sys
import os
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

class JavaScriptErrorLogAnalyzer:
    """Analyzes JavaScript error logs and extracts structured information."""
    
    # Patterns for extracting information from JavaScript error logs
    # Main error pattern - matches common JS error formats
    ERROR_PATTERN = re.compile(
        r'(?:^|\n)(?:Uncaught )?(\w+(?:Error|Exception))(?:: (.+?))?(?=\n\s+at|\n|$)',
        re.MULTILINE | re.DOTALL
    )
    
    # Stack trace patterns - for both browser and Node.js formats
    BROWSER_FRAME_PATTERN = re.compile(r'\s+at\s+(?:(.+?)\s+)?\(?(.+?):(\d+):(\d+)\)?')
    NODE_FRAME_PATTERN = re.compile(r'\s+at\s+(?:(.+?)\s+\()?(.+?):(\d+):(\d+)(?:\))?')
    WEBPACK_FRAME_PATTERN = re.compile(r'\s+at\s+(.+?)\s+\(webpack://(.+?):(\d+):(\d+)\)')
    ANGULAR_FRAME_PATTERN = re.compile(r'\s+at\s+(.+?)\s+\((.+?):(\d+):(\d+)\)')
    
    # Extract info from Chrome/Firefox/Edge console error
    BROWSER_CONSOLE_PATTERN = re.compile(
        r'(?:^|\n)(?:(?:ERROR|EXCEPTION|Uncaught Error|Error):?\s+)(.+?)(?=\n|$)',
        re.MULTILINE
    )
    
    # Extract additional context
    URL_PATTERN = re.compile(r'(?:URL|url|href):\s*\'?\"?([^\'\"]+)\'?\"?')
    LINE_COL_PATTERN = re.compile(r'line\s+(\d+)(?:\s*,\s*column\s+(\d+))?')
    
    # Common JavaScript error types and their descriptions
    ERROR_DESCRIPTIONS = {
        "SyntaxError": "Code contains syntax that JavaScript cannot parse",
        "ReferenceError": "Reference to a variable/function that doesn't exist",
        "TypeError": "Operation on a value of the wrong type",
        "RangeError": "Numeric value outside of acceptable range",
        "URIError": "Incorrect use of URI functions",
        "EvalError": "Error in the eval() function",
        "InternalError": "Error in the JavaScript engine",
        "AggregateError": "Multiple errors wrapped in a single error",
        "Error": "Generic error object",
        "DOMException": "Error with a DOM operation",
        "NetworkError": "Error with network requests",
        "AbortError": "Operation was aborted",
        "TimeoutError": "Operation timed out",
        "SecurityError": "Operation violates security restrictions",
        "InvalidStateError": "Object is in an invalid state for the operation",
        "NotFoundError": "Requested resource not found",
        "NotSupportedError": "Operation not supported",
        "NotAllowedError": "Operation not allowed in this context",
        "QuotaExceededError": "Storage quota exceeded",
        "UnknownError": "Error with unknown cause"
    }
    
    # Common JavaScript error suggestions
    ERROR_SUGGESTIONS = {
        "SyntaxError": [
            "Check for missing or mismatched parentheses, brackets, or braces",
            "Verify proper use of semicolons",
            "Look for invalid variable names or reserved keywords",
            "Ensure proper use of template literals and string quotes",
            "Check for typos in JavaScript syntax"
        ],
        "ReferenceError": [
            "Make sure the variable or function is defined before use",
            "Check for typos in variable/function names",
            "Verify variable scope - it might be defined in a different scope",
            "Check import statements if using modules",
            "Ensure the referenced library or script is loaded"
        ],
        "TypeError": [
            "Verify the type of value before performing operations",
            "Check if a variable is null or undefined before accessing properties",
            "Use typeof or instanceof to verify types",
            "Ensure functions are called with the correct argument types",
            "Check if you're trying to use an array method on a non-array"
        ],
        "RangeError": [
            "Check array indices to ensure they're within bounds",
            "Verify numeric parameters are within valid ranges",
            "Check for infinite recursion or excessive loop iterations",
            "Ensure JSON.stringify doesn't have circular references"
        ],
        "URIError": [
            "Check encodings in URI functions like encodeURI() or decodeURI()",
            "Ensure URI components are properly escaped",
            "Verify URL parameters are correctly formatted"
        ],
        "NetworkError": [
            "Check network connectivity",
            "Verify the URL is correct and accessible",
            "Check for CORS issues if making cross-origin requests",
            "Ensure proper credentials are provided if required",
            "Verify API keys or authentication tokens"
        ],
        "SecurityError": [
            "Ensure the script has necessary permissions",
            "Check Content Security Policy (CSP) headers",
            "Verify same-origin policy compliance",
            "Check if using secure context (HTTPS) when required"
        ],
        "DOMException": [
            "Verify DOM elements exist before manipulating them",
            "Check if trying to modify read-only properties",
            "Ensure proper event handling and delegation",
            "Verify HTML element IDs and selectors"
        ],
        "Error": [
            "Look for more specific error information in the message",
            "Check custom throw statements in the code",
            "Look for framework-specific error details",
            "Review application logic for unexpected conditions"
        ]
    }
    
    def __init__(self, log_content: str):
        """Initialize with the content of the error log."""
        self.log_content = log_content
        self.parsed_errors = []
    
    def parse(self) -> List[Dict[str, Any]]:
        """Parse the error log and extract structured information about JavaScript errors."""
        # First try to match standard error patterns
        error_matches = list(self.ERROR_PATTERN.finditer(self.log_content))
        
        if not error_matches:
            # Try console error patterns if no standard errors found
            console_matches = list(self.BROWSER_CONSOLE_PATTERN.finditer(self.log_content))
            if console_matches:
                for match in console_matches:
                    error_info = self._parse_console_error(match.group(1))
                    if error_info:
                        self.parsed_errors.append(error_info)
            else:
                # Check for any text that might contain error information
                if any(err_type in self.log_content for err_type in ["Error", "Exception", "TypeError", "SyntaxError", "ReferenceError"]):
                    fallback_error = self._parse_unstructured_error()
                    if fallback_error:
                        self.parsed_errors.append(fallback_error)
        else:
            for match in error_matches:
                # Get the start position of this error in the log
                start_pos = match.start()
                
                # Get the next error's start position if any
                next_error_pos = None
                for next_match in error_matches:
                    if next_match.start() > start_pos:
                        next_error_pos = next_match.start()
                        break
                
                # Extract the full error including the stack trace
                if next_error_pos:
                    error_text = self.log_content[start_pos:next_error_pos]
                else:
                    error_text = self.log_content[start_pos:]
                
                # Parse this error
                error_info = self._parse_error(error_text, match.group(1), match.group(2))
                if error_info:
                    self.parsed_errors.append(error_info)
        
        return self.parsed_errors
    
    def _parse_error(self, error_text: str, error_type: str, error_message: Optional[str]) -> Dict[str, Any]:
        """Parse a single JavaScript error and extract its information."""
        error_type = error_type.strip() if error_type else "UnknownError"
        error_message = error_message.strip() if error_message else ""
        
        # Extract the stack frames
        stack_frames = []
        
        # Try different frame patterns (browser, node, webpack, angular)
        frame_matches = list(self.BROWSER_FRAME_PATTERN.finditer(error_text))
        if not frame_matches:
            frame_matches = list(self.NODE_FRAME_PATTERN.finditer(error_text))
        if not frame_matches:
            frame_matches = list(self.WEBPACK_FRAME_PATTERN.finditer(error_text))
        if not frame_matches:
            frame_matches = list(self.ANGULAR_FRAME_PATTERN.finditer(error_text))
        
        for i, frame_match in enumerate(frame_matches):
            function_name, file_path, line_num, col_num = frame_match.groups()
            function_name = function_name.strip() if function_name else "<anonymous>"
            
            # Detect if this is likely framework code vs. user code
            is_framework_code = (
                "node_modules" in file_path or
                "webpack:" in file_path or
                file_path.startswith("http://localhost") or
                "vendor" in file_path or
                file_path.startswith("/") or
                any(fw in file_path.lower() for fw in [
                    "react", "angular", "vue", "jquery", "lodash", "axios", "express", 
                    "next", "nuxt", "ember", "backbone", "three.js", "d3", "bootstrap"
                ])
            )
            
            # Mark the first frame as the error location
            is_error_location = (i == 0)
            
            stack_frames.append({
                "function": function_name,
                "file": file_path,
                "line": int(line_num),
                "column": int(col_num),
                "is_framework_code": is_framework_code,
                "is_error_location": is_error_location
            })
        
        # Extract additional context that might be in the error text
        url_match = self.URL_PATTERN.search(error_text)
        url = url_match.group(1) if url_match else None
        
        # Get error description and suggestions
        error_description = self.ERROR_DESCRIPTIONS.get(error_type, "Unrecognized JavaScript error type")
        suggestions = self.ERROR_SUGGESTIONS.get(error_type, ["No specific suggestions available for this error type"])
        
        return {
            "error_type": error_type,
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions,
            "url": url
        }
    
    def _parse_console_error(self, error_text: str) -> Dict[str, Any]:
        """Parse an error from browser console logs that may not have a stack trace."""
        # Try to extract error type from the message
        error_type = "UnknownError"
        error_message = error_text.strip()
        
        # Look for common error types in the message
        for known_type in self.ERROR_DESCRIPTIONS.keys():
            if known_type in error_message:
                error_type = known_type
                error_message = error_message.replace(known_type + ":", "").strip()
                break
        
        # Try to extract URL if present
        url_match = self.URL_PATTERN.search(error_text)
        url = url_match.group(1) if url_match else None
        
        # Try to extract line and column
        line_col_match = self.LINE_COL_PATTERN.search(error_text)
        line = int(line_col_match.group(1)) if line_col_match else None
        column = int(line_col_match.group(2)) if line_col_match and line_col_match.group(2) else None
        
        # Create a single stack frame if we have line/column info
        stack_frames = []
        if line is not None:
            stack_frames.append({
                "function": "<anonymous>",
                "file": url or "unknown",
                "line": line,
                "column": column or 0,
                "is_framework_code": False,
                "is_error_location": True
            })
        
        # Get error description and suggestions
        error_description = self.ERROR_DESCRIPTIONS.get(error_type, "Unrecognized JavaScript error type")
        suggestions = self.ERROR_SUGGESTIONS.get(error_type, ["No specific suggestions available for this error type"])
        
        return {
            "error_type": error_type,
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions,
            "url": url
        }
    
    def _parse_unstructured_error(self) -> Optional[Dict[str, Any]]:
        """Attempt to extract error information from unstructured text."""
        lines = self.log_content.splitlines()
        
        error_type = "UnknownError"
        error_message = lines[0] if lines else "Unknown error"
        
        # Try to identify error type from common keywords
        for known_type in self.ERROR_DESCRIPTIONS.keys():
            if known_type in self.log_content:
                error_type = known_type
                # Extract message near the error type mention
                pattern = re.compile(f"{re.escape(known_type)}:?\\s*(.+?)(?:\\n|$)")
                match = pattern.search(self.log_content)
                if match:
                    error_message = match.group(1).strip()
                break
        
        # Look for file and line information
        file_pattern = re.compile(r'(?:in|at|file)\s+[\'"]?([^\'"\s:]+)[\'"]?(?::(\d+))?(?::(\d+))?')
        file_match = file_pattern.search(self.log_content)
        
        stack_frames = []
        if file_match:
            file_path = file_match.group(1)
            line = int(file_match.group(2)) if file_match.group(2) else None
            column = int(file_match.group(3)) if file_match.group(3) else None
            
            if line:
                stack_frames.append({
                    "function": "<anonymous>",
                    "file": file_path,
                    "line": line,
                    "column": column or 0,
                    "is_framework_code": False,
                    "is_error_location": True
                })
        
        # Get error description and suggestions
        error_description = self.ERROR_DESCRIPTIONS.get(error_type, "Unrecognized JavaScript error type")
        suggestions = self.ERROR_SUGGESTIONS.get(error_type, ["No specific suggestions available for this error type"])
        
        return {
            "error_type": error_type,
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions,
            "url": None
        }
    
    def summarize(self) -> Dict[str, Any]:
        """Provide a summary of the errors found in the log."""
        if not self.parsed_errors:
            self.parse()
            
        if not self.parsed_errors:
            return {"status": "No JavaScript errors found in the log"}
            
        error_counts = defaultdict(int)
        for error in self.parsed_errors:
            error_counts[error["error_type"]] += 1
            
        return {
            "status": f"Found {len(self.parsed_errors)} error(s) in the log",
            "error_counts": dict(error_counts),
            "errors": self.parsed_errors
        }
    
    def format_for_llm(self) -> str:
        """Format the parsed errors in a way that's helpful for LLMs."""
        summary = self.summarize()
        
        if summary.get("status") == "No JavaScript errors found in the log":
            return "No JavaScript errors found in the log file."
            
        result = [f"# JavaScript Error Log Analysis\n"]
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
            
            if error.get("url"):
                result.append(f"**URL:** {error['url']}")
            
            # Add error location
            error_location = next((frame for frame in error["stack_frames"] if frame.get("is_error_location")), None)
            if error_location:
                result.append(f"\n**Error Location:**")
                result.append(f"- Function: {error_location['function']}")
                result.append(f"- File: {error_location['file']}")
                result.append(f"- Line: {error_location['line']}")
                result.append(f"- Column: {error_location['column']}")
            
            # Add stack trace (condensed)
            if error["stack_frames"]:
                result.append(f"\n**Stack Trace:**")
                for frame in error["stack_frames"][:5]:  # Show only top 5 frames to keep it manageable
                    is_app_code = not frame["is_framework_code"]
                    result.append(f"- {frame['function']} ({frame['file']}:{frame['line']}:{frame['column']}) {'[Your Code]' if is_app_code else ''}")
            
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
    Analyze a JavaScript error log file and return formatted results.
    
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
    
    analyzer = JavaScriptErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No JavaScript errors found in the log":
            return "No JavaScript errors found in the log file."
        
        return f"Found {len(analyzer.parsed_errors)} errors in the log file. Use --format json or --format llm for detailed output."


def analyze_text(log_content: str, format_type: str = "llm") -> str:
    """
    Analyze JavaScript error log content provided as a string.
    
    Args:
        log_content: The error log content as a string
        format_type: Output format ('text', 'json', or 'llm')
    
    Returns:
        Formatted analysis as a string
    """
    analyzer = JavaScriptErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No JavaScript errors found in the log":
            return "No JavaScript errors found in the log."
        
        return f"Found {len(analyzer.parsed_errors)} errors in the log. Use format='json' or format='llm' for detailed output."


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="JavaScript Error Log Analyzer for LLMs")
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
python javascript_error_analyzer.py error_log.txt --format llm

# As a library
from javascript_error_analyzer import analyze_text

js_error_log = '''
Uncaught TypeError: Cannot read property 'length' of undefined
    at processData (app.js:42:25)
    at handleClick (app.js:15:10)
    at HTMLButtonElement.onclick (index.html:27:21)
'''

formatted_analysis = analyze_text(js_error_log)
print(formatted_analysis)
"""