"""The name of a member of a set that is keyed by region, unique across the regions of the model."""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import REGION, REGION_NAME_SEPARATOR


def express_member_name(member_col: str) -> pl.Expr:
    """The member, after its region and a separator when two regions of the table hold it.

    The canonical stage evaluates it over every region of the model, before a scope filters any
    row, so a member keeps one name in every table that a step reads.
    """
    is_shared = pl.col(REGION).n_unique().over(member_col) > 1
    return (
        pl.when(is_shared)
        .then(pl.concat_str(REGION, pl.lit(REGION_NAME_SEPARATOR), member_col))
        .otherwise(pl.col(member_col))
    )
