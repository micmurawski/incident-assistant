# Mean Agent

A tool for injecting realistic bugs into codebases for testing and educational purposes.

## Overview

Mean Agent is a sophisticated tool that automatically injects realistic bugs into codebases. It's designed to help:
- Test the effectiveness of code review processes
- Evaluate automated testing tools
- Train developers to spot common bugs
- Create realistic test scenarios for debugging tools

## Features

- **Intelligent Error Injection**: Uses Claude 3.5 Sonnet to analyze code and suggest realistic bugs
- **Multiple Error Types**: Injects various types of errors including:
  - Logic errors (incorrect conditionals, off-by-one errors)
  - Variable scope issues
  - Error handling problems
  - Missing edge case handling
  - Type conversion issues
  - Resource leaks
- **Smart File Selection**: Automatically selects appropriate files to modify
- **Comprehensive Documentation**: Generates detailed ERROR.md documenting all injected errors
- **Version Control Integration**: Commits changes to a new Git branch for easy tracking

## Requirements

- Python 3.x
- Git
- Anthropic API key (for Claude 3.5 Sonnet)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd mean_agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your Anthropic API key:
```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

## Usage

Run the mean agent on a repository:

```bash
python mean_agent.py /path/to/repository [--branch BRANCH_NAME]
```

Arguments:
- `repo_path`: Path to the repository to inject errors into
- `--branch`: (Optional) Name of the branch to create (defaults to error-injection-<timestamp>)

## Output

The tool will:
1. Analyze the codebase
2. Select files for modification
3. Inject realistic errors
4. Generate ERROR.md documenting all changes
5. Commit changes to a new Git branch

## ERROR.md Format

The generated ERROR.md file includes:
- File path
- Line number
- Error type
- Description of the error
- Original code
- Modified code with the error

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[Add your license information here]
