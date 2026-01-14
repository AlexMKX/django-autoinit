# django-autoinit

Two-phase initialization for Django containers: **infrastructure** (cluster-wide) and **node** (per-container) init with distributed locking.

## Features

- **Infrastructure init**: Cluster-wide steps (migrations, bootstrap) protected by PostgreSQL advisory lock
- **Node init**: Per-node/per-volume steps (collectstatic) with file marker + lock
- **Run ID versioning**: Prevents stale readiness/markers across deployments
- **Idempotent**: Safe to run multiple times
- **Hook-based**: Apps register init steps via `AutoInitMixin`

## Installation

```bash
pip install django-autoinit
```

## Quick Start

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    'autoinit',  # Add early in the list
    # ... other apps
]
```

### 2. Configure settings

```python
# Required: Redis-backed cache for cross-container readiness
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
    }
}

# Optional settings (with defaults)
AUTOINIT_TIMEOUT_SEC = 300  # Lock/wait timeout
AUTOINIT_CACHE_ALIAS = 'default'  # Cache alias for readiness
AUTOINIT_MARKER_DIR = '/tmp/autoinit'  # Node marker directory
AUTOINIT_READINESS_KEY_PREFIX = 'autoinit:ready'
```

### 3. Set Run ID in production

```bash
export AUTOINIT_RUN_ID="deploy-$(date +%s)"
```

### 4. Update container entrypoint

```bash
#!/bin/bash
set -e

python manage.py autoinit_infrastructure
python manage.py autoinit_node

exec "$@"
```

### 5. Add hooks to your apps (optional)

```python
# myapp/apps.py
from django.apps import AppConfig
from autoinit import AutoInitMixin

class MyAppConfig(AppConfig, AutoInitMixin):
    name = 'myapp'

    def handle_infrastructure_init(self) -> None:
        """Called once per cluster during infrastructure init."""
        from myapp.tasks import seed_data_task
        seed_data_task.delay()

    def handle_node_init(self) -> None:
        """Called once per node during node init."""
        pass  # Optional
```

## Architecture

### Two-Phase Initialization

```
Container Start
      │
      ▼
┌─────────────────────────────────────┐
│  autoinit_infrastructure            │
│  ─────────────────────────────────  │
│  1. Wait for DB                     │
│  2. Acquire PostgreSQL advisory lock│
│  3. Run migrations                  │
│  4. Call app hooks                  │
│  5. Set readiness in cache          │
└─────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  autoinit_node                      │
│  ─────────────────────────────────  │
│  1. Wait for readiness              │
│  2. Check file marker               │
│  3. Acquire file lock               │
│  4. Run collectstatic               │
│  5. Call app hooks                  │
│  6. Create marker                   │
└─────────────────────────────────────┘
      │
      ▼
   Main Process (gunicorn, celery, etc.)
```

### Concurrency Safety

- **Infrastructure lock**: PostgreSQL advisory lock via `django-pglock`
- **Node lock**: File lock via `filelock`
- **Readiness**: Django cache (Redis recommended)
- **Markers**: File-based, includes Run ID

## Management Commands

### `autoinit_infrastructure`

Run cluster-wide infrastructure initialization.

```bash
python manage.py autoinit_infrastructure [--run-id RUN_ID] [--timeout SECONDS]
```

### `autoinit_node`

Run per-node initialization.

```bash
python manage.py autoinit_node [--run-id RUN_ID] [--timeout SECONDS] [--fatal-on-error]
```

### `set_ready`

Manage readiness state (diagnostic).

```bash
python manage.py set_ready check [--run-id RUN_ID]
python manage.py set_ready set [--run-id RUN_ID]
python manage.py set_ready clear [--run-id RUN_ID]
```

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `AUTOINIT_TIMEOUT_SEC` | `300` | Timeout for lock acquisition and readiness wait |
| `AUTOINIT_CACHE_ALIAS` | `'default'` | Django cache alias for readiness state |
| `AUTOINIT_MARKER_DIR` | `'/tmp/autoinit'` | Directory for node init markers |
| `AUTOINIT_READINESS_KEY_PREFIX` | `'autoinit:ready'` | Cache key prefix for readiness |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `AUTOINIT_RUN_ID` | Deployment identifier (required in production) |

## Hook Contract

Apps implement hooks via `AutoInitMixin`:

```python
class MyAppConfig(AppConfig, AutoInitMixin):
    def handle_infrastructure_init(self) -> None:
        """Infrastructure hook - runs once per cluster.
        
        - Must be idempotent
        - Failures are fatal (raise to abort)
        - Called in INSTALLED_APPS order
        """
        pass

    def handle_node_init(self) -> None:
        """Node hook - runs once per node/volume.
        
        - Must be idempotent
        - Non-fatal by default (logged and skipped)
        - Called in INSTALLED_APPS order
        """
        pass
```

## Dependencies

- Django >= 5.0
- django-pglock >= 1.6
- filelock >= 3.13
- Redis (recommended for cache backend)

## License

MIT
