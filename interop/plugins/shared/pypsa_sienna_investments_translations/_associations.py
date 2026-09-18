"""The rows linking each supplemental attribute to the component it describes.

The attributes travel in one flat array, so the association carries the type of the
attribute as well as its id, and the type of the component as well as its name. The sink
resolves the name to an id.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from interop.plugins.shared.sienna_investments_constants import (
    SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA,
    SiennaSupplementalAttribute,
    SiennaSupplementalAttributeAssociationCol,
)

A = SiennaSupplementalAttributeAssociationCol


def build_association_rows(
    attribute_type: SiennaSupplementalAttribute,
    attribute_ids: Sequence[int],
    component_names: Sequence[str],
    component_types: Sequence[str],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            A.COMPONENT_NAME: list(component_names),
            A.COMPONENT_TYPE: list(component_types),
            A.ATTRIBUTE_ID: list(attribute_ids),
            A.ATTRIBUTE_TYPE: [str(attribute_type)] * len(attribute_ids),
        },
        schema=SUPPLEMENTAL_ATTRIBUTE_ASSOCIATION_SCHEMA,
    )
