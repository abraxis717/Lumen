# Agent Booster Integration — Summary

## Source
`update/AGENT-BOOSTER-INTEGRATION.md`

## What It Specifies
The Agent Booster integration defines how Lumen exposes its rendering and computation
capabilities to external AI agents through a standardized protocol.

## Key Points
- Agents communicate with Lumen via a structured agent protocol
- Agents can request: rendering operations, compute tasks, data access
- The protocol supports both synchronous and asynchronous operations
- Integration point: `harness/` directory for agent-facing APIs
- Agent identity is managed via `data/users.json` with role-based permissions

## Integration Points
1. **Protocol Layer**: Agent request/response format
2. **Permission Layer**: Role-based access control (admin, architect, evaluator, service)
3. **Execution Layer**: Agent requests routed to appropriate Lumen subsystems
4. **Memory Layer**: Agent interactions stored in `data/memories.json`

## Status
- Specification document received from Co-Architects
- Integration skeleton in `docs/agent-booster.md`
- Protocol implementation pending Rust bindings in lumen_core/

## References
- See `docs/agent-booster.md` for the full integration spec
- Agent permissions stored in `data/users.json`
- Agent interactions logged to `data/memories.json`
