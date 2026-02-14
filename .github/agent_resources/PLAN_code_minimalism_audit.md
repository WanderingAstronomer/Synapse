# Code Minimalism Audit — Plan

## Problem Statement
Audit the Synapse codebase to identify technical debt, unnecessary complexity, and feature bloat. The goal is to find areas where the same outcomes can be achieved with less code, fewer abstractions, and lower cognitive load.

## Audit Scope

### Layer-by-Layer Review
1. **Engine layer** (`synapse/engine/`) — Pure calculation modules
2. **Services layer** (`synapse/services/`) — Persistence and coordination
3. **Bot layer** (`synapse/bot/`) — Discord event handlers and cogs
4. **API layer** (`synapse/api/`) — FastAPI routes and dependencies
5. **Database/Config** (`synapse/database/`, `synapse/config.py`, `synapse/constants.py`)
6. **Tests & Infrastructure** (`tests/`, `alembic/`, Docker, pyproject.toml)

### Review Criteria
- **Bloat**: Dead code, unused imports, redundant variables, stdlib-replaceable logic
- **Over-Engineering**: Excessive patterns, single-implementation interfaces, deep nesting
- **YAGNI**: Code for non-existent future use cases
- **Simplification**: Concrete proposals with "stripped down" alternatives

## Approach
- Use subagents for parallel auditing of independent layers
- Collect findings per layer
- Compile into structured audit report

## Output
Final report in `.github/agent_resources/AUDIT_code_minimalism.md`
