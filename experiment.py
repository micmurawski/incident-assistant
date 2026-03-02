import asyncio
import json
import os

import yaml

from agent.tooling.chaos_meshr import ChaosTools

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAULT_VAULT_PATH = os.path.join(BASE_DIR, "agent", "fault-vault", "scenarios.yaml")

with open(FAULT_VAULT_PATH, "r") as f:
    data = yaml.safe_load(f)

scenario = data["scenarios"][0]


def get_chaos_tool(scenario: dict):
    return next((tool for tool in ChaosTools.tools if tool.name == scenario["chaos_method"]), None)


async def main():
    print("playing scenario: ", scenario["id"])
    print()
    result = await get_chaos_tool(scenario)(**scenario["chaos_params"])
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
