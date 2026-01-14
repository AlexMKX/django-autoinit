"""Management command: autoinit_node

Purpose: Run per-node/per-volume initialization with marker + file lock.

Related:
- autoinit.orchestrator.run_node_init: Core implementation
- entrypoint.sh: Calls this command after autoinit_infrastructure
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from autoinit.orchestrator import (
    AutoInitError,
    get_run_id,
    run_node_init,
)


class Command(BaseCommand):
    """Run node initialization with file marker and lock.

    Purpose: Entrypoint command for per-node init steps.

    Key Behaviors:
    - Waits for infrastructure readiness
    - Checks marker file (skips if already done)
    - Runs collectstatic and app hooks
    - Creates marker on completion

    Related:
    - autoinit_infrastructure: Must complete first
    """

    help = 'Run node initialization (collectstatic, app hooks) with file marker'

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
            help='Readiness wait timeout in seconds (defaults to AUTOINIT_TIMEOUT_SEC)',
        )
        parser.add_argument(
            '--fatal-on-error',
            action='store_true',
            help='Treat hook errors as fatal (default: log and continue)',
        )

    def handle(self, *args, **options) -> None:
        run_id = options.get('run_id') or get_run_id()
        timeout = options.get('timeout')
        fatal_on_error = options.get('fatal_on_error', False)

        self.stdout.write(f'autoinit_node: starting (run_id={run_id})')

        try:
            run_node_init(
                run_id=run_id,
                timeout=timeout,
                fatal_on_error=fatal_on_error,
            )
            self.stdout.write(
                self.style.SUCCESS('autoinit_node: completed')
            )
        except AutoInitError as e:
            self.stderr.write(
                self.style.ERROR(f'autoinit_node: FAILED - {e}')
            )
            sys.exit(1)
