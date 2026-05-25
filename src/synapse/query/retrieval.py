from __future__ import annotations

import json
from typing import Any

from synapse.context.dag import ContextDag
from synapse.provider.base import LLMProvider
from synapse.serialization import stable_hash
from synapse.storage.sqlite import SQLiteEventStore


class HybridRetrievalEngine:
    """Working 4-stage hybrid context retrieval engine for AI coding agents."""

    def __init__(
        self,
        *,
        event_store: SQLiteEventStore,
        dag: ContextDag,
        llm_provider: LLMProvider,
    ) -> None:
        self.event_store = event_store
        self.dag = dag
        self.llm_provider = llm_provider
        self.max_traversal_nodes = 500
        self.max_semantic_candidates = 200

    def retrieve(
        self,
        query: str,
        context_hash: str,
        *,
        max_tokens: int = 4000,
        expansion_depth: int = 3,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Perform the 4-stage hybrid retrieval:

        1. Temporal Filter: Extract the active elements at context_hash ancestry.
        2. Structural Traversal: Identify start nodes from query and expand to neighbors.
        3. Semantic Recall: Rank semantic objects within the traversed boundary using structural reranking.
        4. LLM Synthesis: Pack bounded context and call LLM.
        """
        # --- Stage 1: Temporal Filtering ---
        active_nodes, active_semantics, active_edges = self._reconstruct_active_state(context_hash)

        # --- Stage 2: Structural Traversal ---
        # Find starting nodes matching keywords
        query_words = {word.lower().strip() for word in query.split() if len(word) > 2}
        start_nodes = set()
        for nid, node in active_nodes.items():
            labels_str = " ".join(node.get("labels", [])).lower()
            metadata_str = str(node.get("metadata", {})).lower()
            source_uri = str(node.get("source_uri", "")).lower()
            if any(
                word in labels_str or word in metadata_str or word in source_uri
                for word in query_words
            ):
                start_nodes.add(nid)

        # Expand neighbors up to a fixed bound to avoid graph and token explosions.
        # Track structural distance for reranking.
        visited_nodes: dict[str, int] = dict.fromkeys(start_nodes, 0)
        frontier = set(start_nodes)
        for depth in range(1, expansion_depth + 1):
            next_frontier = set()
            for edge in active_edges.values():
                if len(visited_nodes) >= self.max_traversal_nodes:
                    break
                from_id = edge["from_id"]
                to_id = edge["to_id"]
                if from_id in frontier and to_id not in visited_nodes:
                    next_frontier.add(to_id)
                    visited_nodes[to_id] = depth
                if to_id in frontier and from_id not in visited_nodes:
                    next_frontier.add(from_id)
                    visited_nodes[from_id] = depth
            frontier = next_frontier

        if not visited_nodes:
            ordered_nodes = sorted(
                active_nodes.items(),
                key=lambda item: (
                    str(item[1].get("source_uri", "")),
                    str(item[1].get("stable_id", item[0])),
                ),
            )
            visited_nodes = {node_id: 2 for node_id, _ in ordered_nodes[: self.max_traversal_nodes]}

        # --- Stage 3: Semantic Recall ---
        # Collect semantic objects linked to visited nodes
        candidate_semantics = []
        # Mapping from source_uri to best structural distance
        uri_distances: dict[str, int] = {}
        for nid, dist in visited_nodes.items():
            uri = active_nodes[nid].get("source_uri")
            if uri:
                uri_distances[uri] = min(uri_distances.get(uri, dist), dist)

        for sid, sem in active_semantics.items():
            # Invalidation Check: If this is an overlay tied to a target,
            # verify the target still exists in the active context.
            metadata = sem.get("metadata_json", {}) or sem.get("metadata", {})
            target_id = metadata.get("target_stable_id")
            if target_id and target_id not in active_nodes and target_id not in active_semantics:
                continue

            uri = sem.get("source_uri")
            sem_dist = None
            stable_id = str(sem.get("stable_id")) if sem.get("stable_id") else None

            if sid in visited_nodes:
                sem_dist = visited_nodes[sid]
            elif stable_id and stable_id in visited_nodes:
                sem_dist = visited_nodes[stable_id]
            elif target_id and isinstance(target_id, str) and target_id in visited_nodes:
                sem_dist = visited_nodes[target_id]
            elif uri and isinstance(uri, str) and uri in uri_distances:
                sem_dist = uri_distances[uri]

            if sem_dist is not None:
                sem["_structural_distance"] = sem_dist
                candidate_semantics.append(sem)

        if not candidate_semantics:
            candidate_semantics = sorted(
                active_semantics.values(),
                key=lambda sem: (
                    str(sem.get("source_uri", "")),
                    str(sem.get("stable_id", "")),
                ),
            )
            for sem in candidate_semantics:
                sem["_structural_distance"] = 2

        candidate_semantics = candidate_semantics[: self.max_semantic_candidates]

        # Rank candidates based on structural reranking heuristics
        ranked_candidates = self._rank_semantics(query, candidate_semantics)

        # --- Stage 4: Context Packing Engine ---
        # Budget tokens (approx 4 chars per token)
        char_budget = max_tokens * 4
        packed_context_blocks = []
        grounding_sources = []
        char_used = 0
        seen_uris = set()
        trace_scores = []

        for sem, score in ranked_candidates:
            uri = sem.get("source_uri", "Unknown")
            kind = sem.get("kind", "note")
            summary = sem.get("summary", "")

            trace_scores.append(
                {
                    "stable_id": sem.get("stable_id"),
                    "source_uri": uri,
                    "score": score,
                    "structural_distance": sem.get("_structural_distance"),
                }
            )

            # Deduplication logic: limit repeated uri info unless high relevance overlay
            dedup_key = f"{uri}:{kind}"
            if dedup_key in seen_uris and "overlay" not in sem.get("tags", []):
                continue
            seen_uris.add(dedup_key)

            block = f"### Element: {uri}\nKind: {kind}\nSummary: {summary}\n"
            if char_used + len(block) > char_budget:
                break
            packed_context_blocks.append(block)
            grounding_sources.append(sem)
            char_used += len(block)

        context_str = "\n".join(packed_context_blocks)

        system_prompt = (
            "You are an AI coding assistant with deep structural repository understanding.\n"
            "Answer the user query based ONLY on the provided grounded structural context.\n"
            "Follow these rules:\n"
            "1. Rely exclusively on the provided context. If the answer cannot be found, state what is missing.\n"
            "2. Cite the exact source files and structural elements in your explanation.\n"
            "3. Use overlays and annotations to guide your reasoning.\n"
        )

        user_prompt = f"Repository Context:\n{context_str}\n\nUser Question: {query}\n"

        response = self.llm_provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )

        trace = {
            "start_nodes_count": len(start_nodes),
            "expanded_nodes_count": len(visited_nodes),
            "semantic_candidates_count": len(candidate_semantics),
            "packed_blocks_count": len(packed_context_blocks),
            "top_scores": trace_scores[:10],
            "tokens_budget_used": char_used // 4,
        }

        return response.content, grounding_sources, trace

    def active_context_state(
        self, context_hash: str
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        return self._reconstruct_active_state(context_hash)

    def _reconstruct_active_state(
        self, context_hash: str
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        ordered_ancestry = self.dag.ancestry(context_hash)
        ancestry = set(ordered_ancestry)

        node_rows = self.event_store.graph_nodes_for_contexts(ordered_ancestry)
        edge_rows = self.event_store.graph_edges_for_contexts(ordered_ancestry)
        sem_rows = self.event_store.semantic_objects_for_contexts(ordered_ancestry)

        active_nodes: dict[str, dict[str, Any]] = {}
        active_semantics: dict[str, dict[str, Any]] = {}
        active_edges: dict[str, dict[str, Any]] = {}

        nodes_by_ctx: dict[str, list[Any]] = {}
        for r in node_rows:
            nodes_by_ctx.setdefault(str(r["context_hash"]), []).append(r)
        edges_by_ctx: dict[str, list[Any]] = {}
        for r in edge_rows:
            edges_by_ctx.setdefault(str(r["context_hash"]), []).append(r)
        sems_by_ctx: dict[str, list[Any]] = {}
        for r in sem_rows:
            sems_by_ctx.setdefault(str(r["context_hash"]), []).append(r)

        for ctx in reversed(ordered_ancestry):
            for r in nodes_by_ctx.get(ctx, []):
                valid_to = r.get("valid_to_context")
                if valid_to and str(valid_to) in ancestry:
                    active_nodes.pop(str(r["stable_id"]), None)
                else:
                    active_nodes[str(r["stable_id"])] = {
                        "stable_id": str(r["stable_id"]),
                        "node_type": str(r["node_type"]),
                        "labels": json.loads(str(r["labels_json"])),
                        "metadata": json.loads(str(r["metadata_json"])),
                        "source_uri": str(r["source_uri"]),
                        "confidence": float(r["confidence"]),
                        "valid_from_context": r.get("valid_from_context"),
                        "valid_to_context": r.get("valid_to_context"),
                    }

            for r in edges_by_ctx.get(ctx, []):
                valid_to = r.get("valid_to_context")
                if valid_to and str(valid_to) in ancestry:
                    active_edges.pop(str(r["stable_id"]), None)
                else:
                    active_edges[str(r["stable_id"])] = {
                        "stable_id": str(r["stable_id"]),
                        "from_id": str(r["from_id"]),
                        "to_id": str(r["to_id"]),
                        "relation": str(r["relation"]),
                        "metadata": json.loads(str(r["metadata_json"])),
                        "source_uri": str(r["source_uri"]),
                        "confidence": float(r["confidence"]),
                        "valid_from_context": r.get("valid_from_context"),
                        "valid_to_context": r.get("valid_to_context"),
                    }

            for r in sems_by_ctx.get(ctx, []):
                valid_to = r.get("valid_to_context")
                if valid_to and str(valid_to) in ancestry:
                    active_semantics.pop(str(r["stable_id"]), None)
                else:
                    active_semantics[str(r["stable_id"])] = {
                        "stable_id": str(r["stable_id"]),
                        "kind": str(r["kind"]),
                        "summary": str(r["summary"]),
                        "tags": json.loads(str(r["tags_json"])),
                        "metadata_json": json.loads(str(r["metadata_json"])),
                        "source_uri": str(r["source_uri"]),
                        "source_hash": r.get("source_hash"),
                        "confidence": float(r["confidence"]),
                        "valid_from_context": r.get("valid_from_context"),
                        "valid_to_context": r.get("valid_to_context"),
                    }

        return active_nodes, active_semantics, active_edges

    def _rank_semantics(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[tuple[dict[str, Any], float]]:
        """Rank semantic candidates based on query similarity.

        Implements production-grade hybrid retrieval scoring:
        score = semantic_similarity + structural_distance_weight + confidence_weight + overlay_quality
        """
        query_words = {w.lower().strip() for w in query.split() if len(w) > 2}
        try:
            query_emb = self._get_embedding(query)
        except Exception:
            query_emb = None

        ranked = []
        for cand in candidates:
            summary = cand.get("summary", "")
            match_count = sum(1 for w in query_words if w in summary.lower())
            keyword_score = match_count / max(1, len(query_words))

            emb_score = 0.0
            if query_emb:
                try:
                    cand_emb = self._get_embedding(summary)
                    emb_score = self._cosine_similarity(query_emb, cand_emb)
                except Exception:
                    emb_score = 0.0

            # Structural distance penalty
            dist = cand.get("_structural_distance", 2)
            structural_weight = max(0.0, 1.0 - (dist * 0.2))

            # Confidence weight
            confidence = cand.get("confidence", 0.5)

            # Overlay quality boost
            tags = cand.get("tags", [])
            overlay_boost = 0.2 if "overlay" in tags else 0.0

            total_score = (
                0.5 * emb_score
                + 0.2 * keyword_score
                + 0.15 * structural_weight
                + 0.1 * confidence
                + 0.05 * overlay_boost
            )
            ranked.append((cand, total_score))

        # Sort descending by score
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def _get_embedding(self, text: str) -> list[float]:
        provider_name = type(self.llm_provider).__name__
        text_hash = stable_hash({"text": text})

        cached = self.event_store.get_embedding(text_hash, provider_name)
        if cached is not None:
            return cached

        emb = self.llm_provider.embed(text)
        self.event_store.put_embedding(text_hash, provider_name, emb)
        return emb

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot_product = sum(x * y for x, y in zip(a, b, strict=False))
        magnitude_a = sum(x * x for x in a) ** 0.5
        magnitude_b = sum(x * x for x in b) ** 0.5
        if magnitude_a * magnitude_b == 0:
            return 0.0
        return float(dot_product / (magnitude_a * magnitude_b))
