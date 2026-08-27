from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlPolicy:
    """Single source of truth for main-window control availability.

    Keeping this logic independent from Qt makes it testable and prevents
    scattered ``setEnabled`` calls from drifting out of sync with the worker.
    """

    start_enabled: bool
    stop_enabled: bool
    settings_enabled: bool
    connection_test_enabled: bool
    save_shortcut_enabled: bool


def control_policy(
    *,
    worker_active: bool,
    stop_requested: bool,
    connection_test_active: bool,
) -> ControlPolicy:
    if worker_active:
        return ControlPolicy(
            start_enabled=False,
            stop_enabled=not stop_requested,
            settings_enabled=False,
            connection_test_enabled=False,
            save_shortcut_enabled=False,
        )

    return ControlPolicy(
        start_enabled=not connection_test_active,
        stop_enabled=False,
        settings_enabled=True,
        connection_test_enabled=not connection_test_active,
        save_shortcut_enabled=True,
    )
