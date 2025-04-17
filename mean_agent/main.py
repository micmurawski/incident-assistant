# Example of how to use the error injection langgraph

from mean_agent import run_error_injection

REPO_PATH = "../services/robot-shop"
BRANCH_NAME = "test-errors-branch"

run_error_injection(REPO_PATH, BRANCH_NAME)
