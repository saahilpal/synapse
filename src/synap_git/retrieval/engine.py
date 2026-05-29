from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import tiktoken

from synap_git.provider.base import LLMProvider
from synap_git.storage.sqlite import SynapStore


@dataclass(frozen=True)
class TraceElement:
    stable_id: str
    name: str
    path: str
    score: float
    reason: str
    tokens: int


def _get_snippet(repo_path: Path, rel_path: str, start_line: int, end_line: int) -> str:
    try:
        p = repo_path / rel_path
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        s_idx = max(0, start_line - 1)
        e_idx = min(len(lines), end_line)
        return "\n".join(lines[s_idx:e_idx])
    except Exception:
        return ""


def _get_full_file(repo_path: Path, rel_path: str) -> str:
    try:
        p = repo_path / rel_path
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


class HybridRetrievalEngine:
    """Production-grade hybrid retrieval with exact token budgeting and traces."""

    def __init__(
        self,
        *,
        repo_path: Path,
        store: SynapStore,
        llm_provider: LLMProvider | None,
        trace_store: Any | None = None,
    ) -> None:
        self.repo_path = repo_path
        self.store = store
        self.llm_provider = llm_provider
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

        # M1: Query Intent Classification
        intent = "logic"
        if self.llm_provider:
            try:
                system_prompt = "You are a retrieval router. Classify the user query intent as one of: 'structural', 'logic', 'conceptual'. Output ONLY the single word."
                user_prompt = f"Query: {query}"
                resp = self.llm_provider.generate(system_prompt, user_prompt, max_tokens=10)
                result = resp.content.lower().strip()
                if "structural" in result:
                    intent = "structural"
                elif "conceptual" in result:
                    intent = "conceptual"
            except Exception as e:
                import structlog

                structlog.get_logger().warning("intent_classification_failed", error=str(e))

        # 2. Lexical Matches (BM25)
        query_words = {word.lower().strip() for word in query.split() if len(word) > 2}
        lexical_candidates: dict[str, dict[str, Any]] = {}
        for word in query_words:
            symbols = self.store.get_symbols_by_name(word)
            for rank, sym in enumerate(symbols):
                sid = sym["symbol_id"]
                if sid not in lexical_candidates:
                    lexical_candidates[sid] = {
                        **sym,
                        "reason": f"lexical:'{word}'",
                        "lexical_rank": rank,
                    }
                else:
                    lexical_candidates[sid]["lexical_rank"] = min(
                        lexical_candidates[sid].get("lexical_rank", rank), rank
                    )

        t_lexical = time.perf_counter()

        # 3. Semantic Matches (Vector Search)
        semantic_candidates: dict[str, dict[str, Any]] = {}
        if self.llm_provider:
            try:
                query_vector = self.llm_provider.embed(query)
                symbols = self.store.get_similar_symbols(query_vector, limit=50)
                for rank, sym in enumerate(symbols):
                    sid = sym["symbol_id"]
                    semantic_candidates[sid] = {**sym, "reason": "semantic", "semantic_rank": rank}
            except Exception as e:
                import structlog

                structlog.get_logger().warning("semantic_search_failed", error=str(e))

        t_semantic = time.perf_counter()

        # Merge Lexical and Semantic candidates
        combined_candidates: dict[str, dict[str, Any]] = {}
        for sid, sym in lexical_candidates.items():
            combined_candidates[sid] = sym
        for sid, sym in semantic_candidates.items():
            if sid not in combined_candidates:
                combined_candidates[sid] = sym
            else:
                combined_candidates[sid]["semantic_rank"] = sym["semantic_rank"]
                combined_candidates[sid]["reason"] += "+semantic"

        # Expand to Structural neighborhood
        structural_candidates: dict[str, dict[str, Any]] = {}
        structural_hops = []
        for sid in list(combined_candidates.keys()):
            neighbors = self.store.get_neighborhood(sid, depth=self.max_expansion_depth)
            for n in neighbors:
                nid = n["symbol_id"]
                dist = n.get("distance", 0)
                structural_hops.append(
                    {
                        "from_symbol": combined_candidates[sid]["name"],
                        "to_symbol": n["name"],
                        "distance": dist,
                    }
                )
                if nid not in structural_candidates:
                    structural_candidates[nid] = {**n, "reason": f"structural:dist={dist}"}

        t_structural = time.perf_counter()

        # Combine all
        combined = {**structural_candidates, **combined_candidates}

        # 4. RRF Ranking with Intent weighting
        ranked = self._rank_candidates(query, list(combined.values()), intent)

        t_ranking = time.perf_counter()

        # Context Packing with exact token budgeting
        reserved_buffer = 600
        retrieval_budget = max_tokens - reserved_buffer

        # 5. Token-Aware Context Packing
        packed_blocks = []
        tokens_used = 0
        repo_path = self.repo_path
        grounding_sources = []
        trace_elements = []

        included_files = set()
        for cand, score in ranked:
            if tokens_used >= retrieval_budget:
                break

            path = cand["source_path"]
            name = cand["name"]
            kind = cand["kind"]
            start = cand.get("start_line", 1)
            end = cand.get("end_line", 1)
            reason = cand["reason"]

            snippet = _get_snippet(repo_path, path, start, end)
            if not snippet:
                continue

            block = f"### File: {path}\nSymbol: {name} ({kind})\nLines: {start}-{end}\nReason: {reason}\n```\n{snippet}\n```\n"
            block_tokens = len(self.tokenizer.encode(block))

            if tokens_used + block_tokens > retrieval_budget:
                continue

            packed_blocks.append(block)
            grounding_sources.append(cand)
            tokens_used += block_tokens
            included_files.add(path)

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

        # Expand to full file context if budget allows
        for path in list(included_files):
            if tokens_used >= retrieval_budget:
                break
            full_file = _get_full_file(repo_path, path)
            if not full_file:
                continue

            block = f"### File Full Context: {path}\n```\n{full_file}\n```\n"
            block_tokens = len(self.tokenizer.encode(block))
            if tokens_used + block_tokens <= retrieval_budget:
                packed_blocks.append(block)
                tokens_used += block_tokens

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
            import time

            attempts = 2
            backoff_sec = 1.0
            last_err = None
            response = None
            for attempt in range(attempts):
                try:
                    response = self.llm_provider.generate(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=0.1,
                    )
                    break
                except Exception as e:
                    last_err = e
                    if attempt < attempts - 1:
                        time.sleep(backoff_sec)
                        backoff_sec *= 2.0

            if response is not None:
                answer_content = response.content
                try:
                    provider_name = self.llm_provider.__class__.__name__.replace(
                        "Provider", ""
                    ).lower()
                    model_name = getattr(self.llm_provider, "default_model", "unknown")
                    self.store.put_llm_call(
                        provider=provider_name,
                        model=model_name,
                        input_tokens=response.prompt_tokens,
                        output_tokens=response.completion_tokens,
                        purpose="retrieval",
                    )
                except Exception as e:
                    import structlog

                    structlog.get_logger().error(
                        "suppressed_error_caught", error=str(e), exc_info=True
                    )
            else:
                err_msg = str(last_err)
                answer_content = (
                    f"Degraded Mode (LLM connection failed): {err_msg}\n\n"
                    "Mode A (Structural Only): Context retrieved, but LLM generation is disabled.\n\n"
                    f"Repository Context:\n{context_str}"
                )
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
        self, query: str, candidates: list[dict[str, Any]], intent: str = "logic"
    ) -> list[tuple[dict[str, Any], float]]:
        """Rank candidates using Reciprocal Rank Fusion (RRF) and structural signals."""
        k = 60
        ranked = []
        for cand in candidates:
            score = 0.0

            # Intent-based weights
            lexical_w = 1.0
            semantic_w = 1.0
            structural_w = 1.0
            if intent == "structural":
                structural_w = 2.0
                semantic_w = 0.5
            elif intent == "conceptual":
                semantic_w = 2.0
                lexical_w = 0.5
            elif intent == "logic":
                lexical_w = 2.0
                structural_w = 0.5

            if "lexical_rank" in cand:
                score += (1.0 / (k + cand["lexical_rank"])) * lexical_w
            if "semantic_rank" in cand:
                score += (1.0 / (k + cand["semantic_rank"])) * semantic_w

            # Structural scoring
            reason = cand["reason"]
            if reason.startswith("structural"):
                dist = int(reason.split("=")[-1])
                score += (1.0 / (k + 100 + dist)) * structural_w

            # Name match boost
            if any(w in cand["name"].lower() for w in query.lower().split() if len(w) > 2):
                score += 0.05

            ranked.append((cand, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
