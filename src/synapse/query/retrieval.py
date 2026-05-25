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
        self._embedding_cache: dict[str, list[float]] = {}
        self.max_embedding_cache_entries = 1024
        self.max_traversal_nodes = 500
        self.max_semantic_candidates = 200

    def retrieve(
        self,
        query: str,
        context_hash: str,
        *,
        max_tokens: int = 4000,
        expansion_depth: int = 2,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Perform the 4-stage hybrid retrieval:

        1. Temporal Filter: Extract the active elements at context_hash ancestry.
        2. Structural Traversal: Identify start nodes from query and expand to neighbors.
        3. Semantic Recall: Rank semantic objects within the traversed boundary.
        4. LLM Synthesis: Pack grounded context and call LLM.
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
        visited_nodes = set(start_nodes)
        frontier = set(start_nodes)
        for _ in range(expansion_depth):
            next_frontier = set()
            for edge in active_edges.values():
                if len(visited_nodes) >= self.max_traversal_nodes:
                    break
                from_id = edge["from_id"]
                to_id = edge["to_id"]
                if from_id in frontier and to_id not in visited_nodes:
                    next_frontier.add(to_id)
                    visited_nodes.add(to_id)
                if to_id in frontier and from_id not in visited_nodes:
                    next_frontier.add(from_id)
                    visited_nodes.add(from_id)
            frontier = next_frontier

        if not visited_nodes:
            ordered_nodes = sorted(
                active_nodes.items(),
                key=lambda item: (
                    str(item[1].get("source_uri", "")),
                    str(item[1].get("stable_id", item[0])),
                ),
            )
            visited_nodes = {node_id for node_id, _ in ordered_nodes[: self.max_traversal_nodes]}

        # --- Stage 3: Semantic Recall ---
        # Collect semantic objects linked to visited nodes (matching by source_uri or stable_id)
        candidate_semantics = []
        visited_uris = {
            active_nodes[nid]["source_uri"]
            for nid in visited_nodes
            if "source_uri" in active_nodes[nid]
        }

        for sid, sem in active_semantics.items():
            is_match = (
                sid in visited_nodes
                or sem.get("source_uri") in visited_uris
                or sem.get("stable_id") in visited_nodes
            )
            if is_match:
                candidate_semantics.append(sem)

        if not candidate_semantics:
            candidate_semantics = sorted(
                active_semantics.values(),
                key=lambda sem: (
                    str(sem.get("source_uri", "")),
                    str(sem.get("stable_id", "")),
                ),
            )
        candidate_semantics = candidate_semantics[: self.max_semantic_candidates]

        # Rank candidates based on semantic similarity
        ranked_candidates = self._rank_semantics(query, candidate_semantics)

        # --- Stage 4: LLM Synthesis ---
        # Budget tokens (approx 4 chars per token)
        char_budget = max_tokens * 4
        packed_context_blocks = []
        grounding_sources = []
        char_used = 0

        for sem, _score in ranked_candidates:
            block = (
                f"### Element: {sem.get('source_uri', 'Unknown')}\n"
                f"Kind: {sem.get('kind', 'note')}\n"
                f"Summary: {sem.get('summary', '')}\n"
                f"Metadata: {json.dumps(sem.get('metadata_json', {}))}\n"
            )
            if char_used + len(block) > char_budget:
                break
            packed_context_blocks.append(block)
            grounding_sources.append(sem)
            char_used += len(block)

        context_str = "\n".join(packed_context_blocks)

        system_prompt = (
            "You are an AI coding assistant with repository understanding.\n"
            "Answer the user query based ONLY on the following structurally-relevant repository context.\n"
            "Follow these grounding rules:\n"
            "1. Rely only on the provided context. If it does not contain the answer, say what is missing.\n"
            "2. Cite the source files (e.g. `src/synapse/cli.py`) in your explanation.\n"
            "3. Treat semantic overlays as annotations. Structural extraction remains the source of truth.\n"
        )

        user_prompt = f"Repository Context:\n{context_str}\n\nUser Question: {query}\n"

        response = self.llm_provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )

        return response.content, grounding_sources

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

        Combines keyword matches and cosine similarity of embeddings.
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

            # 2. Embedding similarity score
            emb_score = 0.0
            if query_emb:
                try:
                    cand_emb = self._get_embedding(summary)
                    emb_score = self._cosine_similarity(query_emb, cand_emb)
                except Exception:
                    emb_score = 0.0

            # Combined score: prioritize embeddings, fall back to keyword score
            total_score = 0.7 * emb_score + 0.3 * keyword_score
            ranked.append((cand, total_score))

        # Sort descending by score
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def _get_embedding(self, text: str) -> list[float]:
        key = stable_hash(
            {
                "provider": type(self.llm_provider).__name__,
                "text": text,
            }
        )
        if key in self._embedding_cache:
            return self._embedding_cache[key]
        emb = self.llm_provider.embed(text)
        if len(self._embedding_cache) >= self.max_embedding_cache_entries:
            self._embedding_cache.pop(next(iter(self._embedding_cache)))
        self._embedding_cache[key] = emb
        return emb

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot_product = sum(x * y for x, y in zip(a, b, strict=False))
        magnitude_a = sum(x * x for x in a) ** 0.5
        magnitude_b = sum(x * x for x in b) ** 0.5
        if magnitude_a * magnitude_b == 0:
            return 0.0
        return float(dot_product / (magnitude_a * magnitude_b))
