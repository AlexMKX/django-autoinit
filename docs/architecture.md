# AutoInit Architecture

## Overview

AutoInit provides two-phase initialization for Django containers, ensuring cluster-wide steps run exactly once and node-specific steps run once per container/volume.

## Problem Statement

In containerized Django deployments:

1. **Migrations** must run exactly once per deployment, not per container
2. **Bootstrap commands** (superuser creation, seeding) should be idempotent but run only once
3. **Static file collection** should run per node/volume, not repeatedly
4. Multiple containers starting simultaneously create race conditions

## Solution

AutoInit separates initialization into two phases:

### Phase 1: Infrastructure Init

- **Scope**: Cluster-wide (once per database/deployment)
- **Lock**: PostgreSQL advisory lock
- **Steps**: Migrations, bootstrap hooks
- **Output**: Readiness state in cache

### Phase 2: Node Init

- **Scope**: Per node or per shared volume
- **Lock**: File lock + marker
- **Steps**: collectstatic, node-specific hooks
- **Trigger**: Waits for infrastructure readiness

## Components

### Orchestrator (`orchestrator.py`)

Core logic module containing:

- `run_infrastructure_init()`: Main infrastructure init function
- `run_node_init()`: Main node init function
- Readiness helpers: `is_ready()`, `set_ready()`, `wait_for_ready()`
- Lock/marker utilities

### AutoInitMixin (`mixins.py`)

Hook interface for Django apps:

```python
class AutoInitMixin:
    def handle_infrastructure_init(self) -> None: ...
    def handle_node_init(self) -> None: ...
```

### Management Commands

- `autoinit_infrastructure`: Entrypoint for infrastructure init
- `autoinit_node`: Entrypoint for node init
- `set_ready`: Diagnostic command for readiness management

## Locking Strategy

### PostgreSQL Advisory Lock

Used for infrastructure init to ensure cluster-wide exclusivity:

```python
with pglock.advisory('autoinit_infrastructure', timeout=300) as acquired:
    if acquired:
        run_infrastructure_init()
```

**Why PostgreSQL?** Already available in Django deployments, no additional infrastructure.

### File Lock + Marker

Used for node init to handle shared volumes:

1. Check marker file existence (fast path)
2. Acquire file lock
3. Double-check marker inside lock
4. Execute node init
5. Create marker

**Why file-based?** Supports both container-local and shared volume scenarios.

## Run ID Versioning

Each deployment has a unique Run ID:

- Set via `AUTOINIT_RUN_ID` environment variable
- Falls back to deterministic hash in dev
- Used in readiness keys: `autoinit:ready:<run_id>`
- Used in marker files: `.autoinit_node_<run_id>.marker`

This prevents:
- Old readiness state affecting new deployments
- Old markers preventing init in new deployments

## Sequence Diagram

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Container A │  │ Container B │  │  PostgreSQL │  │    Redis    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       │ autoinit_infrastructure        │                │
       │────────────────┼───────────────▶│                │
       │                │         lock acquired          │
       │                │◀───────────────│                │
       │                │                │                │
       │ autoinit_infrastructure        │                │
       │                │────────────────▶│                │
       │                │         wait for lock          │
       │                │                │                │
       │ migrations     │                │                │
       │───────────────▶│                │                │
       │                │                │                │
       │ set_ready      │                │                │
       │────────────────┼────────────────┼───────────────▶│
       │                │                │                │
       │ release lock   │                │                │
       │────────────────┼───────────────▶│                │
       │                │         lock acquired          │
       │                │◀───────────────│                │
       │                │                │                │
       │                │ check ready    │                │
       │                │────────────────┼───────────────▶│
       │                │         ready=true             │
       │                │◀───────────────┼───────────────│
       │                │                │                │
       │ autoinit_node  │ release lock   │                │
       │                │───────────────▶│                │
       │                │                │                │
       ▼                ▼                ▼                ▼
```

## Error Handling

### Infrastructure Init

- **Fatal**: Any failure aborts the container startup
- **Rationale**: Critical steps (migrations) must succeed

### Node Init

- **Non-fatal by default**: Hook failures are logged and skipped
- **Configurable**: `--fatal-on-error` flag for strict mode
- **Rationale**: Static files may fail without breaking app functionality

## Configuration

All configuration via Django settings with sensible defaults:

| Setting | Default | Purpose |
|---------|---------|---------|
| `AUTOINIT_TIMEOUT_SEC` | 300 | Lock/wait timeout |
| `AUTOINIT_CACHE_ALIAS` | 'default' | Cache for readiness |
| `AUTOINIT_MARKER_DIR` | '/tmp/autoinit' | Marker storage |
