"""The name of a member of an OSeMOSYS set that is keyed by region, in an event or a warning."""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import REGION
from interop.plugins.shared.osemosys_sienna_constants import REGION_NAME_SEPARATOR


def express_report_name(member_col: str) -> pl.Expr:
    """The region and the member, which name the member in an event and a warning."""
    return pl.concat_str(REGION, pl.lit(REGION_NAME_SEPARATOR), member_col)
