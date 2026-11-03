"""Consumption-rate forecasting from station stock sensor readings.

Each station bin sits on a load cell, which reports how many whole units are
left, every few seconds. Readings that close together mostly show no change, then
a sudden drop of one unit, so the rate is the least-squares slope of the readings
over a sliding window (2 minutes by default) rather than reading-to-reading
differences. Two special cases:
  - a jump up in stock is a delivery: the window restarts from the new level;
  - an empty bin (stock 0) is not "zero demand", the line is just stopped: the
    last known rate is kept, so the station still gets a delivery.
Until there is enough data, the configured rate is used.
"""

from __future__ import annotations

from collections import deque


class ConsumptionForecaster:
    def __init__(self, window_s: float = 120.0, min_span_s: float = 20.0, refill_jump: float = 3.0):
        self.window_s = window_s        # how much history the slope uses
        self.min_span_s = min_span_s    # need at least this much history for an estimate
        self.refill_jump = refill_jump  # stock increase above this = a delivery
        self._readings: dict[tuple[str, str], deque] = {}
        self._last_rate: dict[tuple[str, str], float] = {}

    def update(self, station: str, material: str, t_s: float, stock: float) -> None:
        key = (station, material)
        d = self._readings.setdefault(key, deque())
        if d and stock - d[-1][1] > self.refill_jump:
            d.clear()
        d.append((t_s, stock))
        while d and d[0][0] < t_s - self.window_s:
            d.popleft()
        rate = self._slope_rate(d)
        if rate is not None:
            self._last_rate[key] = rate

    def _slope_rate(self, d: deque) -> float | None:
        pts = [(t, s) for t, s in d if s > 0]  # an empty bin says nothing about demand
        if len(pts) < 2 or pts[-1][0] - pts[0][0] < self.min_span_s:
            return None
        n = len(pts)
        mt = sum(t for t, _ in pts) / n
        ms = sum(s for _, s in pts) / n
        var = sum((t - mt) ** 2 for t, _ in pts)
        slope = sum((t - mt) * (s - ms) for t, s in pts) / var
        return max(0.0, -slope * 60.0)

    def rate_per_min(self, station: str, material: str, fallback: float) -> float:
        """Forecast rate, or `fallback` (the configured rate) until there is enough data."""
        return self._last_rate.get((station, material), fallback)


def estimate_rate(readings: list[tuple[float, float]], fallback: float = 0.0, **kwargs) -> float:
    """Rate in units/min from a list of (time_s, stock) readings."""
    f = ConsumptionForecaster(**kwargs)
    for t, stock in readings:
        f.update("_", "_", t, stock)
    return f.rate_per_min("_", "_", fallback)
