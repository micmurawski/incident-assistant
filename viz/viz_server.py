import json
import os
import sys
import traceback
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Add agent to path so we can import models
sys.path.append(os.path.join(os.getcwd(), "agent"))

try:
    from agent.persistence.model import TaskModel
    from agent.persistence.settings import init_db
    import peewee
    # Initialize and bind the database
    print("Initializing database...")
    init_db()
    print("Database initialized successfully.")
except Exception as e:
    print(f"CRITICAL: Error importing agent models or initializing DB: {e}")
    traceback.print_exc()
    TaskModel = None

app = FastAPI(title="Agent Task Visualization")

# Templates and Static Files
templates = Jinja2Templates(directory="viz/templates")

class Selection(BaseModel):
    task_id: str
    root_id: str

class Feedback(BaseModel):
    task_id: str
    root_id: str
    feedback: str

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("viz_index.html", {"request": request})

@app.get("/api/roots")
async def get_roots():
    """List all unique root task IDs."""
    if TaskModel is None:
        return JSONResponse(status_code=500, content={"error": "TaskModel not initialized. Check server logs."})
    try:
        query = TaskModel.select(TaskModel.root_id).distinct()
        roots = [row.root_id for row in query]
        return {"roots": roots}
    except Exception as e:
        print(f"Error fetching roots: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/tasks/{root_id}")
async def get_tasks(root_id: str):
    """Get the full task tree for a given root ID."""
    if TaskModel is None:
        return JSONResponse(status_code=500, content={"error": "TaskModel not initialized."})
    try:
        query = TaskModel.select().where(TaskModel.root_id == root_id)
        tasks = []
        for task in query:
            tasks.append({
                "id": task.id,
                "status": task.status,
                "todo_list": json.loads(task.todo_list) if task.todo_list else [],
                "children": json.loads(task.children) if task.children else [],
                "parent": task.parent,
                "assignee": task.assignee,
                "assigner": task.assigner,
                "conversation": json.loads(task.conversation) if task.conversation else [],
                "created_at": task.created_at.isoformat() if isinstance(task.created_at, datetime) else task.created_at,
            })
        return {"tasks": tasks}
    except Exception as e:
        print(f"Error fetching tasks for root {root_id}: {e}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/selection")
async def get_selection():
    """Retrieve the current task selection."""
    if os.path.exists("selected_task.json"):
        with open("selected_task.json", "r") as f:
            return json.load(f)
    return {"task_id": None, "root_id": None}

@app.post("/api/select")
async def select_task(selection: Selection):
    """Record a task selection."""
    print(f"Task selected: {selection.task_id} in root {selection.root_id}")
    # For now, just save to a file for the agent to potentially pick up
    with open("selected_task.json", "w") as f:
        json.dump(selection.dict(), f)
    return {"status": "ok", "selected": selection.task_id}

@app.post("/api/feedback")
async def add_feedback(fb: Feedback):
    """Inject feedback into a task's conversation in the database."""
    if TaskModel is None:
        return JSONResponse(status_code=500, content={"error": "TaskModel not initialized."})
    try:
        # Load the task
        task_row = TaskModel.get((TaskModel.root_id == fb.root_id) & (TaskModel.id == fb.task_id))
        conv = json.loads(task_row.conversation) if task_row.conversation else []
        conv.append({"role": "user", "content": fb.feedback})
        
        # Update status if needed (e.g. from AWAITING_FEEDBACK to IN_PROGRESS)
        status = task_row.status
        if status == "AWAITING_FEEDBACK":
            status = "IN_PROGRESS"
            
        TaskModel.update(
            conversation=json.dumps(conv),
            status=status,
            updated_at=datetime.now()
        ).where((TaskModel.root_id == fb.root_id) & (TaskModel.id == fb.task_id)).execute()
        
        return {"status": "ok", "message": "Feedback added"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
