import asyncio
import json
from pathlib import Path

from agent.rlm.container import ContainerRLMSandbox, ContainersResourceManager

PATH_TO_KEYS = Path("/Users/micmur/GITHUB/o8s/api_key.json")
KEYS = json.load(open(PATH_TO_KEYS))
# Connection details
GRAFANA_URL = KEYS["grafana_url"]
GRAFANA_TOKEN = KEYS["grafana_api_token"]


async def main():
    # 1. Create sandbox with credentials in ENV
    env = {
        "GRAFANA_URL": GRAFANA_URL,
        "GRAFANA_TOKEN": GRAFANA_TOKEN,
        "PYTHONPATH": "/app"
    }

    # Resolve the path to the 'agent' directory to mount it
    # We mount the directory containing the 'agent' package
    # This script is at agent/agent/rlm/test_direct_container_fetch.py
    # We want to mount the 'agent' folder that contains 'grafana_client', etc.
    # The 'agent' folder is two levels up from this script.
    agent_dir = Path(__file__).resolve().parent.parent

    sandbox: ContainerRLMSandbox = ContainersResourceManager.get_container(
        id="direct-fetch-sandbox",
        image="python:3.12-slim",
        env=env,
    )

    # 2. Start with mounting the agent package
    # We mount the 'agent' folder to '/app/agent'
    volumes = {
        str(agent_dir): {"bind": "/app/agent", "mode": "ro"}
    }
    sandbox.start(volumes=volumes)

    try:
        # 3. Prepare requirements inside container
        print("Installing dependencies in container...")
        await sandbox.pip_install(["pandas", "httpx"])
        

        # 4. Execute code that fetches data DIRECTLY in the container
        # Note: We use the SYNC GrafanaPandasClient here, so no asyncio.run needed!
        direct_fetch_script = """
import os
import pandas as pd
from agent.grafana_client import GrafanaClient, GrafanaPandasClient

url = os.getenv("GRAFANA_URL")
token = os.getenv("GRAFANA_TOKEN")

# Initialize the SYNC client
pd_client = GrafanaPandasClient(url, token)

print(f"Fetching data directly from {url}...")
# Synchronous call - perfectly safe inside the sandbox execution
# df = pd_client.query_prometheus('up', from_time='now-5m')
df = pd_client.query_loki('{namespace="application", app="mysql"}', from_time="now-15m")
print(f"Successfully created DataFrame in container runtime. Shape: {df.shape}")
print("Column types:")
print(df.dtypes)
print("\\nFirst 5 rows:")
print(df.head())
"""
        result = await sandbox.execute_code(direct_fetch_script)
        print("\nSandbox Execution Result:")
        print(result)

    finally:
        sandbox.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
