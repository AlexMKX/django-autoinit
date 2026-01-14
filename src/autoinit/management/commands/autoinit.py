"""Management command: autoinit

Purpose: Combined infrastructure + node initialization in single process.

Related:
- autoinit.orchestrator: Core implementation
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from autoinit.orchestrator import (
    AutoInitError,
    get_run_id,
    run_infrastructure_init,
    run_node_init,
)


class Command(BaseCommand):
    """Run both infrastructure and node initialization in single process.

    Purpose: Avoid double Django initialization by combining both phases.

    Key Behaviors:
    - Runs infrastructure init (migrations, app hooks, set ready)
    - Runs node init (collectstatic, app hooks, marker)
    - Single Django initialization
    """

    help = 'Run infrastructure and node initialization in single process'

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
            help='Lock/wait timeout in seconds (defaults to AUTOINIT_TIMEOUT_SEC)',
        )
        parser.add_argument(
            '--fatal-on-error',
            action='store_true',
            help='Treat node hook errors as fatal (default: log and continue)',
        )

    def handle(self, *args, **options) -> None:
        run_id = options.get('run_id') or get_run_id()
        timeout = options.get('timeout')
        fatal_on_error = options.get('fatal_on_error', False)

        self.stdout.write(f'autoinit: starting (run_id={run_id})')

        try:
            # Phase 1: Infrastructure
            self.stdout.write('autoinit: infrastructure phase')
            run_infrastructure_init(run_id=run_id, timeout=timeout)

            # Phase 2: Node
            self.stdout.write('autoinit: node phase')
            run_node_init(
                run_id=run_id,
                timeout=timeout,
                fatal_on_error=fatal_on_error,
            )

            self.stdout.write(self.style.SUCCESS('autoinit: completed'))

        except AutoInitError as e:
            self.stderr.write(self.style.ERROR(f'autoinit: FAILED - {e}'))
            sys.exit(1)
