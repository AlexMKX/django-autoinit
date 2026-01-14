# AutoInit Configuration

## Django Settings

### AUTOINIT_TIMEOUT_SEC

Timeout in seconds for lock acquisition and readiness wait.

- **Type**: `int`
- **Default**: `300`
- **Usage**: Controls how long autoinit waits for:
  - PostgreSQL advisory lock acquisition
  - Readiness state before node init
  - File lock acquisition

```python
AUTOINIT_TIMEOUT_SEC = 600  # 10 minutes
```

### AUTOINIT_CACHE_ALIAS

Django cache alias used for storing readiness state.

- **Type**: `str`
- **Default**: `'default'`
- **Requirement**: Must be a cross-container cache (Redis recommended)

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
    },
    'autoinit': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/2',
    }
}

AUTOINIT_CACHE_ALIAS = 'autoinit'
```

### AUTOINIT_MARKER_DIR

Directory for node init marker files.

- **Type**: `str` (path)
- **Default**: `'/tmp/autoinit'`
- **Usage**: 
  - Container-local: Use default `/tmp/autoinit`
  - Shared volume: Set to mounted volume path

```python
# For node-group semantics (multiple containers share markers)
AUTOINIT_MARKER_DIR = '/shared/autoinit'
```

### AUTOINIT_READINESS_KEY_PREFIX

Prefix for readiness cache keys.

- **Type**: `str`
- **Default**: `'autoinit:ready'`
- **Format**: `{prefix}:{run_id}`

```python
AUTOINIT_READINESS_KEY_PREFIX = 'myapp:autoinit:ready'
```

## Environment Variables

### AUTOINIT_RUN_ID

Unique identifier for the deployment/build.

- **Required**: In production
- **Fallback**: Deterministic hash of `cwd` in development

```bash
# Set during deployment
export AUTOINIT_RUN_ID="deploy-$(git rev-parse --short HEAD)-$(date +%s)"

# Or use CI/CD build ID
export AUTOINIT_RUN_ID="${CI_PIPELINE_ID}"
```

## Cache Requirements

AutoInit requires a cache backend that is:

1. **Cross-container**: All containers must see the same state
2. **Persistent**: State must survive container restarts within deployment
3. **Fast**: Used for polling readiness

### Recommended: Redis

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
    }
}
```

### Not Recommended

- **LocMemCache**: Not cross-container
- **FileBasedCache**: May not be shared
- **DatabaseCache**: Too slow for polling

## Marker Directory Configuration

### Single Container (default)

Each container has its own marker space:

```python
AUTOINIT_MARKER_DIR = '/tmp/autoinit'  # Default
```

### Node Group (shared volume)

Multiple containers share markers via volume:

```python
AUTOINIT_MARKER_DIR = '/app/shared/autoinit'
```

```yaml
# docker-compose.yml
services:
  web:
    volumes:
      - shared_data:/app/shared
  worker:
    volumes:
      - shared_data:/app/shared

volumes:
  shared_data:
```

## Complete Example

```python
# settings.py

# Cache for readiness state
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379/1",
    }
}

# AutoInit settings
AUTOINIT_TIMEOUT_SEC = int(os.environ.get('AUTOINIT_TIMEOUT_SEC', 300))
AUTOINIT_CACHE_ALIAS = 'default'
AUTOINIT_MARKER_DIR = os.environ.get('AUTOINIT_MARKER_DIR', '/tmp/autoinit')
AUTOINIT_READINESS_KEY_PREFIX = 'autoinit:ready'
```

```bash
# entrypoint.sh
#!/bin/bash
set -e

export AUTOINIT_RUN_ID="${DEPLOY_ID:-dev}"

python manage.py autoinit_infrastructure
python manage.py autoinit_node

exec "$@"
```
