# Agent Booster Integration Specification

## Purpose
Define how Lumen integrates with external AI agent frameworks through a standardized
agent protocol.

## Protocol Overview
Agents communicate with Lumen via structured JSON requests. Each request specifies:
- **agent_id**: Identity of the requesting agent
- **operation**: Type of operation (render, compute, query, store)
- **parameters**: Operation-specific parameters
- **priority**: Request priority (low, normal, high, critical)
- **timeout_ms**: Maximum time to wait for response

## Permission Model
Access is controlled by role-based permissions:
- **admin**: Full access (read, write, deploy, admin)
- **architect**: Design and deploy access (read, write, deploy)
- **evaluator**: Read-only access to evaluation data
- **service**: Programmatic access (read, write)

## Request Lifecycle
1. Agent sends request via agent protocol
2. Lumen validates agent identity and permissions
3. Request is routed to appropriate subsystem
4. Subsystem executes and returns response
5. Response is logged to memory store

## API Endpoints
### POST /agent/execute
Execute an agent operation.
Returns: operation result or error

### GET /agent/status
Check agent system status.
Returns: system health and active agent count

### POST /agent/register
Register a new agent identity.
Returns: agent credentials

## Integration Points
- `lumen_core/` — Core execution engine
- `Weaver_ASI/` — Intent routing layer
- `vault/` — Persistent storage
- `harness/` — Evaluation framework for agent performance

## Security
- All agent communications are authenticated
- Rate limiting applied per agent
- Audit logging for all operations
- Permission checks on every request
