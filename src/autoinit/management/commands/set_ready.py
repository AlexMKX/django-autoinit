"""Management command: set_ready

Purpose: Diagnostic command to manage readiness state manually.

Related:
- autoinit.orchestrator: Readiness state management
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from autoinit.orchestrator import (
    clear_ready,
    get_run_id,
    is_ready,
    set_ready,
)


class Command(BaseCommand):
    """Manage autoinit readiness state.

    Purpose: Diagnostic/debugging tool for readiness management.

    Key Behaviors:
    - Check current readiness state
    - Set or clear readiness for a run ID
    """

    help = 'Manage autoinit readiness state (check/set/clear)'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            'action',
            choices=['check', 'set', 'clear'],
            help='Action to perform on readiness state',
        )
        parser.add_argument(
            '--run-id',
            type=str,
            default=None,
            help='Deployment run ID (defaults to AUTOINIT_RUN_ID env or generated)',
        )

    def handle(self, *args, **options) -> None:
        action = options['action']
        run_id = options.get('run_id') or get_run_id()

        if action == 'check':
            ready = is_ready(run_id)
            status = 'READY' if ready else 'NOT READY'
            self.stdout.write(f'autoinit readiness (run_id={run_id}): {status}')

        elif action == 'set':
            set_ready(run_id)
            self.stdout.write(
                self.style.SUCCESS(f'autoinit readiness SET (run_id={run_id})')
            )

        elif action == 'clear':
            clear_ready(run_id)
            self.stdout.write(
                self.style.WARNING(f'autoinit readiness CLEARED (run_id={run_id})')
            )
