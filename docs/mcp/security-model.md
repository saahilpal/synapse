# MCP Security Model

## Purpose

The MCP security model prevents agents from poisoning memory, exfiltrating sensitive context, or mutating cognition without authorization.

## Architecture

```mermaid
flowchart LR
    Client[MCP client]
    Auth[Local authorization]
    Policy[Permission policy]
    Runtime[Runtime command]
    Audit[Audit event]

    Client --> Auth --> Policy --> Runtime --> Audit
```

## Lifecycle

Each MCP request is authenticated locally where possible, authorized by tool/resource scope, executed through runtime services, and audited if it reads sensitive context or mutates state.

## Responsibilities

- Default to read-only.
- Separate read, note, rollback, repair, and admin permissions.
- Redact sensitive evidence.
- Mark agent-supplied content as untrusted.
- Require explicit approval for durable memory promotion.

## Data Flow

Requests carry client identity and intended action. Runtime policies evaluate requested access against repository, branch, context, and trust scope.

## Failure Modes

- Confused-deputy tool calls.
- Prompt injection in repository docs.
- Agent output promoted as verified fact.
- Tool metadata over-discloses capabilities.

## Edge Cases

- Same agent connected through multiple clients.
- User changes permissions while request is running.
- Tool call requests rollback during active merge conflict.
- Resource contains mixed-trust facts.

## Scalability Notes

Local permissions are enough for MVP. Team deployments need signed clients and policy files.

## Security Notes

Never rely on model behavior for enforcement. Enforcement belongs in Synapse runtime code.

## Performance Considerations

Permission checks must be cheap enough to run on every request.

## Future Extensibility

Add signed tool manifests and per-agent capability grants for shared environments.

