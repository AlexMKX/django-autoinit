"""Module: autoinit.orchestrator

Purpose: Core initialization orchestration with distributed locking and readiness management.

Key Components:
- get_run_id: Get or generate deployment run ID
- is_ready / set_ready: Readiness state in Django cache
- run_infrastructure_init: Cluster-wide init with PostgreSQL advisory lock
- run_node_init: Per-node init with file marker + lock

Architecture:
Infrastructure init uses django-pglock for PostgreSQL advisory locks.
Node init uses filelock for file-based locking and markers.
Readiness state stored in Django cache (Redis recommended).
All functions preserve INSTALLED_APPS order when calling hooks.

Related Modules:
- autoinit.mixins: AutoInitMixin hook interface
- django-pglock: PostgreSQL advisory locks
- filelock: File-based locking
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pglock
from django.apps import apps
from django.conf import settings
from django.core import management
from django.db import connection
from filelock import FileLock, Timeout

from autoinit.mixins import AutoInitMixin

if TYPE_CHECKING:
    from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AutoInitError(Exception):
    """Base exception for autoinit errors."""

    pass


class AutoInitTimeoutError(AutoInitError):
    """Raised when lock acquisition or readiness wait times out."""

    pass


class AutoInitInfrastructureError(AutoInitError):
    """Raised when infrastructure init fails."""

    pass


def get_run_id() -> str:
    """Get deployment run ID from environment or generate deterministic fallback.

    Purpose: Provide unique identifier for deployment/build to version readiness and markers.

    Key Behaviors:
    - Returns AUTOINIT_RUN_ID env var if set
    - Falls back to deterministic hash of cwd for dev environments

    Returns:
        Run ID string (either from env or generated dev-XXXXXXXX format)
    """
    env_value = os.environ.get('AUTOINIT_RUN_ID')
    if env_value:
        return env_value
    base = os.getcwd().encode()
    return 'dev-' + hashlib.md5(base).hexdigest()[:8]


def _get_timeout() -> int:
    """Get timeout value from settings."""
    return getattr(settings, 'AUTOINIT_TIMEOUT_SEC', 300)


def _get_cache_alias() -> str:
    """Get cache alias from settings."""
    return getattr(settings, 'AUTOINIT_CACHE_ALIAS', 'default')


def _get_readiness_key_prefix() -> str:
    """Get readiness key prefix from settings."""
    return getattr(settings, 'AUTOINIT_READINESS_KEY_PREFIX', 'autoinit:ready')


def _get_marker_dir() -> Path:
    """Get marker directory from settings."""
    return Path(getattr(settings, 'AUTOINIT_MARKER_DIR', '/tmp/autoinit'))


def _get_readiness_key(run_id: str) -> str:
    """Build cache key for readiness state."""
    prefix = _get_readiness_key_prefix()
    return f'{prefix}:{run_id}'


def is_ready(run_id: str | None = None) -> bool:
    """Check if infrastructure init is complete for the given run ID.

    Purpose: Allow node init to wait for infrastructure init completion.

    Args:
        run_id: Deployment run ID (defaults to current run ID)

    Returns:
        True if infrastructure init completed for this run ID
    """
    from django.core.cache import caches

    run_id = run_id or get_run_id()
    cache = caches[_get_cache_alias()]
    key = _get_readiness_key(run_id)
    return cache.get(key) == 1


def set_ready(run_id: str | None = None) -> None:
    """Mark infrastructure init as complete for the given run ID.

    Purpose: Signal to node init that infrastructure is ready.

    Args:
        run_id: Deployment run ID (defaults to current run ID)
    """
    from django.core.cache import caches

    run_id = run_id or get_run_id()
    cache = caches[_get_cache_alias()]
    key = _get_readiness_key(run_id)
    # Set with long TTL (24 hours) - should survive container restarts
    cache.set(key, 1, timeout=86400)
    logger.info('autoinit: set ready', extra={'run_id': run_id})


def clear_ready(run_id: str | None = None) -> None:
    """Clear readiness state for the given run ID.

    Purpose: Reset readiness for testing or manual intervention.

    Args:
        run_id: Deployment run ID (defaults to current run ID)
    """
    from django.core.cache import caches

    run_id = run_id or get_run_id()
    cache = caches[_get_cache_alias()]
    key = _get_readiness_key(run_id)
    cache.delete(key)
    logger.info('autoinit: cleared ready', extra={'run_id': run_id})


def wait_for_ready(run_id: str | None = None, timeout: int | None = None) -> None:
    """Wait for infrastructure init to complete.

    Purpose: Block until infrastructure is ready before proceeding with node init.

    Args:
        run_id: Deployment run ID (defaults to current run ID)
        timeout: Maximum seconds to wait (defaults to AUTOINIT_TIMEOUT_SEC)

    Raises:
        AutoInitTimeoutError: If timeout exceeded waiting for readiness
    """
    run_id = run_id or get_run_id()
    timeout = timeout or _get_timeout()
    start = time.monotonic()

    while not is_ready(run_id):
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise AutoInitTimeoutError(
                f'Timeout waiting for infrastructure readiness (run_id={run_id}, timeout={timeout}s)'
            )
        time.sleep(1)
        logger.debug('autoinit: waiting for ready', extra={'run_id': run_id, 'elapsed': elapsed})


def wait_for_db(timeout: int | None = None) -> None:
    """Wait for database to become available.

    Purpose: Block until database connection is established.

    Args:
        timeout: Maximum seconds to wait (defaults to AUTOINIT_TIMEOUT_SEC)

    Raises:
        AutoInitTimeoutError: If timeout exceeded waiting for database
    """
    timeout = timeout or _get_timeout()
    start = time.monotonic()

    while True:
        try:
            connection.ensure_connection()
            logger.info('autoinit: database connection established')
            return
        except Exception as e:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise AutoInitTimeoutError(
                    f'Timeout waiting for database connection (timeout={timeout}s): {e}'
                )
            logger.debug('autoinit: waiting for database', extra={'elapsed': elapsed, 'error': str(e)})
            time.sleep(1)


def _get_apps_with_mixin() -> list[AppConfig]:
    """Get all app configs that implement AutoInitMixin in INSTALLED_APPS order.

    Purpose: Discover apps participating in autoinit.

    Returns:
        List of AppConfig instances with AutoInitMixin, in INSTALLED_APPS order
    """
    result = []
    for app_config in apps.get_app_configs():
        if isinstance(app_config, AutoInitMixin):
            result.append(app_config)
    return result


def _run_migrations() -> None:
    """Run Django migrations.

    Purpose: Core infrastructure step - apply database migrations.
    """
    logger.info('autoinit: running migrations')
    management.call_command('migrate', '--noinput', verbosity=1)


def _run_collectstatic() -> None:
    """Run Django collectstatic.

    Purpose: Core node step - collect static files.
    """
    logger.info('autoinit: running collectstatic')
    management.call_command('collectstatic', '--noinput', verbosity=1)


def run_infrastructure_init(run_id: str | None = None, timeout: int | None = None) -> None:
    """Execute infrastructure initialization with distributed lock.

    Purpose: Run cluster-wide init steps exactly once per deployment.

    Key Behaviors:
    - Waits for database connectivity
    - Acquires PostgreSQL advisory lock
    - Runs migrations
    - Calls handle_infrastructure_init on all apps with AutoInitMixin
    - Sets readiness state on completion

    Args:
        run_id: Deployment run ID (defaults to current run ID)
        timeout: Lock acquisition timeout (defaults to AUTOINIT_TIMEOUT_SEC)

    Raises:
        AutoInitTimeoutError: If lock acquisition times out
        AutoInitInfrastructureError: If any infrastructure step fails

    Related:
    - management/commands/autoinit_infrastructure.py: Management command wrapper
    """
    run_id = run_id or get_run_id()
    timeout = timeout or _get_timeout()

    logger.info('autoinit: starting infrastructure init', extra={'run_id': run_id})

    # Wait for database
    wait_for_db(timeout)

    # Check if already ready (another container completed init)
    if is_ready(run_id):
        logger.info('autoinit: infrastructure already ready', extra={'run_id': run_id})
        return

    # Acquire distributed lock using django-pglock
    with pglock.advisory('autoinit_infrastructure', timeout=timeout) as acquired:
        if not acquired:
            raise AutoInitTimeoutError(
                f'Lock acquisition timed out (timeout={timeout}s)'
            )

        # Double-check readiness inside lock (another process may have completed)
        if is_ready(run_id):
            logger.info('autoinit: infrastructure ready (checked inside lock)', extra={'run_id': run_id})
            return

        try:
            # Core infrastructure: migrations
            _run_migrations()

            # App hooks in INSTALLED_APPS order
            for app_config in _get_apps_with_mixin():
                logger.info(
                    'autoinit: running infrastructure hook',
                    extra={'app': app_config.name},
                )
                app_config.handle_infrastructure_init()

            # Mark as ready
            set_ready(run_id)
            logger.info('autoinit: infrastructure init completed', extra={'run_id': run_id})

        except Exception as e:
            logger.exception('autoinit: infrastructure init failed', extra={'run_id': run_id})
            raise AutoInitInfrastructureError(f'Infrastructure init failed: {e}') from e


def _get_node_marker_path(run_id: str) -> Path:
    """Get path to node marker file for given run ID."""
    marker_dir = _get_marker_dir()
    return marker_dir / f'.autoinit_node_{run_id}.marker'


def _check_node_marker(run_id: str) -> bool:
    """Check if node init marker exists for given run ID."""
    marker_path = _get_node_marker_path(run_id)
    return marker_path.exists()


def _create_node_marker(run_id: str) -> None:
    """Create node init marker for given run ID."""
    marker_path = _get_node_marker_path(run_id)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.touch()


def run_node_init(
    run_id: str | None = None,
    timeout: int | None = None,
    fatal_on_error: bool = False,
) -> None:
    """Execute node initialization with marker + file lock.

    Purpose: Run per-node/per-volume init steps idempotently.

    Key Behaviors:
    - Waits for infrastructure readiness
    - Checks marker file (skips if already done for this run ID)
    - Acquires file lock for marker operations
    - Runs collectstatic
    - Calls handle_node_init on all apps with AutoInitMixin
    - Creates marker on completion

    Args:
        run_id: Deployment run ID (defaults to current run ID)
        timeout: Lock/wait timeout (defaults to AUTOINIT_TIMEOUT_SEC)
        fatal_on_error: If True, raise on hook errors; otherwise log and continue

    Raises:
        AutoInitTimeoutError: If readiness wait or lock acquisition times out

    Related:
    - management/commands/autoinit_node.py: Management command wrapper
    """
    run_id = run_id or get_run_id()
    timeout = timeout or _get_timeout()

    logger.info('autoinit: starting node init', extra={'run_id': run_id})

    # Wait for infrastructure readiness
    logger.info('autoinit: waiting for infrastructure readiness', extra={'run_id': run_id})
    wait_for_ready(run_id, timeout)
    logger.info('autoinit: infrastructure ready, proceeding', extra={'run_id': run_id})

    # Check marker (fast path - already done)
    if _check_node_marker(run_id):
        logger.info('autoinit: node init already done (marker exists)', extra={'run_id': run_id})
        return

    # File lock for marker operations
    marker_path = _get_node_marker_path(run_id)
    lock_path = marker_path.with_suffix('.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with FileLock(lock_path, timeout=timeout):
            # Double-check marker inside lock
            if _check_node_marker(run_id):
                logger.info('autoinit: node init done (checked inside lock)', extra={'run_id': run_id})
                return

            # Core node step: collectstatic
            _run_collectstatic()

            # App hooks in INSTALLED_APPS order
            for app_config in _get_apps_with_mixin():
                logger.info(
                    'autoinit: running node hook',
                    extra={'app': app_config.name},
                )
                try:
                    app_config.handle_node_init()
                except Exception as e:
                    if fatal_on_error:
                        raise
                    logger.warning(
                        'autoinit: node hook failed (non-fatal)',
                        extra={'app': app_config.name, 'error': str(e)},
                    )

            # Create marker
            _create_node_marker(run_id)
            logger.info('autoinit: node init completed', extra={'run_id': run_id})

    except Timeout:
        raise AutoInitTimeoutError(
            f'File lock acquisition timed out (timeout={timeout}s)'
        )
