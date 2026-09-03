"""``CaisoStackModelBuilder``: write the pair of CSVs the CAISO stack-model source reads.

The source takes two files a user writes from CAISO's published assessment: an hourly
stack model, and a monthly capacity-by-fuel appendix. This builder writes both in the
column shape the source expects, so a test states only the few values it cares about and
every other column lands at zero.

The builder is plain Python, so it can be driven directly. The matching pytest-bdd
vocabulary lives in ``interop_testing.steps.caiso_stack_model``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import polars as pl

# Headers the source reads, spelled as the published assessment spells them.
_MONTH = "MONTH"
_DAY = "Day"
_HOUR_ENDING = "HOUR (PDT)"
_LOAD = "2025 IEPR Forecast"
_CHARGING_LOAD = "Charging Load (Y/N)"
_SURPLUS = "Surplus MW"
_FUEL_TYPE = "Fuel type"

# The eight columns the source reads as available capacity, and the two it reads as
# dispatch. Every one is written on every row, so a test names only what it asserts on.
CAPACITY_CATEGORIES = (
    "Natural Gas",
    "Nuclear",
    "Hydro",
    "Other",
    "Other Renewables",
    "Solar",
    "Wind",
    "Imports",
)
DISPATCH_CATEGORIES = ("Battery Storage", "Demand Response")

# The appendix states one column per month, under these headers.
MONTH_HEADERS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

# The stack model states each hour twice, once with battery charging folded into demand
# and once without. The source reads the with-charging scenario.
CHARGING_LOAD_YES = "Y"


class CaisoStackModelBuilder:
    """Incrementally builds the stack-model and appendix tables, and writes them once."""

    def __init__(self) -> None:
        self._hours: list[dict[str, object]] = []
        self._appendix: dict[str, dict[str, float]] = {}
        self._saved = False

    def _check_not_saved(self, what: str) -> None:
        if self._saved:
            raise RuntimeError(f"Cannot add {what}: stack model already saved.")

    def add_hour(
        self,
        *,
        month: int,
        day: int,
        hour_ending: int,
        load: float,
        surplus: float,
        charging_load: str = CHARGING_LOAD_YES,
    ) -> None:
        """Add one hour of the stack model, with every capacity and dispatch column at zero."""
        self._check_not_saved(f"hour ending {hour_ending}")
        row: dict[str, object] = {
            _MONTH: month,
            _DAY: day,
            _HOUR_ENDING: hour_ending,
            _LOAD: load,
            _CHARGING_LOAD: charging_load,
            _SURPLUS: surplus,
        }
        for category in (*CAPACITY_CATEGORIES, *DISPATCH_CATEGORIES):
            row[category] = 0.0
        self._hours.append(row)

    def set_capacity(self, category: str, value: float) -> None:
        """State one availability category on the hour added last."""
        self._set_category(CAPACITY_CATEGORIES, "capacity", category, value)

    def set_dispatch(self, category: str, value: float) -> None:
        """State one dispatch category on the hour added last."""
        self._set_category(DISPATCH_CATEGORIES, "dispatch", category, value)

    def _set_category(
        self, allowed: tuple[str, ...], kind: str, category: str, value: float
    ) -> None:
        self._check_not_saved(f"{kind} {category!r}")
        if category not in allowed:
            raise ValueError(f"{category!r} is not a stack-model {kind} category: {allowed}")
        if not self._hours:
            raise RuntimeError(f"Add an hour before stating its {kind}.")
        self._hours[-1][category] = value

    def add_appendix_fuel(self, fuel_type: str, values_by_month: Mapping[str, float]) -> None:
        """State one appendix fuel row's capacity in the named months; the rest stay at zero.

        Calling this again for the same fuel adds to the months already stated rather than
        replacing them, so a test can state one month at a time.
        """
        self._check_not_saved(f"appendix fuel {fuel_type!r}")
        unknown = sorted(set(values_by_month) - set(MONTH_HEADERS))
        if unknown:
            raise ValueError(f"Not appendix month headers: {unknown}")
        self._appendix.setdefault(fuel_type, {}).update(values_by_month)

    def save(self, stack_model_path: Path, appendix_path: Path) -> None:
        if self._saved:
            raise RuntimeError("Stack model already saved. Cannot call save() twice.")
        # Both files always carry rows in practice, and an empty one has no column types
        # for the source to read, so each is required rather than written empty.
        if not self._hours:
            raise RuntimeError("A stack model needs at least one hour before it is saved.")
        if not self._appendix:
            raise RuntimeError("An appendix needs at least one fuel row before it is saved.")
        _write_csv(pl.DataFrame(self._hours), stack_model_path)
        _write_csv(pl.DataFrame(self._appendix_rows()), appendix_path)
        self._saved = True

    def _appendix_rows(self) -> list[dict[str, object]]:
        return [
            {
                _FUEL_TYPE: fuel_type,
                **{header: float(by_month.get(header, 0.0)) for header in MONTH_HEADERS},
            }
            for fuel_type, by_month in self._appendix.items()
        ]


def _write_csv(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(path)
