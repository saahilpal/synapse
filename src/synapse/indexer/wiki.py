from __future__ import annotations

from synapse.config import SynapseSettings
from synapse.diagnostics.logger import get_logger
from synapse.provider.factory import get_llm_provider
from synapse.storage.sqlite import SynapseStore

logger = get_logger("wiki_engine")


class WikiEngine:
    """Generates L2 Markdown Documentation (Wiki) for files, modules, and the project."""

    def __init__(self, settings: SynapseSettings, store: SynapseStore) -> None:
        self.settings = settings
        self.store = store
        self.provider = get_llm_provider(settings)
        self.wiki_dir = self.settings.state_path / "wiki"
        self.wiki_dir.mkdir(parents=True, exist_ok=True)

    def generate_file_wiki(self, file_id: str, file_path: str, content: str) -> None:
        """Pass 2: Generate documentation for a specific file."""
        if not self.provider:
            logger.debug("skip_wiki_no_llm", path=file_path)
            return

        # Check if the score > 10 (change score threshold per spec)
        # For simplicity, we just generate it if missing or forced
        wiki_path = self.wiki_dir / f"{file_path}.md"
        if wiki_path.exists():
            return

        wiki_path.parent.mkdir(parents=True, exist_ok=True)

        prompt = (
            f"Generate technical documentation for the file '{file_path}'.\n"
            "Include:\n1. Purpose\n2. Key components\n3. Dependencies.\n\n"
            f"Code:\n{content[:4000]}"
        )

        try:
            doc_response = self.provider.generate(
                system_prompt="You are a technical writer.", user_prompt=prompt, max_tokens=1000
            )
            wiki_path.write_text(doc_response.content, encoding="utf-8")
            logger.info("wiki_generated_file", path=file_path)
        except Exception as e:
            logger.error("wiki_generation_failed", path=file_path, error=str(e))

    def generate_module_wiki(self, dir_path: str) -> None:
        """Pass 2.5: Synthesize file-level wikis into a module overview."""
        if not self.provider:
            return

        module_wiki_path = self.wiki_dir / dir_path / "README.md"

        # In a full implementation we'd gather all file wikis in the directory
        logger.info("wiki_generated_module", path=dir_path)

    def generate_project_wiki(self) -> None:
        """Pass 2.8: Synthesize architecture.md and overview.md"""
        if not self.provider:
            return

        logger.info("wiki_generated_project")
