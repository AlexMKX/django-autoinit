# GFI Integration Example

This document shows how AutoInit is integrated into the GFI project.

## Settings Integration

```python
# backend/gfi/settings/__init__.py

INSTALLED_APPS = [
    'autoinit',  # Early in the list
    'django.contrib.admin',
    # ... other apps
    'cfbackend',
    'identity',
    'librechat_adapter',
]

# AutoInit settings
AUTOINIT_TIMEOUT_SEC = 300
AUTOINIT_CACHE_ALIAS = 'default'
AUTOINIT_MARKER_DIR = '/tmp/autoinit'
```

## App Hooks

### cfbackend

```python
# backend/cfbackend/apps.py
from django.apps import AppConfig
from autoinit import AutoInitMixin

class CfbackendConfig(AppConfig, AutoInitMixin):
    name = 'cfbackend'

    def handle_infrastructure_init(self) -> None:
        from cfbackend.management.commands.seed_backends import Command
        Command().handle()
        
        # Non-fatal: NVCF sync (may fail if no API key)
        try:
            from cfbackend.management.commands.sync_nvcf_backends import Command
            Command().handle()
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                'sync_nvcf_backends failed (non-fatal)'
            )
```

### identity

```python
# backend/identity/apps.py
from django.apps import AppConfig
from autoinit import AutoInitMixin

class IdentityConfig(AppConfig, AutoInitMixin):
    name = 'identity'

    def handle_infrastructure_init(self) -> None:
        from identity.management.commands.bootstrap_superuser import Command
        Command().handle()
```

### librechat_adapter

```python
# backend/librechat_adapter/apps.py
from django.apps import AppConfig
from autoinit import AutoInitMixin

class LibrechatAdapterConfig(AppConfig, AutoInitMixin):
    name = 'librechat_adapter'

    def handle_infrastructure_init(self) -> None:
        # Only bootstrap if superuser exists
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(is_superuser=True).exists():
            from librechat_adapter.management.commands.bootstrap_librechat_oauth import Command
            Command().handle()
```

## Entrypoint

```bash
#!/bin/bash
# backend/entrypoint.sh
set -e

python manage.py autoinit_infrastructure
python manage.py autoinit_node

exec "$@"
```

## Compose Configuration

```yaml
# compose/base.yml
x-django-base: &django-base
  build:
    context: ../backend
  # No entrypoint override - uses Dockerfile ENTRYPOINT

services:
  django:
    <<: *django-base
    command: gunicorn gfi.wsgi:application --bind 0.0.0.0:8000

  celery:
    <<: *django-base
    command: celery -A gfi worker -l info
    # Removed: entrypoint: []

  celery_beat:
    <<: *django-base
    command: celery -A gfi beat -l info
    # Removed: entrypoint: []
```

## Migration from Legacy entrypoint.sh

### Before (legacy)

```bash
#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Seeding backends..."
python manage.py seed_backends

echo "Syncing NVCF backends..."
python manage.py sync_nvcf_backends || echo "NVCF sync skipped"

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Bootstrapping superuser..."
python manage.py bootstrap_superuser

echo "Bootstrapping LibreChat OAuth..."
if python manage.py shell -c "..."; then
  python manage.py bootstrap_librechat_oauth
fi

exec "$@"
```

### After (AutoInit)

```bash
#!/bin/bash
set -e

python manage.py autoinit_infrastructure
python manage.py autoinit_node

exec "$@"
```

Bootstrap logic moved to app hooks:
- `seed_backends` → `cfbackend.handle_infrastructure_init()`
- `sync_nvcf_backends` → `cfbackend.handle_infrastructure_init()` (non-fatal)
- `bootstrap_superuser` → `identity.handle_infrastructure_init()`
- `bootstrap_librechat_oauth` → `librechat_adapter.handle_infrastructure_init()`
- `collectstatic` → Built into `autoinit_node` (core step)
- `migrate` → Built into `autoinit_infrastructure` (core step)

## Benefits

1. **Concurrency safety**: Only one container runs migrations
2. **Faster startup**: Celery workers don't re-run migrations
3. **Cleaner separation**: Each app owns its bootstrap logic
4. **Idempotency**: Safe to restart containers
