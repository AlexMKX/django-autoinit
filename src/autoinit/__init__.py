"""Module: autoinit

Purpose: Two-phase initialization for Django containers with distributed locking.

Key Components:
- AutoInitMixin: Mixin for AppConfig to register infrastructure/node init hooks
- orchestrator: Core init orchestration (locks, markers, readiness)
- Management commands: autoinit_infrastructure, autoinit_node, set_ready

Architecture:
Infrastructure init runs once per cluster (PostgreSQL advisory lock).
Node init runs once per node/volume (file marker + lock).
Readiness state stored in Django cache (Redis).

Related Modules:
- django-pglock: PostgreSQL advisory locks
- filelock: File-based locking for node markers
"""

__version__ = '0.1.0'

from autoinit.mixins import AutoInitMixin

__all__ = ['AutoInitMixin', '__version__']
