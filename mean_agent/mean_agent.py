import os
from typing import Dict, List, Tuple, Any, TypedDict, Annotated
from datetime import datetime
import random
import tempfile
import subprocess
import uuid

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END, START
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

# Type definitions for our state


class FileContent(TypedDict):
    path: str
    content: str


class ErrorDetail(TypedDict):
    file_path: str
    line_number: int
    original_code: str
    modified_code: str
    error_type: str
    description: str


class GraphState(TypedDict):
    repo_path: str
    branch_name: str
    files: List[FileContent]
    selected_files: List[FileContent]
    errors: List[ErrorDetail]
    current_file: FileContent
    error_md_content: str


# Initialize LLM
llm = ChatAnthropic(
    model="claude-3-5-sonnet-20240620",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY")
)

# Set up JSON parser
json_parser = JsonOutputParser()

# Step 1: Initialize the repository analysis


def init_repo_analysis(state: GraphState) -> GraphState:
    """Initialize the repository analysis by scanning files."""
    repo_path = state["repo_path"]
    branch_name = state["branch_name"]
    files = []

    res = subprocess.run(
        ["git", "show-ref", "--quiet", f"refs/heads/{branch_name}"],
        cwd=repo_path,
        check=False
    )
    if res.returncode == 0:
        subprocess.run(
            ["git", "checkout", branch_name],
            cwd=repo_path,
            check=True
        )
        subprocess.run(
            ["git", "reset", "--hard", "master"],
            cwd=repo_path,
            check=True
        )
    for root, _, filenames in os.walk(repo_path):
        for filename in filenames:
            if filename.endswith(('.py', '.js', '.ts', '.java', '.cpp', '.c')):
                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, repo_path)

                # Skip files in .git, node_modules, etc.
                if any(part.startswith('.') or part == 'node_modules' for part in relative_path.split(os.sep)):
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        files.append(
                            {"path": relative_path, "content": content})
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")

    return {**state, "files": files}

# Step 2: Select files to inject errors into


def select_files_for_errors(state: GraphState) -> GraphState:
    """Select a subset of files to inject errors into."""
    files = state["files"]
    # Randomly select up to 3 files or 10% of the files, whichever is greater
    num_files_to_select = max(3, int(len(files) * 0.1))
    selected_indices = random.sample(
        range(len(files)), min(num_files_to_select, len(files)))
    selected_files = [files[i] for i in selected_indices]

    return {**state, "selected_files": selected_files}

# Step 3: Analyze a file to determine potential error injection points


def analyze_file(state: GraphState) -> GraphState:
    """Analyze the current file to find potential error injection points."""
    if not state["selected_files"]:
        return {**state, "next": "generate_error_md"}

    # Get the next file to analyze
    current_file = state["selected_files"][0]
    updated_selected_files = state["selected_files"][1:]

    return {
        **state,
        "current_file": current_file,
        "selected_files": updated_selected_files,
    }

# Step 4: Use LLM to suggest errors to inject


def suggest_errors(state: GraphState) -> GraphState:
    """Use LLM to suggest errors that could be injected into the code."""
    current_file = state["current_file"]

    # Prompt template for error suggestion
    suggest_errors_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="""
        You are an expert code analyst tasked with identifying places to inject realistic bugs into code for testing purposes.
        Your goal is to introduce subtle errors that could realistically occur during development.
        
        Types of errors to consider:
        1. Logic errors (incorrect conditionals, off-by-one errors)
        2. Variable scope issues
        3. Error handling problems
        4. Missing edge case handling
        5. Type conversion issues
        6. Resource leaks
        
        For each suggested error, provide:
        - Line number to modify
        - Original code snippet
        - Modified code snippet with error
        - Error type
        - Brief description of the error and its potential impact
        
        Requirements for error:
        - The error should not break compilation
        - The error should cause problems during runtime
        
        Format your response as JSON with this structure:
        {
            "errors": [
                {
                    "line_number": <int>,
                    "original_code": "<original code snippet>",
                    "modified_code": "<modified code with error>",
                    "error_type": "<error_type>",
                    "description": "<description of error and impact>"
                }
            ]
        }
        Respond only with the JSON response, no other text or comments.
        """),
        HumanMessage(content=f"""
        Please analyze this code from file {current_file['path']} and suggest 1-2 realistic bugs to inject:
        
        ```
        {current_file['content']}
        ```
        """)
    ])

    # Get suggestions from LLM
    chain = suggest_errors_prompt | llm | json_parser
    result = chain.invoke({})

    # Create error details
    new_errors = []
    for error in result["errors"]:
        new_errors.append({
            "file_path": current_file["path"],
            "line_number": error["line_number"],
            "original_code": error["original_code"],
            "modified_code": error["modified_code"],
            "error_type": error["error_type"],
            "description": error["description"],
        })

    return {**state, "errors": state["errors"] + new_errors}

# Step 5: Inject errors into the code


def inject_errors(state: GraphState) -> GraphState:
    """Inject the suggested errors into the file."""
    current_file = state["current_file"]
    current_errors = [e for e in state["errors"]
                      if e["file_path"] == current_file["path"]]

    if not current_errors:
        return state

    file_content = current_file["content"]
    lines = file_content.split('\n')

    # Sort errors by line number in descending order to avoid offsets
    sorted_errors = sorted(
        current_errors, key=lambda e: e["line_number"], reverse=True)

    for error in sorted_errors:
        line_num = error["line_number"] - 1  # Adjust for 0-indexing
        if 0 <= line_num < len(lines):
            # Replace the line with the modified code
            lines[line_num] = error["modified_code"]

    # Update the file content in our state
    modified_content = '\n'.join(lines)
    updated_file = {**current_file, "content": modified_content}

    # Find and update the file in the files list
    updated_files = state["files"].copy()
    for i, file in enumerate(updated_files):
        if file["path"] == current_file["path"]:
            updated_files[i] = updated_file
            break

    return {**state, "files": updated_files}

# Step 6: Generate ERROR.md content


def generate_error_md(state: GraphState) -> GraphState:
    """Generate the ERROR.md file documenting all the injected errors."""
    error_md_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="""
        Create an ERROR.md file that documents all the errors that were injected into the codebase.
        The documentation should be clear, well-structured, and include all relevant details about each error.
        
        For each error, include:
        1. File path
        2. Line number
        3. Error type
        4. Description of the error
        5. Original code
        6. Modified code with the error
        
        Start with a brief introduction explaining the purpose of this document and when it was generated.
        """),
        HumanMessage(content=f"""
        Generate ERROR.md content for these injected errors:
        
        {state["errors"]}
        """)
    ])

    # Get ERROR.md content from LLM
    chain = error_md_prompt | llm
    result = chain.invoke({})

    if isinstance(result, AIMessage):
        error_md_content = result.content
    else:
        error_md_content = str(result)

    return {**state, "error_md_content": error_md_content}

# Step 7: Commit changes to a new branch


def commit_changes(state: GraphState) -> GraphState:
    """Commit the changes to a new branch in the repository."""
    repo_path = state["repo_path"]
    branch_name = state["branch_name"]

    try:
        # Create a new branch
        res = subprocess.run(
            ["git", "show-ref", "--quiet", f"refs/heads/{branch_name}"],
            cwd=repo_path,
            check=False
        )
        if res.returncode != 0:
            subprocess.run(["git", "-C", repo_path, "checkout",
                           "-b", branch_name], check=True)
        else:
            subprocess.run(
                ["git", "checkout", branch_name],
                cwd=repo_path,
                check=True
            )

        # Write modified files
        for file in state["files"]:
            file_path = os.path.join(repo_path, file["path"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file["content"])

        # Write ERROR.md
        with open(os.path.join(repo_path, "ERROR.md"), 'w', encoding='utf-8') as f:
            f.write(state["error_md_content"])

        # Add all changes
        subprocess.run(["git", "-C", repo_path, "add", "."], check=True)

        # Commit changes
        commit_message = f"Inject test errors - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(["git", "-C", repo_path, "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "-C", repo_path, "push", "origin", branch_name], check=True)

        print(f"Changes committed to branch: {branch_name}")

    except subprocess.CalledProcessError as e:
        print(f"Git operation failed: {e}")

    return state

# Define the state graph


def create_error_injection_graph():
    """Create the langgraph for error injection."""
    # Initialize the graph
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("init_repo_analysis", init_repo_analysis)
    graph.add_node("select_files_for_errors", select_files_for_errors)
    graph.add_node("analyze_file", analyze_file)
    graph.add_node("suggest_errors", suggest_errors)
    graph.add_node("inject_errors", inject_errors)
    graph.add_node("generate_error_md", generate_error_md)
    graph.add_node("commit_changes", commit_changes)

    # Add edges
    graph.add_edge(START, "init_repo_analysis")
    graph.add_edge("init_repo_analysis", "select_files_for_errors")
    graph.add_edge("select_files_for_errors", "analyze_file")

    # Conditional edge: If there are selected files, process them; otherwise generate ERROR.md
    graph.add_conditional_edges(
        "analyze_file",
        lambda state: "generate_error_md" if not state["selected_files"] else "suggest_errors"
    )
    graph.add_edge("suggest_errors", "inject_errors")
    graph.add_edge("inject_errors", "analyze_file")
    graph.add_edge("generate_error_md", "commit_changes")
    graph.add_edge("commit_changes", END)

    # Compile the graph
    return graph.compile()

# Function to run the error injection process


def run_error_injection(repo_path: str, branch_name: str = None):
    """Run the error injection process on the specified repository."""
    if branch_name is None:
        branch_name = f"error-injection-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Initialize the state
    initial_state = GraphState(
        repo_path=repo_path,
        branch_name=branch_name,
        files=[],
        selected_files=[],
        errors=[],
        current_file={"path": "", "content": ""},
        error_md_content=""
    )

    # Create and run the graph
    graph = create_error_injection_graph()
    graph.invoke(initial_state)

    print(
        f"Error injection completed. Changes committed to branch '{branch_name}'.")
    print(f"ERROR.md has been generated with documentation of all injected errors.")


# Example usage
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Inject errors into a codebase for testing.")
    parser.add_argument("repo_path", help="Path to the repository")
    parser.add_argument(
        "--branch", help="Name of the branch to create (defaults to error-injection-<timestamp>)")

    args = parser.parse_args()

    run_error_injection(args.repo_path, args.branch)
