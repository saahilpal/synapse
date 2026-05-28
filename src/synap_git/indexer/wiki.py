from __future__ import annotations

from synap_git.config import SynapSettings
from synap_git.diagnostics.logger import get_logger
from synap_git.provider.factory import get_llm_provider
from synap_git.storage.sqlite import SynapStore

logger = get_logger("wiki_engine")


class WikiEngine:
    """Generates L2 Markdown Documentation (Wiki) for files, modules, and the project."""

    def __init__(self, settings: SynapSettings, store: SynapStore) -> None:
        self.settings = settings
        self.store = store
        self.provider = get_llm_provider(settings)
        self.wiki_dir = self.settings.state_path / "wiki"
        self.wiki_dir.mkdir(parents=True, exist_ok=True)

    def generate_file_wiki(self, file_id: str, file_path: str, content: str) -> None:
        """Pass 2: Enqueue documentation for background worker."""
        self.store.enqueue_wiki(file_path)

    def generate_module_wiki(self, dir_path: str) -> None:
        """Pass 2.5: Enqueue module-level wiki synthesis."""
        self.store.enqueue_wiki(dir_path)

    def generate_project_wiki(self) -> None:
        """Pass 2.8: Enqueue project level wiki pages."""
        self.store.enqueue_wiki("overview.md")
        self.store.enqueue_wiki("architecture.md")
        self.store.enqueue_wiki("schema.md")

    def ensure_wiki_page(self, wiki_filepath: str) -> None:
        """Ensure the wiki page exists and is fresh. If stale or missing, generate synchronously."""
        is_project_wiki = wiki_filepath in (
            "overview",
            "overview.md",
            "architecture",
            "architecture.md",
            "schema",
            "schema.md",
        )

        if is_project_wiki:
            source_path = wiki_filepath
            if not source_path.endswith(".md"):
                source_path += ".md"
        else:
            source_path = wiki_filepath
            if source_path.endswith(".md"):
                source_path = source_path[:-3]

        disk_filename = wiki_filepath
        if not disk_filename.endswith(".md"):
            disk_filename += ".md"
        wiki_path = self.wiki_dir / disk_filename

        if not self.provider:
            # Create a simple structural placeholder if no LLM configured
            if not wiki_path.exists():
                wiki_path.parent.mkdir(parents=True, exist_ok=True)
                wiki_path.write_text(
                    f"# {wiki_filepath}\nStructural mode only. No LLM configured.", encoding="utf-8"
                )
            return

        status_entry = self.store.get_wiki_status(source_path)

        if wiki_path.exists():
            if status_entry is None or status_entry["status"] == "fresh":
                if status_entry is None:
                    self.store.set_wiki_status(source_path, None, "fresh")
                return

        # Stale or missing, generate it synchronously
        if is_project_wiki:
            self.generate_project_wiki_page_sync(source_path)
        else:
            try:
                full_path = self.settings.repository_path / source_path
                if not full_path.exists() or not full_path.is_file():
                    return
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return

            file_entry = self.store.get_file_by_path(source_path)
            git_oid = file_entry["git_oid"] if file_entry else ""
            self.generate_file_wiki_sync(source_path, content, git_oid)

    def generate_file_wiki_sync(self, file_path: str, content: str, git_oid: str) -> None:
        """Generate file wiki synchronously and write to disk, updating cache status."""
        if not self.provider:
            return

        wiki_path = self.wiki_dir / f"{file_path}.md"
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

            # Record status
            self.store.set_wiki_status(file_path, git_oid, "fresh")

            # Record LLM call usage
            try:
                provider_name = self.provider.__class__.__name__.replace("Provider", "").lower()
                model_name = getattr(self.provider, "default_model", "unknown")
                self.store.put_llm_call(
                    provider=provider_name,
                    model=model_name,
                    input_tokens=doc_response.prompt_tokens,
                    output_tokens=doc_response.completion_tokens,
                    purpose="wiki",
                    file_path=file_path,
                )
            except Exception:
                pass
        except Exception as e:
            logger.error("wiki_generation_failed", path=file_path, error=str(e))

    def generate_project_wiki_page_sync(self, page_name: str) -> None:
        """Generate project level wikis (overview, architecture, schema) synchronously."""
        if not self.provider:
            return

        clean_name = page_name
        if not clean_name.endswith(".md"):
            clean_name += ".md"

        wiki_path = self.wiki_dir / clean_name
        wiki_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with self.store.connect() as conn:
                files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                symbols_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
                rows = conn.execute("SELECT name, kind FROM symbols LIMIT 20").fetchall()
                top_symbols = ", ".join([f"{r['name']} ({r['kind']})" for r in rows])
        except Exception:
            files_count, symbols_count, top_symbols = 0, 0, ""

        prompt = (
            f"Generate a project-level {clean_name} document.\n"
            f"The codebase contains {files_count} files and {symbols_count} symbols.\n"
            f"Some top symbols include: {top_symbols}.\n"
            "Provide a high quality structural breakdown."
        )

        try:
            doc_response = self.provider.generate(
                system_prompt="You are a senior systems architect.",
                user_prompt=prompt,
                max_tokens=1500,
            )
            wiki_path.write_text(doc_response.content, encoding="utf-8")
            logger.info("wiki_generated_project_page", page=clean_name)

            self.store.set_wiki_status(clean_name, None, "fresh")

            # Record LLM call usage
            try:
                provider_name = self.provider.__class__.__name__.replace("Provider", "").lower()
                model_name = getattr(self.provider, "default_model", "unknown")
                self.store.put_llm_call(
                    provider=provider_name,
                    model=model_name,
                    input_tokens=doc_response.prompt_tokens,
                    output_tokens=doc_response.completion_tokens,
                    purpose="wiki_project",
                    file_path=clean_name,
                )
            except Exception:
                pass
        except Exception as e:
            logger.error("wiki_project_generation_failed", page=clean_name, error=str(e))
