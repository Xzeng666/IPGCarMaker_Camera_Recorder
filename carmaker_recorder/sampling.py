from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class PeriodicSimTimeSampler:
    """Robust periodic selector driven by simulation time.

    A frame is selected when it reaches/crosses the next due time. The next due
    instant is advanced arithmetically, avoiding float-to-int truncation errors.
    Simulation-time rollback resets the schedule explicitly.
    """

    hz: float
    epsilon_sec: float = 1e-6

    def __post_init__(self) -> None:
        if self.hz <= 0:
            raise ValueError("sampler hz must be > 0")
        self.period = 1.0 / float(self.hz)
        self.next_due: float | None = None
        self.last_time: float | None = None
        self.selected = 0
        self.resets = 0

    def reset(self, sim_time: float | None = None) -> None:
        self.next_due = sim_time
        self.last_time = sim_time
        self.resets += 1

    def should_sample(self, sim_time: float) -> bool:
        t = float(sim_time)
        if not math.isfinite(t):
            return False

        if self.next_due is None:
            self.next_due = t + self.period
            self.last_time = t
            self.selected += 1
            return True

        if self.last_time is not None and t + self.epsilon_sec < self.last_time:
            # A new CarMaker run may reset simulation time to zero while the
            # Recorder process stays alive. Treat it as a new sampling epoch.
            self.next_due = t + self.period
            self.last_time = t
            self.selected += 1
            self.resets += 1
            return True

        self.last_time = t
        if t + self.epsilon_sec < self.next_due:
            return False

        # Advance by all elapsed periods in one operation. This avoids loops for
        # large time jumps while preserving the periodic schedule.
        steps = max(1, int(math.floor((t - self.next_due + self.epsilon_sec) / self.period)) + 1)
        self.next_due += steps * self.period
        self.selected += 1
        return True
