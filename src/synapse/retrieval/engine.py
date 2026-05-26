from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import tiktoken

from synapse.provider.base import LLMProvider
from synapse.storage.sqlite import SynapseStore


@dataclass(frozen=True)
class TraceElement:
    stable_id: str
    name: str
    path: str
    score: float
    reason: str
    tokens: int


class HybridRetrievalEngine:
    """Production-grade hybrid retrieval with exact token budgeting and traces."""

    def __init__(
        self,
        *,
        store: SynapseStore,
        llm_provider: LLMProvider | None,
        trace_store: Any | None = None,
    ) -> None:
        self.store = store
        self.llm_provider = llm_provider
        # Use tiktoken for exact budgeting
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.max_expansion_depth = 2
        self.trace_store = trace_store

    def retrieve(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        is_dirty: bool = False,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Perform deterministic 4-stage retrieval: Temporal -> Structural -> Lexical -> Semantic."""
        import time

        t_start = time.perf_counter()
        trace_id = str(uuid4())
        start_time = datetime.now(UTC)

        # 1. Temporal Filter: Handled by SynapseStore methods which operate on current state
        # (In a more advanced version, we'd filter by specific commit/branch here)

        # 2. & 3. Lexical + Structural
        query_words = {word.lower().strip() for word in query.split() if len(word) > 2}

        # Start with Lexical matches
        lexical_candidates: dict[str, dict[str, Any]] = {}
        for word in query_words:
            symbols = self.store.get_symbols_by_name(word)
            for sym in symbols:
                sid = sym["symbol_id"]
                if sid not in lexical_candidates:
                    lexical_candidates[sid] = {**sym, "reason": f"lexical:'{word}'"}

        t_lexical = time.perf_counter()

        # Expand to Structural neighborhood
        structural_candidates: dict[str, dict[str, Any]] = {}
        structural_hops = []
        for sid in list(lexical_candidates.keys()):
            neighbors = self.store.get_neighborhood(sid, depth=self.max_expansion_depth)
            for n in neighbors:
                nid = n["symbol_id"]
                dist = n.get("distance", 0)
                structural_hops.append(
                    {
                        "from_symbol": lexical_candidates[sid]["name"],
                        "to_symbol": n["name"],
                        "distance": dist,
                    }
                )
                if nid not in structural_candidates:
                    structural_candidates[nid] = {**n, "reason": f"structural:dist={dist}"}

        t_structural = time.perf_counter()

        # Combine and Rank
        combined = {**structural_candidates, **lexical_candidates}

        # 4. Semantic Ranking (simplified for recovery)
        ranked = self._rank_candidates(query, list(combined.values()))

        t_ranking = time.perf_counter()

        # Context Packing with exact token budgeting
        packed_blocks = []
        grounding_sources = []
        trace_elements = []
        tokens_used = 0

        # Reserve buffer for system/user prompts
        reserved_buffer = 600
        retrieval_budget = max_tokens - reserved_buffer

        for cand, score in ranked:
            path = cand["source_path"]
            name = cand["name"]
            kind = cand["kind"]
            lines = f"{cand['start_line']}-{cand['end_line']}"
            reason = cand["reason"]

            block = f"### File: {path}\nSymbol: {name} ({kind})\nLines: {lines}\nReason: {reason}\n"
            block_tokens = len(self.tokenizer.encode(block))

            if tokens_used + block_tokens > retrieval_budget:
                remaining = retrieval_budget - tokens_used
                trace_elements.append(
                    TraceElement(
                        stable_id=cand["symbol_id"],
                        name=name,
                        path=path,
                        score=score,
                        reason=f"truncated:over_budget. Requires {block_tokens} tokens, but only {remaining} remain.",
                        tokens=block_tokens,
                    )
                )
                continue

            packed_blocks.append(block)
            grounding_sources.append(cand)
            tokens_used += block_tokens

            trace_elements.append(
                TraceElement(
                    stable_id=cand["symbol_id"],
                    name=name,
                    path=path,
                    score=score,
                    reason=reason,
                    tokens=block_tokens,
                )
            )

        context_str = "\n".join(packed_blocks)

        # Gating: Only approved lessons affect retrieval
        approved_lessons = self.store.get_lessons("approved")
        if approved_lessons:
            lesson_blocks = ["# APPROVED SYSTEM MEMORY (CRITICAL: MUST ADHERE)"]
            for i, lesson in enumerate(approved_lessons, 1):
                lesson_blocks.append(
                    f"[{i}] DO NOT DO THIS: {lesson['what_failed']} - BECAUSE: {lesson['why_failed']}"
                )
            context_str = "\n".join(lesson_blocks) + "\n\n" + context_str

        system_prompt = (
            "You are an AI coding assistant with deep structural repository understanding.\n"
            "Answer the user query based ONLY on the provided grounded structural context.\n"
            "Cite source files and symbol names in your explanation.\n"
        )
        user_prompt = f"Repository Context:\n{context_str}\n\nUser Question: {query}\n"

        t_packing = time.perf_counter()

        if self.llm_provider:
            response = self.llm_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
            )
            answer_content = response.content
            try:
                provider_name = self.llm_provider.__class__.__name__.replace("Provider", "").lower()
                model_name = getattr(self.llm_provider, "default_model", "unknown")
                self.store.put_llm_call(
                    provider=provider_name,
                    model=model_name,
                    input_tokens=response.prompt_tokens,
                    output_tokens=response.completion_tokens,
                    purpose="retrieval",
                )
            except Exception:
                pass
        else:
            answer_content = (
                "Mode A (Structural Only): Context retrieved, but LLM generation is disabled."
            )

        t_llm = time.perf_counter()

        token_allocation = {
            "max_tokens": max_tokens,
            "reserved_buffer": reserved_buffer,
            "retrieval_budget": retrieval_budget,
            "tokens_used": tokens_used,
            "remaining": retrieval_budget - tokens_used,
        }

        timeline = {
            "lexical_search_ms": (t_lexical - t_start) * 1000,
            "structural_expansion_ms": (t_structural - t_lexical) * 1000,
            "semantic_ranking_ms": (t_ranking - t_structural) * 1000,
            "context_packing_ms": (t_packing - t_ranking) * 1000,
            "llm_generation_ms": (t_llm - t_packing) * 1000,
            "total_ms": (t_llm - t_start) * 1000,
        }

        trace = {
            "trace_id": trace_id,
            "query": query,
            "nodes_explored": len(combined),
            "tokens_used": tokens_used,
            "token_allocation": token_allocation,
            "timeline": timeline,
            "elements": [e.__dict__ for e in trace_elements[:40]],
            "structural_hops": structural_hops[:20],
            "dirty_tree_warning": is_dirty,
            "latency_ms": (t_llm - t_start) * 1000,
        }

        if self.trace_store:
            self.trace_store.record_trace(
                trace_type="retrieval",
                summary=f"Retrieval for query: {query}",
                details=trace,
            )

        return answer_content, grounding_sources, trace

    def _rank_candidates(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[tuple[dict[str, Any], float]]:
        """Rank based on priority: Lexical > Structural > Distance."""
        ranked = []
        for cand in candidates:
            # Base score from reason
            reason = cand["reason"]
            if reason.startswith("lexical"):
                score = 1.0
            elif reason.startswith("structural"):
                dist = int(reason.split("=")[-1])
                score = 0.8**dist
            else:
                score = 0.5

            # Name match boost
            if any(w in cand["name"].lower() for w in query.lower().split()):
                score += 0.2

            ranked.append((cand, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
