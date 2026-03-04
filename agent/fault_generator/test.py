import asyncio

from framework import AsyncFlow
from framework.decorators import node

shared = {
    "apps": ["cart", "catalogue", "dispatch", "mongo", "mysql", "payment", "ratings", "redis", "shipping", "user", "web"],
    "fault_classes": [2, 3, 4]
}


@node(parallel_batch=True)
async def first_a(apps: list[str], fault_classes: list[int]):
    print(f"first: {apps}, {fault_classes}")
    return {"first": "done"}


@node
async def second_a(apps: list[str], fault_classes: list[int]):
    print(f"second: {apps}, {fault_classes}")
    return {"second": "done"}


first_a >> second_a

async_flow = AsyncFlow(first_a)


async def main():
    await async_flow.run_async(shared)

if __name__ == "__main__":
    asyncio.run(main())
