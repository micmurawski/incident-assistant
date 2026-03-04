import asyncio

from framework import AsyncFlow
from framework.decorators import NO_APPEND, node

# For batch nodes, shared[items_key] must be a list of dicts (one per item) with keys matching the node's params.
# first_a(app: str) expects each item to have "app". Use items_key="app_items" so shared["apps"] stays for second_a.
APPS = ["cart", "catalogue", "dispatch", "mongo", "mysql", "payment", "ratings", "redis", "shipping", "user", "web"]

shared = {
    "apps": APPS,
    "fault_classes": [2, 3, 4],
}


@node
async def first_a(apps: list[str], fault_classes: list[int]):
    # create list of dicts with all possible combinations of apps and fault classes
    app_fault_combinations = []
    for app in apps:
        for fault_class in fault_classes:
            app_fault_combinations.append({"app": app, "fault_class": fault_class})
    return {
        "app_items": app_fault_combinations
    }


# Skip some items; writes to shared["results"], preserves shared["app_items"] for downstream
@node(batch=True, items_key="app_items")
async def second_a(app: str, fault_class: int):
    print(f"second: {app} fault_class={fault_class}")
    if app == "mongo":
        print(f"skipping: {app}")
        return NO_APPEND  # not added to shared["results"]
    return {"app": app, "fault_class": fault_class, "first": "done"}

# Map results into a dict: shared["names"]["last"] = app (each item returns (key, value))
@node(batch=True, items_key="results", results_key="names", results_type=dict)
async def third_a(app: str):
    print(f"third: {app}")
    return ("last", app)

first_a >> second_a >> third_a
async_flow = AsyncFlow(start=first_a)


async def main():
    await async_flow.run_async(shared)
    print(shared)

if __name__ == "__main__":
    asyncio.run(main())
