"""Consumption-rate forecasting from station stock sensor readings.

Each station bin sits on a load cell, which reports how many units are left.
The rate is an exponentially weighted moving average (EWMA) of the observed
consumption, so it follows changes in production speed without jumping on one
noisy reading. A jump up in stock is a delivery (refill), not negative usage, so
it is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Track:
    t_s: float
    stock: float
    rate_per_min: float | None = None


class ConsumptionForecaster:
    def __init__(self, alpha: float = 0.3, min_dt_s: float = 5.0, refill_jump: float = 3.0):
        self.alpha = alpha            # weight of the newest sample (0..1)
        self.min_dt_s = min_dt_s      # ignore readings closer together than this
        self.refill_jump = refill_jump  # stock increase above this = a delivery
        self._tracks: dict[tuple[str, str], _Track] = {}

    def update(self, station: str, material: str, t_s: float, stock: float) -> None:
        key = (station, material)
        track = self._tracks.get(key)
        if track is None:
            self._tracks[key] = _Track(t_s, stock)
            return
        dt = t_s - track.t_s
        if stock - track.stock > self.refill_jump:
            track.t_s, track.stock = t_s, stock      # refill: restart from the new level
            return
        if dt < self.min_dt_s:
            return
        sample = max(0.0, track.stock - stock) / dt * 60.0
        if track.rate_per_min is None:
            track.rate_per_min = sample
        else:
            track.rate_per_min = self.alpha * sample + (1 - self.alpha) * track.rate_per_min
        track.t_s, track.stock = t_s, stock

    def rate_per_min(self, station: str, material: str, fallback: float) -> float:
        """Forecast rate, or `fallback` (the configured rate) until there is data."""
        track = self._tracks.get((station, material))
        if track is None or track.rate_per_min is None:
            return fallback
        return track.rate_per_min


def ewma_rate(readings: list[tuple[float, float]], alpha: float = 0.3,
              fallback: float = 0.0) -> float:
    """Rate in units/min from a list of (time_s, stock) readings."""
    f = ConsumptionForecaster(alpha=alpha)
    for t, stock in readings:
        f.update("_", "_", t, stock)
    return f.rate_per_min("_", "_", fallback)
