"""Translation objects for an extendable PyPSA Generator -> Sienna SupplyTechnology.

A generator whose capacity the network lets a plan change is a candidate, and each candidate
becomes one technology named after it. What the plan may build is the gap between
``p_nom_min`` and ``p_nom_max``; what building it costs is the overnight cost, the fixed
O&M and the discount rate and lifetime PyPSA annuitises them with.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_MW,
    UNIT_YEARS,
)
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    FUEL_COL,
    POWER_SYSTEMS_TYPE_COL,
    PRIME_MOVER_COL,
    REGION_COL,
    TECHNICAL_LIFE_COL,
    UNIT_SIZE_COL,
    build_financial_data_translation,
    capacity_limits_struct,
    capital_cost_struct,
    investments_skip_report,
    operation_cost_struct,
    pypsa_source_field,
    sienna_dest_field,
)
from interop.plugins.shared.sienna_constants import (
    PRIME_MOVERS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    SiennaComponent,
    SiennaCostType,
)
from interop.plugins.shared.sienna_investments_constants import (
    SiennaInvestmentsComponent,
    SiennaSupplyTechnologyCol,
)
from interop.plugins.shared.translation_runner import (
    SkipRule,
    Translation,
    default_translation,
    direct_translation,
    fill_defaults,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

_source = partial(pypsa_source_field, PyPSAComponent.GENERATOR)
_dest = partial(sienna_dest_field, SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY)

S = SiennaSupplyTechnologyCol

_direct = partial(direct_translation, _source, _dest, name_col=PyPSAGeneratorCol.NAME)
_default = partial(default_translation, _dest, name_col=PyPSAGeneratorCol.NAME)

_generator_skip = partial(
    investments_skip_report,
    component=PyPSAComponent.GENERATOR,
    name_col=PyPSAGeneratorCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.GENERATORS].plural,
)

UNBOUNDED_BUILD_SKIP = _generator_skip(
    reason="are extendable and put no upper bound on the capacity a build may add",
    note=(
        "p_nom_max is not a finite number of MW, so the technology has no maximum installed "
        "capacity to state"
    ),
    attribute_col=PyPSAGeneratorCol.P_NOM_MAX,
)

UNBOUNDED_LIFETIME_SKIP = _generator_skip(
    reason="are extendable and state no finite lifetime",
    note=(
        "lifetime is not a finite number of years, so the technology has no capital recovery "
        "period to annuitise its overnight cost across"
    ),
    attribute_col=PyPSAGeneratorCol.LIFETIME,
)

SUPPLY_SKIPS: tuple[SkipRule, ...] = (
    SkipRule(keep=pl.col(PyPSAGeneratorCol.P_NOM_MAX).is_finite(), report=UNBOUNDED_BUILD_SKIP),
    SkipRule(keep=pl.col(PyPSAGeneratorCol.LIFETIME).is_finite(), report=UNBOUNDED_LIFETIME_SKIP),
)


def fill_supply_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add the expansion columns PyPSA omits when every generator shares its default."""
    return fill_defaults(
        table,
        [
            (PyPSAGeneratorCol.P_NOM_MIN, 0.0),
            (PyPSAGeneratorCol.P_NOM_MAX, float("inf")),
            (PyPSAGeneratorCol.OVERNIGHT_COST, 0.0),
            (PyPSAGeneratorCol.DISCOUNT_RATE, 0.0),
            (PyPSAGeneratorCol.LIFETIME, float("inf")),
            (PyPSAGeneratorCol.FOM_COST, 0.0),
        ],
        [(PyPSAGeneratorCol.P_NOM_EXTENDABLE, False)],
    )


SUPPLY_ID = row_position_id_translation(
    _dest,
    dest_name_col=S.NAME,
    id_col=S.ID,
    note="assigned by 1-based row position in the SupplyTechnology DataFrame",
)

SUPPLY_NAME = _direct(source_col=PyPSAGeneratorCol.NAME, dest_col=S.NAME)

SUPPLY_AVAILABLE = _default(
    dest_col=S.AVAILABLE,
    value=True,
    note="PyPSA states no availability for a candidate; the technology may be built",
)

SUPPLY_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSAGeneratorCol.NAME],
                    PyPSAGeneratorCol.P_NOM_EXTENDABLE,
                    old[PyPSAGeneratorCol.P_NOM_EXTENDABLE],
                )
            ],
            destinations=[
                _dest(
                    old[PyPSAGeneratorCol.NAME],
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
                )
            ],
            derivation="an extendable Generator is a candidate, and each becomes one technology",
        )
    ],
)

SUPPLY_POWER_SYSTEMS_TYPE = _direct(
    source_col=PyPSAGeneratorCol.CARRIER,
    dest_col=S.POWER_SYSTEMS_TYPE,
    expr=pl.col(POWER_SYSTEMS_TYPE_COL),
    derivation="carrier -> the base system type a build becomes, via the user mappings file",
)

SUPPLY_REGION = _direct(
    source_col=PyPSAGeneratorCol.BUS,
    dest_col=S.REGION_NAME,
    expr=pl.col(REGION_COL),
    derivation="the area of the bus the generator sits on",
)

SUPPLY_PRIME_MOVER = _direct(
    source_col=PyPSAGeneratorCol.CARRIER,
    dest_col=S.PRIME_MOVER_TYPE,
    expr=pl.col(PRIME_MOVER_COL).cast(PRIME_MOVERS_DTYPE),
    derivation="carrier -> PrimeMovers via the user mappings file",
)

SUPPLY_FUEL = _direct(
    source_col=PyPSAGeneratorCol.CARRIER,
    dest_col=S.FUEL,
    expr=pl.when(pl.col(FUEL_COL).is_not_null())
    .then(pl.concat_list(pl.col(FUEL_COL)))
    .otherwise(pl.lit(None, dtype=pl.List(pl.Utf8))),
    derivation="carrier -> the one ThermalFuels entry the user mappings file names, or none",
)

SUPPLY_CAPITAL_COSTS = _direct(
    source_col=PyPSAGeneratorCol.OVERNIGHT_COST,
    dest_col=S.CAPITAL_COSTS,
    expr=capital_cost_struct(pl.col(PyPSAGeneratorCol.OVERNIGHT_COST)),
    unit=UNIT_DOLLARS_PER_MW,
    derivation="overnight_cost as the proportional term of a linear capital cost curve",
)

_cost_type = (
    pl.when(pl.col(POWER_SYSTEMS_TYPE_COL) == SiennaComponent.THERMAL_STANDARD)
    .then(pl.lit(SiennaCostType.THERMAL))
    .otherwise(pl.lit(SiennaCostType.RENEWABLE))
)

SUPPLY_OPERATION_COSTS = _direct(
    source_col=PyPSAGeneratorCol.FOM_COST,
    dest_col=S.OPERATION_COSTS,
    expr=operation_cost_struct(pl.col(PyPSAGeneratorCol.FOM_COST), _cost_type),
    unit=UNIT_DOLLARS_PER_MW_YEAR,
    derivation="fom_cost as the fixed term of the operation cost",
    note=(
        "the cost representation follows the base system type a build becomes: thermal for a "
        "ThermalStandard and renewable for the rest, and both carry the fixed term"
    ),
)

SUPPLY_UNIT_SIZE = _direct(
    source_col=UNIT_SIZE_COL,
    dest_col=S.UNIT_SIZE,
    expr=pl.col(UNIT_SIZE_COL),
    unit=UNIT_MW,
    derivation="the size of one unit, from the extensions sidecar",
)

SUPPLY_CAPACITY_LIMITS = Translation(
    exprs=[
        capacity_limits_struct(
            pl.col(PyPSAGeneratorCol.P_NOM_MIN), pl.col(PyPSAGeneratorCol.P_NOM_MAX)
        ).alias(S.CAPACITY_LIMITS)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSAGeneratorCol.NAME],
                    PyPSAGeneratorCol.P_NOM_MIN,
                    old[PyPSAGeneratorCol.P_NOM_MIN],
                    UNIT_MW,
                ),
                _source(
                    old[PyPSAGeneratorCol.NAME],
                    PyPSAGeneratorCol.P_NOM_MAX,
                    old[PyPSAGeneratorCol.P_NOM_MAX],
                    UNIT_MW,
                ),
            ],
            destinations=[
                _dest(
                    old[PyPSAGeneratorCol.NAME],
                    S.CAPACITY_LIMITS,
                    new[S.CAPACITY_LIMITS],
                    UNIT_MW,
                )
            ],
            derivation="p_nom_min, p_nom_max -> capacity_limits.{min, max}",
        )
    ],
)

SUPPLY_LIFETIME = _direct(
    source_col=TECHNICAL_LIFE_COL,
    dest_col=S.LIFETIME,
    expr=pl.col(TECHNICAL_LIFE_COL).cast(pl.Int64),
    unit=UNIT_YEARS,
    derivation="the technical life, from the extensions sidecar",
    note="how long a built unit runs, which is not the period its cost is recovered over",
)

SUPPLY_TRANSLATIONS: list[Translation] = [
    SUPPLY_ID,
    SUPPLY_NAME,
    SUPPLY_AVAILABLE,
    SUPPLY_SIENNA_TYPE,
    SUPPLY_POWER_SYSTEMS_TYPE,
    SUPPLY_REGION,
    SUPPLY_PRIME_MOVER,
    SUPPLY_FUEL,
    SUPPLY_CAPITAL_COSTS,
    SUPPLY_OPERATION_COSTS,
    SUPPLY_UNIT_SIZE,
    SUPPLY_CAPACITY_LIMITS,
    SUPPLY_LIFETIME,
]


def build_supply_translations(base_year: int) -> list[Translation]:
    """Every SupplyTechnology translation, including the one the base year decides."""
    return [
        *SUPPLY_TRANSLATIONS,
        build_financial_data_translation(
            _source,
            _dest,
            name_col=PyPSAGeneratorCol.NAME,
            lifetime_col=PyPSAGeneratorCol.LIFETIME,
            discount_rate_col=PyPSAGeneratorCol.DISCOUNT_RATE,
            dest_col=S.FINANCIAL_DATA,
            base_year=base_year,
        ),
    ]
