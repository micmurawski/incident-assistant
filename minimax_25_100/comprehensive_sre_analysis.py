"""
comprehensive_sre_analysis.py - Complete SRE Agent Pattern Analysis

This script provides comprehensive analysis of SRE agent patterns to identify
what leads to success and failure in incident resolution.

Key Analyses:
1. N-gram analysis of tool call sequences 
2. Task assignment depth and width patterns
3. Success correlation analysis for individual metrics
4. Incident type specific patterns
5. Statistical significance testing

The script is designed to be configurable and work with different datasets.
"""

import sqlite3
import json
import os
import argparse
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from collections import defaultdict, Counter
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Set
from scipy import stats
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

# Style configuration
sns.set_theme(style="whitegrid", font_scale=1.1)
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.dpi": 200,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
})

PALETTE = {
    "success": "#16A34A",
    "failure": "#DC2626", 
    "partial": "#F59E0B",
    "high": "#059669",
    "medium": "#D97706",
    "low": "#EF4444",
    "learning": "#2563EB",
    "no_learning": "#F59E0B",
}

# =============================================================================
# Core Data Structures and Constants
# =============================================================================

DEFAULT_SUCCESS_METRICS = {
    "root_cause_analysis": 0,
    "successful_fix": 0,
    "system_recovery_visible": 0,
}

SUCCESS_LEVELS = {
    0: "failure",
    1: "low", 
    2: "medium",
    3: "high"
}

# Invalid tools that should be excluded from analysis
INVALID_TOOLS = {
    "assign_issue", "read_1file", "read_issue", "assign__task"
}

# Success criteria definitions
SUCCESS_CRITERIA = {
    "rca_success": lambda ep: ep["rca"] == 1,          # Root Cause Analysis successful
    "fix_success": lambda ep: ep["fix"] == 1,          # Fix implementation successful  
    "recovery_success": lambda ep: ep["recovery"] == 1, # System recovery visible
    "score_ge_1": lambda ep: ep["score"] >= 1,         # At least 1 success metric achieved
    "score_ge_2": lambda ep: ep["score"] >= 2,         # At least 2 success metrics achieved
    "score_eq_3": lambda ep: ep["score"] == 3,         # All 3 success metrics achieved (perfect score)
    "composite_success": lambda ep: ep["score"] >= 2,  # Primary definition: score >= 2 (same as score_ge_2)
}

# =============================================================================
# Utility Functions
# =============================================================================

def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string with multiple format attempts."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
    return None

def _extract_json_object(text: str) -> Optional[dict]:
    """Extract JSON object from text with various fallback strategies."""
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

def extract_success_metrics(task: dict) -> dict:
    """Extract success metrics from task conversation."""
    try:
        conversation = json.loads(task["conversation"])
        if not conversation:
            return dict(DEFAULT_SUCCESS_METRICS)
        
        last = conversation[-1]
        content = last.get("content", "") if isinstance(last, dict) else ""
        if isinstance(content, list):
            content = "\n".join(
                x.get("text", "") for x in content if isinstance(x, dict)
            )
        elif not isinstance(content, str):
            content = str(content)
        
        parsed = _extract_json_object(content)
        if parsed is None:
            return dict(DEFAULT_SUCCESS_METRICS)
        
        return {
            "root_cause_analysis": int(parsed.get("root_cause_analysis", 0)),
            "successful_fix": int(parsed.get("successful_fix", 0)),
            "system_recovery_visible": int(parsed.get("system_recovery_visible", 0)),
        }
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        return dict(DEFAULT_SUCCESS_METRICS)

# =============================================================================
# Data Loading and Processing
# =============================================================================

class EpisodeDataLoader:
    """Handles loading and preprocessing of episode data from databases."""
    
    def __init__(self, db_path: str, db_label: str):
        self.db_path = db_path
        self.db_label = db_label
        
    def load_episodes(self) -> List[dict]:
        """Load episodes with comprehensive task tree and message analysis."""
        if not os.path.exists(self.db_path):
            print(f"Database not found at {self.db_path}")
            return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks")
        rows = cursor.fetchall()
        
        # Build task dictionary
        tasks = {}
        for row in rows:
            tasks[row["id"]] = dict(row)
            tasks[row["id"]]["children_ids"] = (
                json.loads(row["children"]) if row["children"] else []
            )
            tasks[row["id"]]["created_at_dt"] = parse_date(row["created_at"])
            tasks[row["id"]]["resolved_at_dt"] = parse_date(row["resolved_at"])
        
        episodes = []
        for tid, task in tasks.items():
            is_root = not task["parent"] or task["parent"] == ""
            if is_root:
                episode = self._process_episode(tid, task, tasks)
                episodes.append(episode)
        
        conn.close()
        return episodes
    
    def _process_episode(self, task_id: str, task: dict, tasks: dict) -> dict:
        """Process individual episode with comprehensive metrics."""
        # Extract success metrics
        success = extract_success_metrics(task)
        score = sum(success.values())
        
        # Calculate task tree metrics
        tree_metrics = self._calculate_tree_metrics(task_id, tasks)
        
        # Extract message and tool sequences
        sequences = self._extract_sequences(task)
        
        # Calculate timing metrics
        created = task["created_at_dt"]
        resolved = task["resolved_at_dt"]
        duration = (resolved - created).total_seconds() if created and resolved else None
        
        # Extract incident information
        parts = task_id.split("-")
        incident_type = parts[1] if len(parts) > 1 else "unknown"
        service_name = parts[2] if len(parts) > 2 else "unknown"
        
        return {
            "id": task_id,
            "db_label": self.db_label,
            "score": score,
            "rca": success.get("root_cause_analysis", 0),
            "fix": success.get("successful_fix", 0),
            "recovery": success.get("system_recovery_visible", 0),
            "success_level": SUCCESS_LEVELS[score],
            "incident_type": incident_type,
            "service_name": service_name,
            "duration_seconds": duration,
            "created_at": created,
            "resolved_at": resolved,
            
            # Tree structure metrics
            "max_depth": tree_metrics["max_depth"],
            "total_children": tree_metrics["total_children"],
            "width_at_depth": tree_metrics["width_at_depth"],
            "avg_branching_factor": tree_metrics["avg_branching_factor"],
            
            # Message and tool metrics
            "total_messages": sequences["total_messages"],
            "user_messages": sequences["user_messages"], 
            "assistant_messages": sequences["assistant_messages"],
            "tool_sequence": sequences["tool_sequence"],
            "assign_sequence": sequences["assign_sequence"],
            "total_tools": len(sequences["tool_sequence"]),
            "total_assigns": len(sequences["assign_sequence"]),
            "unique_tools": len(set(t["tool"] for t in sequences["tool_sequence"])),
            "unique_assignees": len(set(a["assignee"] for a in sequences["assign_sequence"])),
            "tool_errors": sequences["tool_errors"],
            "error_rate": len(sequences["tool_errors"]) / len(sequences["tool_sequence"]) if sequences["tool_sequence"] else 0,
            "iterations": task.get("iterations_count", 0),
        }
    
    def _calculate_tree_metrics(self, root_id: str, tasks: dict) -> dict:
        """Calculate comprehensive task tree metrics."""
        def get_subtree_stats(task_id: str, depth: int = 0) -> tuple:
            task = tasks[task_id]
            max_depth = depth
            descendants = []
            width_at_depth = defaultdict(int)
            width_at_depth[depth] = 1
            
            children = task["children_ids"]
            if children:
                for child_id in children:
                    if child_id in tasks:
                        child_descendants, child_max_depth, child_widths = get_subtree_stats(child_id, depth + 1)
                        descendants.append(child_id)
                        descendants.extend(child_descendants)
                        max_depth = max(max_depth, child_max_depth)
                        for d, w in child_widths.items():
                            width_at_depth[d] += w
            
            return descendants, max_depth, width_at_depth
        
        descendants, max_depth, width_at_depth = get_subtree_stats(root_id)
        
        # Calculate average branching factor
        total_branching = 0
        internal_nodes = 0
        
        def calc_branching(task_id: str):
            nonlocal total_branching, internal_nodes
            task = tasks[task_id]
            children_count = len(task["children_ids"])
            if children_count > 0:
                total_branching += children_count
                internal_nodes += 1
                for child_id in task["children_ids"]:
                    if child_id in tasks:
                        calc_branching(child_id)
        
        calc_branching(root_id)
        avg_branching_factor = total_branching / internal_nodes if internal_nodes > 0 else 0
        
        return {
            "max_depth": max_depth,
            "total_children": len(descendants),
            "width_at_depth": dict(width_at_depth),
            "avg_branching_factor": avg_branching_factor,
            "max_width": max(width_at_depth.values()) if width_at_depth else 0,
        }
    
    def _extract_sequences(self, task: dict) -> dict:
        """Extract tool and assignment sequences from messages."""
        tool_sequence = []
        assign_sequence = []
        tool_errors = []
        
        try:
            messages_history = json.loads(task["messages_history"]) if task["messages_history"] else []
            
            for i, msg in enumerate(messages_history):
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if item.get("type") == "tool_use":
                            tool_name = item.get("name", "unknown")
                            tool_sequence.append({
                                "position": i,
                                "tool": tool_name,
                                "id": item.get("id"),
                                "input": item.get("input", {})
                            })
                            
                            # Extract assignment details
                            if tool_name == "assign_task":
                                tool_input = item.get("input", {})
                                assign_sequence.append({
                                    "position": i,
                                    "assignee": tool_input.get("assignee", "unknown"),
                                    "description": tool_input.get("description", ""),
                                    "task_id": tool_input.get("task_id", "")
                                })
                                
                        elif item.get("type") == "tool_result":
                            if item.get("is_error"):
                                tool_errors.append({
                                    "position": i,
                                    "tool_id": item.get("tool_use_id"),
                                    "error": True
                                })
            
            total_messages = len(messages_history)
            user_messages = sum(1 for m in messages_history if m.get("role") == "user")
            assistant_messages = sum(1 for m in messages_history if m.get("role") == "assistant")
            
        except (json.JSONDecodeError, TypeError):
            messages_history = []
            total_messages = user_messages = assistant_messages = 0
        
        return {
            "tool_sequence": tool_sequence,
            "assign_sequence": assign_sequence,
            "tool_errors": tool_errors,
            "total_messages": total_messages,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
        }

# =============================================================================
# N-gram Pattern Analysis
# =============================================================================

class NGramAnalyzer:
    """Analyzes n-gram patterns in tool usage and task assignments."""
    
    def __init__(self, episodes: List[dict]):
        self.episodes = episodes
        
    def extract_tool_ngrams(self, episodes: List[dict], n: int) -> Counter:
        """Extract n-grams from tool sequences."""
        ngrams = Counter()
        
        for episode in episodes:
            tools = [t["tool"] for t in episode["tool_sequence"] 
                    if t["tool"] not in INVALID_TOOLS]
            
            if len(tools) >= n:
                for i in range(len(tools) - n + 1):
                    ngram = tuple(tools[i:i+n])
                    ngrams[ngram] += 1
        
        return ngrams
    
    def extract_assignment_ngrams(self, episodes: List[dict], n: int) -> Counter:
        """Extract n-grams from assignment sequences."""
        ngrams = Counter()
        
        for episode in episodes:
            assignees = [a["assignee"] for a in episode["assign_sequence"]]
            
            if len(assignees) >= n:
                for i in range(len(assignees) - n + 1):
                    ngram = tuple(assignees[i:i+n])
                    ngrams[ngram] += 1
        
        return ngrams
    
    def extract_mixed_ngrams(self, episodes: List[dict], n: int) -> Counter:
        """Extract n-grams from combined tool and assignment sequences."""
        ngrams = Counter()
        
        for episode in episodes:
            # Combine tool uses and assignments chronologically
            combined = []
            
            for tool_item in episode["tool_sequence"]:
                if tool_item["tool"] not in INVALID_TOOLS:
                    combined.append(("tool", tool_item["tool"], tool_item["position"]))
            
            for assign_item in episode["assign_sequence"]:
                combined.append(("assign", assign_item["assignee"], assign_item["position"]))
            
            # Sort by position
            combined.sort(key=lambda x: x[2])
            sequence = [f"{item[0]}:{item[1]}" for item in combined]
            
            if len(sequence) >= n:
                for i in range(len(sequence) - n + 1):
                    ngram = tuple(sequence[i:i+n])
                    ngrams[ngram] += 1
        
        return ngrams
    
    def analyze_patterns_by_criterion(self, criterion_name: str, criterion_func, min_frequency: int = 3):
        """Analyze patterns for a specific success criterion."""
        successful = [ep for ep in self.episodes if criterion_func(ep)]
        failed = [ep for ep in self.episodes if not criterion_func(ep)]
        
        results = {
            "criterion": criterion_name,
            "success_count": len(successful),
            "failure_count": len(failed),
            "success_rate": len(successful) / len(self.episodes) if self.episodes else 0,
            "tool_patterns": {},
            "assignment_patterns": {},
            "mixed_patterns": {},
        }
        
        # Analyze tool, assignment, and mixed patterns for n=2,3,4
        for n in range(2, 5):
            success_tools = self.extract_tool_ngrams(successful, n)
            failed_tools = self.extract_tool_ngrams(failed, n)
            
            success_assigns = self.extract_assignment_ngrams(successful, n)
            failed_assigns = self.extract_assignment_ngrams(failed, n)
            
            success_mixed = self.extract_mixed_ngrams(successful, n)
            failed_mixed = self.extract_mixed_ngrams(failed, n)
            
            results["tool_patterns"][n] = self._compare_patterns(success_tools, failed_tools, min_frequency)
            results["assignment_patterns"][n] = self._compare_patterns(success_assigns, failed_assigns, min_frequency)
            results["mixed_patterns"][n] = self._compare_patterns(success_mixed, failed_mixed, min_frequency)
        
        return results
    
    def _compare_patterns(self, success_patterns: Counter, failed_patterns: Counter, min_frequency: int) -> dict:
        """Compare success vs failure patterns."""
        all_patterns = set(success_patterns.keys()) | set(failed_patterns.keys())
        
        pattern_stats = []
        for pattern in all_patterns:
            s_count = success_patterns.get(pattern, 0)
            f_count = failed_patterns.get(pattern, 0)
            total = s_count + f_count
            
            if total >= min_frequency:
                success_rate = s_count / total
                pattern_stats.append({
                    "pattern": pattern,
                    "success_count": s_count,
                    "failure_count": f_count,
                    "total_count": total,
                    "success_rate": success_rate,
                })
        
        # Sort by success rate, then by frequency
        pattern_stats.sort(key=lambda x: (x["success_rate"], x["total_count"]), reverse=True)
        
        return {
            "top_success_patterns": pattern_stats[:10],
            "top_failure_patterns": sorted(pattern_stats, key=lambda x: x["success_rate"])[:10],
            "most_frequent": sorted(pattern_stats, key=lambda x: x["total_count"], reverse=True)[:10],
        }

# =============================================================================
# Depth and Width Analysis
# =============================================================================

class TreeStructureAnalyzer:
    """Analyzes task tree structure patterns and correlations with success."""
    
    def __init__(self, episodes: List[dict]):
        self.episodes = episodes
        
    def analyze_depth_correlation(self, criterion_name: str, criterion_func) -> dict:
        """Analyze correlation between tree depth and success."""
        successful = [ep for ep in self.episodes if criterion_func(ep)]
        failed = [ep for ep in self.episodes if not criterion_func(ep)]
        
        success_depths = [ep["max_depth"] for ep in successful]
        failed_depths = [ep["max_depth"] for ep in failed]
        all_depths = [ep["max_depth"] for ep in self.episodes]
        success_binary = [1 if criterion_func(ep) else 0 for ep in self.episodes]
        
        # Calculate correlations
        pearson_r, pearson_p = stats.pearsonr(all_depths, success_binary)
        spearman_r, spearman_p = stats.spearmanr(all_depths, success_binary)
        
        # Statistical comparison
        if success_depths and failed_depths:
            t_stat, t_p = stats.ttest_ind(success_depths, failed_depths)
        else:
            t_stat = t_p = None
        
        return {
            "criterion": criterion_name,
            "pearson_correlation": {"r": pearson_r, "p": pearson_p},
            "spearman_correlation": {"r": spearman_r, "p": spearman_p},
            "t_test": {"statistic": t_stat, "p_value": t_p} if t_stat else None,
            "success_depths": {
                "mean": np.mean(success_depths) if success_depths else 0,
                "median": np.median(success_depths) if success_depths else 0,
                "std": np.std(success_depths) if success_depths else 0,
                "min": min(success_depths) if success_depths else 0,
                "max": max(success_depths) if success_depths else 0,
            },
            "failed_depths": {
                "mean": np.mean(failed_depths) if failed_depths else 0,
                "median": np.median(failed_depths) if failed_depths else 0,
                "std": np.std(failed_depths) if failed_depths else 0,
                "min": min(failed_depths) if failed_depths else 0,
                "max": max(failed_depths) if failed_depths else 0,
            },
        }
    
    def analyze_width_correlation(self, criterion_name: str, criterion_func) -> dict:
        """Analyze correlation between tree width (children count) and success."""
        successful = [ep for ep in self.episodes if criterion_func(ep)]
        failed = [ep for ep in self.episodes if not criterion_func(ep)]
        
        success_widths = [ep["total_children"] for ep in successful]
        failed_widths = [ep["total_children"] for ep in failed]
        all_widths = [ep["total_children"] for ep in self.episodes]
        success_binary = [1 if criterion_func(ep) else 0 for ep in self.episodes]
        
        # Calculate correlations
        pearson_r, pearson_p = stats.pearsonr(all_widths, success_binary)
        spearman_r, spearman_p = stats.spearmanr(all_widths, success_binary)
        
        # Statistical comparison
        if success_widths and failed_widths:
            t_stat, t_p = stats.ttest_ind(success_widths, failed_widths)
        else:
            t_stat = t_p = None
        
        return {
            "criterion": criterion_name,
            "pearson_correlation": {"r": pearson_r, "p": pearson_p},
            "spearman_correlation": {"r": spearman_r, "p": spearman_p},
            "t_test": {"statistic": t_stat, "p_value": t_p} if t_stat else None,
            "success_widths": {
                "mean": np.mean(success_widths) if success_widths else 0,
                "median": np.median(success_widths) if success_widths else 0,
                "std": np.std(success_widths) if success_widths else 0,
                "min": min(success_widths) if success_widths else 0,
                "max": max(success_widths) if success_widths else 0,
            },
            "failed_widths": {
                "mean": np.mean(failed_widths) if failed_widths else 0,
                "median": np.median(failed_widths) if failed_widths else 0,
                "std": np.std(failed_widths) if failed_widths else 0,
                "min": min(failed_widths) if failed_widths else 0,
                "max": max(failed_widths) if failed_widths else 0,
            },
        }
    
    def analyze_branching_patterns(self, criterion_name: str, criterion_func) -> dict:
        """Analyze branching factor patterns."""
        successful = [ep for ep in self.episodes if criterion_func(ep)]
        failed = [ep for ep in self.episodes if not criterion_func(ep)]
        
        success_branching = [ep["avg_branching_factor"] for ep in successful]
        failed_branching = [ep["avg_branching_factor"] for ep in failed]
        
        return {
            "criterion": criterion_name,
            "success_branching": {
                "mean": np.mean(success_branching) if success_branching else 0,
                "median": np.median(success_branching) if success_branching else 0,
                "std": np.std(success_branching) if success_branching else 0,
            },
            "failed_branching": {
                "mean": np.mean(failed_branching) if failed_branching else 0,
                "median": np.median(failed_branching) if failed_branching else 0,
                "std": np.std(failed_branching) if failed_branching else 0,
            },
        }

# =============================================================================
# Visualization and Reporting
# =============================================================================

class AnalysisVisualizer:
    """Creates comprehensive visualizations of analysis results."""
    
    def __init__(self, output_dir: str = "./figures"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def create_correlation_heatmap(self, episodes: List[dict], filename: str = "correlation_heatmap.png"):
        """Create correlation heatmap of structural metrics vs success."""
        df = pd.DataFrame(episodes)
        
        # Select metrics for correlation
        structure_cols = ["max_depth", "total_children", "avg_branching_factor", "total_tools"]
        success_cols = ["score", "rca", "fix", "recovery"]
        
        corr_data = df[structure_cols + success_cols]
        correlation_matrix = corr_data.corr()
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(correlation_matrix, annot=True, cmap="RdBu_r", center=0,
                   square=True, fmt=".3f", cbar_kws={"shrink": 0.8})
        plt.title("Correlation Matrix: Structure vs Success Metrics")
        plt.tight_layout()
        plt.savefig(f"{self.output_dir}/{filename}")
        plt.close()
    
    def create_success_distribution(self, episodes: List[dict], filename: str = "success_distribution.png"):
        """Create success score distribution visualization."""
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        fig.suptitle("Success Metrics Distribution", fontsize=16, fontweight="bold")
        
        # Overall score distribution
        scores = [ep["score"] for ep in episodes]
        score_counts = Counter(scores)
        
        ax = axes[0, 0]
        bars = ax.bar(score_counts.keys(), score_counts.values(),
                     color=[PALETTE["failure"] if s < 2 else PALETTE["success"] for s in score_counts.keys()])
        ax.set_xlabel("Composite Score")
        ax.set_ylabel("Episode Count")
        ax.set_title("Overall Score Distribution")
        ax.set_xticks(list(range(4)))
        
        # Individual metrics
        for i, (metric, title) in enumerate([("rca", "Root Cause Analysis"), 
                                           ("fix", "Successful Fix"), 
                                           ("recovery", "System Recovery")]):
            ax = axes[0, 1] if i == 0 else axes[1, i-1]
            values = [ep[metric] for ep in episodes]
            value_counts = Counter(values)
            
            colors = [PALETTE["failure"] if v == 0 else PALETTE["success"] for v in value_counts.keys()]
            ax.bar(value_counts.keys(), value_counts.values(), color=colors)
            ax.set_xlabel("Success (0=No, 1=Yes)")
            ax.set_ylabel("Episode Count")
            ax.set_title(title)
            ax.set_xticks([0, 1])
        
        plt.tight_layout()
        plt.savefig(f"{self.output_dir}/{filename}")
        plt.close()
    
    def create_depth_width_analysis(self, episodes: List[dict], filename: str = "depth_width_analysis.png"):
        """Create depth vs width analysis visualization."""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle("Task Tree Structure Analysis", fontsize=16, fontweight="bold")
        
        # Prepare data
        df = pd.DataFrame(episodes)
        df["success_binary"] = df["score"] >= 2
        
        # Depth vs Success scatter
        ax = axes[0, 0]
        successful = df[df["success_binary"]]
        failed = df[~df["success_binary"]]
        
        ax.scatter(successful["max_depth"], successful["score"], 
                  alpha=0.6, color=PALETTE["success"], label="Successful", s=40)
        ax.scatter(failed["max_depth"], failed["score"], 
                  alpha=0.6, color=PALETTE["failure"], label="Failed", s=40)
        ax.set_xlabel("Max Depth")
        ax.set_ylabel("Composite Score")
        ax.set_title("Depth vs Success")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Width vs Success scatter
        ax = axes[0, 1]
        ax.scatter(successful["total_children"], successful["score"], 
                  alpha=0.6, color=PALETTE["success"], label="Successful", s=40)
        ax.scatter(failed["total_children"], failed["score"], 
                  alpha=0.6, color=PALETTE["failure"], label="Failed", s=40)
        ax.set_xlabel("Total Children")
        ax.set_ylabel("Composite Score")
        ax.set_title("Width vs Success")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Depth distribution by success
        ax = axes[1, 0]
        success_depths = successful["max_depth"]
        failed_depths = failed["max_depth"]
        
        ax.hist(success_depths, bins=15, alpha=0.7, label="Successful", color=PALETTE["success"])
        ax.hist(failed_depths, bins=15, alpha=0.7, label="Failed", color=PALETTE["failure"])
        ax.set_xlabel("Max Depth")
        ax.set_ylabel("Episode Count")
        ax.set_title("Depth Distribution")
        ax.legend()
        
        # Width distribution by success
        ax = axes[1, 1]
        success_widths = successful["total_children"]
        failed_widths = failed["total_children"]
        
        ax.hist(success_widths, bins=15, alpha=0.7, label="Successful", color=PALETTE["success"])
        ax.hist(failed_widths, bins=15, alpha=0.7, label="Failed", color=PALETTE["failure"])
        ax.set_xlabel("Total Children")
        ax.set_ylabel("Episode Count")
        ax.set_title("Width Distribution")
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(f"{self.output_dir}/{filename}")
        plt.close()
    
    def create_learning_comparison_visualizations(self, episodes: List[dict]):
        """Create learning vs no-learning comparison visualizations."""
        # Separate episodes by learning status
        learning_episodes = [ep for ep in episodes if "learning" in ep["db_label"].lower() and "no" not in ep["db_label"].lower()]
        no_learning_episodes = [ep for ep in episodes if "no" in ep["db_label"].lower()]
        
        if not learning_episodes or not no_learning_episodes:
            print("Insufficient data for learning comparison visualizations")
            return
        
        # Figure 1: Success rate comparison
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle("Learning vs No-Learning Agent Comparison", fontsize=16, fontweight="bold")
        
        # Success rate comparison by metric
        ax = axes[0, 0]
        success_criteria_names = ["RCA", "Fix", "Recovery", "Score≥2"]
        success_criteria_funcs = [
            lambda ep: ep["rca"] == 1,
            lambda ep: ep["fix"] == 1,
            lambda ep: ep["recovery"] == 1,
            lambda ep: ep["score"] >= 2
        ]
        
        learning_rates = []
        no_learning_rates = []
        
        for criterion_func in success_criteria_funcs:
            learning_success = sum(1 for ep in learning_episodes if criterion_func(ep))
            no_learning_success = sum(1 for ep in no_learning_episodes if criterion_func(ep))
            
            learning_rate = learning_success / len(learning_episodes) * 100
            no_learning_rate = no_learning_success / len(no_learning_episodes) * 100
            
            learning_rates.append(learning_rate)
            no_learning_rates.append(no_learning_rate)
        
        x = np.arange(len(success_criteria_names))
        width = 0.35
        
        bars1 = ax.bar(x - width/2, learning_rates, width, label='Learning', color=PALETTE["learning"], alpha=0.8)
        bars2 = ax.bar(x + width/2, no_learning_rates, width, label='No-Learning', color=PALETTE["no_learning"], alpha=0.8)
        
        ax.set_xlabel('Success Metrics')
        ax.set_ylabel('Success Rate (%)')
        ax.set_title('Success Rate Comparison')
        ax.set_xticks(x)
        ax.set_xticklabels(success_criteria_names)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Add value labels on bars
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax.annotate(f'{height:.1f}%',
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom', fontsize=8)
        
        # Depth comparison
        ax = axes[0, 1]
        learning_depths = [ep["max_depth"] for ep in learning_episodes]
        no_learning_depths = [ep["max_depth"] for ep in no_learning_episodes]
        
        ax.hist(learning_depths, bins=15, alpha=0.7, label="Learning", color=PALETTE["learning"])
        ax.hist(no_learning_depths, bins=15, alpha=0.7, label="No-Learning", color=PALETTE["no_learning"])
        ax.set_xlabel("Max Depth")
        ax.set_ylabel("Episode Count")
        ax.set_title("Task Tree Depth Distribution")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Width comparison
        ax = axes[1, 0]
        learning_widths = [ep["total_children"] for ep in learning_episodes]
        no_learning_widths = [ep["total_children"] for ep in no_learning_episodes]
        
        ax.hist(learning_widths, bins=15, alpha=0.7, label="Learning", color=PALETTE["learning"])
        ax.hist(no_learning_widths, bins=15, alpha=0.7, label="No-Learning", color=PALETTE["no_learning"])
        ax.set_xlabel("Total Children")
        ax.set_ylabel("Episode Count")
        ax.set_title("Task Tree Width Distribution")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Depth vs Success scatter
        ax = axes[1, 1]
        learning_df = pd.DataFrame(learning_episodes)
        no_learning_df = pd.DataFrame(no_learning_episodes)
        
        learning_successful = learning_df[learning_df["score"] >= 2]
        learning_failed = learning_df[learning_df["score"] < 2]
        no_learning_successful = no_learning_df[no_learning_df["score"] >= 2]
        no_learning_failed = no_learning_df[no_learning_df["score"] < 2]
        
        # Plot successful episodes (score >= 2)
        ax.scatter(learning_successful["max_depth"], learning_successful["score"], 
                  alpha=0.7, color=PALETTE["learning"], marker='o', s=40, label="Learning (Score ≥ 2)")
        ax.scatter(no_learning_successful["max_depth"], no_learning_successful["score"], 
                  alpha=0.7, color=PALETTE["no_learning"], marker='o', s=40, label="No-Learning (Score ≥ 2)")
        
        # Plot failed episodes (score < 2)
        ax.scatter(learning_failed["max_depth"], learning_failed["score"], 
                  alpha=0.4, color=PALETTE["learning"], marker='x', s=30, label="Learning (Score < 2)")
        ax.scatter(no_learning_failed["max_depth"], no_learning_failed["score"], 
                  alpha=0.4, color=PALETTE["no_learning"], marker='x', s=30, label="No-Learning (Score < 2)")
        
        ax.set_xlabel("Max Depth")
        ax.set_ylabel("Composite Score")
        ax.set_title("Depth vs Success by Agent Type")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f"{self.output_dir}/learning_comparison_analysis.png")
        plt.close()
        
        print("  - learning_comparison_analysis.png")

# =============================================================================
# Main Analysis Engine
# =============================================================================

class ComprehensiveAnalyzer:
    """Main analysis engine that coordinates all analyses."""
    
    def __init__(self, db_paths: Dict[str, str], output_dir: str = "./figures"):
        self.db_paths = db_paths
        self.output_dir = output_dir
        self.episodes = []
        self.ngram_analyzer = None
        self.tree_analyzer = None
        self.visualizer = AnalysisVisualizer(output_dir)
        
    def load_all_data(self):
        """Load data from all specified databases."""
        print("Loading episode data...")
        
        for label, db_path in self.db_paths.items():
            print(f"  Loading from {label}: {db_path}")
            loader = EpisodeDataLoader(db_path, label)
            episodes = loader.load_episodes()
            self.episodes.extend(episodes)
            print(f"    Loaded {len(episodes)} episodes")
        
        print(f"Total episodes loaded: {len(self.episodes)}")
        
        # Initialize analyzers
        self.ngram_analyzer = NGramAnalyzer(self.episodes)
        self.tree_analyzer = TreeStructureAnalyzer(self.episodes)
    
    def run_comprehensive_analysis(self):
        """Run all analyses and generate comprehensive report."""
        print("\n" + "="*80)
        print(" COMPREHENSIVE SRE AGENT ANALYSIS")
        print("="*80)
        
        # Basic statistics
        self._print_basic_statistics()
        
        # Check if we have learning vs no-learning comparison
        db_labels = set(ep["db_label"] for ep in self.episodes)
        has_learning_comparison = len(db_labels) > 1 and any("learning" in label.lower() for label in db_labels)
        
        if has_learning_comparison:
            # Separate learning comparison analysis
            self._run_learning_comparison_analysis()
        
        # Analyze patterns for each success criterion
        results = {}
        for criterion_name, criterion_func in SUCCESS_CRITERIA.items():
            print(f"\n{'='*60}")
            print(f" ANALYSIS FOR: {criterion_name.upper()}")
            print(f"{'='*60}")
            
            # N-gram pattern analysis
            ngram_results = self.ngram_analyzer.analyze_patterns_by_criterion(
                criterion_name, criterion_func, min_frequency=3
            )
            
            # Tree structure analysis
            depth_results = self.tree_analyzer.analyze_depth_correlation(
                criterion_name, criterion_func
            )
            width_results = self.tree_analyzer.analyze_width_correlation(
                criterion_name, criterion_func
            )
            branching_results = self.tree_analyzer.analyze_branching_patterns(
                criterion_name, criterion_func
            )
            
            results[criterion_name] = {
                "ngrams": ngram_results,
                "depth": depth_results,
                "width": width_results,
                "branching": branching_results,
            }
            
            # Print results for this criterion
            self._print_criterion_results(criterion_name, results[criterion_name])
        
        # Create visualizations
        print(f"\n{'='*60}")
        print(" GENERATING VISUALIZATIONS")
        print(f"{'='*60}")
        
        self.visualizer.create_correlation_heatmap(self.episodes)
        self.visualizer.create_success_distribution(self.episodes)
        self.visualizer.create_depth_width_analysis(self.episodes)
        
        if has_learning_comparison:
            self.visualizer.create_learning_comparison_visualizations(self.episodes)
        
        print(f"Visualizations saved to: {self.output_dir}")
        
        # Generate summary insights
        self._print_summary_insights(results)
        
        if has_learning_comparison:
            self._print_learning_comparison_insights()
        
        return results
    
    def _print_basic_statistics(self):
        """Print basic statistics about the dataset."""
        print(f"\nDATASET OVERVIEW:")
        print(f"  Total episodes: {len(self.episodes)}")
        
        # Episodes by database
        db_counts = Counter(ep["db_label"] for ep in self.episodes)
        for db_label, count in db_counts.items():
            print(f"  {db_label}: {count} episodes")
        
        # Success rate statistics
        print(f"\nSUCCESS RATE OVERVIEW:")
        for criterion_name, criterion_func in SUCCESS_CRITERIA.items():
            successful_count = sum(1 for ep in self.episodes if criterion_func(ep))
            rate = successful_count / len(self.episodes) * 100 if self.episodes else 0
            print(f"  {criterion_name}: {successful_count}/{len(self.episodes)} ({rate:.1f}%)")
        
        # Score distribution
        print(f"\nSCORE DISTRIBUTION:")
        score_counts = Counter(ep["score"] for ep in self.episodes)
        for score in sorted(score_counts.keys()):
            count = score_counts[score]
            pct = count / len(self.episodes) * 100
            print(f"  Score {score}: {count} episodes ({pct:.1f}%)")
    
    def _print_criterion_results(self, criterion_name: str, results: dict):
        """Print results for a specific success criterion."""
        ngram_data = results["ngrams"]
        depth_data = results["depth"]
        width_data = results["width"]
        
        success_rate = ngram_data["success_rate"] * 100
        print(f"\nSuccess rate for {criterion_name}: {ngram_data['success_count']}/{ngram_data['success_count'] + ngram_data['failure_count']} ({success_rate:.1f}%)")
        
        # Depth correlation results
        print(f"\nDEPTH CORRELATION:")
        depth_corr = depth_data["pearson_correlation"]
        depth_sig = "***" if depth_corr["p"] < 0.001 else "**" if depth_corr["p"] < 0.01 else "*" if depth_corr["p"] < 0.05 else ""
        print(f"  Pearson r = {depth_corr['r']:.3f} (p = {depth_corr['p']:.3f}){depth_sig}")
        print(f"  Successful depth: μ={depth_data['success_depths']['mean']:.2f}, σ={depth_data['success_depths']['std']:.2f}")
        print(f"  Failed depth: μ={depth_data['failed_depths']['mean']:.2f}, σ={depth_data['failed_depths']['std']:.2f}")
        
        # Width correlation results  
        print(f"\nWIDTH CORRELATION:")
        width_corr = width_data["pearson_correlation"]
        width_sig = "***" if width_corr["p"] < 0.001 else "**" if width_corr["p"] < 0.01 else "*" if width_corr["p"] < 0.05 else ""
        print(f"  Pearson r = {width_corr['r']:.3f} (p = {width_corr['p']:.3f}){width_sig}")
        print(f"  Successful width: μ={width_data['success_widths']['mean']:.2f}, σ={width_data['success_widths']['std']:.2f}")
        print(f"  Failed width: μ={width_data['failed_widths']['mean']:.2f}, σ={width_data['failed_widths']['std']:.2f}")
        
        # Top n-gram patterns
        print(f"\nTOP SUCCESSFUL PATTERNS:")
        
        for n in [2, 3]:
            tool_patterns = ngram_data["tool_patterns"][n]["top_success_patterns"]
            assign_patterns = ngram_data["assignment_patterns"][n]["top_success_patterns"]
            
            if tool_patterns:
                print(f"\n  Tool {n}-grams:")
                for i, pattern in enumerate(tool_patterns[:3]):
                    rate = pattern["success_rate"] * 100
                    pattern_str = " → ".join(pattern["pattern"])
                    print(f"    {pattern_str}: {pattern['success_count']}/{pattern['total_count']} ({rate:.1f}%)")
            
            if assign_patterns:
                print(f"\n  Assignment {n}-grams:")
                for i, pattern in enumerate(assign_patterns[:3]):
                    rate = pattern["success_rate"] * 100
                    pattern_str = " → ".join(pattern["pattern"])
                    print(f"    {pattern_str}: {pattern['success_count']}/{pattern['total_count']} ({rate:.1f}%)")
    
    def _print_summary_insights(self, results: dict):
        """Print key insights and recommendations."""
        print(f"\n{'='*80}")
        print(" KEY INSIGHTS & RECOMMENDATIONS")
        print(f"{'='*80}")
        
        # Hypothesis testing results
        print(f"\nHYPOTHESIS TEST RESULTS:")
        
        composite_depth = results["composite_success"]["depth"]["pearson_correlation"]
        composite_width = results["composite_success"]["width"]["pearson_correlation"]
        
        depth_significant = composite_depth["p"] < 0.05 and composite_depth["r"] > 0
        width_significant = composite_width["p"] < 0.05 and composite_width["r"] > 0
        
        print(f"  H1 - 'Greater depth leads to better success':")
        print(f"       {'SUPPORTED' if depth_significant else 'NOT SUPPORTED'} (r={composite_depth['r']:.3f}, p={composite_depth['p']:.3f})")
        
        print(f"  H2 - 'Greater width leads to better success':")
        print(f"       {'SUPPORTED' if width_significant else 'NOT SUPPORTED'} (r={composite_width['r']:.3f}, p={composite_width['p']:.3f})")
        
        # Most effective patterns
        print(f"\nMOST EFFECTIVE PATTERNS:")
        
        # Find best tool sequences
        best_tool_patterns = []
        for criterion in ["composite_success", "rca_success", "fix_success", "recovery_success"]:
            for n in [2, 3]:
                patterns = results[criterion]["ngrams"]["tool_patterns"][n]["top_success_patterns"]
                best_tool_patterns.extend(patterns[:2])  # Top 2 from each
        
        # Sort by success rate and frequency
        best_tool_patterns.sort(key=lambda x: (x["success_rate"], x["total_count"]), reverse=True)
        
        print(f"  Top tool sequences:")
        shown = set()
        count = 0
        for pattern in best_tool_patterns:
            pattern_str = " → ".join(pattern["pattern"])
            if pattern_str not in shown and count < 5:
                rate = pattern["success_rate"] * 100
                print(f"    {pattern_str}: {rate:.1f}% success rate ({pattern['total_count']} uses)")
                shown.add(pattern_str)
                count += 1
        
        # Best assignment sequences
        best_assign_patterns = []
        for criterion in ["composite_success", "rca_success", "fix_success", "recovery_success"]:
            for n in [2, 3]:
                patterns = results[criterion]["ngrams"]["assignment_patterns"][n]["top_success_patterns"]
                best_assign_patterns.extend(patterns[:2])
        
        best_assign_patterns.sort(key=lambda x: (x["success_rate"], x["total_count"]), reverse=True)
        
        print(f"  Top assignment sequences:")
        shown = set()
        count = 0
        for pattern in best_assign_patterns:
            pattern_str = " → ".join(pattern["pattern"])
            if pattern_str not in shown and count < 5:
                rate = pattern["success_rate"] * 100
                print(f"    {pattern_str}: {rate:.1f}% success rate ({pattern['total_count']} uses)")
                shown.add(pattern_str)
                count += 1
        
        print(f"\nAnalysis complete! Check {self.output_dir}/ for visualizations.")
    
    def _run_learning_comparison_analysis(self):
        """Run comprehensive comparison between learning and no-learning agents."""
        print(f"\n{'='*80}")
        print(" LEARNING vs NO-LEARNING AGENT COMPARISON")
        print(f"{'='*80}")
        
        # Separate episodes by learning status
        learning_episodes = [ep for ep in self.episodes if "learning" in ep["db_label"].lower() and "no" not in ep["db_label"].lower()]
        no_learning_episodes = [ep for ep in self.episodes if "no" in ep["db_label"].lower() or ("learning" not in ep["db_label"].lower() and "single" not in ep["db_label"].lower())]
        
        print(f"Learning agent episodes: {len(learning_episodes)}")
        print(f"No-learning agent episodes: {len(no_learning_episodes)}")
        
        if not learning_episodes or not no_learning_episodes:
            print("Insufficient data for learning comparison")
            return
        
        # Compare overall success rates
        self._compare_success_rates(learning_episodes, no_learning_episodes)
        
        # Compare depth/width hypotheses
        self._compare_depth_width_hypotheses(learning_episodes, no_learning_episodes)
        
        # Compare top patterns
        self._compare_patterns(learning_episodes, no_learning_episodes)
    
    def _compare_success_rates(self, learning_episodes: List[dict], no_learning_episodes: List[dict]):
        """Compare success rates between learning and no-learning agents."""
        print(f"\nSUCCESS RATE COMPARISON:")
        print(f"{'Metric':<25} {'Learning':<15} {'No-Learning':<15} {'Difference':<12} {'P-value':<10}")
        print("-" * 80)
        
        for criterion_name, criterion_func in SUCCESS_CRITERIA.items():
            learning_success = sum(1 for ep in learning_episodes if criterion_func(ep))
            no_learning_success = sum(1 for ep in no_learning_episodes if criterion_func(ep))
            
            learning_rate = learning_success / len(learning_episodes) * 100
            no_learning_rate = no_learning_success / len(no_learning_episodes) * 100
            difference = learning_rate - no_learning_rate
            
            # Chi-square test for proportions
            from scipy.stats import chi2_contingency
            contingency = [
                [learning_success, len(learning_episodes) - learning_success],
                [no_learning_success, len(no_learning_episodes) - no_learning_success]
            ]
            chi2, p_value, _, _ = chi2_contingency(contingency)
            
            print(f"{criterion_name:<25} {learning_rate:<15.1f} {no_learning_rate:<15.1f} {difference:<12.1f} {p_value:<10.3f}")
    
    def _compare_depth_width_hypotheses(self, learning_episodes: List[dict], no_learning_episodes: List[dict]):
        """Compare depth/width correlations between learning approaches."""
        print(f"\n{'='*80}")
        print(" DEPTH/WIDTH HYPOTHESIS COMPARISON")
        print(f"{'='*80}")
        
        for criterion_name in ["score_ge_1", "score_ge_2", "score_eq_3", "rca_success", "fix_success", "recovery_success"]:
            if criterion_name not in SUCCESS_CRITERIA:
                continue
                
            criterion_func = SUCCESS_CRITERIA[criterion_name]
            print(f"\n{criterion_name.upper()}:")
            
            # Analyze learning agent
            learning_analyzer = TreeStructureAnalyzer(learning_episodes)
            learning_depth = learning_analyzer.analyze_depth_correlation(criterion_name, criterion_func)
            learning_width = learning_analyzer.analyze_width_correlation(criterion_name, criterion_func)
            
            # Analyze no-learning agent
            no_learning_analyzer = TreeStructureAnalyzer(no_learning_episodes)
            no_learning_depth = no_learning_analyzer.analyze_depth_correlation(criterion_name, criterion_func)
            no_learning_width = no_learning_analyzer.analyze_width_correlation(criterion_name, criterion_func)
            
            # Compare depth correlations
            learning_depth_r = learning_depth["pearson_correlation"]["r"]
            learning_depth_p = learning_depth["pearson_correlation"]["p"]
            no_learning_depth_r = no_learning_depth["pearson_correlation"]["r"]
            no_learning_depth_p = no_learning_depth["pearson_correlation"]["p"]
            
            print(f"  Depth Correlation:")
            print(f"    Learning:    r={learning_depth_r:>7.3f} (p={learning_depth_p:.3f}) {'***' if learning_depth_p < 0.001 else '**' if learning_depth_p < 0.01 else '*' if learning_depth_p < 0.05 else ''}")
            print(f"    No-Learning: r={no_learning_depth_r:>7.3f} (p={no_learning_depth_p:.3f}) {'***' if no_learning_depth_p < 0.001 else '**' if no_learning_depth_p < 0.01 else '*' if no_learning_depth_p < 0.05 else ''}")
            print(f"    Difference:  Δr={learning_depth_r - no_learning_depth_r:>7.3f}")
            
            # Compare width correlations
            learning_width_r = learning_width["pearson_correlation"]["r"]
            learning_width_p = learning_width["pearson_correlation"]["p"]
            no_learning_width_r = no_learning_width["pearson_correlation"]["r"]
            no_learning_width_p = no_learning_width["pearson_correlation"]["p"]
            
            print(f"  Width Correlation:")
            print(f"    Learning:    r={learning_width_r:>7.3f} (p={learning_width_p:.3f}) {'***' if learning_width_p < 0.001 else '**' if learning_width_p < 0.01 else '*' if learning_width_p < 0.05 else ''}")
            print(f"    No-Learning: r={no_learning_width_r:>7.3f} (p={no_learning_width_p:.3f}) {'***' if no_learning_width_p < 0.001 else '**' if no_learning_width_p < 0.01 else '*' if no_learning_width_p < 0.05 else ''}")
            print(f"    Difference:  Δr={learning_width_r - no_learning_width_r:>7.3f}")
            
            # Hypothesis verification
            depth_significant_learning = learning_depth_p < 0.05 and learning_depth_r > 0
            depth_significant_no_learning = no_learning_depth_p < 0.05 and no_learning_depth_r > 0
            width_significant_learning = learning_width_p < 0.05 and learning_width_r > 0
            width_significant_no_learning = no_learning_width_p < 0.05 and no_learning_width_r > 0
            
            print(f"  Hypothesis Results:")
            print(f"    H1 (Depth→Success): Learning={'SUPPORTED' if depth_significant_learning else 'NOT SUPPORTED'}, No-Learning={'SUPPORTED' if depth_significant_no_learning else 'NOT SUPPORTED'}")
            print(f"    H2 (Width→Success): Learning={'SUPPORTED' if width_significant_learning else 'NOT SUPPORTED'}, No-Learning={'SUPPORTED' if width_significant_no_learning else 'NOT SUPPORTED'}")
    
    def _compare_patterns(self, learning_episodes: List[dict], no_learning_episodes: List[dict]):
        """Compare successful patterns between learning approaches."""
        print(f"\n{'='*80}")
        print(" PATTERN COMPARISON: LEARNING vs NO-LEARNING")
        print(f"{'='*80}")
        
        # Analyze patterns for each group
        learning_analyzer = NGramAnalyzer(learning_episodes)
        no_learning_analyzer = NGramAnalyzer(no_learning_episodes)
        
        for criterion_name, criterion_func in [("composite_success", SUCCESS_CRITERIA["composite_success"])]:
            print(f"\n{criterion_name.upper()} PATTERNS:")
            
            learning_patterns = learning_analyzer.analyze_patterns_by_criterion(criterion_name, criterion_func, min_frequency=2)
            no_learning_patterns = no_learning_analyzer.analyze_patterns_by_criterion(criterion_name, criterion_func, min_frequency=2)
            
            # Compare top assignment patterns
            print(f"\nTOP ASSIGNMENT PATTERNS (2-grams):")
            print(f"  Learning Agent:")
            learning_assigns = learning_patterns["assignment_patterns"][2]["top_success_patterns"]
            for i, pattern in enumerate(learning_assigns[:3]):
                if pattern["total_count"] >= 2:
                    rate = pattern["success_rate"] * 100
                    pattern_str = " → ".join(pattern["pattern"])
                    print(f"    {pattern_str}: {pattern['success_count']}/{pattern['total_count']} ({rate:.1f}%)")
            
            print(f"  No-Learning Agent:")
            no_learning_assigns = no_learning_patterns["assignment_patterns"][2]["top_success_patterns"]
            for i, pattern in enumerate(no_learning_assigns[:3]):
                if pattern["total_count"] >= 2:
                    rate = pattern["success_rate"] * 100
                    pattern_str = " → ".join(pattern["pattern"])
                    print(f"    {pattern_str}: {pattern['success_count']}/{pattern['total_count']} ({rate:.1f}%)")
            
            # Compare top tool patterns
            print(f"\nTOP TOOL PATTERNS (2-grams):")
            print(f"  Learning Agent:")
            learning_tools = learning_patterns["tool_patterns"][2]["top_success_patterns"]
            for i, pattern in enumerate(learning_tools[:3]):
                if pattern["total_count"] >= 2:
                    rate = pattern["success_rate"] * 100
                    pattern_str = " → ".join(pattern["pattern"])
                    print(f"    {pattern_str}: {pattern['success_count']}/{pattern['total_count']} ({rate:.1f}%)")
            
            print(f"  No-Learning Agent:")
            no_learning_tools = no_learning_patterns["tool_patterns"][2]["top_success_patterns"]
            for i, pattern in enumerate(no_learning_tools[:3]):
                if pattern["total_count"] >= 2:
                    rate = pattern["success_rate"] * 100
                    pattern_str = " → ".join(pattern["pattern"])
                    print(f"    {pattern_str}: {pattern['success_count']}/{pattern['total_count']} ({rate:.1f}%)")
    
    def _print_learning_comparison_insights(self):
        """Print key insights from learning comparison."""
        print(f"\n{'='*80}")
        print(" LEARNING vs NO-LEARNING INSIGHTS")
        print(f"{'='*80}")
        
        # Separate episodes
        learning_episodes = [ep for ep in self.episodes if "learning" in ep["db_label"].lower() and "no" not in ep["db_label"].lower()]
        no_learning_episodes = [ep for ep in self.episodes if "no" in ep["db_label"].lower()]
        
        if not learning_episodes or not no_learning_episodes:
            print("Insufficient data for learning comparison insights")
            return
        
        # Overall success comparison
        learning_composite_success = sum(1 for ep in learning_episodes if ep["score"] >= 2)
        no_learning_composite_success = sum(1 for ep in no_learning_episodes if ep["score"] >= 2)
        
        learning_rate = learning_composite_success / len(learning_episodes) * 100
        no_learning_rate = no_learning_composite_success / len(no_learning_episodes) * 100
        improvement = learning_rate - no_learning_rate
        
        print(f"\nOVERALL PERFORMANCE:")
        print(f"  Learning Agent:    {learning_composite_success}/{len(learning_episodes)} episodes successful (score ≥ 2) ({learning_rate:.1f}%)")
        print(f"  No-Learning Agent: {no_learning_composite_success}/{len(no_learning_episodes)} episodes successful (score ≥ 2) ({no_learning_rate:.1f}%)")
        print(f"  Performance {'Improvement' if improvement > 0 else 'Decline'}: {abs(improvement):.1f} percentage points")
        
        # Depth/Width insights
        learning_depths = [ep["max_depth"] for ep in learning_episodes]
        no_learning_depths = [ep["max_depth"] for ep in no_learning_episodes]
        learning_widths = [ep["total_children"] for ep in learning_episodes]
        no_learning_widths = [ep["total_children"] for ep in no_learning_episodes]
        
        print(f"\nSTRUCTURAL DIFFERENCES:")
        print(f"  Average Depth:    Learning={np.mean(learning_depths):.2f}, No-Learning={np.mean(no_learning_depths):.2f}")
        print(f"  Average Width:    Learning={np.mean(learning_widths):.2f}, No-Learning={np.mean(no_learning_widths):.2f}")
        
        depth_diff = np.mean(learning_depths) - np.mean(no_learning_depths)
        width_diff = np.mean(learning_widths) - np.mean(no_learning_widths)
        
        print(f"  Learning agent uses {'deeper' if depth_diff > 0 else 'shallower'} trees (Δ={abs(depth_diff):.2f})")
        print(f"  Learning agent uses {'wider' if width_diff > 0 else 'narrower'} trees (Δ={abs(width_diff):.2f})")

# =============================================================================
# Command Line Interface
# =============================================================================

def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(description="Comprehensive SRE Agent Pattern Analysis")
    parser.add_argument("--agent-db", default="./agent.db", 
                       help="Path to learning agent database")
    parser.add_argument("--no-learning-db", default="./agent_no_learning.db",
                       help="Path to no-learning agent database")
    parser.add_argument("--output-dir", default="./figures",
                       help="Output directory for visualizations")
    parser.add_argument("--single-db", 
                       help="Analyze only a single database (provide path)")
    parser.add_argument("--min-frequency", type=int, default=3,
                       help="Minimum frequency for pattern analysis")
    
    args = parser.parse_args()
    
    # Determine which databases to analyze
    if args.single_db:
        db_paths = {"single": args.single_db}
    else:
        db_paths = {
            "learning": args.agent_db,
            "no_learning": args.no_learning_db,
        }
    
    # Initialize and run analysis
    analyzer = ComprehensiveAnalyzer(db_paths, args.output_dir)
    analyzer.load_all_data()
    
    if not analyzer.episodes:
        print("No episodes loaded. Check database paths.")
        return
    
    results = analyzer.run_comprehensive_analysis()
    
    print(f"\nAnalysis complete!")
    print(f"Results saved to: {args.output_dir}")

if __name__ == "__main__":
    main()