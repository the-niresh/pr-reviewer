"""Directed code graph built from graphify graph.json.

The file is directed:false and the CLI walks it undirected. Direction is
recovered from each link's source and target. This module never shells out to
the graphify CLI.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_BLAST_RELATIONS = frozenset({"calls", "re_exports"})
_WALK_SECONDS = 5.0


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    source_file: str


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    confidence: str


@dataclass(frozen=True)
class CodeGraph:
    nodes: dict[str, GraphNode]
    edges: tuple[GraphEdge, ...]

    def blast_radius(self, symbol: str, depth: int) -> list[str]:
        inbound: dict[str, list[str]] = defaultdict(list)
        known = set(self.nodes)
        for edge in self.edges:
            known.add(edge.source)
            known.add(edge.target)
            if edge.confidence != "EXTRACTED":
                continue
            if edge.relation not in _BLAST_RELATIONS:
                continue
            inbound[edge.target].append(edge.source)
        if symbol not in known:
            return []
        deadline = time.monotonic() + _WALK_SECONDS
        seen: set[str] = set()
        found: list[str] = []
        queue: deque[tuple[str, int]] = deque([(symbol, 0)])
        while queue:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"TIMEOUT walking blast radius for {symbol}")
            current, level = queue.popleft()
            if level >= depth:
                continue
            for caller in inbound.get(current, []):
                if caller in seen:
                    continue
                seen.add(caller)
                found.append(caller)
                queue.append((caller, level + 1))
        return found


def load_code_graph(path: Path) -> CodeGraph:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    raw_links = data.get("links")
    if raw_links is None:
        raw_links = data.get("edges") or []
    nodes = {
        str(item["id"]): GraphNode(
            id=str(item["id"]),
            label=str(item.get("label") or item["id"]),
            source_file=str(item.get("source_file") or ""),
        )
        for item in data.get("nodes") or []
    }
    edges = tuple(
        GraphEdge(
            source=str(item["source"]),
            target=str(item["target"]),
            relation=str(item.get("relation") or ""),
            confidence=str(item.get("confidence") or "INFERRED"),
        )
        for item in raw_links
    )
    return CodeGraph(nodes=nodes, edges=edges)
