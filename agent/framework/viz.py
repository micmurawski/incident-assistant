from mermaid import Mermaid

from framework import Flow


def build_mermaid(flow):
    ids, visited, lines = {}, set(), ["graph LR"]
    ctr = 1

    def get_id(n):
        nonlocal ctr
        return ids[n] if n in ids else (ids.setdefault(n, f"N{ctr}"), (ctr := ctr + 1))[0]

    def link(a, b, label=None):
        if label == "default":
            lines.append(f"    {a} -.-> {b}")
            return

        if label:
            lines.append(f"    {a} -->|{label}| {b}")
        else:
            lines.append(f"    {a} --> {b}")

    def walk(node, parent=None, label=None):
        if node in visited:
            return parent and link(parent, get_id(node), label)
        visited.add(node)
        if isinstance(node, Flow):
            node.start_node and parent and link(parent, get_id(node.start_node), label)
            lines.append(f"\n    subgraph sub_flow_{get_id(node)}[{type(node).__name__}]")
            node.start_node and walk(node.start_node, parent, label)
            for label, nxt in node.successors.items():
                node.start_node and walk(nxt, get_id(node.start_node), label) or (
                    parent and link(parent, get_id(nxt), label)
                ) or walk(nxt, parent, label)
            lines.append("    end\n")
        else:
            lines.append(f"    {(nid := get_id(node))}[{type(node).__name__}]")
            if not parent:
                link("START([START])", nid)
            parent and link(parent, nid, label)
            [walk(nxt, nid, label) for label, nxt in node.successors.items()]
            if len(node.successors) == 0 or "default" not in node.successors:
                link(nid, "END([END])")

    walk(flow)
    return "\n".join(lines)


def to_png(flow: Flow, filename: str):
    Mermaid(build_mermaid(flow)).to_png(filename)
