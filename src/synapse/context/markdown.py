from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from synapse.context.objects import (
    Confidence,
    EvidenceSpan,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
)
from synapse.context.scanner import FileObservation, RepositoryScan

HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")
LINK_RE = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")
TODO_RE = re.compile(r"\b(TODO|FIXME|HACK)\b", re.IGNORECASE)

KIND_KEYWORDS: tuple[tuple[SemanticKind, tuple[str, ...]], ...] = (
    (SemanticKind.DECISION, ("decision", "adr", "chosen", "accepted")),
    (SemanticKind.CONSTRAINT, ("constraint", "must", "non-goal", "requirement")),
    (SemanticKind.ASSUMPTION, ("assumption", "assume", "temporary")),
    (SemanticKind.RISK, ("risk", "failure", "threat", "hazard")),
    (SemanticKind.ROADMAP, ("roadmap", "phase", "milestone", "timeline")),
    (SemanticKind.INTEGRATION, ("integration", "api", "mcp", "adapter")),
    (SemanticKind.ARCHITECTURE, ("architecture", "runtime", "system", "storage")),
)


@dataclass(frozen=True)
class MarkdownChunk:
    source_path: Path
    relative_path: str
    heading_path: tuple[str, ...]
    heading_level: int
    title: str
    content: str
    start_line: int
    end_line: int
    links: tuple[str, ...]


class MarkdownContextExtractor:
    """Extracts first-class context objects from Markdown heading chunks."""

    def extract_scan(self, scan: RepositoryScan) -> tuple[SemanticObject, ...]:
        objects: list[SemanticObject] = []
        for file in scan.markdown_files():
            objects.extend(self.extract_file(file))
        return tuple(objects)

    def extract_file(self, file: FileObservation) -> tuple[SemanticObject, ...]:
        chunks = self.chunk_file(file.path, file.relative_path)
        objects: list[SemanticObject] = []
        for chunk in chunks:
            kind = self.classify(chunk)
            if kind is None:
                continue
            summary = self.summarize(chunk)
            stable_id = SemanticObject.derive_id(
                kind=kind,
                source_uri=chunk.relative_path,
                source_hash=file.content_hash,
                heading_path=chunk.heading_path,
                content=chunk.content,
            )
            provenance = Provenance(
                source_uri=chunk.relative_path,
                source_type=SourceType.MARKDOWN,
                source_hash=file.content_hash,
                evidence=(
                    EvidenceSpan(
                        source_uri=chunk.relative_path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        source_hash=file.content_hash,
                    ),
                ),
            )
            confidence = Confidence(
                score=0.78 if kind is not SemanticKind.NOTE else 0.55,
                rationale=f"markdown heading/content matched {kind.value} context",
                evidence_count=1,
            )
            objects.append(
                SemanticObject(
                    stable_id=stable_id,
                    kind=kind,
                    summary=summary,
                    tags=self.tags_for(kind, chunk),
                    metadata={
                        "heading_path": chunk.heading_path,
                        "heading_level": chunk.heading_level,
                        "title": chunk.title,
                        "links": chunk.links,
                    },
                    provenance=provenance,
                    confidence=confidence,
                )
            )
        return tuple(objects)

    def chunk_file(self, path: Path, relative_path: str) -> tuple[MarkdownChunk, ...]:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        chunks: list[MarkdownChunk] = []
        current_title = path.stem
        current_level = 1
        heading_stack: list[tuple[int, str]] = [(1, current_title)]
        start_line = 1
        body: list[str] = []

        def flush(end_line: int) -> None:
            content = "\n".join(body).strip()
            if not content:
                return
            heading_path = tuple(title for _, title in heading_stack)
            chunks.append(
                MarkdownChunk(
                    source_path=path,
                    relative_path=relative_path,
                    heading_path=heading_path,
                    heading_level=current_level,
                    title=current_title,
                    content=content,
                    start_line=start_line,
                    end_line=end_line,
                    links=tuple(match.group("target") for match in LINK_RE.finditer(content)),
                )
            )

        for line_number, line in enumerate(lines, start=1):
            match = HEADING_RE.match(line)
            if match:
                flush(line_number - 1)
                level = len(match.group(1))
                title = match.group("title").strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                current_title = title
                current_level = level
                start_line = line_number
                body = []
            else:
                body.append(line)
        flush(len(lines))
        return tuple(chunks)

    def classify(self, chunk: MarkdownChunk) -> SemanticKind | None:
        title_haystack = " ".join(chunk.heading_path).lower()
        for kind, keywords in KIND_KEYWORDS:
            if any(keyword in title_haystack for keyword in keywords):
                return kind
        haystack = f"{chunk.title}\n{chunk.content[:1000]}".lower()
        if TODO_RE.search(haystack):
            return SemanticKind.TODO
        for kind, keywords in KIND_KEYWORDS:
            if any(keyword in haystack for keyword in keywords):
                return kind
        if chunk.heading_level <= 2 and len(chunk.content.strip()) >= 80:
            return SemanticKind.NOTE
        return None

    def summarize(self, chunk: MarkdownChunk) -> str:
        clean = re.sub(r"\s+", " ", chunk.content).strip()
        prefix = " > ".join(chunk.heading_path)
        if len(clean) > 360:
            clean = f"{clean[:357].rstrip()}..."
        return f"{prefix}: {clean}" if prefix else clean

    def tags_for(self, kind: SemanticKind, chunk: MarkdownChunk) -> tuple[str, ...]:
        tags = {kind.value, "markdown"}
        if chunk.links:
            tags.add("linked")
        return tuple(sorted(tags))
