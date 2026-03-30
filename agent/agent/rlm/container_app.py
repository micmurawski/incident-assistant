from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agent.rlm.container import ContainerRLMSandbox, ContainersResourceManager

app = FastAPI()

# Instantiate the sandbox manager globally for the agent app
sandbox: ContainerRLMSandbox = ContainersResourceManager.get_container("test")


@app.on_event("startup")
def startup_event():
    # Spin up the Docker environment automatically when this app starts
    sandbox.start()


@app.on_event("shutdown")
def shutdown_event():
    sandbox.shutdown()


class CodeRequest(BaseModel):
    code: str


@app.post("/api/execute")
async def execute_endpoint(payload: CodeRequest):
    """Your LLM/Agent calls this REST endpoint to execute code."""
    result = await sandbox.execute_code(payload.code)
    return {"result": result}


@app.post("/api/reset")
def reset_endpoint():
    """Endpoint to wipe the container's memory."""
    sandbox.reset_interpreter()
    return {"status": "success", "message": "Interpreter memory wiped."}


@app.get("/ui/history", response_class=HTMLResponse)
def view_history():
    """A primitive but effective UI to view what the LLM is doing in real-time."""
    html = """
    <html><body style='font-family: monospace; max-width: 800px; margin: auto; padding: 20px; background: #1e1e1e; color: #d4d4d4;'>
    <h2 style='color: #569cd6;'>Agent Execution History</h2>
    <button onclick='fetch("/api/reset", {method: "POST"}).then(()=>location.reload())' 
            style='padding:10px; background:#f44336; color:white; border:none; border-radius:4px; cursor:pointer;'>
        Hard Reset Interpreter
    </button>
    <hr style='border-color: #333;'>
    """

    for entry in sandbox.get_history():
        action = entry["action"]
        content = entry["content"]

        if action == "CODE_INPUT":
            bg, title_col = "#2d2d2d", "#ce9178"
        elif action == "CODE_OUTPUT":
            bg, title_col = "#1e1e1e", "#4af626"
        elif action == "SYSTEM":
            bg, title_col = "#004080", "#4fc1ff"
        else:
            bg, title_col = "#4d0000", "#f44336"

        html += f"<div style='background: {bg}; padding: 10px; margin-bottom: 10px; border-left: 4px solid {title_col};'>"
        html += f"<strong style='color: {title_col};'>{action}:</strong>"
        html += f"<pre style='white-space: pre-wrap; margin-top: 5px;'>{content}</pre>"
        html += "</div>"

    html += "</body></html>"
    return html

# Run this file with: uvicorn app:app --reload
