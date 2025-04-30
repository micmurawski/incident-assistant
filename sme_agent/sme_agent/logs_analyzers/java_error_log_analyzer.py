#!/usr/bin/env python3
"""
Java Error Log Analyzer for LLMs

This script processes Java exception stack traces and extracts structured information to help
LLMs debug Java problems more effectively. It handles multiple exceptions in a single log,
extracts cause chains, and provides suggestions for common Java errors.
"""

import re
import json
import sys
import os
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

class JavaErrorLogAnalyzer:
    """Analyzes Java error logs and extracts structured information."""
    
    # Patterns for extracting information from Java stack traces
    EXCEPTION_PATTERN = re.compile(
        r'(?:^|\n)(\w+(?:\.\w+)*(?:Exception|Error|Throwable)(?::|$))(?:\s*(.+?))?(?=\n\s+at|\n\s*Caused by:|\Z)',
        re.MULTILINE | re.DOTALL
    )
    FRAME_PATTERN = re.compile(r'\s+at\s+([^\(]+)\(([^:]+):(\d+)\)')
    CAUSED_BY_PATTERN = re.compile(
        r'Caused by:\s+(\w+(?:\.\w+)*(?:Exception|Error|Throwable))(?::\s*(.+?))?(?=\n\s+at|\n\s*Caused by:|\Z)',
        re.MULTILINE | re.DOTALL
    )
    SUPPRESSED_PATTERN = re.compile(
        r'Suppressed:\s+(\w+(?:\.\w+)*(?:Exception|Error|Throwable))(?::\s*(.+?))?(?=\n\s+at|\n\s*Caused by:|\Z)',
        re.MULTILINE | re.DOTALL
    )
    
    # Common Java exception types and their descriptions
    EXCEPTION_DESCRIPTIONS = {
        "NullPointerException": "Attempt to access or modify a null object reference",
        "ArrayIndexOutOfBoundsException": "Attempt to access an array element with an invalid index",
        "ClassCastException": "Attempt to cast an object to an incompatible class type",
        "IllegalArgumentException": "Method received an argument that's inappropriate",
        "IllegalStateException": "Method was invoked at an inappropriate time or the object is in an inappropriate state",
        "NoSuchMethodException": "Method doesn't exist in the specified class",
        "IndexOutOfBoundsException": "Index is out of range for a list, string, or array",
        "ConcurrentModificationException": "Object was modified during iteration",
        "SQLException": "Error accessing a database",
        "IOException": "Error during I/O operations",
        "FileNotFoundException": "Attempt to access a file that doesn't exist",
        "ClassNotFoundException": "JVM can't find a class during runtime that was available during compile time",
        "NoClassDefFoundError": "JVM can't find the class definition during runtime",
        "OutOfMemoryError": "Java Virtual Machine ran out of memory",
        "StackOverflowError": "Stack overflow occurred (often due to infinite recursion)",
        "NumberFormatException": "Attempt to convert a string to a numeric type failed",
        "ArithmeticException": "Arithmetic error, such as division by zero",
        "InterruptedException": "Thread was interrupted during execution",
        "UnsupportedOperationException": "Operation is not supported",
        "RuntimeException": "General runtime exception"
    }
    
    # Common Java exception suggestions
    EXCEPTION_SUGGESTIONS = {
        "NullPointerException": [
            "Add null checks before accessing object references",
            "Use Optional<T> to handle nullable values",
            "Look for uninitialized variables or fields",
            "Check if method calls return null under certain conditions"
        ],
        "ArrayIndexOutOfBoundsException": [
            "Verify array indices are within bounds before access",
            "Check loop conditions to ensure they don't exceed array length",
            "Use Collections like ArrayList that can dynamically resize",
            "Consider using array.length to validate indices"
        ],
        "ClassCastException": [
            "Verify the object type before casting using instanceof",
            "Review the class hierarchy to ensure proper inheritance",
            "Check generic types and ensure type safety",
            "Be careful with type erasure in generics"
        ],
        "IllegalArgumentException": [
            "Add parameter validation at the start of methods",
            "Check API documentation for expected parameter values",
            "Use Objects.requireNonNull() for required parameters",
            "Use validation frameworks like Jakarta Bean Validation"
        ],
        "IllegalStateException": [
            "Ensure proper object initialization before method calls",
            "Check object lifecycle and state transitions",
            "Verify preconditions for methods are met",
            "Consider implementing a state machine for complex objects"
        ],
        "NoSuchMethodException": [
            "Check method name and signature for typos",
            "Verify the method exists in the target class",
            "Check for method accessibility (public, private, etc.)",
            "Consider version conflicts between compiled code and runtime libraries"
        ],
        "ConcurrentModificationException": [
            "Use ConcurrentHashMap or CopyOnWriteArrayList for concurrent access",
            "Use Iterator's remove() method instead of Collection's remove()",
            "Create a copy of the collection before iteration if modifications are needed",
            "Use Java 8 streams with proper parallel processing"
        ],
        "SQLException": [
            "Check database connection parameters",
            "Verify SQL syntax and table/column names",
            "Ensure proper resource handling with try-with-resources",
            "Check for database-specific error codes",
            "Use prepared statements to prevent SQL injection"
        ],
        "IOException": [
            "Verify file paths and permissions",
            "Check if resources are closed properly (use try-with-resources)",
            "Handle network connectivity issues",
            "Implement retry mechanisms for transient failures"
        ],
        "FileNotFoundException": [
            "Verify the file path is correct",
            "Check if the file exists before accessing it",
            "Ensure the application has proper permissions to access the file",
            "Consider using Files.exists() to check file existence"
        ],
        "ClassNotFoundException": [
            "Check the classpath configuration",
            "Verify JAR files contain the required classes",
            "Ensure dependencies are correctly defined in build tools",
            "Check for version conflicts in dependencies"
        ],
        "NoClassDefFoundError": [
            "Check for errors during class initialization",
            "Verify all required classes are available at runtime",
            "Look for version incompatibilities between JARs",
            "Check for static initializer errors"
        ],
        "OutOfMemoryError": [
            "Increase heap size with -Xmx JVM option",
            "Look for memory leaks (tools: JVisualVM, MAT)",
            "Review object lifecycle management",
            "Consider weak references for caching",
            "Use memory-efficient data structures"
        ],
        "StackOverflowError": [
            "Check for infinite recursion",
            "Increase stack size with -Xss JVM option",
            "Consider iterative approach instead of recursion",
            "Add base cases to recursive methods"
        ]
    }
    
    def __init__(self, log_content: str):
        """Initialize with the content of the error log."""
        self.log_content = log_content
        self.parsed_errors = []
    
    def parse(self) -> List[Dict[str, Any]]:
        """Parse the error log and extract structured information about Java exceptions."""
        # Find all exceptions in the log
        exception_matches = list(self.EXCEPTION_PATTERN.finditer(self.log_content))
        
        if not exception_matches:
            # Try to handle logs that might not match the pattern exactly
            if "Exception" in self.log_content or "Error" in self.log_content:
                # Try a more lenient approach for less standard logs
                return self._parse_non_standard_log()
            else:
                return []
        
        for match in exception_matches:
            # Get the start position of this exception in the log
            start_pos = match.start()
            
            # Get the next exception's start position if any
            next_exception_pos = None
            for next_match in exception_matches:
                if next_match.start() > start_pos:
                    next_exception_pos = next_match.start()
                    break
            
            # Extract the full exception including the stack trace
            if next_exception_pos:
                exception_text = self.log_content[start_pos:next_exception_pos]
            else:
                exception_text = self.log_content[start_pos:]
            
            # Parse this exception
            error_info = self._parse_exception(exception_text)
            if error_info:
                self.parsed_errors.append(error_info)
        
        return self.parsed_errors
    
    def _parse_non_standard_log(self) -> List[Dict[str, Any]]:
        """Handle logs that don't match the standard exception pattern."""
        # Look for lines that might contain exception names
        exception_lines = re.finditer(r'(?:^|\n)([\w.]+(?:Exception|Error|Throwable))', self.log_content)
        
        for match in exception_lines:
            exception_name = match.group(1)
            if exception_name in self.EXCEPTION_DESCRIPTIONS or "Exception" in exception_name or "Error" in exception_name:
                error_type = exception_name
                error_class = error_type.split('.')[-1]
                
                # Try to find a message associated with this exception
                message_match = re.search(exception_name + r'[:\s]+(.+)(?:\n|$)', self.log_content)
                message = message_match.group(1).strip() if message_match else ""
                
                # Create a basic error info without stack frames
                error_description = self.EXCEPTION_DESCRIPTIONS.get(error_class, "Unrecognized Java exception type")
                suggestions = self.EXCEPTION_SUGGESTIONS.get(error_class, ["No specific suggestions available for this exception type"])
                
                self.parsed_errors.append({
                    "error_type": error_type,
                    "error_class": error_class,
                    "message": message,
                    "stack_frames": [],
                    "description": error_description,
                    "suggestions": suggestions,
                    "caused_by": None
                })
        
        return self.parsed_errors
    
    def _parse_exception(self, exception_text: str) -> Optional[Dict[str, Any]]:
        """Parse a single Java exception and extract its information."""
        # Extract exception type and message
        exception_match = self.EXCEPTION_PATTERN.search(exception_text)
        if not exception_match:
            return None
        
        error_type = exception_match.group(1).strip()
        error_message = exception_match.group(2).strip() if exception_match.group(2) else ""
        
        # Extract the error class (without package)
        error_class = error_type.split('.')[-1]
        
        # Extract stack frames
        stack_frames = []
        for i, frame_match in enumerate(self.FRAME_PATTERN.finditer(exception_text)):
            method, file_path, line_num = frame_match.groups()
            stack_frames.append({
                "method": method.strip(),
                "file": file_path.strip(),
                "line": int(line_num),
                "is_application_code": not (
                    method.startswith("java.") or 
                    method.startswith("javax.") or 
                    method.startswith("sun.") or 
                    method.startswith("com.sun.") or
                    method.startswith("org.apache.") or
                    method.startswith("org.springframework.")
                ),
                "is_error_location": i == 0  # First frame is the error location
            })
        
        # Extract "Caused by" exceptions (if any)
        caused_by = None
        caused_by_match = self.CAUSED_BY_PATTERN.search(exception_text)
        if caused_by_match:
            caused_by_type = caused_by_match.group(1).strip()
            caused_by_message = caused_by_match.group(2).strip() if caused_by_match.group(2) else ""
            caused_by_class = caused_by_type.split('.')[-1]
            
            # Extract the stack frames for the "Caused by" exception
            caused_by_frames = []
            caused_by_text = exception_text[caused_by_match.start():]
            for i, frame_match in enumerate(self.FRAME_PATTERN.finditer(caused_by_text)):
                method, file_path, line_num = frame_match.groups()
                caused_by_frames.append({
                    "method": method.strip(),
                    "file": file_path.strip(),
                    "line": int(line_num),
                    "is_application_code": not (
                        method.startswith("java.") or 
                        method.startswith("javax.") or 
                        method.startswith("sun.") or 
                        method.startswith("com.sun.") or
                        method.startswith("org.apache.") or
                        method.startswith("org.springframework.")
                    ),
                    "is_error_location": i == 0  # First frame is the error location
                })
            
            caused_by_description = self.EXCEPTION_DESCRIPTIONS.get(caused_by_class, 
                                                                  "Unrecognized Java exception type")
            caused_by_suggestions = self.EXCEPTION_SUGGESTIONS.get(caused_by_class, 
                                                                 ["No specific suggestions available for this exception type"])
            
            caused_by = {
                "error_type": caused_by_type,
                "error_class": caused_by_class,
                "message": caused_by_message,
                "stack_frames": caused_by_frames,
                "description": caused_by_description,
                "suggestions": caused_by_suggestions
            }
        
        # Get error description and suggestions
        error_description = self.EXCEPTION_DESCRIPTIONS.get(error_class, "Unrecognized Java exception type")
        suggestions = self.EXCEPTION_SUGGESTIONS.get(error_class, ["No specific suggestions available for this exception type"])
        
        return {
            "error_type": error_type,
            "error_class": error_class,
            "message": error_message,
            "stack_frames": stack_frames,
            "description": error_description,
            "suggestions": suggestions,
            "caused_by": caused_by
        }
    
    def summarize(self) -> Dict[str, Any]:
        """Provide a summary of the errors found in the log."""
        if not self.parsed_errors:
            self.parse()
            
        if not self.parsed_errors:
            return {"status": "No Java exceptions found in the log"}
            
        exception_counts = defaultdict(int)
        for error in self.parsed_errors:
            exception_counts[error["error_class"]] += 1
            
        return {
            "status": f"Found {len(self.parsed_errors)} exception(s) in the log",
            "exception_counts": dict(exception_counts),
            "exceptions": self.parsed_errors
        }
    
    def format_for_llm(self) -> str:
        """Format the parsed errors in a way that's helpful for LLMs."""
        summary = self.summarize()
        
        if summary.get("status") == "No Java exceptions found in the log":
            return "No Java exceptions found in the log file."
            
        result = [f"# Java Exception Log Analysis\n"]
        result.append(f"Found {len(self.parsed_errors)} exception(s) in the log.\n")
        
        # Add exception type distribution
        result.append("## Exception Distribution")
        for exception_type, count in summary["exception_counts"].items():
            result.append(f"- {exception_type}: {count} occurrence(s)")
        result.append("")
        
        # Add detailed analysis of each exception
        result.append("## Detailed Exception Analysis")
        
        for i, error in enumerate(self.parsed_errors, 1):
            result.append(f"\n### Exception {i}: {error['error_type']}")
            result.append(f"**Message:** {error['message']}")
            result.append(f"**Description:** {error['description']}")
            
            # Add information about application frames
            app_frames = [frame for frame in error["stack_frames"] if frame["is_application_code"]]
            if app_frames:
                result.append(f"\n**Application Code Location:**")
                top_frame = app_frames[0]  # First application frame is usually the source of the error
                result.append(f"- Method: {top_frame['method']}")
                result.append(f"- File: {top_frame['file']}")
                result.append(f"- Line: {top_frame['line']}")
            
            # Add stack trace (condensed)
            if error["stack_frames"]:
                result.append(f"\n**Stack Trace (top 5 frames):**")
                for frame in error["stack_frames"][:5]:  # Show only top 5 frames to keep it manageable
                    is_app_code = frame["is_application_code"]
                    result.append(f"- {frame['method']} ({frame['file']}:{frame['line']}) {'[Your Code]' if is_app_code else ''}")
            
            # Add "Caused by" information if present
            if error["caused_by"]:
                caused_by = error["caused_by"]
                result.append(f"\n**Caused By:** {caused_by['error_type']}")
                result.append(f"**Cause Message:** {caused_by['message']}")
                result.append(f"**Cause Description:** {caused_by['description']}")
                
                # Add root cause location
                app_frames = [frame for frame in caused_by["stack_frames"] if frame["is_application_code"]]
                if app_frames:
                    result.append(f"\n**Root Cause Location:**")
                    top_frame = app_frames[0]
                    result.append(f"- Method: {top_frame['method']}")
                    result.append(f"- File: {top_frame['file']}")
                    result.append(f"- Line: {top_frame['line']}")
            
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
    Analyze a Java error log file and return formatted results.
    
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
    
    analyzer = JavaErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No Java exceptions found in the log":
            return "No Java exceptions found in the log file."
        
        return f"Found {len(analyzer.parsed_errors)} exceptions in the log file. Use --format json or --format llm for detailed output."


def analyze_text(log_content: str, format_type: str = "llm") -> str:
    """
    Analyze Java error log content provided as a string.
    
    Args:
        log_content: The error log content as a string
        format_type: Output format ('text', 'json', or 'llm')
    
    Returns:
        Formatted analysis as a string
    """
    analyzer = JavaErrorLogAnalyzer(log_content)
    analyzer.parse()
    
    if format_type.lower() == 'json':
        return analyzer.to_json()
    elif format_type.lower() == 'llm':
        return analyzer.format_for_llm()
    else:
        # Default text output
        summary = analyzer.summarize()
        if summary.get("status") == "No Java exceptions found in the log":
            return "No Java exceptions found in the log."
        
        return f"Found {len(analyzer.parsed_errors)} exceptions in the log. Use format='json' or format='llm' for detailed output."


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Java Error Log Analyzer for LLMs")
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
python java_error_analyzer.py error_log.txt --format llm

# As a library
from java_error_analyzer import analyze_text

java_error_log = '''
Exception in thread "main" java.lang.NullPointerException: Cannot invoke "String.length()" because "str" is null
    at com.example.MyClass.processString(MyClass.java:25)
    at com.example.MyClass.main(MyClass.java:10)
'''

formatted_analysis = analyze_text(java_error_log)
print(formatted_analysis)
"""