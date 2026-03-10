# Evolving Agentic Contexts for Self-Improving Auto-remediation of Microservice Applications

The goal of this project is to experiment with whether a multi-agent system can increase performance on auto-remediations for applications running on a Kubernetes cluster using **Agentic Context Engineering**.

## Experiment Setup

* **Incident Selection:** A script randomly chooses an incident scenario from one of the defined classes.
* **Resolution Phase:** An agent attempts to resolve the incident and restore service health.
    * **Attempts:** The agent has 3 attempts per incident.
    * **Playbook:** The agent utilizes an evolving **PLAYBOOK** (SOP) embedded in its context. Initially, this playbook is empty.
* **ACE Pipeline:** Periodically, the Agentic Context Evolution Pipeline is triggered. It analyzes past incident resolutions (Tasks) to **ADD, UPDATE, or DELETE** heuristics in the PLAYBOOK.

## Learning Schedule (Trigger Frequency)

The ACE pipeline follows a strategy analogous to **Epsilon-Greedy** in Reinforcement Learning:

*   **Exploration Phase ($\epsilon$ is high):** Initially, the pipeline is triggered frequently (e.g., after every 1-3 incidents) to build a baseline playbook.
*   **Exploitation Phase ($\epsilon$ decays):** As the playbook matures, the trigger frequency decreases (e.g., every 5-10 incidents), allowing us to validate the heuristics across larger batches.
*   **Transition:** We start with **Batch Learning** (analyzing multiple incidents to find systemic patterns) and will transition to **Online Learning** (refining after every incident).

## Performance Measures

*   **TTR (Time To Resolution):** Calculated as the duration between task creation and successful resolution (or number of steps taken).
*   **Success Rate:** The percentage of incidents successfully resolved within the 3-attempt limit.
*   **Heuristic Quality:** Evaluated by the Reflector during the ACE loop to ensure new rules don't introduce regressions.

## Incident Classes

Incidents are categorized into five distinct classes to challenge different aspects of the agent's reasoning:

1.  **Chaos Mesh (Infrastructure/Network):** Network partitions, latency spikes, or pod failures introduced via Chaos Mesh.
2.  **Code Ingestion (Logic Regressions):** Introduction of logical bugs or performance regressions directly into the service code.
3.  **K8s Configuration (Resource/Config):** Misconfigured resource limits (OOMKilled), incorrect environment variables, or service/ingress mismatches.
4.  **Service Code (Runtime/State):** Deadlocks, unclosed database connections, or cache exhaustion.
5.  **The "Red Herring" (Combination):** A random combination of the above (e.g., a network delay occurring simultaneously with a bad deployment) to test the agent's ability to prioritize root causes.

## Scientific Sources

*   [Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models](https://arxiv.org/pdf/2510.04618)
*   [Leveraging Large Language Models for the Auto-remediation of Microservice Applications: An Experimental Study](https://dl.acm.org/doi/pdf/10.1145/3663529.3663855)
*   [Reliable Decision-Making for Multi-Agent LLM System](https://multiagents.org/2025_artifacts/reliable_decision_making_for_multi_agent_llm_systems.pdf)
*   [LLM Multi-Agent Systems: Challenges and Open Problems](https://arxiv.org/pdf/2402.03578)
