import time

from agent.tasks.tasks import Task


def collect_tasks(t: Task) -> list[Task]:
    all_tasks = []
    all_tasks.append(t)
    for child in t.children:
        all_tasks.extend(collect_tasks(child))
    return all_tasks


def collect_meaningful_actions(goal: Task) -> tuple[list[str], set[str], bool]:
    all_tasks = collect_tasks(goal)
    deploy_app_called = False
    meaningful_actions = []
    modified_files = set()
    for t in all_tasks:
        for tu in t.tool_usage:
            name = tu.get("name")
            if name == "deploy_app":
                deploy_app_called = True
                meaningful_actions.append("- Action: `deploy_app` was executed.")
            elif name in ("write_file", "replace", "apply_diff", "patch_file"):
                # Try to extract file path from various possible input schemas
                inp: dict = tu.get("input", {})
                path = (
                    inp.get("path")
                    or inp.get("filename")
                    or inp.get("file_path")
                )
                if path:
                    modified_files.add(path)
                    meaningful_actions.append(f"- Action: `{name}` modified `{path}`")
    return meaningful_actions, modified_files, deploy_app_called



def live_timer(seconds: int | float):
    start_time = time.perf_counter()
    try:
        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed >= seconds:
                break
            print(f"\rElapsed time: {elapsed:.0f} seconds", end="", flush=True)

            time.sleep(0.5)  # Update frequently for a smooth look
    except KeyboardInterrupt:
        print("\nTimer stopped.")
