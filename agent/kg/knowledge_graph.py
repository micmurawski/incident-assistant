import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import numpy as np
from mermaid import Mermaid
from scipy.cluster.vq import kmeans2


def generate_id(embedding: list[float] | np.ndarray | list) -> str:
    if isinstance(embedding, np.ndarray):
        return hashlib.sha256(embedding.tobytes()).hexdigest()
    elif isinstance(embedding, list) and len(embedding) > 0 and isinstance(embedding[0], (Node, Edge)):
        # For collections, create ID from concatenated IDs
        combined = "".join(item.id for item in embedding)
        return hashlib.sha256(combined.encode()).hexdigest()
    return hashlib.sha256(json.dumps(embedding).encode()).hexdigest()


@dataclass
class Node:
    properties: dict
    embedding: np.ndarray | list[float]
    _knowledge_graph: "KnowledgeGraph" = field(default=None, repr=False)
    _id: str = field(default=None)

    def __post_init__(self):
        if self._id is None:
            self._id = generate_id(self.embedding)

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self.properties["name"]

    def neighbors(self) -> list["Node"]:
        if self._knowledge_graph is None:
            return []
        return [
            self._knowledge_graph.nodes[edge.target]
            for edge in self._knowledge_graph.edges.values()
            if isinstance(edge, Edge) and edge.source == self.id and edge.target in self._knowledge_graph.nodes
        ]


@dataclass
class NodeCollection:
    nodes: list[Node]
    _knowledge_graph: "KnowledgeGraph" = field(default=None, repr=False)
    _id: str = field(default=None)

    def __post_init__(self):
        if self._id is None:
            self._id = generate_id(self.nodes)

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        name = "+".join([node.properties["name"] for node in self.nodes])
        return name

    @property
    def embedding(self) -> np.ndarray:
        """Return centroid of all node embeddings."""
        embeddings = [
            node.embedding if isinstance(node.embedding, np.ndarray) else np.array(node.embedding)
            for node in self.nodes
        ]
        return np.mean(embeddings, axis=0)


@dataclass
class Edge:
    source: str
    target: str
    properties: dict
    embedding: np.ndarray | list[float]
    _knowledge_graph: "KnowledgeGraph" = field(default=None, repr=False)
    _id: str = field(default=None)

    def __post_init__(self):
        if self._id is None:
            self._id = generate_id(self.embedding)

    @property
    def id(self) -> str:
        return self._id


@dataclass
class EdgeCollection:
    edges: list[Edge]
    _knowledge_graph: "KnowledgeGraph" = field(default=None, repr=False)
    _id: str = field(default=None)

    def __post_init__(self):
        if self._id is None:
            self._id = generate_id(self.edges)

    @property
    def id(self) -> str:
        return self._id

    @property
    def source(self) -> str:
        """Return source from first edge (all should have same source/target after clustering)."""
        return self.edges[0].source if self.edges else None

    @property
    def target(self) -> str:
        """Return target from first edge."""
        return self.edges[0].target if self.edges else None

    @property
    def embedding(self) -> np.ndarray:
        """Return centroid of all edge embeddings."""
        embeddings = [
            edge.embedding if isinstance(edge.embedding, np.ndarray) else np.array(edge.embedding)
            for edge in self.edges
        ]
        return np.mean(embeddings, axis=0)


class Distance(Enum):
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    MANHATTAN = "manhattan"
    CHEBYSHEV = "chebyshev"
    MINKOWSKI = "minkowski"


def distance(
    embedding1: np.ndarray | list[float],
    embedding2: np.ndarray | list[float],
    distance_metric: Distance = Distance.COSINE,
    **kwargs,
) -> float:
    if not isinstance(embedding1, np.ndarray):
        embedding1 = np.array(embedding1)
    if not isinstance(embedding2, np.ndarray):
        embedding2 = np.array(embedding2)

    if distance_metric == Distance.COSINE:
        norm_product = np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        if norm_product == 0:
            return 1.0  # Maximum distance for zero vectors
        return 1 - np.dot(embedding1, embedding2) / norm_product
    elif distance_metric == Distance.EUCLIDEAN:
        return np.linalg.norm(embedding1 - embedding2)
    elif distance_metric == Distance.MANHATTAN:
        return np.sum(np.abs(embedding1 - embedding2))
    elif distance_metric == Distance.CHEBYSHEV:
        return np.max(np.abs(embedding1 - embedding2))
    elif distance_metric == Distance.MINKOWSKI:
        p = kwargs.get("p", 2)
        return np.sum(np.abs(embedding1 - embedding2) ** p) ** (1 / p)
    raise ValueError(f"Invalid distance metric: {distance_metric}")


@dataclass
class KnowledgeGraph:
    nodes: dict[str, Node | NodeCollection] = field(default_factory=dict)
    edges: dict[str, Edge | EdgeCollection] = field(default_factory=dict)

    def add_node(self, node: Node | NodeCollection):
        self.nodes[node.id] = node
        node._knowledge_graph = self

    def add_edge(self, edge: Edge | EdgeCollection):
        self.edges[edge.id] = edge
        edge._knowledge_graph = self

    def coarsen_graph(
        self, node_epsilon: float, edge_epsilon: float, distance_metric: Distance = Distance.COSINE, **kwargs
    ) -> "KnowledgeGraph":
        """
        Create a coarsened version of the graph by merging similar nodes and edges.

        Args:
            node_epsilon: Maximum distance threshold for merging nodes (lower = stricter)
            edge_epsilon: Maximum distance threshold for merging edges (lower = stricter)
            distance_metric: Distance metric to use for similarity comparison
            **kwargs: Additional arguments for distance metric (e.g., p for Minkowski)

        Returns:
            A new coarsened KnowledgeGraph
        """
        coarsened_graph = KnowledgeGraph()

        # Step 1: Flatten and cluster nodes
        flat_nodes = self._flatten_nodes()
        node_clusters = self._cluster_items(flat_nodes, node_epsilon, distance_metric, **kwargs)

        # Step 2: Create NodeCollections or single Nodes for each cluster
        node_id_mapping = {}  # old_id -> new_id

        for cluster in node_clusters:
            if len(cluster) == 1:
                # Single node - add as is
                new_node = Node(
                    properties=cluster[0].properties.copy(),
                    embedding=cluster[0].embedding.copy()
                    if isinstance(cluster[0].embedding, np.ndarray)
                    else np.array(cluster[0].embedding),
                )
                coarsened_graph.add_node(new_node)
                node_id_mapping[cluster[0].id] = new_node.id
            else:
                # Multiple nodes - create NodeCollection
                node_collection = NodeCollection(nodes=cluster)
                coarsened_graph.add_node(node_collection)
                # Map all old node IDs to the new collection ID
                for old_node in cluster:
                    node_id_mapping[old_node.id] = node_collection.id

        # Step 3: Update edges with new node IDs
        flat_edges = self._flatten_edges()
        updated_edges = []

        for edge in flat_edges:
            new_source = node_id_mapping.get(edge.source, edge.source)
            new_target = node_id_mapping.get(edge.target, edge.target)

            # Skip self-loops created by merging
            if new_source == new_target:
                continue

            updated_edge = Edge(
                source=new_source,
                target=new_target,
                properties=edge.properties.copy(),
                embedding=edge.embedding.copy() if isinstance(edge.embedding, np.ndarray) else np.array(edge.embedding),
            )
            updated_edges.append(updated_edge)

        # Step 4: Cluster edges by both embedding similarity and connectivity
        edge_clusters = self._cluster_edges(updated_edges, edge_epsilon, distance_metric, **kwargs)

        # Step 5: Create EdgeCollections or single Edges for each cluster
        for cluster in edge_clusters:
            if len(cluster) == 1:
                # Single edge - add as is
                coarsened_graph.add_edge(cluster[0])
            else:
                # Multiple edges - create EdgeCollection
                edge_collection = EdgeCollection(edges=cluster)
                coarsened_graph.add_edge(edge_collection)

        return coarsened_graph

    def _flatten_nodes(self) -> list[Node]:
        """Extract all individual nodes from the graph, including those in NodeCollections."""
        flat_nodes = []
        for node_item in self.nodes.values():
            if isinstance(node_item, Node):
                flat_nodes.append(node_item)
            elif isinstance(node_item, NodeCollection):
                flat_nodes.extend(node_item.nodes)
        return flat_nodes

    def _flatten_edges(self) -> list[Edge]:
        """Extract all individual edges from the graph, including those in EdgeCollections."""
        flat_edges = []
        for edge_item in self.edges.values():
            if isinstance(edge_item, Edge):
                flat_edges.append(edge_item)
            elif isinstance(edge_item, EdgeCollection):
                flat_edges.extend(edge_item.edges)
        return flat_edges

    def _cluster_items(
        self, items: list[Node | Edge], epsilon: float, distance_metric: Distance, **kwargs
    ) -> list[list[Node | Edge]]:
        """
        Cluster items based on embedding similarity using greedy clustering.
        """
        clusters = []
        used = set()

        for i, item in enumerate(items):
            if i in used:
                continue

            cluster = [item]
            used.add(i)

            emb_i = item.embedding if isinstance(item.embedding, np.ndarray) else np.array(item.embedding)

            for j in range(i + 1, len(items)):
                if j in used:
                    continue

                emb_j = (
                    items[j].embedding if isinstance(items[j].embedding, np.ndarray) else np.array(items[j].embedding)
                )
                dist = distance(emb_i, emb_j, distance_metric, **kwargs)

                if dist < epsilon:
                    cluster.append(items[j])
                    used.add(j)

            clusters.append(cluster)

        return clusters

    def _cluster_edges(
        self, edges: list[Edge], epsilon: float, distance_metric: Distance, **kwargs
    ) -> list[list[Edge]]:
        """
        Cluster edges based on both embedding similarity AND connectivity (same source/target).
        Only edges with the same source and target nodes can be merged.
        """
        # Group edges by (source, target) pair first
        edge_groups = {}
        for edge in edges:
            key = (edge.source, edge.target)
            if key not in edge_groups:
                edge_groups[key] = []
            edge_groups[key].append(edge)

        # Cluster within each group
        all_clusters = []
        for group_edges in edge_groups.values():
            if len(group_edges) == 1:
                all_clusters.append(group_edges)
            else:
                # Cluster by embedding similarity within this group
                clusters = self._cluster_items(group_edges, epsilon, distance_metric, **kwargs)
                all_clusters.extend(clusters)

        return all_clusters

    def kmeans_cluster_nodes(
        self, k: int, max_iterations: int = 100, initialization: Literal["random", "kmeans++"] = "kmeans++", **kwargs
    ) -> dict[str, int]:
        """
        Cluster nodes using K-means algorithm via scipy.

        Args:
            k: Number of clusters
            max_iterations: Maximum number of iterations
            initialization: Method for initializing centroids ("random" or "kmeans++")
            **kwargs: Additional arguments passed to scipy kmeans2

        Returns:
            Dictionary mapping node_id to cluster_id (0 to k-1)
        """
        # Get all individual nodes (flatten NodeCollections)
        flat_nodes = self._flatten_nodes()

        if len(flat_nodes) < k:
            # Not enough nodes for k clusters
            return {node.id: i for i, node in enumerate(flat_nodes)}

        # Extract embeddings
        embeddings = []
        node_ids = []
        for node in flat_nodes:
            emb = node.embedding if isinstance(node.embedding, np.ndarray) else np.array(node.embedding)
            embeddings.append(emb)
            node_ids.append(node.id)

        embeddings = np.array(embeddings)

        # Use scipy's kmeans2 for clustering
        try:
            centroids, cluster_assignments = kmeans2(embeddings, k, iter=max_iterations, minit=initialization, **kwargs)
        except Exception as e:
            # Fallback to random assignment if scipy fails
            print(f"Warning: scipy kmeans2 failed ({e}), using random assignment")
            cluster_assignments = np.random.randint(0, k, len(embeddings))

        return {node_ids[i]: int(cluster_id) for i, cluster_id in enumerate(cluster_assignments)}

    def get_cluster_summary(self, cluster_assignments: dict[str, int]) -> dict:
        """
        Get a summary of the clustering results.

        Args:
            cluster_assignments: Dictionary mapping node_id to cluster_id

        Returns:
            Dictionary with cluster statistics and node information
        """
        summary = {
            "total_nodes": len(cluster_assignments),
            "num_clusters": len(set(cluster_assignments.values())),
            "cluster_sizes": {},
            "cluster_nodes": {},
        }

        # Count nodes per cluster
        for node_id, cluster_id in cluster_assignments.items():
            if cluster_id not in summary["cluster_sizes"]:
                summary["cluster_sizes"][cluster_id] = 0
                summary["cluster_nodes"][cluster_id] = []

            summary["cluster_sizes"][cluster_id] += 1
            summary["cluster_nodes"][cluster_id].append(node_id)

        return summary


def build_mermaid(kg: KnowledgeGraph):
    def link(a, b, label=None):
        if label == "default":
            lines.append(f"    {a} -.-> {b}")
            return

        if label:
            lines.append(f"    {a} -->|{label}| {b}")
        else:
            lines.append(f"    {a} --> {b}")

    nodes_ids, visited_edges, visited_nodes, lines = {}, set(), set(), ["graph LR"]

    ctr = 1

    def get_id(n: Node | NodeCollection):
        nonlocal ctr
        if n.name not in nodes_ids:
            nodes_ids[n.name] = f"id{ctr}[{n.name}]"
            ctr += 1
        return nodes_ids[n.name]

    edge: Edge | EdgeCollection
    for edge in kg.edges.values():
        if edge.id in visited_edges:
            continue
        src = edge.source
        target = edge.target
        link(get_id(kg.nodes[src]), get_id(kg.nodes[target]))
        visited_edges.add(edge.id)
        visited_nodes.add(src)
        visited_nodes.add(target)

    for node in kg.nodes.values():
        if node.id in visited_nodes:
            continue

        lines.append(f"    {get_id(node)}")
        visited_nodes.add(node.id)

    return "\n".join(lines)


def to_png(flow: KnowledgeGraph, filename: str):
    # print(build_mermaid(flow))
    Mermaid(build_mermaid(flow)).to_png(filename)


# Example usage
if __name__ == "__main__":
    # Create a sample knowledge graph with more nodes for clustering
    kg = KnowledgeGraph()

    # Add nodes with different types and embeddings
    nodes_data = [
        {"name": "Alice", "type": "person", "embedding": [0.1, 0.2, 0.3, 0.4]},
        {"name": "Alice Smith", "type": "person", "embedding": [0.11, 0.21, 0.31, 0.41]},
        {"name": "Bob", "type": "person", "embedding": [0.9, 0.8, 0.7, 0.6]},
        {"name": "Bob Johnson", "type": "person", "embedding": [0.89, 0.81, 0.71, 0.59]},
        {"name": "Python", "type": "language", "embedding": [0.2, 0.1, 0.8, 0.9]},
        {"name": "Java", "type": "language", "embedding": [0.19, 0.11, 0.79, 0.91]},
        {"name": "JavaScript", "type": "language", "embedding": [0.21, 0.09, 0.81, 0.89]},
        {"name": "Machine Learning", "type": "concept", "embedding": [0.7, 0.6, 0.2, 0.1]},
        {"name": "AI", "type": "concept", "embedding": [0.71, 0.59, 0.21, 0.09]},
        {"name": "Deep Learning", "type": "concept", "embedding": [0.69, 0.61, 0.19, 0.11]},
    ]

    nodes = []
    for data in nodes_data:
        node = Node(properties={"name": data["name"], "type": data["type"]}, embedding=np.array(data["embedding"]))
        kg.add_node(node)
        nodes.append(node)

    # Create edges to demonstrate relationships
    edges_data = [
        # Person-knows-language relationships
        {"source": "Alice", "target": "Python", "relationship": "knows", "embedding": [0.15, 0.15, 0.55, 0.65]},
        {"source": "Alice Smith", "target": "Python", "relationship": "knows", "embedding": [0.16, 0.16, 0.54, 0.66]},
        {"source": "Bob", "target": "Java", "relationship": "knows", "embedding": [0.55, 0.45, 0.75, 0.75]},
        {"source": "Bob Johnson", "target": "Java", "relationship": "knows", "embedding": [0.54, 0.46, 0.74, 0.76]},
        {"source": "Alice", "target": "JavaScript", "relationship": "knows", "embedding": [0.16, 0.15, 0.56, 0.65]},
        {"source": "Bob", "target": "JavaScript", "relationship": "knows", "embedding": [0.56, 0.45, 0.76, 0.75]},
        # Person-works-with-concept relationships
        {
            "source": "Alice",
            "target": "Machine Learning",
            "relationship": "works_with",
            "embedding": [0.4, 0.4, 0.5, 0.5],
        },
        {"source": "Alice Smith", "target": "AI", "relationship": "works_with", "embedding": [0.41, 0.39, 0.51, 0.49]},
        {"source": "Bob", "target": "Deep Learning", "relationship": "works_with", "embedding": [0.8, 0.7, 0.45, 0.35]},
        {
            "source": "Bob Johnson",
            "target": "Machine Learning",
            "relationship": "works_with",
            "embedding": [0.8, 0.7, 0.45, 0.35],
        },
        # Language-related-to-concept relationships
        {
            "source": "Python",
            "target": "Machine Learning",
            "relationship": "used_for",
            "embedding": [0.45, 0.35, 0.5, 0.5],
        },
        {"source": "Python", "target": "AI", "relationship": "used_for", "embedding": [0.46, 0.34, 0.51, 0.49]},
        {
            "source": "Java",
            "target": "Deep Learning",
            "relationship": "used_for",
            "embedding": [0.55, 0.45, 0.75, 0.75],
        },
        {"source": "JavaScript", "target": "AI", "relationship": "used_for", "embedding": [0.46, 0.34, 0.51, 0.49]},
        # Concept-related-to-concept relationships
        {"source": "Machine Learning", "target": "AI", "relationship": "subset_of", "embedding": [0.7, 0.6, 0.2, 0.1]},
        {
            "source": "Deep Learning",
            "target": "Machine Learning",
            "relationship": "subset_of",
            "embedding": [0.7, 0.6, 0.2, 0.1],
        },
    ]

    edges = []
    for data in edges_data:
        # Find source and target nodes by name
        source_node = next((n for n in nodes if n.name == data["source"]), None)
        target_node = next((n for n in nodes if n.name == data["target"]), None)

        if source_node and target_node:
            edge = Edge(
                source=source_node.id,
                target=target_node.id,
                properties={"relationship": data["relationship"]},
                embedding=np.array(data["embedding"]),
            )
            kg.add_edge(edge)
            edges.append(edge)

    print(f"Original graph: {len(kg.nodes)} nodes, {len(kg.edges)} edges")
    to_png(kg, "original.png")
    # Demonstrate K-means clustering
    print("\n=== K-means Clustering Demo ===")

    # Cluster into 3 groups
    cluster_assignments = kg.kmeans_cluster_nodes(k=3, max_iterations=50, initialization="kmeans++")
    to_png(kg, "k3.png")
    # Get cluster summary
    summary = kg.get_cluster_summary(cluster_assignments)

    print(f"Clustered {summary['total_nodes']} nodes into {summary['num_clusters']} clusters")
    print(f"Cluster sizes: {summary['cluster_sizes']}")

    # Show which nodes are in which cluster
    for cluster_id in range(summary["num_clusters"]):
        print(f"\nCluster {cluster_id} ({summary['cluster_sizes'][cluster_id]} nodes):")
        for node_id in summary["cluster_nodes"][cluster_id]:
            node = kg.nodes[node_id]
            print(f"  - {node.properties['name']} ({node.properties['type']})")

    # Test with different initialization methods
    print("\n=== Testing Different Initialization Methods ===")

    for init_method in ["random", "kmeans++"]:
        assignments = kg.kmeans_cluster_nodes(k=3, initialization=init_method)
        summary = kg.get_cluster_summary(assignments)
        print(f"{init_method}: {summary['cluster_sizes']}")

    # Test with different numbers of clusters
    print("\n=== Testing Different Numbers of Clusters ===")

    for k in [2, 3, 4]:
        assignments = kg.kmeans_cluster_nodes(k=k, initialization="kmeans++")
        summary = kg.get_cluster_summary(assignments)
        print(f"k={k}: {summary['cluster_sizes']}")

    print("\n=== Original Coarsening Demo ===")

    # Coarsen the graph (original functionality)
    coarsened = kg.coarsen_graph(node_epsilon=0.2, edge_epsilon=0.1, distance_metric=Distance.COSINE)

    print(f"Coarsened graph: {len(coarsened.nodes)} nodes, {len(coarsened.edges)} edges")
    print(f"Node types: {[type(n).__name__ for n in coarsened.nodes.values()]}")
    print(f"Edge types: {[type(e).__name__ for e in coarsened.edges.values()]}")

    # Show some example edges from the coarsened graph
    print("\nExample edges in coarsened graph:")
    for i, (edge_id, edge) in enumerate(list(coarsened.edges.items())[:5]):
        source_name = coarsened.nodes[edge.source].name
        target_name = coarsened.nodes[edge.target].name
        print(f"  {source_name} ----> {target_name}")

    if len(coarsened.edges) > 5:
        print(f"  ... and {len(coarsened.edges) - 5} more edges")
