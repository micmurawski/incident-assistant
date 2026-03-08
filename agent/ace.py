import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List
from uuid import uuid5

import yaml
from anthropic import Anthropic

from agent.code_index.models import (EmbedderResponse, IEmbedder,
                                     IVectorStoreClient, Payload, PointStruct,
                                     VectorStoreSearchResult)
from agent.code_index.vector_store import VectorStoreClient
# --- Domain Entities ---
from agent.constants import QDRANT_INCIDENT_NAMESPACE
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_PATH = os.path.join(BASE_DIR, "incidents")
POST_MORTEM_SEPARATOR = "--POST-MORTEM-- \n\n"


@dataclass
class IncidentData:
    """The raw input: what the agent sees when the pager goes off."""
    id: str
    description: str
    metrics_dashboard: str  # Text representation of graphs (e.g., "CPU: 99%, DB_Conn: 0")

    def to_markdown(self) -> str:
        return f"""
        # Incident: {self.id} \n
        ## Description: \n
        {self.description} \n
        ## Metrics Dashboard: \n
        {self.metrics_dashboard} \n
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "metrics_dashboard": self.metrics_dashboard,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IncidentData":
        return cls(id=data["id"], description=data["description"], metrics_dashboard=data["metrics_dashboard"])


@dataclass
class PostMortem:
    """The Ground Truth: provided after the fact to teach the agent."""
    id: str
    root_cause_analysis: str
    successful_fix: str

    def to_markdown(self) -> str:
        return f"""
        # Post Mortem {self.id}
        ## Root Cause Analysis
        {self.root_cause_analysis}
        ## Successful Fix
        {self.successful_fix}
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "root_cause_analysis": self.root_cause_analysis,
            "successful_fix": self.successful_fix,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PostMortem":
        return cls(id=data["id"], root_cause_analysis=data["root_cause_analysis"], successful_fix=data["successful_fix"])


@dataclass
class IncidentTask(Task):
    """An ACE Task that tracks incident data, post-mortem, and performance."""
    incident_data: IncidentData = None
    post_mortem: PostMortem = None

    @property
    def ttr(self) -> float | None:
        """Time To Resolution in seconds."""
        if self.resolved_at and self.created_at:
            return (self.resolved_at - self.created_at).total_seconds()
        return None

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.DONE


@dataclass
class RunbookRule:
    """A single evolving rule in the Playbook."""
    id: str
    condition: str
    action: str
    reasoning: str
    category: str  # e.g., "Database", "Network", "Application"


@dataclass
class Incident:
    id: str
    incident_data: IncidentData
    post_mortem: PostMortem

    async def index_incident(self, embedder: IEmbedder, vector_store: IVectorStoreClient):
        incident_data = {
            "incident_data": self.incident_data.to_dict(),
            "post_mortem": self.post_mortem.to_dict(),
        }
        yaml_text = yaml.dump(incident_data)
        # save to file
        file_path = f"incidents/incident_{self.id}.yaml"
        num_of_lines = len(yaml_text.split("\n"))

        with open(file_path, "w") as f:
            f.write(yaml_text)

        embedding_result: EmbedderResponse = await embedder.create_embeddings([yaml_text])
        embedding = embedding_result.embeddings[0]
        point_id = str(uuid5(QDRANT_INCIDENT_NAMESPACE, self.id))

        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=Payload(
                id=point_id,
                file_path=file_path,
                code_chunk=yaml_text,
                start_line=0,
                end_line=num_of_lines,
                segment_hash=f"incident_{self.id}",
                type="markdown",
            ),
        )
        await vector_store.upsert_points([point], collection_name="incidents")


# --- The Evolving Playbook ---


class IncidentPlaybook:
    def __init__(self):
        self.rules: List[RunbookRule] = []

    def add_rule(self, condition: str, action: str, reasoning: str, category: str):
        new_id = f"rule_{len(self.rules) + 1:03d}"
        self.rules.append(RunbookRule(new_id, condition, action, reasoning, category))
        print(f"✅ [Playbook] Learned new heuristic: {new_id} ({category})")

    def get_context_block(self) -> str:
        """Injects the current wisdom into the Agent."""
        if not self.rules:
            return "No specific runbook procedures known. Rely on general SRE first principles."

        context = "## 🛡️ EVOLVING RUNBOOK (SOP)\n"
        context += "Prioritize these learned heuristics over general assumptions:\n"
        for r in self.rules:
            context += f"- [{r.category.upper()}] IF {r.condition} -> THEN {r.action}. (Why: {r.reasoning})\n"
        return context

# --- The ACE Pipeline ---


class IncidentManagerACE:
    def __init__(self, model: str = "claude-3-5-sonnet-latest"):
        self.client = Anthropic()
        self.model = model
        self.playbook = IncidentPlaybook()
        self.vector_store = VectorStoreClient(workspace_path=WORKSPACE_PATH)

    def _call(self, system: str, user: str) -> str:
        response = self.client.messages.create(
            model=self.model, max_tokens=2048, temperature=0.0,
            system=system, messages=[{"role": "user", "content": user}]
        )
        return response.content[0].text

    async def respond_to_incident(self, incident: IncidentData) -> str:
        """
        ACTOR: Responds to an incident using the evolved playbook.
        """
        print(f"\n🚀 [ACTOR] Responding to incident {incident.id}...")

        system = f"""You are an Expert SRE Agent. 
        Use the following Evolving Runbook (SOP) to mitigate the incident.
        
        {self.playbook.get_context_block()}
        
        Provide a concise mitigation plan."""

        user = f"""
        {incident.to_markdown()}
        
        What is your mitigation plan?
        """

        plan = self._call(system, user)
        return plan

    # 2. REFLECTOR: The Post-Mortem Analyst
    async def analyze_performance(self, task: IncidentTask) -> str:
        print(f"\n🔍 [REFLECTOR] Analyzing performance for {task.incident_data.id}...")

        system = """You are an Expert Incident Analyst. 
        Compare the Agent's performance against the HISTORICAL POST-MORTEM (Ground Truth).
        
        Analyze:
        1. Success: Did the agent's plan align with the successful fix?
        2. TTR: Was the resolution efficient?
        3. Reflection: What pattern led to success or what signal did the agent miss?
        
        Output a crisp reflection."""

        user = f"""
        --- CURRENT INCIDENT DESCRIPTION ---
        {task.incident_data.to_markdown()}
        
        --- POST-MORTEM (GROUND TRUTH) ---
        {task.post_mortem.to_markdown()}
        
        --- AGENT PERFORMANCE ---
        Success: {task.success}
        TTR: {task.ttr} seconds
        """

        # Search for similar incidents for context
        try:
            similar_incidents: list[VectorStoreSearchResult] = await self.vector_store.search(task.incident_data.description, collection_name="incidents")
            if similar_incidents:
                user += "\n--- SIMILAR HISTORICAL INCIDENTS ---\n"
                for i, result in enumerate(similar_incidents[:2]):
                    payload = result.payload
                    file_path = payload.get("file_path")
                    if os.path.exists(file_path):
                        with open(file_path, "r") as f:
                            hist_data = yaml.safe_load(f)
                            h_inc = IncidentData.from_dict(hist_data.get("incident_data"))
                            h_pm = PostMortem.from_dict(hist_data.get("post_mortem"))
                            user += h_inc.to_markdown() + POST_MORTEM_SEPARATOR + h_pm.to_markdown() + "\n"
        except Exception as e:
            print(f"   [Reflector Warning] Could not fetch similar incidents: {e}")

        reflection = self._call(system, user)
        return reflection

    # 3. CURATOR: The Runbook Author
    def update_runbook(self, reflection: str):
        print("\n📝 [CURATOR] Updating Runbook based on Reflection...")

        system = """You are the Knowledge Base Curator.
        Based on the reflection, extract a GENERALIZABLE heuristic (IF/THEN rule).
        
        Return ONLY a JSON object (no markdown):
        {
            "action": "ADD", 
            "condition": "short condition string",
            "mitigation": "specific action",
            "reasoning": "why this works",
            "category": "DB|NET|APP|SEC"
        }
        If the reflection suggests updating an existing rule or deleting an incorrect one, use:
        {"action": "UPDATE", "rule_id": "rule_001", ...} or {"action": "DELETE", "rule_id": "rule_001"}
        If no action is needed, return {"action": "NONE"}.
        """

        try:
            response = self._call(system, f"Reflection: {reflection}")
            data = json.loads(response)

            if data["action"] == "ADD":
                self.playbook.add_rule(
                    data["condition"],
                    data["mitigation"],
                    data["reasoning"],
                    data["category"]
                )
            elif data["action"] == "DELETE":
                # Find and remove the rule
                self.playbook.rules = [r for r in self.playbook.rules if r.id != data["rule_id"]]
                print(f"🗑️ [Playbook] Deleted rule: {data['rule_id']}")
            # UPDATE logic can be added here
        except Exception as e:
            print(f"   [Curator Error] Could not update runbook: {e}")

    # --- The Training Loop ---
    async def train_on_history(self, task: IncidentTask):
        """
        Feeds a historical task into the system to evolve the playbook.
        """

        # 2. Reflector compares it to what actually happened
        reflection = await self.analyze_performance(task)

        # 3. Curator updates the playbook
        self.update_runbook(reflection)

# --- EXECUTION SCENARIO ---


async def run_scenario():
    ace_manager = IncidentManagerACE()

    # === SCENARIO 1: Training on a historical incident ===
    inc_1 = IncidentData(
        id="INC-2024-001",
        description="Users reporting 500 errors on checkout.",
        metrics_dashboard="""
        [Global Latency]: Spiked to 5s
        [DB CPU]: 15% (Normal)
        [App Error Rate]: 12%
        [Last Deployment]: 10 mins ago (Service: Checkout-v2)
        """
    )

    pm_1 = PostMortem(
        id="INC-2024-001",
        root_cause_analysis="The DB CPU was low, ruling out database load. The issue coincided exactly with Checkout-v2 deploy.",
        successful_fix="Rolled back Checkout-v2 to v1 immediately.",
    )

    # Create a task representing the resolution effort
    task_1 = IncidentTask(
        id="task_001",
        status=TaskStatus.DONE,  # Assume it was successful for training
        incident_data=inc_1,
        post_mortem=pm_1,
        created_at=datetime.now(),
        resolved_at=datetime.now()  # Mock TTR
    )

    print("\n--- 📂 TRAINING ON HISTORICAL INCIDENT 1 ---")
    await ace_manager.train_on_history(task_1)

    # === SCENARIO 2: Responding to a similar incident ===
    inc_2 = IncidentData(
        id="INC-2024-045",
        description="Login service is timing out.",
        metrics_dashboard="""
        [Global Latency]: Spiked to 8s
        [DB CPU]: 10% (Normal)
        [Last Deployment]: 5 mins ago (Service: Auth-v9)
        """
    )

    print("\n--- 🚨 LIVE INCIDENT RESPONSE (Using Evolved Context) ---")
    final_plan = await ace_manager.respond_to_incident(inc_2)

    print("\n>>> FINAL AGENT PLAN:")
    print(final_plan)

if __name__ == "__main__":
    asyncio.run(run_scenario())
