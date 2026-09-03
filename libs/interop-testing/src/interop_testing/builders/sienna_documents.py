"""Constructors for the SiennaSchemas document a Sienna system fixture is written as.

The component objects follow the ../SiennaSchemas structure: flat objects with an integer
``id``, integer references, nested operation_cost / MinMax limits / InOut efficiency, and
no serialisation envelope. ``write_sienna_system`` serialises them as the SiennaSchemas
target — a JSON object mapping each Sienna type name to a list of its objects, with a
sibling ``TimeSeriesAssociation`` list. Time-series value arrays go in an HDF5 sidecar
keyed by ``time_series_uuid``; PyPSA round-trip fields go in an ``extensions.json``
companion. This is the shape the Sienna-system reader Source parses.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import numpy as np

TIME_SERIES_RESOLUTION_SECONDS = 3600
TIME_SERIES_INITIAL_TIME = "2020-01-01T00:00:00"

_TIME_SERIES_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_OID, "transitionzero.interop")

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
    document: dict[str, Any] = {"components": components}

    storage_file = sienna_h5_filename(path)
    document["time_series_associations"] = _build_associations(
        sections.get(_TIME_SERIES, []), id_by_owner, path.parent / storage_file
    )
    document["time_series_storage_filename"] = storage_file

    extensions_file = sienna_extensions_filename(path)
    document["extensions_filename"] = extensions_file
    (path.parent / extensions_file).write_text(
        json.dumps(_build_extensions(sections.get(_EXT, [])), indent=2), encoding="utf-8"
    )

    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


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
    import h5py

    with h5py.File(system_path.parent / sienna_h5_filename(system_path), "w") as h5:
        h5.create_group("time_series")
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
    h5_path: Path,
) -> list[dict[str, Any]]:
    """Write value arrays to the HDF5 sidecar and return the TimeSeriesAssociation records.

    The sidecar is written even when there are no series: the Sienna source requires the
    companion file to exist beside the system JSON.
    """
    import h5py

    associations: list[dict[str, Any]] = []
    with h5py.File(h5_path, "w") as h5:
        root = h5.create_group("time_series")
        for index, series in enumerate(series_list, start=1):
            time_series_uuid = str(uuid.uuid4())
            root.create_group(time_series_uuid).create_dataset(
                "data", data=np.asarray(series["values"], dtype="float64")
            )
            associations.append(
                {
                    "id": index,
                    "owner_type": series["owner_type"],
                    "owner_id": id_by_owner[(series["owner_type"], series["owner_name"])],
                    "name": series["name"],
                    "time_series_uuid": time_series_uuid,
                    "time_series_type": "SingleTimeSeries",
                    "initial_timestamp": series["initial_time"],
                    "resolution": f"P0DT{float(series['resolution_seconds']):.3f}S",
                    "length": len(series["values"]),
                    "scaling_factor_multiplier": series.get("scaling_factor_multiplier"),
                }
            )
    return associations


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
        "variable": _cost_curve(marginal_cost),
    }


def renewable_generation_cost(marginal_cost: float) -> dict[str, Any]:
    return {"cost_type": "RENEWABLE", "fixed": 0.0, "variable": _cost_curve(marginal_cost)}


def hydro_generation_cost(marginal_cost: float) -> dict[str, Any]:
    return {"cost_type": "HYDRO_GEN", "fixed": 0.0, "variable": _cost_curve(marginal_cost)}


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


def sienna_time_series_uuid(sienna_type: str, name: str, attribute: str) -> str:
    """Key a time series is stored under in the HDF5 companion.

    Deliberately a mirror of `sienna_constants.time_series_uuid` rather than a call
    to it: an assertion that derived the expected key from the code that wrote it
    would pass however the scheme changed. Keep the two in sync by hand.
    """
    return str(uuid.uuid5(_TIME_SERIES_UUID_NAMESPACE, f"ts.{sienna_type}.{name}.{attribute}"))
