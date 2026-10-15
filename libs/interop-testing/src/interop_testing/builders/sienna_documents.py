"""Constructors for the SiennaSchemas document a Sienna system fixture is written as.

The component objects follow the ../SiennaSchemas structure: flat objects with an integer
``id``, integer references, nested operation_cost / MinMax limits / InOut efficiency, and
no serialisation envelope. ``write_sienna_system`` serialises them as the SiennaSchemas
target — a JSON object mapping each Sienna type name to a list of its objects, with a
sibling ``TimeSeriesAssociation`` list. Time-series value arrays go in an InfraStore file,
and each association row is the row that store states; PyPSA round-trip fields go in an
``extensions.json`` companion. This is the shape the Sienna-system reader Source parses.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from infrastore import OwnerCategory, SingleTimeSeries, Store
from power_openapi_models.document import SystemDocument, write_document
from power_openapi_models.timeseries.models import TimeSeriesAssociation

from interop_testing.files import read_json

TIME_SERIES_RESOLUTION_SECONDS = 3600
TIME_SERIES_INITIAL_TIME = "2020-01-01T00:00:00"

_SYSTEM_FILENAME = "system.json"

_AREAS = "areas"
_BUSES = "buses"
_GENERATORS = "generators"
_STORAGE = "storage"
_LOADS = "loads"
_ARCS = "arcs"
_LINES = "lines"
_LINKS = "links"
_TIME_SERIES = "time_series"
_EXT = "ext"


def write_sienna_system(path: Path, sections: dict[str, list[dict[str, Any]]]) -> None:
    """Serialise builder sections as a SiennaSchemas system document.

    Components are grouped under a ``components`` sub-object mapping each Sienna type name
    to a list of flat SiennaSchemas objects (integer ``id``, integer references, no envelope).
    Time series become a top-level ``time_series_associations`` list (keyed by integer
    ``owner_id``) with value arrays in an HDF5 sidecar; extension records go in an
    ``extensions.json`` companion, keyed by kind and identified by ``name``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    components, id_by_owner = _build_container(sections)
    storage_file = sienna_h5_filename(path)
    document = SystemDocument(
        name=None,
        description=None,
        frequency=None,
        components=components,
        supplemental_attributes=[],
        supplemental_attribute_associations=[],
        plant_associations=[],
        combined_cycle_associations=[],
        service_associations=[],
        time_series_associations=[
            TimeSeriesAssociation.model_validate(row)
            for row in _build_associations(
                sections.get(_TIME_SERIES, []), id_by_owner, components, path.parent / storage_file
            )
        ],
        time_series_storage_file=storage_file,
    )

    extensions_file = sienna_extensions_filename(path)
    (path.parent / extensions_file).write_text(
        json.dumps(_build_extensions(sections.get(_EXT, [])), indent=2), encoding="utf-8"
    )

    write_document(document, path, indent=2)


# The sidecar kind each Sienna type's records land under. Kinds are neutral, so several
# Sienna types share one.
_KIND_BY_SIENNA_TYPE = {
    "ACBus": "bus",
    "ThermalStandard": "generator",
    "RenewableDispatch": "generator",
    "RenewableNonDispatch": "generator",
    "HydroDispatch": "generator",
    "PowerLoad": "load",
    "Line": "line",
    "TwoTerminalGenericHVDCLine": "controllable_line",
    "EnergyReservoirStorage": "storage",
}


def _build_extensions(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The kind-keyed sidecar document: each record is its name and the fields beside it."""
    document: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        kind = _KIND_BY_SIENNA_TYPE[record["owner_type"]]
        document.setdefault(kind, []).append({"name": record["owner_name"], **record["ext"]})
    return document


def sienna_h5_filename(system_path: Path) -> str:
    """Name of the HDF5 companion written beside the system JSON at ``system_path``."""
    return f"{system_path.stem}_time_series_storage.h5"


def sienna_extensions_filename(system_path: Path) -> str:
    """Name of the extensions.json companion written beside the system JSON."""
    return f"{system_path.stem}_extensions.json"


def write_empty_companions(system_path: Path) -> None:
    """Write a valid empty HDF5 store and an empty extensions document beside ``system_path``.

    For step files that hand-author the system JSON instead of using ``write_sienna_system``.
    """
    path = system_path.parent / sienna_h5_filename(system_path)
    Store.create(str(path), catalog="memory", overwrite=True).close()
    (system_path.parent / sienna_extensions_filename(system_path)).write_text(
        "{}", encoding="utf-8"
    )


def _build_container(
    sections: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[tuple[str, str], int]]:
    """Build the type->list components map and the (sienna_type, name) -> integer id map."""
    components: dict[str, Any] = {}
    id_by_owner: dict[tuple[str, str], int] = {}

    for area in sections.get(_AREAS, []):
        components.setdefault("Area", []).append({"id": area["id"], "name": area["name"]})

    for bus in sections.get(_BUSES, []):
        components.setdefault("ACBus", []).append(_build_bus(bus))
        id_by_owner[("ACBus", bus["name"])] = bus["id"]

    for section in (_GENERATORS, _STORAGE, _LOADS, _LINES, _LINKS):
        for source in sections.get(section, []):
            components.setdefault(source["sienna_type"], []).append(_build_injector(source))
            id_by_owner[(source["sienna_type"], source["name"])] = source["id"]

    # Arcs are topology with no name, so they are not registered as time-series/ext owners.
    for arc in sections.get(_ARCS, []):
        components.setdefault("Arc", []).append(_build_injector(arc))

    return components, id_by_owner


def _build_bus(bus: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": bus["id"],
        "name": bus["name"],
        "number": bus["id"],
        "bustype": bus["bustype"],
        "available": bus.get("available", True),
        "angle": bus.get("angle"),
        "magnitude": bus.get("magnitude"),
        "voltage_limits": bus.get("voltage_limits"),
        "base_voltage": bus["base_voltage"],
        "area": bus.get("area"),
        "load_zone": None,
    }


def _build_injector(source: dict[str, Any]) -> dict[str, Any]:
    """A generator/storage object stays flat; ``bus`` is already an integer id."""
    return {key: value for key, value in source.items() if key != "sienna_type"}


def _build_associations(
    series_list: list[dict[str, Any]],
    id_by_owner: dict[tuple[str, str], int],
    components: dict[str, Any],
    h5_path: Path,
) -> list[dict[str, Any]]:
    """Write the series to an InfraStore file and return the association rows the store states.

    The file is written even when there are no series: the Sienna source requires the
    companion file to exist beside the system JSON. A series is stated per unit and stored in
    megawatts: its values times the capacity of the component that owns it.
    """
    with Store.create(str(h5_path), catalog="memory", overwrite=True) as store:
        for series in series_list:
            store.add_time_series(
                id_by_owner[(series["owner_type"], series["owner_name"])],
                series["owner_type"],
                OwnerCategory.Component,
                SingleTimeSeries(
                    datetime.fromisoformat(series["initial_time"]),
                    f"PT{int(series['resolution_seconds'])}S",
                    np.asarray(series["values"], dtype="float64")
                    * _series_capacity(series, components),
                    series["name"],
                    units="MW",
                    quantity_kind="ActivePower",
                    unit_system="natural_units",
                ),
            )
        rows: list[dict[str, Any]] = json.loads(store.export_time_series_associations_openapi())
    return sorted(rows, key=lambda row: int(row["association_id"]))


def _series_capacity(series: dict[str, Any], components: dict[str, Any]) -> float:
    """The megawatts one per-unit value of the series stands for."""
    owner_type = series["owner_type"]
    owner = next(c for c in components[owner_type] if c["name"] == series["owner_name"])
    if owner_type == "ThermalStandard":
        return float(owner["active_power_limits"]["max"])
    if owner_type in ("RenewableDispatch", "RenewableNonDispatch"):
        return float(owner["rating"])
    if owner_type in ("PowerLoad", "InterruptiblePowerLoad"):
        return float(owner["max_active_power"])
    return float(owner["base_power"])


def ac_bus(bus_id: int, name: str) -> dict[str, Any]:
    return {
        "sienna_type": "ACBus",
        "id": bus_id,
        "name": name,
        "number": bus_id,
        "available": True,
        "base_voltage": 380.0,
        "bustype": "PV",
    }


def _linear_value_curve(proportional_term: float) -> dict[str, Any]:
    return {
        "curve_type": "INPUT_OUTPUT",
        "function_data": {
            "function_type": "LINEAR",
            "constant_term": 0.0,
            "proportional_term": proportional_term,
        },
    }


def _cost_curve(proportional_term: float) -> dict[str, Any]:
    return {
        "variable_cost_type": "COST",
        "power_units": "NATURAL_UNITS",
        "value_curve": _linear_value_curve(proportional_term),
        "vom_cost": _linear_value_curve(0.0),
    }


def thermal_generation_cost(marginal_cost: float) -> dict[str, Any]:
    return {
        "cost_type": "THERMAL",
        "fixed": 0.0,
        "start_up": 0.0,
        "shut_down": 0.0,
        "variable_operation_cost": _cost_curve(marginal_cost),
    }


def renewable_generation_cost(marginal_cost: float) -> dict[str, Any]:
    return {
        "cost_type": "RENEWABLE",
        "fixed": 0.0,
        "variable_operation_cost": _cost_curve(marginal_cost),
    }


def hydro_generation_cost(marginal_cost: float) -> dict[str, Any]:
    return {
        "cost_type": "HYDRO_GEN",
        "fixed": 0.0,
        "variable_operation_cost": _cost_curve(marginal_cost),
    }


def storage_cost(discharge_marginal_cost: float, *, cyclic: bool) -> dict[str, Any]:
    penalty = 1_000_000.0 if cyclic else 0.0
    return {
        "cost_type": "STORAGE",
        "fixed": 0.0,
        "start_up": 0.0,
        "shut_down": 0.0,
        "charge_variable_cost": _cost_curve(0.0),
        "discharge_variable_cost": _cost_curve(discharge_marginal_cost),
        "energy_shortage_cost": penalty,
        "energy_surplus_cost": penalty,
    }


def single_time_series(
    owner_type: str, owner_name: str, name: str, values: list[float]
) -> dict[str, Any]:
    return {
        "owner_type": owner_type,
        "owner_name": owner_name,
        "name": name,
        "resolution_seconds": TIME_SERIES_RESOLUTION_SECONDS,
        "initial_time": TIME_SERIES_INITIAL_TIME,
        "values": values,
    }


# ---------- Reading a written system back ----------


def sienna_components_of_type(data: dict[str, Any], sienna_type: str) -> list[Any]:
    """Every component of one Sienna type in a parsed system document."""
    return data.get("components", {}).get(sienna_type, [])  # type: ignore[no-any-return]


def find_sienna_component(data: dict[str, Any], sienna_type: str, name: str) -> dict[str, Any]:
    """The single component of `sienna_type` named `name`, failing if it is not unique."""
    components = sienna_components_of_type(data, sienna_type)
    matching = [c for c in components if isinstance(c, dict) and c.get("name") == name]
    type_names = [c.get("name") for c in components]
    assert len(matching) == 1, (
        f"expected 1 component type={sienna_type!r} name={name!r}, "
        f"got {len(matching)} (all {sienna_type!r} names: {type_names})"
    )
    return matching[0]


def read_stored_series(
    h5_path: str | Path, sienna_type: str, name: str, attribute: str
) -> list[float]:
    """The values the InfraStore file at ``h5_path`` holds for one series.

    The system JSON beside the file names the series: its row gives the owner and the series
    name, and the store finds the values by the row's ``association_id``. The file holds
    arrays only, so the rows of the document replay into a copy of it.
    """
    store_path = Path(h5_path)
    system_path = store_path.with_name(_SYSTEM_FILENAME)
    document = read_json(system_path)
    owner_id = find_sienna_component(document, sienna_type, name)["id"]
    rows = document.get("time_series_associations", [])
    matching = [
        row
        for row in rows
        if row["owner_type"] == sienna_type
        and row["owner_id"] == owner_id
        and row["name"] == attribute
    ]
    assert len(matching) == 1, (
        f"expected 1 time series {attribute!r} for {sienna_type!r} {name!r} in "
        f"{system_path}, got {len(matching)}"
    )
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / store_path.name
        shutil.copyfile(store_path, copy)
        with Store.open_without_catalog(str(copy)) as store:
            store.import_time_series_associations_openapi(json.dumps(rows))
            series = store.read_by_id(matching[0]["association_id"])
            values = [float(value) for value in series.data]
    return values


def portfolio_attributes_for(
    data: dict[str, Any], attribute_type: str, component_type: str, component_id: int
) -> list[dict[str, Any]]:
    """The supplemental attributes of one type describing one component, by id.

    The document links the two through `supplemental_attribute_associations`, so this walks
    the same route a consumer does: the association carrying the component id and the
    attribute type, then the attribute of that id in the flat array. An attribute may
    describe a component of the base system rather than of the portfolio, which is why the
    id is the argument.
    """
    attribute_ids = {
        row["attribute_id"]
        for row in data.get("supplemental_attribute_associations", [])
        if row["component_id"] == component_id
        and row["component_type"] == component_type
        and row["attribute_type"] == attribute_type
    }
    return [a for a in data.get("supplemental_attributes", []) if a["id"] in attribute_ids]
