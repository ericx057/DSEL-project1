from __future__ import annotations

import html
from typing import Sequence

from src.retrieval.database import SQLiteUnifiedStore


class DiagramService:
    def __init__(self, store: SQLiteUnifiedStore):
        self.store = store

    def render_call_graph_svg(self, query: str, user_tier: int, repo_scope: Sequence[str]) -> str:
        nodes = self.store.graph_search(query, user_tier=user_tier, repo_scope=repo_scope, depth=3, breadth=40)
        node_ids = {node["id"] for node in nodes}
        edges = [
            edge
            for edge in self.store.list_edges(user_tier=user_tier, repo_scope=repo_scope, relationship="calls")
            if edge["source_id"] in node_ids and edge["target_id"] in node_ids
        ]
        width = max(360, 140 * max(1, len(nodes)))
        height = 220
        positions = {
            node["id"]: (70 + index * 130, 110)
            for index, node in enumerate(nodes)
        }
        edge_markup = []
        for edge in edges:
            source = positions.get(edge["source_id"])
            target = positions.get(edge["target_id"])
            if not source or not target:
                continue
            edge_markup.append(
                f'<line x1="{source[0]}" y1="{source[1]}" x2="{target[0]}" y2="{target[1]}" '
                'stroke="#2f3a45" stroke-width="2" marker-end="url(#arrow)" />'
            )
        node_markup = []
        for node in nodes:
            x, y = positions[node["id"]]
            label = html.escape(node.get("symbol_name") or node["file_path"])
            node_markup.append(
                f'<g><rect x="{x - 46}" y="{y - 22}" width="92" height="44" rx="6" '
                'fill="#f8fafc" stroke="#111827" stroke-width="1.5" />'
                f'<text x="{x}" y="{y + 5}" text-anchor="middle" font-family="monospace" '
                f'font-size="12" fill="#111827">{label}</text></g>'
            )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="Call graph">'
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="7" refY="3" '
            'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#2f3a45" /></marker></defs>'
            f'{"".join(edge_markup)}{"".join(node_markup)}</svg>'
        )
