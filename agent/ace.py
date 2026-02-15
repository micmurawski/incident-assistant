import json
from dataclasses import dataclass
import os
from typing import List
from anthropic import Anthropic
from agent.code_index.models import EmbedderResponse, IEmbedder, IVectorStoreClient, VectorStoreSearchResult
from agent.code_index.models import (Payload,
                                     PointStruct)
# --- Domain Entities ---
from agent.constants import QDRANT_INCIDENT_NAMESPACE
from uuid import uuid5
from agent.code_index.vector_store import VectorStoreClient
from typing import Any
import yaml

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

    # 2. REFLECTOR: The Post-Mortem Analyst
    async def analyze_performance(self, incident: IncidentData, post_mortem: PostMortem) -> str:
        print("\n🔍 [REFLECTOR] Comparing Agent Plan vs. Actual Post-Mortem...")
        
        system = """You are an Expert Incident Analyst. 
        Compare the Agent's proposed mitigation against the HISTORICAL POST-MORTEM (Ground Truth).
        
        Did the Agent guess correctly?
        - If YES: What pattern led to success?
        - If NO: What subtle signal in the metrics did the agent miss that the Post-Mortem identified?
        
        Output a crisp reflection."""

        user = f"""
        --- CURRENT INCIDENT DESCRIPTION ---
        {incident.to_markdown()}
        
        --- CURRENT POST-MORTEM ---
        {post_mortem.to_markdown()}
        
        --- HISTORICAL INCIDENTS ---
        """
        
        # TODO: Search for similar incidents from the database and propose a solution
        similar_incidents: list[VectorStoreSearchResult] = await self.vector_store.search(incident.description, collection_name="incidents")
        result: VectorStoreSearchResult
        for i, result in enumerate(similar_incidents):
            payload = result.payload
            file_path = payload.get("file_path")
            yaml_text = open(file_path, "r").read()
            incident_data = yaml.load(yaml_text)
            incident_data = IncidentData.from_dict(incident_data.get("incident_data"))
            post_mortem = PostMortem.from_dict(incident_data.get("post_mortem"))
            if i == 0:
                user += "--- HISTORICAL INCIDENTS --- \n"
            episode = incident_data.to_markdown() + POST_MORTEM_SEPARATOR + post_mortem.to_markdown()
            user += episode + "\n"
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
        If no new rule is needed, return {"action": "NONE"}.
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
        except Exception as e:
            print(f"   [Curator Error] Could not update runbook: {e}")

    # --- The Training Loop ---
    def train_on_history(self, incident: IncidentData, post_mortem: PostMortem):
        """
        Feeds a historical incident into the system to evolve the playbook.
        """

        # 2. Reflector compares it to what actually happened
        reflection = self.analyze_performance(incident, post_mortem)

        # 3. Curator updates the playbook
        self.update_runbook(reflection)

# --- EXECUTION SCENARIO ---


if __name__ == "__main__":
    ace_manager = IncidentManagerACE()

    # === SCENARIO 1: The "False Positive" DB Issue ===
    # Real history: Everyone thought it was the DB, but it was actually a bad deployment.

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
        root_cause_analysis="The DB CPU was low, ruling out database load. The issue coincided exactly with Checkout-v2 deploy.",
        successful_fix="Rolled back Checkout-v2 to v1 immediately.",
    )

    print("\n--- 📂 PROCESSING HISTORICAL INCIDENT 1 ---")
    ace_manager.train_on_history(inc_1, pm_1)

    # === SCENARIO 2: A similar incident occurs later ===
    # Now the agent should recognize the pattern (Low DB CPU + Recent Deploy = Rollback, don't check DB).

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
    # This time, we just ask for a response, we don't train.
    final_plan = ace_manager.respond_to_incident(inc_2)

    print("\n>>> FINAL AGENT PLAN:")
    print(final_plan)
