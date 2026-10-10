"""Decision-local, cooperative CPU pacing without changing simulated time."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
import time


@dataclass(frozen=True)
class PacingConfig:
    """Milliseconds of pause after a budget of sampling CPU work."""

    pause_ms: float = 5.0
    work_ms: float = 50.0

    def __post_init__(self) -> None:
        for name in ("pause_ms", "work_ms"):
            value = getattr(self, name)
            try:
                valid = (
                    not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and isfinite(value)
                    and value > 0
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must be finite and positive")


def validate_pacing(config: PacingConfig | None) -> None:
    if config is not None and not isinstance(config, PacingConfig):
        raise ValueError("pacing must be a PacingConfig or None")


class CpuPacer:
    """Track CPU work only while a rollout is executing on this thread."""

    def __init__(
        self,
        config: PacingConfig,
        *,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._clock = time.thread_time if clock is None else clock
        self._sleep = time.sleep if sleeper is None else sleeper
        self._pause = config.pause_ms / 1000
        self._budget = config.work_ms / 1000
        self._worked = 0.0
        self._last_cpu: float | None = None

    @contextmanager
    def sampling(self) -> Iterator[None]:
        self._last_cpu = self._clock()
        try:
            yield
        finally:
            self._account()
            self._last_cpu = None

    def _account(self) -> None:
        if self._last_cpu is not None:
            now = self._clock()
            self._worked += now - self._last_cpu
            self._last_cpu = now

    def checkpoint(self) -> None:
        self._account()
        if self._last_cpu is not None and self._worked >= self._budget:
            self._sleep(self._pause)
            self._worked = 0.0
            self._last_cpu = self._clock()
