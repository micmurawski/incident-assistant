# Agent Task Explorer

An interactive web-based dashboard to visualize and interact with the agent's task tree.

## Features
- **Hierarchical Visualization**: Browse the full task tree for any root task.
- **Detailed Task View**: Inspect assignee, status, todo list, and full `messages_history` (single source of truth).
- **Interactive Feedback**: Inject user feedback by appending to `messages_history` in the database.
- **Task Selection**: Focus on a specific task for the agent to work on (stores selection in `selected_task.json`).

## How to Run
From the project root:
```bash
PYTHONPATH=. .venv/bin/uvicorn viz.viz_server:app --reload
```
Then open [http://localhost:8000](http://localhost:8000) in your browser.

## Technologies Used
- **Backend**: FastAPI (Python)
- **Database**: Peewee ORM (SQLite)
- **Frontend**: vis.js (Interactive Graph)
