from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter


@dataclass
class WallClockMetric:
    seconds: float = 0.0


@contextmanager
def measure_wall_clock() -> WallClockMetric:
    metric = WallClockMetric()
    start = perf_counter()
    try:
        yield metric
    finally:
        metric.seconds = round(perf_counter() - start, 6)
