import sqlite3
import json
from datetime import datetime
import matplotlib.pyplot as plt
import os
import re
import numpy as np
from typing import Optional

DEFAULT_SUCCESS_METRICS = {
    "root_cause_analysis": 0,
    "successful_fix": 0,
    "system_recovery_visible": 0,
}

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        # try common formats if iso fails
        for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
    return None

def _normalize_success_metrics(raw: dict) -> dict:
    return {
        "root_cause_analysis": int(raw.get("root_cause_analysis", 0)),
        "successful_fix": int(raw.get("successful_fix", 0)),
        "system_recovery_visible": int(raw.get("system_recovery_visible", 0)),
    }

def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None

    candidates = []
    if "```json" in text:
        part = text.split("```json")[-1]
        candidates.append(part.split("```")[0].strip())
    candidates.append(text.strip())

    decoder = json.JSONDecoder()
    for candidate in candidates:
        if not candidate:
            continue
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        for idx, ch in enumerate(candidate):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(candidate[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None

def extract_success_metrics(task: dict, db_label: str) -> dict:
    try:
        conversation = json.loads(task['conversation'])
        if not conversation:
            return dict(DEFAULT_SUCCESS_METRICS)

        last = conversation[-1]
        content = last.get('content', "") if isinstance(last, dict) else ""
        if isinstance(content, list):
            content = "\n".join(
                x.get("text", "") for x in content
                if isinstance(x, dict)
            )
        elif not isinstance(content, str):
            content = str(content)

        parsed = _extract_json_object(content)
        if parsed is None:
            # No score JSON in final message is valid for some tasks.
            return dict(DEFAULT_SUCCESS_METRICS)
        return _normalize_success_metrics(parsed)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        print(f"Error parsing success metrics in {db_label} for task: {task.get('id')}")
        return dict(DEFAULT_SUCCESS_METRICS)

def count_tool_stats(messages_history):
    if not messages_history:
        return 0, 0, {}
    try:
        messages = json.loads(messages_history)
    except:
        return 0, 0, {}
    
    uses = 0
    errors = 0
    failing_tools = {} # tool_name -> count
    tool_map = {} # tool_use_id -> tool_name
    
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "tool_use":
                    uses += 1
                    tool_map[item.get("id")] = item.get("name")
                elif item.get("type") == "tool_result":
                    if item.get("is_error") is True:
                        errors += 1
                        tool_name = tool_map.get(item.get("tool_use_id"), "unknown")
                        failing_tools[tool_name] = failing_tools.get(tool_name, 0) + 1
    return uses, errors, failing_tools

def get_metrics(db_path):
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()
    
    tasks = {}
    for row in rows:
        tasks[row['id']] = dict(row)
        tasks[row['id']]['children_ids'] = json.loads(row['children']) if row['children'] else []
        tasks[row['id']]['todo_list_data'] = json.loads(row['todo_list']) if row['todo_list'] else []
        tasks[row['id']]['created_at_dt'] = parse_date(row['created_at'])
        tasks[row['id']]['resolved_at_dt'] = parse_date(row['resolved_at'])
        
    root_metrics = []
    child_metrics = []
    global_failing_tools = {}
    
    def get_subtree_stats(task_id, current_depth):
        task = tasks[task_id]
        all_descendants = []
        max_d = current_depth
        
        for child_id in task['children_ids']:
            if child_id in tasks:
                descendants, child_max_d = get_subtree_stats(child_id, current_depth + 1)
                all_descendants.append(child_id)
                all_descendants.extend(descendants)
                max_d = max(max_d, child_max_d)
        
        return all_descendants, max_d

    for tid, t in tasks.items():
        is_root = not t['parent'] or t['parent'] == ""
        
        created = t['created_at_dt']
        resolved = t['resolved_at_dt']
        ttr = None
        if created and resolved:
            ttr = (resolved - created).total_seconds()
        
        messages_history = t['messages_history']
        trajectory_len = 0
        try:
            trajectory_len = len(json.loads(messages_history))
        except:
            pass
            
        descendants, max_d = get_subtree_stats(tid, 0)
        tool_uses, tool_errors, failing_tools = count_tool_stats(messages_history)
        
        for tool_name, count in failing_tools.items():
            global_failing_tools[tool_name] = global_failing_tools.get(tool_name, 0) + count

        error_rate = (tool_errors / tool_uses * 100) if tool_uses > 0 else 0
        
        metric = {
            "id": tid,
            "ttr": ttr,
            "trajectory_length": trajectory_len,
            "iterations_count": t.get('iterations_count', 0),
            "child_count": len(descendants),
            "max_depth": max_d,
            "tool_uses": tool_uses,
            "tool_errors": tool_errors,
            "tool_error_rate": error_rate,
            "created_at_dt": created
        }
        
        if is_root:
            parts = tid.split('-')
            metric['incident_type'] = parts[1] if len(parts) > 1 else "unknown"
            metric['service_name'] = parts[2] if len(parts) > 2 else "unknown"

            success = extract_success_metrics(t, db_path)
            metric.update(success)
            metric['score'] = metric.get('root_cause_analysis', 0) + metric.get('successful_fix', 0) + metric.get('system_recovery_visible', 0)
            root_metrics.append(metric)
        else:
            metric["todo_count"] = len(t['todo_list_data'])
            child_metrics.append(metric)
    
    conn.close()
    return root_metrics, child_metrics, global_failing_tools

def plot_task_metrics(root_metrics, child_metrics, global_failing_tools, title, output_filename):
    if not root_metrics and not child_metrics:
        print(f"No metrics gathered for {title}.")
        return

    fig, axs = plt.subplots(6, 2, figsize=(15, 36))
    fig.suptitle(f'Task Analysis Metrics - {title}', fontsize=16)

    # TTR
    root_ttrs = [m['ttr'] for m in root_metrics if m['ttr'] is not None]
    child_ttrs = [m['ttr'] for m in child_metrics if m['ttr'] is not None]
    axs[0, 0].hist(root_ttrs, bins=10, alpha=0.5, label='Root Tasks')
    axs[0, 0].hist(child_ttrs, bins=10, alpha=0.5, label='Child Tasks')
    axs[0, 0].set_title('TTR Distribution (seconds)')
    axs[0, 0].legend()

    # Success %
    total_roots = len(root_metrics)
    rca = (sum(m.get('root_cause_analysis', 0) for m in root_metrics) / total_roots) * 100 if total_roots > 0 else 0
    fix = (sum(m.get('successful_fix', 0) for m in root_metrics) / total_roots) * 100 if total_roots > 0 else 0
    rec = (sum(m.get('system_recovery_visible', 0) for m in root_metrics) / total_roots) * 100 if total_roots > 0 else 0
    axs[0, 1].bar(['Root Cause', 'Successful Fix', 'Recovery Visible'], [rca, fix, rec])
    axs[0, 1].set_title('Root Task Success Metrics (%)')
    axs[0, 1].set_ylim(0, 105)

    # Iterations Count Distribution
    root_iters = [m['iterations_count'] for m in root_metrics]
    child_iters = [m['iterations_count'] for m in child_metrics]
    axs[1, 0].hist(root_iters, bins=10, alpha=0.5, label='Root Tasks')
    axs[1, 0].hist(child_iters, bins=10, alpha=0.5, label='Child Tasks')
    axs[1, 0].set_title('Iterations Count Distribution')
    axs[1, 0].legend()

    # Trajectory
    root_traj = [m['trajectory_length'] for m in root_metrics]
    child_traj = [m['trajectory_length'] for m in child_metrics]
    axs[1, 1].boxplot([root_traj, child_traj], tick_labels=['Root', 'Child'])
    axs[1, 1].set_title('Trajectory Length (Message Count)')

    # Tool Uses
    root_tools = [m['tool_uses'] for m in root_metrics]
    child_tools = [m['tool_uses'] for m in child_metrics]
    axs[2, 0].boxplot([root_tools, child_tools], tick_labels=['Root', 'Child'])
    axs[2, 0].set_title('Tool Uses per Task')

    # Tool Errors (Count)
    root_errs = [m['tool_errors'] for m in root_metrics]
    child_errs = [m['tool_errors'] for m in child_metrics]
    axs[2, 1].boxplot([root_errs, child_errs], tick_labels=['Root', 'Child'])
    axs[2, 1].set_title('Tool Errors per Task (Count)')

    # Tool Error Rate (%)
    root_err_rate = [m['tool_error_rate'] for m in root_metrics]
    child_err_rate = [m['tool_error_rate'] for m in child_metrics]
    axs[3, 0].boxplot([root_err_rate, child_err_rate], tick_labels=['Root', 'Child'])
    axs[3, 0].set_title('Tool Error Rate (%) per Task')

    # Child Count
    root_children = [m['child_count'] for m in root_metrics]
    child_children = [m['child_count'] for m in child_metrics]
    axs[3, 1].boxplot([root_children, child_children], tick_labels=['Root', 'Child'])
    axs[3, 1].set_title('Number of Descendants')

    # Max Depth
    root_depth = [m['max_depth'] for m in root_metrics]
    child_depth = [m['max_depth'] for m in child_metrics]
    axs[4, 0].boxplot([root_depth, child_depth], tick_labels=['Root', 'Child'])
    axs[4, 0].set_title('Subtree Max Depth')

    # Todo Count (Child Only)
    if child_metrics:
        child_todos = [m['todo_count'] for m in child_metrics]
        axs[4, 1].hist(child_todos, bins=10)
        axs[4, 1].set_title('Todo Items per Child Task')

    # Top failing tools
    if global_failing_tools:
        sorted_tools = sorted(global_failing_tools.items(), key=lambda x: x[1], reverse=True)[:10]
        names = [x[0] for x in sorted_tools]
        counts = [x[1] for x in sorted_tools]
        axs[5, 0].barh(names, counts)
        axs[5, 0].set_title('Top 10 Failing Tools (Total Errors)')
        axs[5, 0].invert_yaxis()

    # Success Metrics per Incident Category
    categories = ['1', '2', '3', '4']
    metrics_by_cat = {cat: {'rca': [], 'fix': [], 'rec': []} for cat in categories}
    
    for m in root_metrics:
        cat = m['incident_type']
        if cat in metrics_by_cat:
            metrics_by_cat[cat]['rca'].append(m.get('root_cause_analysis', 0))
            metrics_by_cat[cat]['fix'].append(m.get('successful_fix', 0))
            metrics_by_cat[cat]['rec'].append(m.get('system_recovery_visible', 0))
            
    cat_averages = {
        'rca': [np.mean(metrics_by_cat[cat]['rca']) * 100 if metrics_by_cat[cat]['rca'] else 0 for cat in categories],
        'fix': [np.mean(metrics_by_cat[cat]['fix']) * 100 if metrics_by_cat[cat]['fix'] else 0 for cat in categories],
        'rec': [np.mean(metrics_by_cat[cat]['rec']) * 100 if metrics_by_cat[cat]['rec'] else 0 for cat in categories]
    }

    x = np.arange(len(categories))
    width = 0.25
    
    axs[5, 1].bar(x - width, cat_averages['rca'], width, label='Root Cause', color='#66b3ff')
    axs[5, 1].bar(x, cat_averages['fix'], width, label='Successful Fix', color='#99ff99')
    axs[5, 1].bar(x + width, cat_averages['rec'], width, label='Recovery Visible', color='#ffcc99')
    
    axs[5, 1].set_title('Success Metrics % by Incident Type')
    axs[5, 1].set_xticks(x)
    axs[5, 1].set_xticklabels([f"Type {c}" for c in categories])
    axs[5, 1].set_ylim(0, 110)
    axs[5, 1].legend(fontsize='small')

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_filename)
    plt.close()

def plot_success_comparison(root_metrics_no_learning, root_metrics_agent, output_filename):
    # Sort root_metrics_no_learning chronologically
    root_metrics_no_learning.sort(key=lambda x: x['created_at_dt'] if x['created_at_dt'] else datetime.min)
    
    # Map agent metrics by ID for easy lookup
    agent_map = {m['id']: m for m in root_metrics_agent}
    
    master_ids = [m['id'] for m in root_metrics_no_learning]
    n = len(master_ids)
    
    if n == 0:
        print("No root tasks found in no_learning database.")
        return

    def get_color(score):
        cmap = plt.get_cmap('Set1')
        if score == 0: return cmap(0)
        if score < 3: return cmap(4)
        return cmap(2)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(max(12, n * 0.6), 8), sharex=True)
    indices = np.arange(n)
    
    # Top Chart: No Learning
    colors1 = [get_color(t['score']) for t in root_metrics_no_learning]
    bars1 = ax1.bar(indices, np.ones(n), color=colors1, edgecolor='none', width=0.8)
    ax1.set_title("Agent No Learning (Top)")
    ax1.set_ylabel("Success Score")
    ax1.set_yticks([])
    
    for i, bar in enumerate(bars1):
        ax1.text(bar.get_x() + bar.get_width()/2., 1.05,
                f"{root_metrics_no_learning[i]['score']}/3", ha='center', va='bottom', fontsize=8)

    # Bottom Chart: Agent
    agent_data = [agent_map.get(tid) for tid in master_ids]
    colors2 = [get_color(t['score']) if t else (0,0,0,0) for t in agent_data]
    bars2 = ax2.bar(indices, [1 if t else 0 for t in agent_data], color=colors2, edgecolor='none', width=0.8)
    ax2.set_title("Agent (Bottom)")
    ax2.set_ylabel("Success Score")
    ax2.set_yticks([])

    for i, bar in enumerate(bars2):
        if agent_data[i]:
            ax2.text(bar.get_x() + bar.get_width()/2., 1.05,
                    f"{agent_data[i]['score']}/3", ha='center', va='bottom', fontsize=8)
        else:
            ax2.text(bar.get_x() + bar.get_width()/2., 0.5, "N/A", ha='center', va='center', fontsize=8, color='gray')

    # Shared X labels
    labels = [f"{t['service_name']}\n{t['incident_type']}" for t in root_metrics_no_learning]
    ax2.set_xticks(indices)
    ax2.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)

    # Add vertical lines every 5th bar
    for i in range(4, n - 1, 5):
        pos = i + 0.5
        ax1.axvline(x=pos, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax2.axvline(x=pos, color='black', linestyle='--', linewidth=1, alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(output_filename)
    plt.close()

def analyze():
    db_no_learning = "./agent_no_learning.db"
    db_agent = "./agent.db"
    
    metrics_no_learning = get_metrics(db_no_learning)
    metrics_agent = get_metrics(db_agent)
    
    if metrics_no_learning:
        print("Plotting task_metrics_no_learning.png")
        plot_task_metrics(*metrics_no_learning, "No Learning", "task_metrics_no_learning.png")
    
    if metrics_agent:
        print("Plotting task_metrics_agent.png")
        plot_task_metrics(*metrics_agent, "Agent", "task_metrics_agent.png")
        
    if metrics_no_learning and metrics_agent:
        print("Plotting success_chronological_all.png")
        plot_success_comparison(metrics_no_learning[0], metrics_agent[0], "success_chronological_all.png")

if __name__ == "__main__":
    analyze()
