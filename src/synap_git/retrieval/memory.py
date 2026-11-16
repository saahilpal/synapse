from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import structlog

from synap_git.storage.sqlite import SynapStore

logger = structlog.get_logger()


class DeduplicationStatus(str, Enum):
    DUPLICATE = "duplicate"
    CONSOLIDATE = "consolidate"
    NOVEL = "novel"


@dataclass(frozen=True)
class DeduplicationEvaluation:
    status: DeduplicationStatus
    matched_memory_id: str | None
    similarity_score: float
    stage: str
    reason: str


def normalize_tokens(text: str) -> list[str]:
    """Normalize text into lowercase alphanumeric tokens."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text).lower()
    return [t for t in cleaned.split() if len(t) >= 2]


def compute_simhash(text: str) -> int:
    """
    Compute 64-bit lexical SimHash for token-normalized text.
    Deterministic, robust against word reordering and minor phrasing changes.
    """
    tokens = normalize_tokens(text)
    if not tokens:
        return 0

    v = [0] * 64
    for token in tokens:
        token_hash = int.from_bytes(
            hashlib.sha256(token.encode("utf-8")).digest()[:8],
            byteorder="big",
        )
        for i in range(64):
            bit = (token_hash >> i) & 1
            if bit == 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def simhash_hamming_distance(h1: int, h2: int) -> int:
    """Calculate the Hamming distance (number of bit differences) between two 64-bit hashes."""
    return bin(h1 ^ h2).count("1")


def simhash_similarity(h1: int, h2: int) -> float:
    """Calculate the normalized similarity [0.0, 1.0] from SimHash Hamming distance."""
    if h1 == 0 and h2 == 0:
        return 1.0
    dist = simhash_hamming_distance(h1, h2)
    return max(0.0, 1.0 - (dist / 64.0))


def compute_utility_score(
    base_score: float = 1.0,
    citation_count: int = 0,
    positive_feedback: int = 0,
    negative_feedback: int = 0,
    days_since_last_referenced: float = 0.0,
    commit_distance: int = 0,
    half_life_days: float = 30.0,
) -> float:
    """
    Multi-Factor Utility Scoring (U) combining:
    1. Base score (U0)
    2. Citation count log-scaling
    3. Thumbs up/down feedback weighting
    4. Half-life exponential time decay
    5. Git commit distance hyperbolic decay
    """
    citation_factor = 1.0 + 0.25 * math.log1p(max(0, citation_count))
    feedback_factor = max(
        0.1,
        1.0 + 0.20 * max(0, positive_feedback) - 0.40 * max(0, negative_feedback),
    )
    time_decay = math.exp(-math.log(2) * (max(0.0, days_since_last_referenced) / half_life_days))
    commit_decay = 1.0 / (1.0 + 0.02 * max(0, commit_distance))

    utility = base_score * citation_factor * feedback_factor * time_decay * commit_decay
    return max(0.01, float(utility))


class MemoryLifecycleEngine:
    """
    Lifecycle manager for behavioral memories:
    - 2-Stage Deduplication (Stage 1 SimHash lexical + Stage 2 Dense Cosine).
    - Multi-Factor Utility Scoring.
    - Consolidation candidate resolution.
    """

    DUPLICATE_COSINE_THRESHOLD: float = 0.92
    CONSOLIDATE_COSINE_THRESHOLD: float = 0.80

    def __init__(self, store: SynapStore) -> None:
        self.store = store

    def evaluate_deduplication(
        self,
        content: str,
        existing_memories: list[dict[str, Any]],
        candidate_vector: list[float] | None = None,
    ) -> DeduplicationEvaluation:
        """
        Evaluate candidate memory against existing memories using 2-stage deduplication:
        Stage 1: Lexical SimHash / token normalization (Hamming dist <= 3 or SimHash >= 0.95).
        Stage 2: Cosine thresholding (>= 0.92 duplicate, 0.80-0.92 consolidate, < 0.80 novel).
        """
        if not existing_memories:
            return DeduplicationEvaluation(
                status=DeduplicationStatus.NOVEL,
                matched_memory_id=None,
                similarity_score=0.0,
                stage="none",
                reason="No existing memories",
            )

        cand_simhash = compute_simhash(content)

        # Stage 1: Lexical SimHash
        for mem in existing_memories:
            mem_id = (
                mem.get("decision_id")
                or mem.get("lesson_id")
                or mem.get("id")
                or mem.get("global_id")
            )
            mem_hash_raw = mem.get("fingerprint_hash")
            if mem_hash_raw is not None:
                try:
                    mem_simhash = (
                        int(mem_hash_raw, 16)
                        if isinstance(mem_hash_raw, str)
                        else int(mem_hash_raw)
                    )
                except ValueError:
                    mem_simhash = compute_simhash(mem.get("content", ""))
            else:
                mem_simhash = compute_simhash(mem.get("content", ""))

            sim = simhash_similarity(cand_simhash, mem_simhash)
            dist = simhash_hamming_distance(cand_simhash, mem_simhash)
            if dist <= 3 or sim >= 0.95:
                return DeduplicationEvaluation(
                    status=DeduplicationStatus.DUPLICATE,
                    matched_memory_id=mem_id,
                    similarity_score=sim,
                    stage="simhash",
                    reason=f"Lexical SimHash Hamming distance {dist} <= 3 (similarity {sim:.3f})",
                )

        # Stage 2: Cosine thresholding
        if candidate_vector is not None and len(candidate_vector) > 0:
            q_vec = np.asarray(candidate_vector, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            if q_norm > 0:
                q_vec = q_vec / q_norm

            best_sim = -1.0
            best_id = None
            for mem in existing_memories:
                mem_id = (
                    mem.get("decision_id")
                    or mem.get("lesson_id")
                    or mem.get("id")
                    or mem.get("global_id")
                )
                mem_vec_raw = mem.get("vector")
                if mem_vec_raw is None:
                    continue
                if isinstance(mem_vec_raw, bytes):
                    m_vec = np.frombuffer(mem_vec_raw, dtype=np.float32)
                elif isinstance(mem_vec_raw, list | tuple):
                    m_vec = np.asarray(mem_vec_raw, dtype=np.float32)
                else:
                    continue

                m_norm = np.linalg.norm(m_vec)
                if m_norm > 0:
                    m_vec = m_vec / m_norm

                cos_sim = float(np.dot(q_vec, m_vec))
                if cos_sim > best_sim:
                    best_sim = cos_sim
                    best_id = mem_id

            if best_sim >= self.DUPLICATE_COSINE_THRESHOLD:
                return DeduplicationEvaluation(
                    status=DeduplicationStatus.DUPLICATE,
                    matched_memory_id=best_id,
                    similarity_score=best_sim,
                    stage="cosine",
                    reason=f"Cosine similarity {best_sim:.3f} >= {self.DUPLICATE_COSINE_THRESHOLD}",
                )
            if best_sim >= self.CONSOLIDATE_COSINE_THRESHOLD:
                return DeduplicationEvaluation(
                    status=DeduplicationStatus.CONSOLIDATE,
                    matched_memory_id=best_id,
                    similarity_score=best_sim,
                    stage="cosine",
                    reason=f"Cosine similarity {best_sim:.3f} in [{self.CONSOLIDATE_COSINE_THRESHOLD}, {self.DUPLICATE_COSINE_THRESHOLD})",
                )
            return DeduplicationEvaluation(
                status=DeduplicationStatus.NOVEL,
                matched_memory_id=best_id,
                similarity_score=max(0.0, best_sim),
                stage="cosine",
                reason=f"Novel memory: cosine similarity {best_sim:.3f} < {self.CONSOLIDATE_COSINE_THRESHOLD}",
            )

        return DeduplicationEvaluation(
            status=DeduplicationStatus.NOVEL,
            matched_memory_id=None,
            similarity_score=0.0,
            stage="simhash_passed",
            reason="SimHash passed and no dense vector provided",
        )

    def calculate_utility(
        self,
        memory: dict[str, Any],
        current_commit_count: int = 0,
        now_ts: int | None = None,
    ) -> float:
        """Calculate the current multi-factor utility score for a memory record."""
        now = now_ts or int(datetime.now(UTC).timestamp())
        created_at = memory.get("created_at") or now
        last_ref = memory.get("last_referenced_at") or created_at
        days_since_ref = max(0.0, (now - last_ref) / 86400.0)

        citation_count = int(memory.get("citation_count") or 0)
        base_score = float(memory.get("utility_score") or 1.0)

        # Check citations table for feedback counts if memory_id exists
        mem_id = memory.get("decision_id") or memory.get("lesson_id") or memory.get("id") or ""
        citations = self.store.get_citations(mem_id) if mem_id else []
        positive = sum(1 for c in citations if int(c.get("feedback", 0)) > 0)
        negative = sum(1 for c in citations if int(c.get("feedback", 0)) < 0)

        return compute_utility_score(
            base_score=base_score,
            citation_count=citation_count,
            positive_feedback=positive,
            negative_feedback=negative,
            days_since_last_referenced=days_since_ref,
            commit_distance=current_commit_count,
        )


class MemoryRetriever:
    """
    Retriever with strict scope isolation:
    - Repo-Local Scope (<repo>/.synap/synap.db)
    - Cross-Project Global Scope (~/.synap/global_memory.db)
    """

    def __init__(
        self,
        local_store: SynapStore,
        global_db_path: Path | None = None,
    ) -> None:
        self.local_store = local_store
        self.global_db_path = global_db_path or (Path.home() / ".synap" / "global_memory.db")
        self._init_global_db()

    def _init_global_db(self) -> None:
        """Ensure global memory SQLite database and schema exist."""
        self.global_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.global_db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS global_memories (
                    global_id TEXT PRIMARY KEY,
                    context_key TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT,
                    tags TEXT,
                    fingerprint_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_global_category ON global_memories(category);
                CREATE INDEX IF NOT EXISTS idx_global_fingerprint ON global_memories(fingerprint_hash);
            """)

    def list_global_memories(
        self, query: str = "", tag: str = "", limit: int = 10
    ) -> list[dict[str, Any]]:
        """List cross-project global developer habits/tooling with optional query and tag filters."""
        with sqlite3.connect(self.global_db_path) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM global_memories WHERE 1=1"
            params: list[Any] = []
            if query:
                sql += " AND (content LIKE ? OR summary LIKE ? OR context_key LIKE ?)"
                like_q = f"%{query}%"
                params.extend([like_q, like_q, like_q])
            if tag:
                sql += " AND tags LIKE ?"
                params.append(f"%{tag}%")
            sql += " ORDER BY usage_count DESC, updated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def save_global_memory(
        self,
        category: str,
        content: str,
        context_key: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Persist a habit, rule, or architectural pattern to the global cross-project store."""
        global_id = str(uuid4())
        key = context_key or f"{category}:{global_id[:8]}"
        fingerprint = hex(compute_simhash(content))[2:]
        now = int(datetime.now(UTC).timestamp())
        tags_json = json.dumps(tags or [])

        with sqlite3.connect(self.global_db_path) as conn:
            conn.execute(
                """
                INSERT INTO global_memories (
                    global_id, context_key, category, content, summary, tags,
                    fingerprint_hash, created_at, updated_at, usage_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(context_key) DO UPDATE SET
                    content = excluded.content,
                    summary = excluded.summary,
                    tags = excluded.tags,
                    fingerprint_hash = excluded.fingerprint_hash,
                    updated_at = excluded.updated_at
                """,
                (global_id, key, category, content, summary, tags_json, fingerprint, now, now),
            )
        return global_id

    def ingest_global_memory(self, global_id: str, as_category: str = "note") -> str:
        """
        Ingest a global habit into the local repository with source_scope='global'.
        Increments usage_count in global store.
        """
        with sqlite3.connect(self.global_db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM global_memories WHERE global_id = ?",
                (global_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Global memory '{global_id}' not found.")
            conn.execute(
                "UPDATE global_memories SET usage_count = usage_count + 1 WHERE global_id = ?",
                (global_id,),
            )
            data = dict(row)

        local_id = str(uuid4())
        content = data["content"]
        summary = data.get("summary") or content[:120]
        fingerprint = data.get("fingerprint_hash")

        if as_category == "decision":
            self.local_store.put_decision(
                decision_id=local_id,
                branch="main",
                commit_hash="global_ingest",
                content=content,
                context_info=summary,
                fingerprint_hash=fingerprint,
                source_scope="global",
                source_global_id=global_id,
            )
        else:
            self.local_store.store_memory(
                memory_id=local_id,
                context_key=data["context_key"],
                payload=content,
                summary=summary,
            )

        logger.info("global_memory_ingested", global_id=global_id, local_id=local_id)
        return local_id

    def record_feedback(self, memory_id: str, action: str) -> None:
        """
        Record feedback or injection event into memory_citations.
        Action examples: 'injected', 'referenced', 'thumbs_up', 'thumbs_down'.
        """
        citation_id = str(uuid4())
        feedback = 0
        if action in ("thumbs_up", "verified", "positive"):
            feedback = 1
        elif action in ("thumbs_down", "rejected", "negative"):
            feedback = -1

        memory_type = "decision"
        self.local_store.record_citation(
            citation_id=citation_id,
            memory_id=memory_id,
            memory_type=memory_type,
            action=action,
            feedback=feedback,
        )
        logger.info(
            "memory_feedback_recorded", memory_id=memory_id, action=action, feedback=feedback
        )

    def retrieve_local_memories(
        self,
        query: str,
        limit: int = 10,
        min_utility: float = 0.1,
    ) -> list[dict[str, Any]]:
        """
        Strict scope isolation: Retrieve ONLY repo-local decisions and lessons.
        Global memories are never returned here unless already explicitly ingested.
        """
        decisions = self.local_store.get_decisions(limit=limit * 2)
        filtered = []
        for d in decisions:
            if d.get("source_scope", "local") != "local" and not d.get("source_global_id"):
                continue
            if float(d.get("utility_score", 1.0)) < min_utility:
                continue
            if (
                query.lower() in d.get("content", "").lower()
                or query.lower() in (d.get("context") or "").lower()
            ):
                filtered.append(d)
        return filtered[:limit]
