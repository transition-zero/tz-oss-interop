"""The Sienna name of a member of an OSeMOSYS set that is keyed by region."""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import REGION
from interop.plugins.shared.osemosys_canonical.member_names import express_member_name
from interop.plugins.shared.osemosys_sienna_constants import REGION_NAME_SEPARATOR


def express_component_name(member_col: str) -> pl.Expr:
    """The member, after its region and a separator when two regions of the table hold it.

    One member name can be in two regions, and a Sienna name must be unique in its type, so
    the table must hold every component of that type.
    """
    return express_member_name(member_col)


def express_report_name(member_col: str) -> pl.Expr:
    """The region and the member, which name the member in an event and a warning."""
    return pl.concat_str(REGION, pl.lit(REGION_NAME_SEPARATOR), member_col)
