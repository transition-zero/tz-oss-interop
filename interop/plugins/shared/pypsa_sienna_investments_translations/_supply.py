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
    PORTFOLIO_ID_NOTE,
    POWER_SYSTEMS_TYPE_COL,
    PRIME_MOVER_COL,
    REGION_COL,
    TECHNICAL_LIFE_COL,
    UNIT_SIZE_COL,
    build_expansion_skips,
    build_financial_data_translation,
    capacity_limits_struct,
    finite_or_null,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    linear_value_curve,
    pypsa_source_field,
    sienna_dest_field,
    variable_cost_curve,
)
from interop.plugins.shared.sienna_constants import (
    PRIME_MOVERS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    SiennaComponent,
    SiennaCostType,
)
from interop.plugins.shared.sienna_investments_constants import (
    CAPITAL_COST_DTYPE,
    GENERIC_OPERATION_COST_DTYPE,
    SiennaCapitalCostField,
    SiennaInvestmentsComponent,
    SiennaOperationCostField,
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

SUPPLY_SKIPS: tuple[SkipRule, ...] = build_expansion_skips(
    PYPSA_COMPONENT_NAMING[PyPSATable.GENERATORS],
    name_col=PyPSAGeneratorCol.NAME,
    build_limit_col=PyPSAGeneratorCol.P_NOM_MAX,
    capacity_floor_col=PyPSAGeneratorCol.P_NOM_MIN,
    lifetime_col=PyPSAGeneratorCol.LIFETIME,
    overnight_cost_col=PyPSAGeneratorCol.OVERNIGHT_COST,
    discount_rate_col=PyPSAGeneratorCol.DISCOUNT_RATE,
)


def fill_supply_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add the expansion columns PyPSA omits when every generator shares its default.

    PyPSA defaults an overnight cost and a discount rate to NaN rather than to a number, so
    both stay null here and a generator stating neither is dropped rather than built free.
    """
    return fill_defaults(
        table,
        [
            (PyPSAGeneratorCol.P_NOM_MIN, 0.0),
            (PyPSAGeneratorCol.P_NOM_MAX, float("inf")),
            (PyPSAGeneratorCol.OVERNIGHT_COST, None),
            (PyPSAGeneratorCol.DISCOUNT_RATE, None),
            (PyPSAGeneratorCol.LIFETIME, float("inf")),
            (PyPSAGeneratorCol.FOM_COST, 0.0),
        ],
        [(PyPSAGeneratorCol.P_NOM_EXTENDABLE, False)],
    )


def capital_cost_struct(overnight_cost: pl.Expr) -> pl.Expr:
    """A Sienna ``CapitalCost`` whose curve prices one MW of new capacity linearly."""
    return pl.struct(
        linear_value_curve(overnight_cost, input_at_zero=pl.lit(None, dtype=pl.Float64)).alias(
            SiennaCapitalCostField.CAPITAL_COST
        ),
        pl.lit(0.0).alias(SiennaCapitalCostField.INTERCONNECTION_COST),
    ).cast(CAPITAL_COST_DTYPE)


def operation_cost_struct(fixed: pl.Expr, cost_type: pl.Expr) -> pl.Expr:
    """A Sienna ``GenericOperationCost`` carrying the fixed O&M of new capacity.

    A candidate's variable cost belongs to the component the build becomes in the base
    system, so the curve here is zero and only the fixed term carries a number. Only
    ``ThermalGenerationCost`` states a start-up and a shut-down cost, so the other two
    variants leave both null and the sink writes neither.
    """
    thermal_only = (
        pl.when(cost_type == SiennaCostType.THERMAL)
        .then(pl.lit(0.0))
        .otherwise(pl.lit(None, dtype=pl.Float64))
    )
    return pl.struct(
        cost_type.alias(SiennaOperationCostField.COST_TYPE),
        fixed.alias(SiennaOperationCostField.FIXED),
        thermal_only.alias(SiennaOperationCostField.START_UP),
        thermal_only.alias(SiennaOperationCostField.SHUT_DOWN),
        variable_cost_curve(pl.lit(0.0)).alias(SiennaOperationCostField.VARIABLE_OPERATION_COST),
    ).cast(GENERIC_OPERATION_COST_DTYPE)


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
    .when(pl.col(POWER_SYSTEMS_TYPE_COL) == SiennaComponent.HYDRO_DISPATCH)
    .then(pl.lit(SiennaCostType.HYDRO_GEN))
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
        "ThermalStandard, hydro for a HydroDispatch and renewable for the rest, and each "
        "carries the fixed term"
    ),
)

SUPPLY_UNIT_SIZE = _direct(
    source_col=UNIT_SIZE_COL,
    dest_col=S.UNIT_SIZE,
    expr=finite_or_null(pl.col(UNIT_SIZE_COL)),
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
    expr=finite_or_null(pl.col(TECHNICAL_LIFE_COL)).cast(pl.Int64),
    unit=UNIT_YEARS,
    derivation="the technical life, from the extensions sidecar",
    note="how long a built unit runs, which is not the period its cost is recovered over",
)

SUPPLY_TRANSLATIONS: list[Translation] = [
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


def build_supply_translations(base_year: int, start: int) -> list[Translation]:
    """Every SupplyTechnology translation, including the two the caller's numbers decide."""
    return [
        row_position_id_translation(
            _dest,
            dest_name_col=S.NAME,
            id_col=S.ID,
            note=PORTFOLIO_ID_NOTE,
            start=start,
        ),
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
