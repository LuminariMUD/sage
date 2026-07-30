"""
Subgraph ranking algorithms for GraphRAG.

This module implements industry-standard subgraph ranking techniques
to identify the most relevant connected components for query responses.
"""

import logging
from collections import defaultdict, deque
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def extract_connected_components(
    entities: list[dict[str, Any]], relationships: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Extract connected components from entities and relationships.

    Returns list of subgraphs, each containing connected entities and their relationships.
    """
    # Build entity map - use stable_id as primary key
    entity_map = {}
    entity_id_to_name = {}  # For debugging and display

    for e in entities:
        entity_id = e.get("stable_id") or e.get("name")
        if entity_id:
            entity_map[entity_id] = e
            entity_id_to_name[entity_id] = e.get("name", entity_id)

    logger.debug(f"Built entity_map with {len(entity_map)} entities")

    # Build adjacency list and relationship map
    adjacency = defaultdict(set)
    relationship_map = defaultdict(list)

    for rel in relationships:
        source = rel.get("source")
        target = rel.get("target")
        if source and target:
            # Ensure both endpoints exist in entity_map
            if source in entity_map and target in entity_map:
                adjacency[source].add(target)
                adjacency[target].add(source)
                relationship_map[(source, target)].append(rel)
                relationship_map[(target, source)].append(rel)
            else:
                logger.debug(
                    f"Skipping relationship {source} -> {target}: endpoint not in entity_map"
                )

    logger.debug(f"Built adjacency list with {len(adjacency)} connected nodes")

    # Find connected components using BFS
    visited = set()
    components = []

    # Process all entities, including isolated ones
    for entity_id in entity_map:
        if entity_id not in visited:
            # BFS to find all connected nodes
            component_nodes = set()
            component_edges = []
            queue = deque([entity_id])

            while queue:
                current = queue.popleft()
                if current in visited:
                    continue

                visited.add(current)
                component_nodes.add(current)

                # Add neighbors
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        queue.append(neighbor)

                    # Add edges
                    if neighbor in component_nodes:
                        for rel in relationship_map[(current, neighbor)]:
                            if rel not in component_edges:
                                component_edges.append(rel)

            # Create subgraph (including isolated nodes)
            if component_nodes:  # Only add if we have at least one node
                subgraph = {
                    "nodes": [entity_map[nid] for nid in component_nodes if nid in entity_map],
                    "edges": component_edges,
                    "size": len(component_nodes),
                }
                components.append(subgraph)
                logger.debug(
                    f"Created component with {len(component_nodes)} nodes, {len(component_edges)} edges"
                )

    # Sort by size (largest first)
    components.sort(key=lambda x: x["size"], reverse=True)
    return components


def score_subgraph(
    subgraph: dict[str, Any],
    query_embedding: list[float] | None = None,
    episode_similarities: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Score a subgraph based on multiple factors.

    Factors:
    - Semantic relevance (if embeddings provided)
    - Connectivity (graph density)
    - Centrality (average degree)
    - Diversity (entity type variety)
    - Size (number of nodes and edges)
    """
    scores = {}

    num_nodes = len(subgraph["nodes"])
    num_edges = len(subgraph["edges"])

    # 1. Semantic Relevance Score
    if episode_similarities:
        # Check if any nodes reference episodes with high similarity
        relevant_sims = []
        for node in subgraph["nodes"]:
            # Check node metadata for episode references
            if "episode_id" in node.get("metadata", {}):
                ep_id = node["metadata"]["episode_id"]
                if ep_id in episode_similarities:
                    relevant_sims.append(episode_similarities[ep_id])

        scores["semantic_relevance"] = np.mean(relevant_sims) if relevant_sims else 0.0
    else:
        scores["semantic_relevance"] = 0.5  # Default neutral score

    # 2. Connectivity Score (Graph Density)
    if num_nodes > 1:
        max_edges = num_nodes * (num_nodes - 1) / 2  # For undirected graph
        scores["connectivity"] = min(1.0, num_edges / max_edges)
    else:
        scores["connectivity"] = 0.0

    # 3. Centrality Score (Average Degree)
    if num_nodes > 0:
        avg_degree = (2 * num_edges) / num_nodes
        # Normalize: assume 5 connections is "highly connected"
        scores["centrality"] = min(1.0, avg_degree / 5)
    else:
        scores["centrality"] = 0.0

    # 4. Diversity Score (Entity Type Variety)
    entity_types = set()
    for node in subgraph["nodes"]:
        node_type = node.get("type", "unknown")
        entity_types.add(node_type)

    # Assuming 13 total entity types in the system
    scores["diversity"] = len(entity_types) / 13

    # 5. Size Score (Prefer moderately sized subgraphs)
    # Too small = not informative, too large = not focused
    if num_nodes <= 3:
        scores["size_score"] = 0.3
    elif num_nodes <= 10:
        scores["size_score"] = 1.0
    elif num_nodes <= 20:
        scores["size_score"] = 0.7
    else:
        scores["size_score"] = 0.5

    # 6. Relationship Richness (Types of relationships)
    rel_types = set()
    for edge in subgraph["edges"]:
        rel_types.add(edge.get("type", "unknown"))

    # Normalize by assuming 10+ relationship types is rich
    scores["relationship_richness"] = min(1.0, len(rel_types) / 10)

    # Calculate weighted total score
    weights = {
        "semantic_relevance": 0.35,
        "connectivity": 0.20,
        "centrality": 0.15,
        "diversity": 0.10,
        "size_score": 0.10,
        "relationship_richness": 0.10,
    }

    scores["total_score"] = sum(
        scores.get(factor, 0) * weight for factor, weight in weights.items()
    )

    # Add metadata
    scores["num_nodes"] = num_nodes
    scores["num_edges"] = num_edges
    scores["entity_types"] = len(entity_types)
    scores["relationship_types"] = len(rel_types)

    return scores


def rank_subgraphs(
    subgraphs: list[dict[str, Any]],
    query_embedding: list[float] | None = None,
    episode_similarities: dict[str, float] | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Rank subgraphs and return top K with scores.
    """
    scored_subgraphs = []

    for subgraph in subgraphs:
        scores = score_subgraph(subgraph, query_embedding, episode_similarities)
        scored_subgraphs.append({"subgraph": subgraph, "scores": scores})

    # Sort by total score
    scored_subgraphs.sort(key=lambda x: x["scores"]["total_score"], reverse=True)

    # Log top scores
    if scored_subgraphs:
        logger.info(
            f"Top subgraph scores: {[sg['scores']['total_score'] for sg in scored_subgraphs[:3]]}"
        )

    return scored_subgraphs[:top_k]


def merge_overlapping_subgraphs(
    subgraphs: list[dict[str, Any]], overlap_threshold: float = 0.3
) -> list[dict[str, Any]]:
    """
    Merge subgraphs that have significant overlap.

    Args:
        subgraphs: List of subgraphs to potentially merge
        overlap_threshold: Minimum fraction of nodes that must overlap to merge

    Returns:
        List of merged subgraphs
    """
    if len(subgraphs) <= 1:
        return subgraphs

    merged = []
    used = set()

    for i, sg1 in enumerate(subgraphs):
        if i in used:
            continue

        # Start with current subgraph
        merged_nodes = {n.get("stable_id", n.get("name")) for n in sg1["nodes"]}
        merged_edges = list(sg1["edges"])
        merged_node_list = list(sg1["nodes"])

        # Check for overlap with other subgraphs
        for j, sg2 in enumerate(subgraphs[i + 1 :], i + 1):
            if j in used:
                continue

            sg2_nodes = {n.get("stable_id", n.get("name")) for n in sg2["nodes"]}

            # Calculate overlap
            intersection = merged_nodes & sg2_nodes
            overlap = len(intersection) / min(len(merged_nodes), len(sg2_nodes))

            if overlap >= overlap_threshold:
                # Merge subgraphs
                used.add(j)
                merged_nodes.update(sg2_nodes)

                # Add unique edges
                for edge in sg2["edges"]:
                    if edge not in merged_edges:
                        merged_edges.append(edge)

                # Add unique nodes
                for node in sg2["nodes"]:
                    node_id = node.get("stable_id", node.get("name"))
                    if node_id not in [n.get("stable_id", n.get("name")) for n in merged_node_list]:
                        merged_node_list.append(node)

        used.add(i)
        merged.append(
            {"nodes": merged_node_list, "edges": merged_edges, "size": len(merged_node_list)}
        )

    return merged


def filter_by_relevance_path(
    subgraph: dict[str, Any], relevant_node_ids: set[str], max_distance: int = 2
) -> dict[str, Any]:
    """
    Filter subgraph to include only nodes within max_distance of relevant nodes.

    This creates more focused subgraphs centered on query-relevant entities.
    """
    if not relevant_node_ids:
        return subgraph

    # Build adjacency from edges
    adjacency = defaultdict(set)
    for edge in subgraph["edges"]:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            adjacency[source].add(target)
            adjacency[target].add(source)

    # BFS from relevant nodes
    included_nodes = set()
    for start_node in relevant_node_ids:
        if start_node not in adjacency:
            continue

        # BFS with distance tracking
        queue = deque([(start_node, 0)])
        visited_from_start = {start_node}

        while queue:
            current, distance = queue.popleft()

            if distance <= max_distance:
                included_nodes.add(current)

                for neighbor in adjacency[current]:
                    if neighbor not in visited_from_start and distance < max_distance:
                        visited_from_start.add(neighbor)
                        queue.append((neighbor, distance + 1))

    # Filter nodes and edges
    filtered_nodes = [
        n for n in subgraph["nodes"] if n.get("stable_id", n.get("name")) in included_nodes
    ]

    filtered_edges = [
        e
        for e in subgraph["edges"]
        if e.get("source") in included_nodes and e.get("target") in included_nodes
    ]

    return {"nodes": filtered_nodes, "edges": filtered_edges, "size": len(filtered_nodes)}
