# Diagnostic Observability

Trust is built through explainability. Synap provides deep visibility into its internal operations so that developers can verify why specific context was provided to an AI agent.

## Retrieval Traces

Every search or task-context operation generates a unique `trace_id`. Traces can be inspected via the diagnostic UI or the CLI.
A trace includes:
- **Lexical Hits:** Exact keywords that triggered a match.
- **Structural Path:** The chain of dependencies that led to a neighbor symbol.
- **Token Allocation:** Exactly how many tokens were used per file/symbol.
- **Truncation Reason:** Why certain symbols were excluded (e.g., "over budget").

## Index Health

Monitor the state of your local context repository:
- **Symbol Density:** Number of symbols per file.
- **Dependency Coverage:** Verification of cross-file edge completeness.
- **Stale Embeddings:** Identification of symbols needing re-embedding.

## Parser Diagnostics

Synap logs all parser failures, such as:
- **Syntax Errors:** Files that could not be parsed due to invalid code.
- **Unsupported Syntax:** Language constructs that the current Tree-sitter grammar does not support.
- **Performance Timing:** How long each file took to index.

---

## Example Trace View

| Symbol | Score | Reason | Tokens |
| :--- | :--- | :--- | :--- |
| `Authenticator.login` | 1.0 | Lexical Match ("login") | 142 |
| `AuthService.get_user` | 0.8 | Structural (dist=1) | 215 |
| `User` model | 0.6 | Structural (dist=2) | 98 |
| `session_utils` | 0.4 | Semantic (sim=0.72) | (Truncated) |
