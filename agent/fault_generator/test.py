import asyncio

from framework import AsyncFlow
from framework.decorators import node

# For batch nodes, shared[items_key] must be a list of dicts (one per item) with keys matching the node's params.
# first_a(app: str) expects each item to have "app". Use items_key="app_items" so shared["apps"] stays for second_a.
APPS = ["cart", "catalogue", "dispatch", "mongo", "mysql", "payment", "ratings", "redis", "shipping", "user", "web"]

shared = {
    "app_items": [{"app": name} for name in APPS],
    "apps": APPS,
    "fault_classes": [2, 3, 4],
}


@node(parallel_batch=True, items_key="app_items")
async def first_a(app: str):
    print(f"first: {app}")
    return {"first": "done"}


@node
async def second_a(apps: list[str], fault_classes: list[int]):
    print(f"second: {apps}, {fault_classes}")
    return {"second": "done"}


first_a >> second_a

async_flow = AsyncFlow(start=first_a)


async def main():
    await async_flow.run_async(shared)
    print(shared)

if __name__ == "__main__":
    asyncio.run(main())
