"""Translation objects for an extendable PyPSA StorageUnit -> Sienna StorageTechnology.

A Sienna storage technology adds charge power, discharge power and energy independently, so
each has its own capital cost, unit size and capacity limits. A PyPSA StorageUnit states one
power rating and an energy stated as hours of it, so the discharge side carries the rating
and the cost, and the energy side carries the rating multiplied by the hours.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_HOURS,
    UNIT_MW,
    UNIT_MWH,
    UNIT_YEARS,
)
from interop.plugins.shared.pypsa_constants import (
    PYPSA_COMPONENT_NAMING,
    PyPSAComponent,
    PyPSAStorageUnitCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    PORTFOLIO_ID_NOTE,
    POWER_SYSTEMS_TYPE_COL,
    PRIME_MOVER_COL,
    REGION_COL,
    TECHNICAL_LIFE_COL,
    UNIT_SIZE_COL,
    build_expansion_skips,
    build_financial_data_translation,
    capacity_limits_struct,
    investments_skip_report,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    ZERO_IO_CURVE,
    linear_value_curve,
    pypsa_source_field,
    sienna_dest_field,
)
from interop.plugins.shared.sienna_constants import (
    PRIME_MOVERS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    SiennaCostType,
    SiennaStorageTech,
    SiennaStructField,
)
from interop.plugins.shared.sienna_investments_constants import (
    IN_OUT_DTYPE,
    STORAGE_CAPITAL_COST_DTYPE,
    STORAGE_OPERATION_COST_DTYPE,
    SiennaInvestmentsComponent,
    SiennaOperationCostField,
    SiennaStorageCapitalCostField,
    SiennaStorageTechnologyCol,
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

_source = partial(pypsa_source_field, PyPSAComponent.STORAGE_UNIT)
_dest = partial(sienna_dest_field, SiennaInvestmentsComponent.STORAGE_TECHNOLOGY)

S = SiennaStorageTechnologyCol

_direct = partial(direct_translation, _source, _dest, name_col=PyPSAStorageUnitCol.NAME)
_default = partial(default_translation, _dest, name_col=PyPSAStorageUnitCol.NAME)

NO_ENERGY_SKIP = investments_skip_report(
    component=PyPSAComponent.STORAGE_UNIT,
    name_col=PyPSAStorageUnitCol.NAME,
    counted_noun=PYPSA_COMPONENT_NAMING[PyPSATable.STORAGE_UNITS].plural,
    reason="are extendable and hold no energy",
    note=lambda row: (
        f"max_hours is {row[PyPSAStorageUnitCol.MAX_HOURS]}, so the energy capacity limits a "
        "build could add are zero MWh"
    ),
    attribute_col=PyPSAStorageUnitCol.MAX_HOURS,
)

STORAGE_SKIPS: tuple[SkipRule, ...] = (
    *build_expansion_skips(
        PYPSA_COMPONENT_NAMING[PyPSATable.STORAGE_UNITS],
        name_col=PyPSAStorageUnitCol.NAME,
        build_limit_col=PyPSAStorageUnitCol.P_NOM_MAX,
        lifetime_col=PyPSAStorageUnitCol.LIFETIME,
        overnight_cost_col=PyPSAStorageUnitCol.OVERNIGHT_COST,
        discount_rate_col=PyPSAStorageUnitCol.DISCOUNT_RATE,
    ),
    SkipRule(keep=pl.col(PyPSAStorageUnitCol.MAX_HOURS) > 0, report=NO_ENERGY_SKIP),
)


def fill_storage_technology_defaults(table: pl.DataFrame) -> pl.DataFrame:
    """Add the expansion columns PyPSA omits when every storage unit shares its default.

    PyPSA gives ``max_hours`` a default of one hour of the power rating, and defaults an
    overnight cost and a discount rate to NaN rather than to a number, so both of the latter
    stay null here and a unit stating neither is dropped rather than built free.
    """
    return fill_defaults(
        table,
        [
            (PyPSAStorageUnitCol.P_NOM_MIN, 0.0),
            (PyPSAStorageUnitCol.P_NOM_MAX, float("inf")),
            (PyPSAStorageUnitCol.MAX_HOURS, 1.0),
            (PyPSAStorageUnitCol.EFFICIENCY_STORE, 1.0),
            (PyPSAStorageUnitCol.EFFICIENCY_DISPATCH, 1.0),
            (PyPSAStorageUnitCol.OVERNIGHT_COST, None),
            (PyPSAStorageUnitCol.DISCOUNT_RATE, None),
            (PyPSAStorageUnitCol.LIFETIME, float("inf")),
            (PyPSAStorageUnitCol.FOM_COST, 0.0),
        ],
        [(PyPSAStorageUnitCol.P_NOM_EXTENDABLE, False)],
    )


def storage_capital_cost_struct(overnight_cost: pl.Expr) -> pl.Expr:
    """A Sienna ``StorageCapitalCost`` pricing the discharge side alone.

    PyPSA prices a storage unit by its power rating and holds its energy as hours of that
    rating, so the one overnight cost it states belongs to the discharge capacity. Charging
    and energy are added at no cost of their own.
    """
    return pl.struct(
        ZERO_IO_CURVE.alias(SiennaStorageCapitalCostField.CHARGE_CAPITAL_COST),
        linear_value_curve(overnight_cost, input_at_zero=pl.lit(None, dtype=pl.Float64)).alias(
            SiennaStorageCapitalCostField.DISCHARGE_CAPITAL_COST
        ),
        ZERO_IO_CURVE.alias(SiennaStorageCapitalCostField.ENERGY_CAPITAL_COST),
        pl.lit(0.0).alias(SiennaStorageCapitalCostField.INTERCONNECTION_COST),
    ).cast(STORAGE_CAPITAL_COST_DTYPE)


STORAGE_NAME = _direct(source_col=PyPSAStorageUnitCol.NAME, dest_col=S.NAME)

STORAGE_AVAILABLE = _default(
    dest_col=S.AVAILABLE,
    value=True,
    note="PyPSA states no availability for a candidate; the technology may be built",
)

STORAGE_SIENNA_TYPE = Translation(
    exprs=[],
    make_events=lambda old, _: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSAStorageUnitCol.NAME],
                    PyPSAStorageUnitCol.P_NOM_EXTENDABLE,
                    old[PyPSAStorageUnitCol.P_NOM_EXTENDABLE],
                )
            ],
            destinations=[
                _dest(
                    old[PyPSAStorageUnitCol.NAME],
                    SIENNA_TYPE_ATTRIBUTE,
                    SiennaInvestmentsComponent.STORAGE_TECHNOLOGY,
                )
            ],
            derivation="an extendable StorageUnit is a candidate, and each becomes one technology",
        )
    ],
)

STORAGE_POWER_SYSTEMS_TYPE = _direct(
    source_col=PyPSAStorageUnitCol.CARRIER,
    dest_col=S.POWER_SYSTEMS_TYPE,
    expr=pl.col(POWER_SYSTEMS_TYPE_COL),
    derivation="carrier -> the base system type a build becomes, via the user mappings file",
)

STORAGE_REGION = _direct(
    source_col=PyPSAStorageUnitCol.BUS,
    dest_col=S.REGION_NAME,
    expr=pl.col(REGION_COL),
    derivation="the area of the bus the storage unit sits on",
)

STORAGE_PRIME_MOVER = _direct(
    source_col=PyPSAStorageUnitCol.CARRIER,
    dest_col=S.PRIME_MOVER_TYPE,
    expr=pl.col(PRIME_MOVER_COL).cast(PRIME_MOVERS_DTYPE),
    derivation="carrier -> PrimeMovers via the user mappings file",
)

STORAGE_TECH = _default(
    dest_col=S.STORAGE_TECH,
    value=SiennaStorageTech.OTHER_MECH,
    note="PyPSA names no storage chemistry, and StorageTech has no value for an unstated one",
)

STORAGE_CAPITAL_COSTS = _direct(
    source_col=PyPSAStorageUnitCol.OVERNIGHT_COST,
    dest_col=S.CAPITAL_COSTS,
    expr=storage_capital_cost_struct(pl.col(PyPSAStorageUnitCol.OVERNIGHT_COST)),
    unit=UNIT_DOLLARS_PER_MW,
    derivation="overnight_cost as the discharge capital cost; charge and energy cost nothing",
)

STORAGE_OPERATION_COSTS = _direct(
    source_col=PyPSAStorageUnitCol.FOM_COST,
    dest_col=S.OPERATION_COSTS,
    expr=pl.struct(
        pl.lit(SiennaCostType.STORAGE).alias(SiennaOperationCostField.COST_TYPE),
        pl.col(PyPSAStorageUnitCol.FOM_COST).alias(SiennaOperationCostField.FIXED),
        pl.lit(0.0).alias(SiennaOperationCostField.START_UP),
        pl.lit(0.0).alias(SiennaOperationCostField.SHUT_DOWN),
    ).cast(STORAGE_OPERATION_COST_DTYPE),
    unit=UNIT_DOLLARS_PER_MW_YEAR,
    derivation="fom_cost as the fixed term of the storage operation cost",
)

STORAGE_UNIT_SIZE_DISCHARGE = _direct(
    source_col=UNIT_SIZE_COL,
    dest_col=S.UNIT_SIZE_DISCHARGE,
    expr=pl.col(UNIT_SIZE_COL),
    unit=UNIT_MW,
    derivation="the size of one unit, from the extensions sidecar",
)

STORAGE_CAPACITY_LIMITS_DISCHARGE = Translation(
    exprs=[
        capacity_limits_struct(
            pl.col(PyPSAStorageUnitCol.P_NOM_MIN), pl.col(PyPSAStorageUnitCol.P_NOM_MAX)
        ).alias(S.CAPACITY_LIMITS_DISCHARGE)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSAStorageUnitCol.NAME],
                    PyPSAStorageUnitCol.P_NOM_MIN,
                    old[PyPSAStorageUnitCol.P_NOM_MIN],
                    UNIT_MW,
                ),
                _source(
                    old[PyPSAStorageUnitCol.NAME],
                    PyPSAStorageUnitCol.P_NOM_MAX,
                    old[PyPSAStorageUnitCol.P_NOM_MAX],
                    UNIT_MW,
                ),
            ],
            destinations=[
                _dest(
                    old[PyPSAStorageUnitCol.NAME],
                    S.CAPACITY_LIMITS_DISCHARGE,
                    new[S.CAPACITY_LIMITS_DISCHARGE],
                    UNIT_MW,
                )
            ],
            derivation="p_nom_min, p_nom_max -> capacity_limits_discharge.{min, max}",
        )
    ],
)

STORAGE_CAPACITY_LIMITS_ENERGY = Translation(
    exprs=[
        capacity_limits_struct(
            pl.col(PyPSAStorageUnitCol.P_NOM_MIN) * pl.col(PyPSAStorageUnitCol.MAX_HOURS),
            pl.col(PyPSAStorageUnitCol.P_NOM_MAX) * pl.col(PyPSAStorageUnitCol.MAX_HOURS),
        ).alias(S.CAPACITY_LIMITS_ENERGY)
    ],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                _source(
                    old[PyPSAStorageUnitCol.NAME],
                    PyPSAStorageUnitCol.MAX_HOURS,
                    old[PyPSAStorageUnitCol.MAX_HOURS],
                    UNIT_HOURS,
                ),
                _source(
                    old[PyPSAStorageUnitCol.NAME],
                    PyPSAStorageUnitCol.P_NOM_MAX,
                    old[PyPSAStorageUnitCol.P_NOM_MAX],
                    UNIT_MW,
                ),
            ],
            destinations=[
                _dest(
                    old[PyPSAStorageUnitCol.NAME],
                    S.CAPACITY_LIMITS_ENERGY,
                    new[S.CAPACITY_LIMITS_ENERGY],
                    UNIT_MWH,
                )
            ],
            derivation="max_hours x the power capacity limits -> capacity_limits_energy",
        )
    ],
)

STORAGE_EFFICIENCY = _direct(
    source_col=PyPSAStorageUnitCol.EFFICIENCY_STORE,
    dest_col=S.EFFICIENCY,
    expr=pl.struct(
        pl.col(PyPSAStorageUnitCol.EFFICIENCY_STORE).alias(SiennaStructField.IN),
        pl.col(PyPSAStorageUnitCol.EFFICIENCY_DISPATCH).alias(SiennaStructField.OUT),
    ).cast(IN_OUT_DTYPE),
    derivation="(in=efficiency_store, out=efficiency_dispatch)",
)

STORAGE_LIFETIME = _direct(
    source_col=TECHNICAL_LIFE_COL,
    dest_col=S.LIFETIME,
    expr=pl.col(TECHNICAL_LIFE_COL).cast(pl.Int64),
    unit=UNIT_YEARS,
    derivation="the technical life, from the extensions sidecar",
    note="how long a built unit runs, which is not the period its cost is recovered over",
)

STORAGE_TECHNOLOGY_TRANSLATIONS: list[Translation] = [
    STORAGE_NAME,
    STORAGE_AVAILABLE,
    STORAGE_SIENNA_TYPE,
    STORAGE_POWER_SYSTEMS_TYPE,
    STORAGE_REGION,
    STORAGE_PRIME_MOVER,
    STORAGE_TECH,
    STORAGE_CAPITAL_COSTS,
    STORAGE_OPERATION_COSTS,
    STORAGE_UNIT_SIZE_DISCHARGE,
    STORAGE_CAPACITY_LIMITS_DISCHARGE,
    STORAGE_CAPACITY_LIMITS_ENERGY,
    STORAGE_EFFICIENCY,
    STORAGE_LIFETIME,
]


def build_storage_technology_translations(base_year: int, start: int) -> list[Translation]:
    """Every StorageTechnology translation, including the two the caller's numbers decide."""
    return [
        row_position_id_translation(
            _dest, dest_name_col=S.NAME, id_col=S.ID, note=PORTFOLIO_ID_NOTE, start=start
        ),
        *STORAGE_TECHNOLOGY_TRANSLATIONS,
        build_financial_data_translation(
            _source,
            _dest,
            name_col=PyPSAStorageUnitCol.NAME,
            lifetime_col=PyPSAStorageUnitCol.LIFETIME,
            discount_rate_col=PyPSAStorageUnitCol.DISCOUNT_RATE,
            dest_col=S.FINANCIAL_DATA,
            base_year=base_year,
        ),
    ]
