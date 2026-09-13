"""YouTube Data API quota accounting.

The hard facts this class exists to respect:

* A Google Cloud project gets **10,000 units/day**. It cannot be raised by
  paying; the only remedy is an application to Google.
* The allowance resets at **midnight US/Pacific**, not midnight local time.
* Costs are per *call*, not per item: `videos.list` is 1 unit whether you ask
  for 1 video or 50, which is why resolution batches at 50.
* `playlistItems.insert` is **50 units**. A 100-track playlist write costs
  5,000 units - half a day's budget for one playlist.

Every unit is charged *before* the request goes out. Google debits on receipt,
so a crash between charging and sending leaves us over-counted (harmless) while
the reverse would leave us under-counted and liable to blow the real quota
(not harmless). Conservative is the correct direction here.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

try:  # stdlib on 3.9+, but the tz database itself can be absent on slim images
    from zoneinfo import ZoneInfo

    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover - fallback for a missing tzdata
    from datetime import timedelta

    PACIFIC = timezone(timedelta(hours=-8), name="PST")


class QuotaExceeded(RuntimeError):
    """Raised *before* a call that would breach the configured daily cap."""

    def __init__(self, method: str, units: int, spent: int, cap: int):
        self.method = method
        self.units = units
        self.spent = spent
        self.cap = cap
        super().__init__(
            f"{method} needs {units} units but only {cap - spent} of {cap} remain "
            f"today ({spent} already spent). Quota resets at midnight US/Pacific."
        )


class UnknownMethod(KeyError):
    """Raised when a method has no documented unit cost."""


class QuotaLedger:
    """Tracks API spend in SQLite and refuses calls that would overrun it."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        daily_cap: int | None = None,
        costs: dict[str, int] | None = None,
    ):
        cap = config.QUOTA_DAILY_CAP if daily_cap is None else daily_cap
        if cap <= 0:
            raise ValueError("daily_cap must be positive")
        if cap > config.QUOTA_HARD_LIMIT:
            raise ValueError(
                f"daily_cap {cap} exceeds Google's hard limit of "
                f"{config.QUOTA_HARD_LIMIT}; the ceiling cannot be purchased"
            )
        self.conn = conn
        self.daily_cap = cap
        self.costs = dict(costs or config.QUOTA_COSTS)

    # --- time ---------------------------------------------------------------
    @staticmethod
    def today() -> str:
        """Current quota day as YYYY-MM-DD in Google's reset timezone."""
        return datetime.now(PACIFIC).date().isoformat()

    # --- pricing ------------------------------------------------------------
    def cost_of(self, method: str, calls: int = 1) -> int:
        """Units a method costs, without charging anything."""
        if calls < 0:
            raise ValueError("calls must be non-negative")
        try:
            return self.costs[method] * calls
        except KeyError:
            raise UnknownMethod(
                f"no documented cost for {method!r}; add it to config.QUOTA_COSTS "
                "rather than guessing"
            ) from None

    # --- accounting ---------------------------------------------------------
    def spent(self, day: str | None = None) -> int:
        day = day or self.today()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(units), 0) FROM quota_log WHERE day = ?", (day,)
        ).fetchone()
        return int(row[0])

    def remaining(self, day: str | None = None) -> int:
        return max(0, self.daily_cap - self.spent(day))

    def can_afford(self, method: str, calls: int = 1) -> bool:
        return self.cost_of(method, calls) <= self.remaining()

    def check(self, method: str, calls: int = 1) -> int:
        """Raise QuotaExceeded if the call would breach the cap. Returns cost."""
        units = self.cost_of(method, calls)
        spent = self.spent()
        if spent + units > self.daily_cap:
            raise QuotaExceeded(method, units, spent, self.daily_cap)
        return units

    def charge(self, method: str, calls: int = 1, note: str | None = None) -> int:
        """Check, then record the spend. Call immediately before the request."""
        units = self.check(method, calls)
        self.conn.execute(
            "INSERT INTO quota_log (day, method, units, spent_at, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.today(), method, units, datetime.now(timezone.utc).isoformat(), note),
        )
        self.conn.commit()
        return units

    def refund(self, method: str, units: int, note: str = "refund") -> None:
        """Give units back when a request provably never reached Google.

        Only correct for failures raised before the socket write - a DNS or
        connection error. Never refund a 4xx/5xx: Google has already charged.
        """
        if units <= 0:
            raise ValueError("refund units must be positive")
        self.conn.execute(
            "INSERT INTO quota_log (day, method, units, spent_at, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.today(), method, -units, datetime.now(timezone.utc).isoformat(), note),
        )
        self.conn.commit()

    @contextmanager
    def spend(self, method: str, calls: int = 1, note: str | None = None):
        """Charge up front and yield. Refunds only on a pre-flight failure.

            with ledger.spend("videos.list"):
                response = request.execute()
        """
        units = self.charge(method, calls, note)
        try:
            yield units
        except (ConnectionError, TimeoutError):
            self.refund(method, units, note=f"unsent:{method}")
            raise

    # --- reporting ----------------------------------------------------------
    def budget_for(self, method: str) -> int:
        """How many more calls of this method today's remaining budget allows."""
        unit = self.cost_of(method, 1)
        return self.remaining() // unit if unit else 0

    def summary(self, day: str | None = None) -> dict:
        day = day or self.today()
        by_method = {
            r["method"]: r["units"]
            for r in self.conn.execute(
                "SELECT method, SUM(units) AS units FROM quota_log "
                "WHERE day = ? GROUP BY method ORDER BY units DESC",
                (day,),
            )
        }
        spent = self.spent(day)
        return {
            "day": day,
            "cap": self.daily_cap,
            "hard_limit": config.QUOTA_HARD_LIMIT,
            "spent": spent,
            "remaining": max(0, self.daily_cap - spent),
            "by_method": by_method,
        }

    def report(self, day: str | None = None) -> str:
        s = self.summary(day)
        lines = [
            f"quota {s['day']} (US/Pacific)",
            f"  spent     {s['spent']:>6,} / {s['cap']:,} cap "
            f"({s['hard_limit']:,} hard limit)",
            f"  remaining {s['remaining']:>6,}",
        ]
        for method, units in s["by_method"].items():
            lines.append(f"    {method:<22}{units:>6,}")
        return "\n".join(lines)
