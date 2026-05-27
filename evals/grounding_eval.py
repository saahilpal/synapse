import sys
from pathlib import Path

from synap_git.config import RuntimeProfile, SynapSettings
from synap_git.indexer.engine import SynapRuntime


def evaluate_structural_grounding(repo_path: str) -> None:
    path = Path(repo_path)
    print(f"Evaluating Grounding on {path.name}...")

    settings = SynapSettings(repository_path=path, profile=RuntimeProfile.TEST)
    runtime = SynapRuntime(settings)
    runtime.bootstrap(force=True)

    # 1. Measure Precision/Recall for a known symbol
    # Find a symbol that has known dependencies
    with runtime.store.connect() as conn:
        edge = conn.execute("SELECT source_symbol, target_symbol FROM edges LIMIT 1").fetchone()
        if not edge:
            print("No edges found to evaluate.")
            return

        source_id = edge["source_symbol"]
        target_id = edge["target_symbol"]

        source = conn.execute(
            "SELECT name FROM symbols WHERE symbol_id = ?", (source_id,)
        ).fetchone()
        target = conn.execute(
            "SELECT name FROM symbols WHERE symbol_id = ?", (target_id,)
        ).fetchone()

        print(f"Evaluating hop from '{source['name']}' to '{target['name']}'")

        _, sources, _ = runtime.query_hybrid(f"Explain {source['name']}")

        retrieved_names = {s["name"] for s in sources}
        if target["name"] in retrieved_names:
            print("✓ Structural hop successful.")
        else:
            print("✗ Structural hop failed.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evals/grounding_eval.py <repo_path>")
    else:
        evaluate_structural_grounding(sys.argv[1])
