#!/usr/bin/env python3
"""Benchmark suite for Synapse performance validation.

Measures:
- Replay Engine reconstruction speed.
- Graph projection generation and clustering throughput.
- Temporal query flexible parsing and search latency.
"""

from __future__ import annotations

import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from synapse.cognition.objects import (
    Confidence,
    EventType,
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelation,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
)
from synapse.compact import CognitionCompactor
from synapse.config import RuntimeProfile, SynapseSettings
from synapse.projections.models import ProjectionKind
from synapse.runtime.service import SynapseRuntime


def main() -> None:
    print("=" * 60)
    print("SYNAPSE PERFORMANCE BENCHMARK SUITE")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        settings = SynapseSettings(
            repository_path=path,
            state_path=path / ".synapse",
            profile=RuntimeProfile.DEV,
        )
        runtime = SynapseRuntime(settings)
        runtime.initialize_storage()

        store = runtime.event_store
        objects = runtime.object_store
        dag = runtime.dag

        # Setup standard mock objects
        prov = Provenance(source_uri="repo/root", source_type=SourceType.SYSTEM)
        conf = Confidence(score=0.9, rationale="bench", evidence_count=1)

        print("\n--- Phase 1: Ingestion / Commit Scaling ---")
        commit_times = []
        num_contexts = 50

        start_total = time.perf_counter()
        for i in range(num_contexts):
            sem = SemanticObject(
                stable_id=f"fact_{i}",
                kind=SemanticKind.MODULE,
                summary=f"Subsystem module {i} validation check",
                provenance=prov,
                confidence=conf,
                created_at=datetime.now(UTC),
            )
            node = GraphNode(
                stable_id=f"node_{i}",
                node_type=GraphNodeType.MODULE,
                labels=(f"node_{i}", f"src/sub_{i}.py"),
                confidence=conf,
                provenance=prov,
            )
            edge = None
            if i > 0:
                edge = GraphEdge(
                    stable_id=f"edge_{i}",
                    from_id=f"node_{i}",
                    to_id=f"node_{i - 1}",
                    relation=GraphRelation.DEPENDS_ON,
                    confidence=conf,
                    provenance=prov,
                )

            # Build context commit
            c_start = time.perf_counter()
            from synapse.transactions.models import CognitionCommitRequest

            commit_res = runtime.transaction_engine.commit_context_update(
                CognitionCommitRequest(
                    operation=f"bench_op_{i}",
                    event_type=EventType.REPOSITORY_SCANNED,
                    source=f"bench://op_{i}",
                    payload={"step": i},
                    actor="benchmarker",
                    git_commit_hash=f"git_hash_{i}",
                    branch="main",
                    parent_hashes=(runtime.event_store.get_active_head("main"),) if i > 0 else (),
                    semantic_delta=(sem,),
                    summary=f"bench step {i}",
                    provenance=prov,
                    confidence=conf,
                    graph_nodes=(node,),
                    graph_edges=(edge,) if edge else (),
                )
            )
            c_end = time.perf_counter()
            commit_times.append(c_end - c_start)

        total_ingestion_time = time.perf_counter() - start_total
        avg_commit_time = sum(commit_times) / len(commit_times)
        throughput = num_contexts / total_ingestion_time

        print(f"Committed Contexts : {num_contexts}")
        print(f"Total Ingestion Time: {total_ingestion_time:.4f} s")
        print(f"Avg Time Per Commit : {avg_commit_time * 1000:.2f} ms")
        print(f"Commit Throughput   : {throughput:.2f} commits/sec")

        active_hash = store.get_active_head("main")
        assert active_hash is not None

        print("\n--- Phase 2: Replay Engine Reconstruction ---")
        r_start = time.perf_counter()
        replay_result = runtime.replay_engine.replay()
        replay_time = time.perf_counter() - r_start
        print(f"Replay Completion Time: {replay_time:.4f} s")
        print(f"Replay State Hash     : {replay_result.state_hash}")

        print("\n--- Phase 3: Graph Projection Generation ---")
        # Overview projection
        op_start = time.perf_counter()
        proj_overview = runtime.projection_engine.get_projection(
            active_hash, ProjectionKind.OVERVIEW, bypass_cache=True
        )
        op_time = time.perf_counter() - op_start

        # Subsystem projection (triggers clustering when nodes exceed limit)
        sub_start = time.perf_counter()
        proj_sub = runtime.projection_engine.get_projection(
            active_hash, ProjectionKind.SUBSYSTEM, bypass_cache=True
        )
        sub_time = time.perf_counter() - sub_start

        print(
            f"Overview Projection Time  : {op_time * 1000:.2f} ms (Nodes: {len(proj_overview.nodes)})"
        )
        print(
            f"Subsystem Projection Time : {sub_time * 1000:.2f} ms (Nodes: {len(proj_sub.nodes)})"
        )

        print("\n--- Phase 4: Temporal Querying ---")
        q_start = time.perf_counter()
        res_date = runtime.query_engine.query_flexible("after 2000-01-01")
        res_low = runtime.query_engine.query_flexible("low confidence")
        query_time = time.perf_counter() - q_start

        print(f"Date Query Time (2 searches) : {query_time * 1000:.2f} ms")
        print(f"Date Results Matches         : {len(res_date.rows)}")

        print("\n--- Phase 5: Compaction & Cold Migration ---")
        compactor = CognitionCompactor(event_store=store)
        c_start = time.perf_counter()
        compaction_res = compactor.compact()
        compaction_time = time.perf_counter() - c_start

        print(f"Compaction Time           : {compaction_time * 1000:.2f} ms")
        print(f"Deduplicated Fact Records : {compaction_res['deduplicated_records']}")
        print(f"Migrated Cold Contexts     : {compaction_res['migrated_contexts']}")
        print(f"Replay Checkpoint Hash    : {compaction_res['checkpoint_hash']}")

    print("\n" + "=" * 60)
    print("PERFORMANCE VERIFICATION COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
