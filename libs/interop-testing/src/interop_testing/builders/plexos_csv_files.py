"""Writing one PLEXOS Data File CSV, in whichever layout a fixture asks for.

A published PLEXOS package writes its traces in several shapes, and a fixture has to be
able to produce each one so the source's reshaper is read against the real thing.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

# Every written CSV dates its rows to this year; only Month/Day/Period within it vary.
_CSV_YEAR_DEFAULT = 2026

# A monthly-by-name Data File's calendar-month column headers.
_MONTH_COLUMNS = tuple(f"M{month:02d}" for month in range(1, 13))


def normalise_path(text_path: str) -> Path:
    """PLEXOS stores Windows-style paths; write the CSV at the POSIX equivalent."""
    return Path(text_path.replace("\\", "/"))


def write_csv(csv_path: Path, samples: list[list[float]]) -> None:
    """Write one Value column for a single sample, or one numbered column per replication."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["Value"] if len(samples) == 1 else [str(i + 1) for i in range(len(samples))]
    lines = [",".join(["Year", "Month", "Day", "Period", *headers])]
    for hour, values in enumerate(zip(*samples, strict=True)):
        lines.append(
            ",".join([str(_CSV_YEAR_DEFAULT), "1", "1", str(hour + 1), *(str(v) for v in values)])
        )
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv_by_object(csv_path: Path, values_by_object: dict[str, list[float]]) -> None:
    """Write a Month/Day/Period trace with one column per object, headed by the object names."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    objects = list(values_by_object.keys())
    lines = [",".join(["Year", "Month", "Day", "Period", *objects])]
    rows = zip(*values_by_object.values(), strict=True)
    for period, values in enumerate(rows, start=1):
        lines.append(
            ",".join([str(_CSV_YEAR_DEFAULT), "1", "1", str(period), *(str(v) for v in values)])
        )
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv_with_text_column(
    csv_path: Path, hourly_values: list[float], text_column: str, text_values: list[str]
) -> None:
    """Write a Value column plus an unrelated text column PLEXOS carries alongside it."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(["Year", "Month", "Day", "Period", "Value", text_column])]
    for period, (value, text) in enumerate(zip(hourly_values, text_values, strict=True), start=1):
        lines.append(f"{_CSV_YEAR_DEFAULT},1,1,{period},{value},{text}")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv_by_period_column(csv_path: Path, periods_per_day: int, values: list[float]) -> None:
    """Write one row per day with each intra-day period in its own zero-padded column."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [f"{period:02d}" for period in range(1, periods_per_day + 1)]
    lines = [",".join(["Year", "Month", "Day", *headers])]
    for day, start in enumerate(range(0, len(values), periods_per_day)):
        row = values[start : start + periods_per_day]
        lines.append(",".join([_date_columns(day), *(_format_number(v) for v in row)]))
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_number(value: float) -> str:
    """Write a whole number without a decimal point, as a real export does.

    A reader that infers column types from a bounded window then sees an integer column
    that only turns fractional later, which is the case worth reproducing here.
    """
    return str(int(value)) if value.is_integer() else str(value)


def write_daily_csv(csv_path: Path, value_column: str, daily_values: list[float]) -> None:
    """Write one row per day, the value in a column the file names itself."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(["Year", "Month", "Day", value_column])]
    for day, value in enumerate(daily_values):
        lines.append(f"{_date_columns(day)},{value}")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _date_columns(days_in: int) -> str:
    """Year,Month,Day for the nth day of the fixture year, rolling into later months."""
    stamp = date(_CSV_YEAR_DEFAULT, 1, 1) + timedelta(days=days_in)
    return f"{stamp.year},{stamp.month},{stamp.day}"


def write_monthly_csv(csv_path: Path, component: str, monthly_values: list[float]) -> None:
    """Write a single Name-keyed row of twelve calendar-month columns."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(["Name", *_MONTH_COLUMNS])]
    lines.append(",".join([component, *(str(v) for v in monthly_values)]))
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
