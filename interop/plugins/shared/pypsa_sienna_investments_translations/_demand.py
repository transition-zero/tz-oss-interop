"""Translation objects for a PyPSA Load -> Sienna DemandRequirement.

A portfolio states the demand an expansion has to meet. The load's own profile stays with
the base system, so the requirement here names the load and the region it draws in, and the
base system carries the megawatts.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.pypsa_constants import PyPSAComponent, PyPSALoadCol
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    REGION_COL,
    pypsa_source_field,
    sienna_dest_field,
)
from interop.plugins.shared.sienna_constants import SIENNA_TYPE_ATTRIBUTE, SiennaComponent
from interop.plugins.shared.sienna_investments_constants import (
    SiennaDemandRequirementCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.translation_runner import (
    Translation,
    default_translation,
    direct_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

_source = partial(pypsa_source_field, PyPSAComponent.LOAD)
_dest = partial(sienna_dest_field, SiennaInvestmentsComponent.DEMAND_REQUIREMENT)

D = SiennaDemandRequirementCol

_direct = partial(direct_translation, _source, _dest, name_col=PyPSALoadCol.NAME)
_default = partial(default_translation, _dest, name_col=PyPSALoadCol.NAME)

DEMAND_ID = row_position_id_translation(
    _dest,
    dest_name_col=D.NAME,
    id_col=D.ID,
    note="assigned by 1-based row position in the DemandRequirement DataFrame",
)

DEMAND_NAME = _direct(source_col=PyPSALoadCol.NAME, dest_col=D.NAME)

DEMAND_AVAILABLE = _default(
    dest_col=D.AVAILABLE,
    value=True,
    note="PyPSA Load has no availability field; the demand has to be met",
)

DEMAND_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[_source(old[PyPSALoadCol.NAME], PyPSALoadCol.NAME, old[PyPSALoadCol.NAME])],
            destinations=[
                _dest(
                    old[PyPSALoadCol.NAME],
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaInvestmentsComponent.DEMAND_REQUIREMENT,
                )
            ],
            derivation="each Load is one demand the expansion has to meet",
        )
    ],
)

DEMAND_POWER_SYSTEMS_TYPE = _default(
    dest_col=D.POWER_SYSTEMS_TYPE,
    value=SiennaComponent.POWER_LOAD,
    note="the base system type the demand is served as",
)

DEMAND_REGION = _direct(
    source_col=PyPSALoadCol.BUS,
    dest_col=D.REGION_NAME,
    expr=pl.col(REGION_COL),
    derivation="the area of the bus the load sits on",
)

DEMAND_TRANSLATIONS: list[Translation] = [
    DEMAND_ID,
    DEMAND_NAME,
    DEMAND_AVAILABLE,
    DEMAND_SIENNA_TYPE,
    DEMAND_POWER_SYSTEMS_TYPE,
    DEMAND_REGION,
]
