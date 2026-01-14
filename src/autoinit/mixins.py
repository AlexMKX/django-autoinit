"""Module: autoinit.mixins

Purpose: Mixin for Django AppConfig to register initialization hooks.

Key Components:
- AutoInitMixin: Mixin class providing handle_infrastructure_init and handle_node_init hooks
"""

from __future__ import annotations


class AutoInitMixin:
    """Mixin for AppConfig to participate in AutoInit two-phase initialization.

    Purpose: Provide hook interface for apps to register infrastructure and node init steps.

    Key Behaviors:
    - handle_infrastructure_init: Called once per cluster during infra init
    - handle_node_init: Called once per node/volume during node init
    - Both methods must be idempotent

    Design:
    Apps inherit from both AppConfig and AutoInitMixin.
    Management commands discover apps with this mixin and call hooks in INSTALLED_APPS order.

    Related:
    - orchestrator.run_infrastructure_hooks: Calls handle_infrastructure_init
    - orchestrator.run_node_hooks: Calls handle_node_init
    - Tests: tests/autoqa/test_autoinit.py
    """

    def handle_infrastructure_init(self) -> None:
        """Execute infrastructure initialization for this app.

        Purpose: Run cluster-wide init steps (once per database/deployment).

        Key Behaviors:
        - Must be idempotent (safe to run multiple times)
        - Failures are fatal (raise exception to abort init)
        - Called in INSTALLED_APPS order

        Override this method in your AppConfig to add infrastructure init logic.
        """
        pass

    def handle_node_init(self) -> None:
        """Execute node initialization for this app.

        Purpose: Run per-node/per-volume init steps.

        Key Behaviors:
        - Must be idempotent
        - Non-fatal by default (logged and skipped)
        - Called in INSTALLED_APPS order

        Override this method in your AppConfig to add node init logic.
        """
        pass
