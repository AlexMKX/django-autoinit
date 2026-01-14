"""Management command: autoinit_infrastructure

Purpose: Run cluster-wide infrastructure initialization with distributed locking.

Related:
- autoinit.orchestrator.run_infrastructure_init: Core implementation
- entrypoint.sh: Calls this command before starting main process
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from autoinit.orchestrator import (
    AutoInitError,
    get_run_id,
    run_infrastructure_init,
)


class Command(BaseCommand):
    """Run infrastructure initialization with PostgreSQL advisory lock.

    Purpose: Entrypoint command for cluster-wide init steps.

    Key Behaviors:
    - Waits for database connectivity
    - Acquires distributed lock (only one container runs init)
    - Runs migrations and app hooks
    - Sets readiness state for node init

    Related:
    - autoinit_node: Subsequent command for per-node init
    """

    help = 'Run infrastructure initialization (migrations, app hooks) with distributed lock'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--run-id',
            type=str,
            default=None,
            help='Deployment run ID (defaults to AUTOINIT_RUN_ID env or generated)',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=None,
            help='Lock acquisition timeout in seconds (defaults to AUTOINIT_TIMEOUT_SEC)',
        )

    def handle(self, *args, **options) -> None:
        run_id = options.get('run_id') or get_run_id()
        timeout = options.get('timeout')

        self.stdout.write(f'autoinit_infrastructure: starting (run_id={run_id})')

        try:
            run_infrastructure_init(run_id=run_id, timeout=timeout)
            self.stdout.write(
                self.style.SUCCESS('autoinit_infrastructure: completed')
            )
        except AutoInitError as e:
            self.stderr.write(
                self.style.ERROR(f'autoinit_infrastructure: FAILED - {e}')
            )
            sys.exit(1)
