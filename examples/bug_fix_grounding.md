# Example: Bug Fix Grounding

This example demonstrates how Synap provides deterministic grounding for a common bug fix task.

## Scenario
A developer needs to fix a bug where the authentication session doesn't expire correctly.

## Task Command
```bash
synap task-context "fix session expiration bug" .
```

## Retrieval Trace (Diagnostic Output)

| Symbol | Score | Reason | Tokens |
| :--- | :--- | :--- | :--- |
| `auth.session.SessionManager` | 1.0 | Lexical ("session") | 150 |
| `auth.session.expire_session` | 0.95 | Lexical ("expire") | 80 |
| `auth.models.Session` | 0.8 | Structural (dependency) | 120 |
| `api.middleware.SessionMiddleware` | 0.75 | Structural (dependency) | 200 |

## Generated Context Package

### PRIMARY FILES
- `src/synap_git/auth/session.py`: Contains the `SessionManager` class and `expire_session` function.
- `src/synap_git/api/middleware.py`: Uses the session manager to validate requests.

### DEPENDENCIES
- `auth.models.Session`: Defines the data structure for sessions, including the `expires_at` field.

### ARCHITECTURAL RISKS
- Modifying session expiration logic may affect all active API requests.
- Ensure that the middleware correctly handles the transition from active to expired states without leaking sensitive data.

## Resulting AI Behavior
With this grounded context, the AI agent (e.g., Cursor) can precisely locate the `expire_session` function, understand how it is called by the middleware, and propose a fix that correctly updates the `expires_at` check, rather than searching through unrelated files.
