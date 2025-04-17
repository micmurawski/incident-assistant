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
