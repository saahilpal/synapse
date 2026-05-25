from __future__ import annotations

from pathlib import Path

from synapse.config import RuntimeProfile, SynapseSettings
from synapse.mcp.server import SynapseMCPFacade
from synapse.runtime.service import SynapseRuntime


def test_hybrid_retrieval_and_incremental_ingestion_flow(tmp_path: Path) -> None:
    # 1. Initialize settings & runtime with TEST profile (so it uses MockLLMProvider)
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Create test source files
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    auth_file = src_dir / "auth.py"
    auth_file.write_text(
        "class Authenticator:\n"
        "    def authenticate(self, username, password):\n"
        "        return True\n",
        encoding="utf-8",
    )
    payment_file = src_dir / "payment.py"
    payment_file.write_text(
        "def process_payment(amount):\n    return 'success'\n", encoding="utf-8"
    )

    settings = SynapseSettings(
        profile=RuntimeProfile.TEST,
        repository_path=repo_dir,
        state_path=tmp_path / ".synapse",
    )
    settings.ensure_directories()

    runtime = SynapseRuntime(settings)
    runtime.initialize_storage()

    # 2. Bootstrap indexing the repository for the first time
    context_hash_1 = runtime.bootstrap()
    assert context_hash_1 is not None

    # Check that initial files are indexed
    status = runtime.status()
    assert status.events >= 1

    # Verify that the active elements include both files
    mcp = SynapseMCPFacade(runtime)
    window = mcp.get_valid_context_window()
    active_nodes = {
        n["labels"][1]: n
        for n in window.content["active_nodes"]
        if "labels" in n and len(n["labels"]) > 1
    }
    assert "src/auth.py" in active_nodes
    assert "src/payment.py" in active_nodes
    assert any(
        n["node_type"] == "class" and n["labels"][0] == "Authenticator"
        for n in window.content["active_nodes"]
    )
    assert any(
        n["node_type"] == "function" and n["labels"][0] == "process_payment"
        for n in window.content["active_nodes"]
    )

    auth_node_stable_id = active_nodes["src/auth.py"]["stable_id"]
    payment_node_stable_id = active_nodes["src/payment.py"]["stable_id"]

    # 3. Create a Semantic Overlay attached to auth.py
    context_hash_overlay = runtime.add_overlay(
        target_stable_id=auth_node_stable_id,
        prompt_instruction="Explain the security assumptions of the auth module",
    )
    assert context_hash_overlay != context_hash_1

    # Verify overlay is present in the active window
    window = mcp.get_valid_context_window(context_hash=context_hash_overlay)
    overlays = [s for s in window.content["active_semantics"] if "overlay" in s.get("tags", [])]
    assert len(overlays) == 1
    assert overlays[0]["metadata_json"]["target_stable_id"] == auth_node_stable_id

    # 4. Modify auth.py and delete payment.py to trigger incremental scans and invalidations
    payment_file.unlink()  # Delete payment
    auth_file.write_text(
        "class Authenticator:\n"
        "    def authenticate_secure(self, username, password):\n"
        "        # Refactored signature\n"
        "        return True\n",
        encoding="utf-8",
    )

    # Re-index repository
    context_hash_2 = runtime.index_repository(reason="refactored auth and removed payment")

    # Check that payment.py is no longer active (its node has valid_to_context set)
    window2 = mcp.get_valid_context_window(context_hash=context_hash_2)
    active_nodes_2 = {
        n["labels"][1]: n
        for n in window2.content["active_nodes"]
        if "labels" in n and len(n["labels"]) > 1
    }
    assert "src/payment.py" not in active_nodes_2
    assert "src/auth.py" in active_nodes_2

    # Check that the overlay targeting auth.py has been automatically invalidated because auth.py was modified
    overlays_2 = [s for s in window2.content["active_semantics"] if "overlay" in s.get("tags", [])]
    assert (
        len(overlays_2) == 0
    )  # The overlay should have been invalidated and removed from active list!

    # 5. Run hybrid retrieval query
    query_str = "Explain the Authenticator class"
    response, sources = runtime.query_hybrid(query_str, context_hash=context_hash_2)
    assert "Mock Explanation" in response
    assert len(sources) > 0

    # 6. Test other MCP Facade tools
    # Task Context
    task_res = mcp.get_context_for_task(task_description="Refactor Authenticator methods")
    assert "response" in task_res.content

    # Explain Structure
    struct_res = mcp.explain_structure(module_path="src/auth.py")
    assert "explanation" in struct_res.content

    # Related Context (neighbor expansion)
    related_res = mcp.retrieve_related_context(stable_id=auth_node_stable_id)
    assert len(related_res.content["nodes"]) >= 1

    # Temporal Changes
    changes_res = mcp.get_temporal_changes(since_commit=context_hash_1[:8])
    assert "added" in changes_res.content or "error" not in changes_res.content
