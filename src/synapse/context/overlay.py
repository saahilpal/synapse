from __future__ import annotations

import hashlib
from typing import Any

from synapse.context.objects import (
    Confidence,
    EventType,
    Provenance,
    SemanticKind,
    SemanticObject,
    SourceType,
    Validity,
)
from synapse.provider.base import LLMProvider
from synapse.transactions.models import ContextCommitRequest


class SemanticOverlaySystem:
    """Manages AI semantic overlays over structural code nodes."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    def generate_and_persist_overlay(
        self,
        runtime: Any,  # SynapseRuntime, typed as Any to avoid circular imports
        target_stable_id: str,
        prompt_instruction: str,
        *,
        actor: str = "agent",
    ) -> str:
        """Generate an AI overlay annotation and append it as a context commit."""
        runtime.initialize_storage()
        git_state = runtime.git.state()
        parent = runtime.event_store.get_active_head(git_state.effective_branch)
        if not parent:
            raise ValueError("No active context exists to attach an overlay.")

        # Resolve the target node/semantic object
        active_nodes, active_semantics, _ = runtime.retrieval_engine.active_context_state(parent)

        target_summary = ""
        target_uri = "unknown"
        if target_stable_id in active_nodes:
            node = active_nodes[target_stable_id]
            target_summary = f"Node type: {node.get('node_type')}, Labels: {node.get('labels')}"
            target_uri = node.get("source_uri", "unknown")
        elif target_stable_id in active_semantics:
            sem = active_semantics[target_stable_id]
            target_summary = f"Semantic kind: {sem.get('kind')}, Summary: {sem.get('summary')}"
            target_uri = sem.get("source_uri", "unknown")
        else:
            raise ValueError(
                f"Target node/semantic object '{target_stable_id}' is not active in context."
            )

        # Formulate prompt and generate hash
        system_prompt = (
            "You are an AI software architect generating a context overlay.\n"
            "Produce a clear, concise technical annotation for the following codebase element.\n"
        )
        user_prompt = f"Element Summary:\n{target_summary}\n\nInstruction: {prompt_instruction}\n"
        prompt_hash = hashlib.sha256(f"{system_prompt}\n{user_prompt}".encode()).hexdigest()

        # Query LLM
        response = self.llm_provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.2,
        )

        model_info = {
            "provider": self.llm_provider.__class__.__name__,
            "prompt_hash": prompt_hash,
            "instruction": prompt_instruction,
        }

        # Create overlay SemanticObject
        provenance = Provenance(
            source_uri=target_uri,
            source_type=SourceType.AGENT,
            git_commit=git_state.head_commit,
            branch=git_state.effective_branch,
            actor=actor,
        )

        overlay_id = SemanticObject.derive_id(
            kind=SemanticKind.NOTE,
            source_uri=target_uri,
            source_hash=None,
            content=f"overlay:{target_stable_id}:{prompt_hash}",
        )

        overlay_object = SemanticObject(
            stable_id=overlay_id,
            kind=SemanticKind.NOTE,
            summary=response.content,
            tags=("overlay", "ai"),
            metadata={
                "target_stable_id": target_stable_id,
                "model_metadata": model_info,
            },
            provenance=provenance,
            confidence=Confidence(
                score=0.80,
                rationale="AI-generated context overlay",
                evidence_count=1,
            ),
            validity=Validity(
                valid_from_context="__CURRENT_CONTEXT__",
            ),
        )

        result = runtime.transaction_engine.commit_context_update(
            ContextCommitRequest(
                operation="add_overlay",
                event_type=EventType.MANUAL_NOTE_ADDED,
                source="agent://overlay",
                payload={
                    "target_stable_id": target_stable_id,
                    "prompt_instruction": prompt_instruction,
                },
                actor=actor,
                git_commit_hash=git_state.head_commit,
                branch=git_state.effective_branch,
                parent_hashes=(parent,),
                semantic_delta=(overlay_object,),
                summary=f"ai overlay: {response.content[:100]}",
                provenance=provenance,
                confidence=overlay_object.confidence,
            )
        )

        return str(result.context.object_hash)
