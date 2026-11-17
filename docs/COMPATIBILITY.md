# Synapse AI Agent Compatibility Matrix

Synapse provides native, non-destructive integration across the modern AI coding agent ecosystem. This document defines the supported configuration paths, integration formats, verification statuses, and sentinel injection rules.

---

## 1. Master Compatibility Matrix

| AI Agent / Platform | Primary Configuration Path | Secondary / Directives Path | Format | Status | Detection Mechanism |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Claude Code** | `.claude/skills/synap/SKILL.md` | `CLAUDE.md` | Skill + Markdown | **tested end-to-end** | `.claude/`, `CLAUDE.md`, or `claude` binary |
| **Cursor** | `.cursor/rules/synap.mdc` | `.cursorrules` (legacy) | MDC Rule | **tested end-to-end** | `.cursor/`, `.cursorrules`, or `cursor` binary |
| **Codex CLI** | `AGENTS.md` | — | Markdown | **tested end-to-end** | `AGENTS.md`, `.codex/`, or `codex` binary |
| **Gemini CLI** | `AGENTS.md` | `.gemini/config/skills/synap/SKILL.md` | Markdown + Skill | **tested end-to-end** | `.gemini/`, `AGENTS.md`, or `gemini` binary |
| **GitHub Copilot** | `.github/copilot-instructions.md` | — | Markdown | **tested end-to-end** | `.github/` or `copilot-instructions.md` |
| **Windsurf** | `.windsurfrules` | — | Markdown | **tested end-to-end** | `.windsurfrules`, `.codeium/`, or `windsurf` binary |
| **Cline / Roo Code** | `.clinerules` | — | Markdown | **tested end-to-end** | `.clinerules`, `.roomodes`, or `.roo/` |
| **Aider** | `.aider.conf.yml` | — | YAML | **generated, untested** | `.aider.conf.yml` or `aider` binary |
| **Continue** | `.continue/config.json` | — | JSON | **generated, untested** | `.continue/` folder |
| **Zed** | `.zed/settings.json` | — | JSON | **generated, untested** | `.zed/` folder or `zed` binary |

---

## 2. Idempotent Sentinel Injection (`v3.0`)

Synapse guarantees **100% non-destructive updates**. Human instructions, custom rules, prompt headers, and team conventions outside the sentinel block are strictly preserved.

### The Sentinel Block
All managed directives are delimited by versioned sentinel comments:

```markdown
<!-- SYNAP_MANAGED_START: v3.0 -->
# Synapse AI Agent Directives

This project uses Synapse for persistent structural context, graph navigation, and memory.
Follow this 3-step operational loop:

## 1. When to Fetch Context (Before Work)
- Call `get_session_preamble()` at the start of every session or task to load active branch state, latest checkpoint, and approved negative constraints (revert lessons).
- Use `synap context` (or `get_session_preamble()`) to establish repo orientation within a bounded < 750 token budget.
- Never start modifying code before inspecting blast radius and active negative constraints.

## 2. Search Before Grepping
- Query symbols with `search(query="...", summary_only=True)` before performing raw greps across large files.
- Inspect structure with `get_skeleton(file_path="...")` to view typed signatures and docstrings without function bodies (85% token reduction).
- Read exact symbol implementations with `read_symbol(symbol="...", file_path="...")` instead of loading entire files.
- Check call chains with `get_callers(symbol="...")` or `get_neighborhood(symbol="...", direction="upstream")` before refactoring.

## 3. When to Write Memory (After Decisions & Fixes)
- Call `create_checkpoint(doing="...", next_step="...")` before context compaction, task handoffs, or complex edits.
- Record architectural choices with `log_decision(content="...", context_info="...")` to persist structural rationale.
- Store runtime discoveries and environment facts with `remember(key="...", content="...")` and lookup with `recall(key="...")`.
- Never repeat failures recorded in negative constraints. Never store secrets, passwords, or raw logs.
<!-- SYNAP_MANAGED_END -->
```

### Non-Destructive Update Behavior
1. **Fresh Installation**: If the target configuration file does not exist, it is created with the managed block (and required frontmatter/headers where applicable).
2. **Existing File with Sentinels**: The existing block between `<!-- SYNAP_MANAGED_START: ... -->` and `<!-- SYNAP_MANAGED_END -->` is replaced in-place. All human-written content before the start marker and after the end marker is preserved byte-for-byte.
3. **Legacy Directive Upgrades**: Un-sentineled directives matching `# Synapse AI Agent Directives` are upgraded into managed sentinel blocks while retaining preceding human headers.
4. **Existing File without Sentinels**: The managed block is appended cleanly to the end of the file, leaving all existing rules and configurations intact.

---

## 3. Agent-Specific Details

### Claude Code
- **Skill Path:** `.claude/skills/synap/SKILL.md`
- **Directives Path:** `CLAUDE.md`
- **Activation:** Automatically loads the `synap` skill when relevant context triggers fire. The skill is token-budgeted to remain under 600 tokens with `tiktoken` (`o200k_base`).

### Cursor
- **MDC Rule Path:** `.cursor/rules/synap.mdc`
- **Frontmatter:**
  ```yaml
  ---
  description: Synapse AI Agent Directives for persistent context and graph navigation
  globs: *
  alwaysApply: true
  ---
  ```
- **Legacy Fallback:** If `.cursorrules` exists, it is also supported and updated idempotently.

### Codex CLI
- **Path:** `AGENTS.md`
- **Activation:** Codex reads `AGENTS.md` automatically at repository root during session initiation.

### Gemini CLI
- **Skill Path:** `.gemini/config/skills/synap/SKILL.md`
- **Directives Path:** `AGENTS.md`
- **Activation:** Directly loads the Synapse skill template into Gemini CLI's local skill registry.

### GitHub Copilot
- **Path:** `.github/copilot-instructions.md`
- **Activation:** Copilot in VS Code / JetBrains / Web reads this file automatically as project instructions.

### Windsurf
- **Path:** `.windsurfrules`
- **Activation:** Cascade reads `.windsurfrules` on every turn to guide file navigation.

### Cline / Roo Code
- **Path:** `.clinerules`
- **Activation:** Cline/Roo injects `.clinerules` into the system prompt context.

### Aider
- **Path:** `.aider.conf.yml`
- **Activation:** Uses YAML-compatible comment blocks (`# <!-- SYNAP_MANAGED_START: v3.0 -->`) preserving all user-specified models, flags, and repository maps.

### Continue
- **Path:** `.continue/config.json`
- **Activation:** Injects managed directive configuration while preserving all user models, slash commands, and context providers.

### Zed
- **Path:** `.zed/settings.json`
- **Activation:** Injects managed assistant instructions while preserving all editor keybindings, themes, and language server settings.

---

## 4. Automated Agent Detection & Installation

To automatically detect installed agents and configure all of them in one command:

```bash
# Auto-detect installed agents and inject configs
synap install

# Explicitly configure specific agents
synap rules --target claude
synap rules --target cursor
synap rules --target all
```

Programmatic Python interface:
```python
from pathlib import Path
from synap_git.cli.skill_installer import detect_installed_agents, install_skills

repo = Path(".")
detected = detect_installed_agents(repo)
for agent in detected:
    print(f"Detected: {agent.name} ({agent.status})")

# Install to standard targets or all detected
installed = install_skills(repo)
print(f"Installed configs: {installed}")
```
