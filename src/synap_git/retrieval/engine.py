from __future__ import annotations

import functools
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
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


@functools.lru_cache(maxsize=256)
def _get_file_lines(repo_path: Path, rel_path: str) -> list[str] | None:
    try:
        p = repo_path / rel_path
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        import structlog

        structlog.get_logger().warning("file_read_failed", path=rel_path, error=str(e))
        return None


def _get_snippet(repo_path: Path, rel_path: str, start_line: int, end_line: int) -> str:
    lines = _get_file_lines(repo_path, rel_path)
    if lines is None:
        return ""
    s_idx = max(0, start_line - 1)
    e_idx = min(len(lines), end_line)
    return "\n".join(lines[s_idx:e_idx])


def _get_full_file(repo_path: Path, rel_path: str) -> str:
    lines = _get_file_lines(repo_path, rel_path)
    if lines is None:
        return ""
    return "\n".join(lines)


def _normalize_name(name: str) -> str:
    """Normalize identifier by removing underscores and special characters, converting to lowercase."""
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()


def _split_into_subtokens(text: str) -> list[str]:
    """
    Split camelCase, PascalCase, and snake_case into sub-tokens while preserving >= 2 char tokens
    such as db, id, ip, ui, ws, os, fn.
    """
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    parts = re.split(r"[^a-zA-Z0-9]+", s2)
    return [p.lower() for p in parts if len(p) >= 2]


def _extract_query_tokens(query: str) -> set[str]:
    """
    Extract lexical sub-tokens from a query string, preserving short identifiers (>= 2 chars)
    and splitting across casing conventions (camelCase, snake_case).
    """
    tokens: set[str] = set()
    for raw in query.split():
        cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", raw).lower()
        if len(cleaned) >= 2:
            tokens.add(cleaned)
        sub_tokens = _split_into_subtokens(raw)
        for tok in sub_tokens:
            if len(tok) >= 2:
                tokens.add(tok)
        norm = _normalize_name(raw)
        if len(norm) >= 2:
            tokens.add(norm)
    return tokens


def _is_test_candidate(path: str, name: str) -> bool:
    """Determine whether a candidate symbol is a test fixture or located in test code."""
    p = path.replace("\\", "/").lower()
    n = name.lower()
    return (
        p.startswith("tests/")
        or "/tests/" in p
        or p.startswith("test/")
        or "/test_" in p
        or p.endswith("_test.py")
        or p.startswith("test_")
        or n.startswith("test_")
        or "fixture" in n
        or "mock" in n
    )


class QueryIntent(str, Enum):
    SYMBOL_LOOKUP = "symbol_lookup"
    NAVIGATION = "navigation"
    ARCHITECTURE = "architecture"
    DEBUGGING = "debugging"
    PAST_DECISIONS = "past_decisions"


def classify_intent_5tier(query: str) -> QueryIntent:
    """
    5-tier query intent router:
    1. Past Decisions: architectural choices, decisions, history, ADRs.
    2. Debugging: errors, failures, bugs, reverts, why something failed.
    3. Architecture: high-level design, overview, conceptual system diagrams.
    4. Navigation: callers, callees, file paths, imports, references.
    5. Symbol Lookup: exact symbols, declarations, function/class lookups.
    """
    q_lower = query.lower()

    # Tier 1: Past Decisions
    decision_markers = (
        "decision",
        "decisions",
        "why did we",
        "why was",
        "rationale",
        "tradeoff",
        "trade-off",
        "adr",
        "past choice",
    )
    if any(m in q_lower for m in decision_markers):
        return QueryIntent.PAST_DECISIONS

    # Tier 2: Debugging
    debugging_markers = (
        "fail",
        "failing",
        "error",
        "bug",
        "crash",
        "exception",
        "broken",
        "fix",
        "revert",
        "reverted",
        "why does",
        "why did",
        "issue",
        "traceback",
    )
    if any(m in q_lower for m in debugging_markers):
        return QueryIntent.DEBUGGING

    # Tier 3: Architecture
    architecture_markers = (
        "architecture",
        "overview",
        "design",
        "concept",
        "high level",
        "system",
        "pattern",
        "summary",
        "structure",
        "what is",
        "what are",
        "what does",
        "how does",
        "explain",
    )
    if any(m in q_lower for m in architecture_markers):
        return QueryIntent.ARCHITECTURE

    # Tier 4: Navigation
    navigation_markers = (
        "where is",
        "where are",
        "callers",
        "callees",
        "imports",
        "imported",
        "references",
        "referenced by",
        "find file",
        "path to",
        "dependencies",
        "/",
        ".py",
        ".ts",
        ".rs",
        ".go",
    )
    if any(m in q_lower for m in navigation_markers):
        return QueryIntent.NAVIGATION

    # Tier 5: Symbol Lookup
    return QueryIntent.SYMBOL_LOOKUP


def _classify_intent_fast(query: str) -> str:
    """
    Classify query intent into 'conceptual', 'structural', or 'logic'.
    Inverted hierarchy: conceptual words take precedence over structural punctuation
    so queries like 'what is user_id' or 'why does auth/login.py fail' are treated conceptually.
    """
    q_lower = query.lower()
    conceptual_words = (
        "what is",
        "what are",
        "what does",
        "why",
        "how does",
        "how do",
        "how can",
        "how to",
        "overview",
        "explain",
        "architecture",
        "design",
        "concept",
        "summary",
        "pattern",
        "high level",
        "purpose",
        "describe",
    )
    if any(cw in q_lower for cw in conceptual_words):
        return "conceptual"
    structural_tokens = (
        "def ",
        "class ",
        "fn ",
        "func ",
        "import ",
        "from ",
        "()",
        "::",
        "->",
        ".py",
        ".ts",
        ".js",
        ".rs",
        ".go",
        "/",
        "\\",
        "_",
    )
    if any(tok in q_lower for tok in structural_tokens):
        return "structural"
    return "logic"


class HybridRetrievalEngine:
    """Production-grade hybrid retrieval with exact token budgeting and traces."""

    def __init__(
        self,
        *,
        repo_path: Path,
        store: SynapStore,
        llm_provider: LLMProvider | None,
        embed_provider: LLMProvider | None = None,
        trace_store: Any | None = None,
    ) -> None:
        self.repo_path = repo_path
        self.store = store
        self.llm_provider = llm_provider
        self.embed_provider = embed_provider
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.max_expansion_depth = 2
        self.trace_store = trace_store
        self._pagerank_cache: dict[str, float] | None = None
        self._hub_ranks: dict[str, int] | None = None
        try:
            self.index_docs()
        except Exception as e:
            import structlog

            structlog.get_logger().warning("doc_indexing_failed", error=str(e))

    def index_docs(self) -> int:
        """
        Index documentation files (CHANGELOG.md, README.md, CLAUDE.md, AGENTS.md)
        into symbols_fts so documentation queries don't suffer a 100% miss rate.
        """
        doc_names = {"changelog.md", "readme.md", "claude.md", "agents.md"}
        indexed = 0
        if not self.repo_path.exists():
            return 0

        for path in self.repo_path.glob("*.md"):
            if path.name.lower() in doc_names:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    import structlog

                    structlog.get_logger().warning("doc_read_failed", path=str(path), error=str(e))
                    continue

                rel_path = str(path.relative_to(self.repo_path))
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                file_id = hashlib.sha256((rel_path + content_hash).encode()).hexdigest()

                lines = content.splitlines()
                sections: list[dict[str, Any]] = []
                cur_header = path.name
                cur_start = 1
                cur_lines: list[str] = []

                for idx, line in enumerate(lines, 1):
                    if line.startswith("#"):
                        if cur_lines:
                            sections.append(
                                {
                                    "name": cur_header,
                                    "start_line": cur_start,
                                    "end_line": idx - 1,
                                    "text": "\n".join(cur_lines),
                                }
                            )
                        cur_header = line.lstrip("#").strip() or path.name
                        cur_start = idx
                        cur_lines = [line]
                    else:
                        cur_lines.append(line)

                if cur_lines:
                    sections.append(
                        {
                            "name": cur_header,
                            "start_line": cur_start,
                            "end_line": len(lines),
                            "text": "\n".join(cur_lines),
                        }
                    )

                symbols = []
                for s_idx, sec in enumerate(sections):
                    sym_id = hashlib.sha256(f"{file_id}:{s_idx}:{sec['name']}".encode()).hexdigest()
                    symbols.append(
                        {
                            "symbol_id": sym_id,
                            "name": sec["name"],
                            "kind": "doc_section",
                            "start_line": sec["start_line"],
                            "end_line": sec["end_line"],
                            "ast_hash": hashlib.sha256(sec["text"].encode()).hexdigest()[:16],
                            "metadata": {"doc": True, "body": sec["text"]},
                        }
                    )

                self.store.upsert_file_and_symbols(
                    file_id=file_id,
                    path=rel_path,
                    git_oid=content_hash[:8],
                    content_hash=content_hash,
                    language="markdown",
                    symbols=symbols,
                )

                with self.store.connect() as conn:
                    for sym in symbols:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO symbols_fts (symbol_id, name, kind, body)
                            VALUES (?, ?, ?, ?)
                            """,
                            (sym["symbol_id"], sym["name"], sym["kind"], sym["metadata"]["body"]),
                        )

                indexed += len(symbols)

        return indexed

    def _get_pagerank_data(
        self, force_refresh: bool = False
    ) -> tuple[dict[str, float], dict[str, int]]:
        """Retrieve cached Personalized PageRank scores and hub ranks for symbols."""
        if force_refresh or self._pagerank_cache is None or self._hub_ranks is None:
            try:
                hubs = self.store.compute_pagerank(limit=200)
                self._pagerank_cache = {h["symbol_id"]: float(h.get("score", 0.0)) for h in hubs}
                self._hub_ranks = {h["symbol_id"]: idx for idx, h in enumerate(hubs)}
            except Exception as e:
                import structlog

                structlog.get_logger().warning("pagerank_retrieval_failed", error=str(e))
                self._pagerank_cache = {}
                self._hub_ranks = {}
        return self._pagerank_cache, self._hub_ranks

    def retrieve(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        is_dirty: bool = False,
        synthesize_answer: bool = True,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Perform deterministic 4-stage retrieval: Temporal -> Structural -> Lexical -> Semantic."""
        import time

        t_start = time.perf_counter()
        trace_id = str(uuid4())
        start_time = datetime.now(UTC)

        # Ensure documentation files are indexed into symbols_fts
        try:
            self.index_docs()
        except Exception as e:
            import structlog

            structlog.get_logger().warning("doc_indexing_failed", error=str(e))

        # 5-tier query intent routing
        intent_5tier = classify_intent_5tier(query)
        intent = _classify_intent_fast(query)

        # 2. Lexical Matches (BM25) with sub-tokenization & short identifier preservation
        query_words = _extract_query_tokens(query)
        lexical_candidates: dict[str, dict[str, Any]] = {}
        symbols = self.store.get_symbols_by_lexical_query(query_words)
        for rank, sym in enumerate(symbols):
            sid = sym["symbol_id"]
            if sid not in lexical_candidates:
                lexical_candidates[sid] = {
                    **sym,
                    "reason": "lexical_match",
                    "lexical_rank": rank,
                }

        t_lexical = time.perf_counter()

        # 3. Semantic Matches (Vector Search)
        semantic_candidates: dict[str, dict[str, Any]] = {}
        if self.embed_provider:
            try:
                query_vector = self.embed_provider.embed(query)
                if query_vector:
                    symbols = self.store.get_similar_symbols(query_vector, limit=50)
                    for rank, sym in enumerate(symbols):
                        sid = sym["symbol_id"]
                        semantic_candidates[sid] = {
                            **sym,
                            "reason": "semantic",
                            "semantic_rank": rank,
                        }
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

        # Refresh PageRank cache if dirty tree
        if is_dirty:
            self._get_pagerank_data(force_refresh=True)

        # 4. RRF Ranking with 5-tier intent weighting, Graph Centrality, and Casing Calibration
        ranked = self._rank_candidates(
            query, list(combined.values()), intent, intent_5tier=intent_5tier
        )

        t_ranking = time.perf_counter()

        # Context Packing with exact token budgeting
        reserved_buffer = min(500, int(max_tokens * 0.15))
        retrieval_budget = (
            max(100, max_tokens - reserved_buffer) if max_tokens > 100 else max_tokens
        )

        # 5. Token-Aware Context Packing with Contextual Chunk Enrichment
        packed_blocks = []
        tokens_used = 0
        repo_path = self.repo_path
        grounding_sources = []
        trace_elements = []

        # Ingestion of Past Decisions if intent matches
        if intent_5tier == QueryIntent.PAST_DECISIONS:
            decisions = self.store.get_decisions(limit=5)
            if decisions:
                dec_blocks = ["# PAST ARCHITECTURAL DECISIONS"]
                for d in decisions:
                    dec_blocks.append(
                        f"- [{d['decision_id'][:8]}] {d['content']} (Context: {d.get('context', 'none')})"
                    )
                dec_str = "\n".join(dec_blocks)
                dec_toks = len(self.tokenizer.encode(dec_str))
                if tokens_used + dec_toks <= retrieval_budget:
                    packed_blocks.append(dec_str)
                    tokens_used += dec_toks

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

            # Contextual chunk enrichment
            module = cand.get("module_key")
            if not module:
                stem = Path(path).with_suffix("")
                parts = [p for p in stem.parts if p not in ("src", "lib", "app", "packages")]
                module = ".".join(parts) if parts else stem.name

            metadata_raw = cand.get("metadata_json") or cand.get("metadata")
            scope = ""
            if isinstance(metadata_raw, str):
                try:
                    meta_dict = json.loads(metadata_raw)
                    scope = meta_dict.get("scope", "") if isinstance(meta_dict, dict) else ""
                except Exception:
                    scope = ""
            elif isinstance(metadata_raw, dict):
                scope = metadata_raw.get("scope", "")

            symbol_repr = f"{scope}.{name}" if scope else name
            enrichment_header = (
                f"# File: {path} | Module: {module} | Symbol: {symbol_repr} ({kind})"
            )

            snippet = _get_snippet(repo_path, path, start, end)
            if not snippet:
                continue

            numbered_lines = [
                f"{start + i:4d} | {line}" for i, line in enumerate(snippet.splitlines())
            ]
            numbered_snippet = "\n".join(numbered_lines) if numbered_lines else snippet
            block = (
                f"{enrichment_header}\n"
                f"### File: {path}\n"
                f"Symbol: {name} ({kind})\n"
                f"Lines: {start}-{end}\n"
                f"Reason: {reason}\n"
                f"```\n{numbered_snippet}\n```\n"
            )
            block_tokens = len(self.tokenizer.encode(block))

            if tokens_used + block_tokens > retrieval_budget:
                # Graceful folding: fall back to its AST skeleton rather than dropping it entirely
                try:
                    from synap_git.parser.registry import CodeParserRegistry

                    skel_snippet = CodeParserRegistry().skeletonize(repo_path / path, text=snippet)
                except Exception:
                    skel_snippet = None

                if (not skel_snippet or skel_snippet == snippet) and len(snippet.splitlines()) > 3:
                    lines = snippet.splitlines()
                    skel_snippet = lines[0] + "\n    ..."

                if skel_snippet:
                    numbered_skel_lines = [
                        f"{start + i:4d} | {line}"
                        for i, line in enumerate(skel_snippet.splitlines())
                    ]
                    numbered_skel = (
                        "\n".join(numbered_skel_lines) if numbered_skel_lines else skel_snippet
                    )
                    folded_block = (
                        f"{enrichment_header}\n"
                        f"### File: {path}\n"
                        f"Symbol: {name} ({kind}) [AST Skeleton]\n"
                        f"Lines: {start}-{end}\n"
                        f"Reason: {reason}+folded_skeleton\n"
                        f"```\n{numbered_skel}\n```\n"
                    )
                    skel_tokens = len(self.tokenizer.encode(folded_block))
                    if tokens_used + skel_tokens <= retrieval_budget:
                        packed_blocks.append(folded_block)
                        grounding_sources.append(cand)
                        tokens_used += skel_tokens
                        included_files.add(path)
                        trace_elements.append(
                            TraceElement(
                                stable_id=cand["symbol_id"],
                                name=name,
                                path=path,
                                score=score,
                                reason=f"{reason}+folded_skeleton",
                                tokens=skel_tokens,
                            )
                        )
                    else:
                        # Truncate skeleton to fit remaining budget if possible; NEVER append uncompressed code!
                        remaining = retrieval_budget - tokens_used
                        if remaining >= 30:
                            skel_lines = numbered_skel.splitlines()
                            trunc_lines: list[str] = []
                            for sline in skel_lines:
                                cand_folded = (
                                    f"{enrichment_header}\n"
                                    f"### File: {path}\n"
                                    f"Symbol: {name} ({kind}) [AST Skeleton]\n"
                                    f"Lines: {start}-{end}\n"
                                    f"Reason: {reason}+folded_skeleton\n"
                                    f"```\n"
                                    + "\n".join(trunc_lines + [sline, "    ..."])
                                    + "\n```\n"
                                )
                                if len(self.tokenizer.encode(cand_folded)) > remaining:
                                    break
                                trunc_lines.append(sline)
                            if trunc_lines:
                                trunc_block = (
                                    f"{enrichment_header}\n"
                                    f"### File: {path}\n"
                                    f"Symbol: {name} ({kind}) [AST Skeleton]\n"
                                    f"Lines: {start}-{end}\n"
                                    f"Reason: {reason}+folded_skeleton\n"
                                    f"```\n" + "\n".join(trunc_lines + ["    ..."]) + "\n```\n"
                                )
                                t_toks = len(self.tokenizer.encode(trunc_block))
                                packed_blocks.append(trunc_block)
                                grounding_sources.append(cand)
                                tokens_used += t_toks
                                included_files.add(path)
                                trace_elements.append(
                                    TraceElement(
                                        stable_id=cand["symbol_id"],
                                        name=name,
                                        path=path,
                                        score=score,
                                        reason=f"{reason}+folded_skeleton",
                                        tokens=t_toks,
                                    )
                                )
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

        # Expand to structural file skeleton context if budget allows (2-tier token packing)
        for path in list(included_files):
            if tokens_used >= retrieval_budget:
                break
            try:
                from synap_git.parser.registry import CodeParserRegistry

                skel = CodeParserRegistry().skeletonize(repo_path / path)
            except Exception:
                # CRITICAL BUG FIX: Do NOT load full uncompressed file when skeletonize fails!
                skel = None
            if not skel:
                continue

            block = f"### File Structural Skeleton: {path}\n```\n{skel}\n```\n"
            block_tokens = len(self.tokenizer.encode(block))
            if tokens_used + block_tokens <= retrieval_budget:
                packed_blocks.append(block)
                tokens_used += block_tokens
            else:
                remaining = retrieval_budget - tokens_used
                if remaining > 50:
                    skel_lines = skel.splitlines()
                    skel_trunc_lines: list[str] = []
                    for line in skel_lines:
                        cand_b = (
                            f"### File Structural Skeleton: {path}\n```\n"
                            + "\n".join(skel_trunc_lines + [line, "    ..."])
                            + "\n```\n"
                        )
                        if len(self.tokenizer.encode(cand_b)) > remaining:
                            break
                        skel_trunc_lines.append(line)
                    if skel_trunc_lines:
                        final_trunc = (
                            f"### File Structural Skeleton: {path}\n```\n"
                            + "\n".join(skel_trunc_lines + ["    ..."])
                            + "\n```\n"
                        )
                        f_toks = len(self.tokenizer.encode(final_trunc))
                        packed_blocks.append(final_trunc)
                        tokens_used += f_toks

        context_str = "\n".join(packed_blocks)

        # Gating: Only approved lessons affect retrieval
        approved_lessons = self.store.get_lessons("approved")
        if approved_lessons:
            lesson_blocks = ["# APPROVED SYSTEM MEMORY (CRITICAL: MUST ADHERE)"]
            for i, lesson in enumerate(approved_lessons, 1):
                lesson_blocks.append(
                    f"[{i}] DO NOT DO THIS: {lesson['what_failed']} - BECAUSE: {lesson['why_failed']}"
                )
            lesson_str = "\n".join(lesson_blocks)
            tokens_used += len(self.tokenizer.encode(lesson_str))
            context_str = lesson_str + "\n\n" + context_str

        system_prompt = (
            "You are an AI coding assistant with deep structural repository understanding.\n"
            "Answer the user query based ONLY on the provided grounded structural context.\n"
            "Cite source files and symbol names in your explanation.\n"
        )
        user_prompt = f"Repository Context:\n{context_str}\n\nUser Question: {query}\n"

        t_packing = time.perf_counter()

        if self.llm_provider and synthesize_answer:
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
                        try:
                            import anyio

                            anyio.from_thread.run(anyio.sleep, backoff_sec)
                        except Exception:
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

                    structlog.get_logger().error("suppressed_error_caught", error=str(e))
            else:
                err_msg = str(last_err)
                answer_content = (
                    f"Degraded Mode (LLM connection failed): {err_msg}\n\n"
                    "Mode A (Structural Only): Context retrieved, but LLM generation is disabled.\n\n"
                    f"Repository Context:\n{context_str}"
                )
        else:
            # Mode A (Structural Only) / Direct Context: Return the packed code blocks directly!
            answer_content = context_str

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
        self,
        query: str,
        candidates: list[dict[str, Any]],
        intent: str = "logic",
        intent_5tier: QueryIntent | str | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Rank candidates using Reciprocal Rank Fusion (RRF k=60), Graph Centrality, and casing-invariant signals."""
        k = 60
        ranked: list[tuple[dict[str, Any], float]] = []
        pagerank_scores, hub_ranks = self._get_pagerank_data()

        # Precompute query sub-tokens and normalized words
        query_subtokens = set(_split_into_subtokens(query))
        query_normalized = {_normalize_name(w) for w in query.split() if len(w) >= 2}
        query_asks_for_test = any(w in query.lower() for w in ("test", "fixture", "mock", "assert"))

        for cand in candidates:
            score = 0.0
            sid = cand["symbol_id"]
            cand_name = cand.get("name", "")
            cand_path = cand.get("source_path", cand.get("path", ""))

            # Intent-based weights
            lexical_w = 1.0
            semantic_w = 1.0
            structural_w = 1.0
            hub_w = 1.0

            if intent_5tier == QueryIntent.SYMBOL_LOOKUP or intent_5tier == "symbol_lookup":
                lexical_w = 3.0
                semantic_w = 0.5
                structural_w = 0.8
                hub_w = 1.0
            elif intent_5tier == QueryIntent.NAVIGATION or intent_5tier == "navigation":
                structural_w = 2.5
                lexical_w = 1.5
                semantic_w = 0.6
                hub_w = 1.2
            elif intent_5tier == QueryIntent.ARCHITECTURE or intent_5tier == "architecture":
                semantic_w = 2.5
                hub_w = 2.0
                structural_w = 1.0
                lexical_w = 0.8
            elif intent_5tier == QueryIntent.DEBUGGING or intent_5tier == "debugging":
                lexical_w = 2.2
                semantic_w = 1.5
                structural_w = 1.2
                hub_w = 1.0
            elif intent_5tier == QueryIntent.PAST_DECISIONS or intent_5tier == "past_decisions":
                lexical_w = 1.5
                semantic_w = 2.0
                hub_w = 0.8
                structural_w = 0.8
            elif intent == "structural":
                structural_w = 2.0
                semantic_w = 0.5
                hub_w = 1.2
            elif intent == "conceptual":
                semantic_w = 2.0
                lexical_w = 0.5
                hub_w = 1.5
            elif intent == "logic":
                lexical_w = 2.0
                structural_w = 0.5
                hub_w = 1.0

            if "lexical_rank" in cand:
                score += (1.0 / (k + cand["lexical_rank"])) * lexical_w
            if "semantic_rank" in cand:
                score += (1.0 / (k + cand["semantic_rank"])) * semantic_w

            # Structural scoring
            reason = cand.get("reason", "")
            if reason.startswith("structural"):
                dist = int(reason.split("=")[-1]) if "=" in reason else 1
                score += (1.0 / (k + 100 + dist)) * structural_w

            # Graph Centrality: Personalized PageRank hub status
            if sid in hub_ranks:
                hrank = hub_ranks[sid]
                score += (1.0 / (k + hrank)) * hub_w

            pr_score = pagerank_scores.get(sid, 0.0)
            if pr_score > 0.0:
                score += min(pr_score * 0.1, 0.05)

            # Name match boost: Casing-invariant and sub-token matching
            cand_norm = _normalize_name(cand_name)
            cand_subtokens = set(_split_into_subtokens(cand_name))

            if cand_norm and (
                cand_norm in query_normalized
                or any(cand_norm == _normalize_name(qw) for qw in query.split())
            ):
                score += 0.20
            elif cand_subtokens and cand_subtokens.issubset(query_subtokens):
                score += 0.15
            elif any(st in query_subtokens for st in cand_subtokens):
                score += 0.08
            elif any(w in cand_name.lower() for w in query.lower().split() if len(w) >= 2):
                score += 0.05

            # Deprioritize test fixtures so foundational interfaces rank higher
            if _is_test_candidate(cand_path, cand_name) and not query_asks_for_test:
                score *= 0.5

            ranked.append((cand, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
