"""``SiennaSystemBuilder``: assemble a Sienna system in a test and serialise it.

The builder is plain Python, so it can be driven directly. The matching
pytest-bdd vocabulary lives in ``interop_testing.steps.sienna_system``, and the
document primitives it writes through in ``interop_testing.builders.sienna_documents``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from interop_testing.builders.sienna_documents import (
    ac_bus,
    hydro_generation_cost,
    renewable_generation_cost,
    single_time_series,
    storage_cost,
    thermal_generation_cost,
    write_sienna_system,
)


class SiennaSystemBuilder:
    """Incrementally builds a Sienna system and serialises it once.

    Generators reference their bus by integer id, so the builder tracks the
    name-to-id mapping as buses are added and resolves it when components are
    attached.
    """

    def __init__(self) -> None:
        self._areas: list[dict[str, Any]] = []
        self._buses: list[dict[str, Any]] = []
        self._generators: list[dict[str, Any]] = []
        self._storage: list[dict[str, Any]] = []
        self._loads: list[dict[str, Any]] = []
        self._arcs: list[dict[str, Any]] = []
        self._lines: list[dict[str, Any]] = []
        self._links: list[dict[str, Any]] = []
        self._time_series: list[dict[str, Any]] = []
        self._ext: dict[tuple[str, str], dict[str, Any]] = {}
        self._area_ids: dict[str, int] = {}
        self._bus_ids: dict[str, int] = {}
        self._arc_by_endpoints: dict[tuple[int, int], int] = {}
        self._next_area_id: int = 1
        self._next_bus_id: int = 1
        self._next_component_id: int = 1
        self._saved: bool = False

    def _check_not_saved(self, component_desc: str) -> None:
        if self._saved:
            raise RuntimeError(f"Cannot add {component_desc}: system already saved.")

    def _next_id(self) -> int:
        component_id = self._next_component_id
        self._next_component_id += 1
        return component_id

    def add_area(self, name: str) -> None:
        self._check_not_saved(f"area {name!r}")
        area_id = self._next_area_id
        self._next_area_id += 1
        self._area_ids[name] = area_id
        self._areas.append({"id": area_id, "name": name})

    def add_bus(self, name: str, area: str | None = None) -> None:
        self._check_not_saved(f"bus {name!r}")
        bus_id = self._next_bus_id
        self._next_bus_id += 1
        self._bus_ids[name] = bus_id
        bus = ac_bus(bus_id, name)
        if area is not None:
            bus["area"] = self._area_ids[area]
        self._buses.append(bus)

    def add_thermal_standard(
        self,
        name: str,
        bus: str,
        base_power: float,
        rating: float,
        active_power_min: float,
        active_power_max: float,
        marginal_cost: float,
        prime_mover: str,
        fuel: str,
    ) -> None:
        self._check_not_saved(f"ThermalStandard {name!r}")
        self._generators.append(
            {
                "sienna_type": "ThermalStandard",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "status": True,
                "bus": self._bus_ids[bus],
                "active_power": active_power_min,
                "reactive_power": 0.0,
                "rating": rating,
                "active_power_limits": {"min": active_power_min, "max": active_power_max},
                "operation_cost": thermal_generation_cost(marginal_cost),
                "base_power": base_power,
                "prime_mover_type": prime_mover,
                "fuel_type": fuel,
            }
        )

    def add_renewable_dispatch(
        self,
        name: str,
        bus: str,
        base_power: float,
        rating: float,
        active_power: float,
        marginal_cost: float,
        prime_mover: str,
    ) -> None:
        self._check_not_saved(f"RenewableDispatch {name!r}")
        self._generators.append(
            {
                "sienna_type": "RenewableDispatch",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "bus": self._bus_ids[bus],
                "active_power": active_power,
                "reactive_power": 0.0,
                "rating": rating,
                "prime_mover_type": prime_mover,
                "power_factor": 1.0,
                "operation_cost": renewable_generation_cost(marginal_cost),
                "base_power": base_power,
            }
        )

    def add_renewable_non_dispatch(
        self,
        name: str,
        bus: str,
        base_power: float,
        rating: float,
        active_power: float,
        prime_mover: str,
    ) -> None:
        self._check_not_saved(f"RenewableNonDispatch {name!r}")
        self._generators.append(
            {
                "sienna_type": "RenewableNonDispatch",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "bus": self._bus_ids[bus],
                "active_power": active_power,
                "reactive_power": 0.0,
                "rating": rating,
                "prime_mover_type": prime_mover,
                "power_factor": 1.0,
                "base_power": base_power,
            }
        )

    def add_hydro_dispatch(
        self,
        name: str,
        bus: str,
        base_power: float,
        rating: float,
        active_power_min: float,
        active_power_max: float,
        marginal_cost: float,
    ) -> None:
        self._check_not_saved(f"HydroDispatch {name!r}")
        self._generators.append(
            {
                "sienna_type": "HydroDispatch",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "bus": self._bus_ids[bus],
                "active_power": active_power_min,
                "reactive_power": 0.0,
                "rating": rating,
                "prime_mover_type": "HY",
                "active_power_limits": {"min": active_power_min, "max": active_power_max},
                "operation_cost": hydro_generation_cost(marginal_cost),
                "base_power": base_power,
            }
        )

    def add_energy_reservoir_storage(
        self,
        name: str,
        bus: str,
        base_power: float,
        storage_capacity: float,
        initial_level: float,
        rating: float,
        input_max: float,
        output_max: float,
        efficiency_in: float,
        efficiency_out: float,
        discharge_cost: float,
    ) -> None:
        self._check_not_saved(f"EnergyReservoirStorage {name!r}")
        self._storage.append(
            {
                "sienna_type": "EnergyReservoirStorage",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "bus": self._bus_ids[bus],
                "prime_mover_type": "PS",
                "storage_technology_type": "OTHER_MECH",
                "storage_capacity": storage_capacity,
                "storage_level_limits": {"min": 0.0, "max": 1.0},
                "initial_storage_capacity_level": initial_level,
                "rating": rating,
                "active_power": 0.0,
                "input_active_power_limits": {"min": 0.0, "max": input_max},
                "output_active_power_limits": {"min": 0.0, "max": output_max},
                "efficiency": {"in": efficiency_in, "out": efficiency_out},
                "reactive_power": 0.0,
                "base_power": base_power,
                "operation_cost": storage_cost(discharge_cost, cyclic=True),
                "conversion_factor": 1.0,
                "storage_target": initial_level * storage_capacity,
                "cycle_limits": 10000,
            }
        )

    def _generator_by_name(self, name: str) -> dict[str, Any]:
        for generator in self._generators:
            if generator["name"] == name:
                return generator
        raise KeyError(f"no generator {name!r} added yet")

    def set_thermal_ramp_limits(self, name: str, up: float, down: float) -> None:
        self._check_not_saved(f"ramp_limits for ThermalStandard {name!r}")
        self._generator_by_name(name)["ramp_limits"] = {"up": up, "down": down}

    def set_thermal_time_limits(self, name: str, up: float, down: float) -> None:
        self._check_not_saved(f"time_limits for ThermalStandard {name!r}")
        self._generator_by_name(name)["time_limits"] = {"up": up, "down": down}

    def set_thermal_time_at_status(self, name: str, hours: float) -> None:
        self._check_not_saved(f"time_at_status for ThermalStandard {name!r}")
        self._generator_by_name(name)["time_at_status"] = hours

    def set_thermal_start_stop_costs(self, name: str, start_up: float, shut_down: float) -> None:
        self._check_not_saved(f"start/shut costs for ThermalStandard {name!r}")
        operation_cost = self._generator_by_name(name)["operation_cost"]
        operation_cost["start_up"] = start_up
        operation_cost["shut_down"] = shut_down

    def add_power_load(self, name: str, bus: str, max_active_power: float) -> None:
        self._check_not_saved(f"PowerLoad {name!r}")
        self._loads.append(
            {
                "sienna_type": "PowerLoad",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "bus": self._bus_ids[bus],
                "active_power": max_active_power,
                "reactive_power": 0.0,
                "base_power": max_active_power,
                "max_active_power": max_active_power,
                "max_reactive_power": 0.0,
                "conformity": "UNDEFINED",
            }
        )

    def add_line(
        self,
        name: str,
        from_bus: str,
        to_bus: str,
        rating: float,
        r: float = 0.0,
        x: float = 0.0,
        b: float = 0.0,
        g: float = 0.0,
    ) -> None:
        self._check_not_saved(f"Line {name!r}")
        from_id = self._bus_ids[from_bus]
        to_id = self._bus_ids[to_bus]
        endpoint_key = (from_id, to_id)
        if endpoint_key not in self._arc_by_endpoints:
            arc_id = self._next_id()
            self._arcs.append(
                {
                    "sienna_type": "Arc",
                    "id": arc_id,
                    "from": from_id,
                    "to": to_id,
                }
            )
            self._arc_by_endpoints[endpoint_key] = arc_id
        arc_id = self._arc_by_endpoints[endpoint_key]
        self._lines.append(
            {
                "sienna_type": "Line",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "active_power_flow": 0.0,
                "reactive_power_flow": 0.0,
                "arc": arc_id,
                "r": r,
                "x": x,
                "b": {"from": b / 2, "to": b / 2},
                "g": {"from": g / 2, "to": g / 2},
                "rating": rating,
                "angle_limits": {"min": -1.5707963267948966, "max": 1.5707963267948966},
            }
        )

    def add_link(
        self, name: str, from_bus: str, to_bus: str, p_nom: float, efficiency: float
    ) -> None:
        self._check_not_saved(f"TwoTerminalGenericHVDCLine {name!r}")
        arc_id = self._next_id()
        self._arcs.append(
            {
                "sienna_type": "Arc",
                "id": arc_id,
                "from": self._bus_ids[from_bus],
                "to": self._bus_ids[to_bus],
            }
        )
        self._links.append(
            {
                "sienna_type": "TwoTerminalGenericHVDCLine",
                "id": self._next_id(),
                "name": name,
                "available": True,
                "active_power_flow": 0.0,
                "arc": arc_id,
                "active_power_limits_from": {"min": 0.0, "max": p_nom},
                "active_power_limits_to": {"min": 0.0, "max": p_nom * efficiency},
                "reactive_power_limits_from": {"min": 0.0, "max": 0.0},
                "reactive_power_limits_to": {"min": 0.0, "max": 0.0},
                "loss": {
                    "curve_type": "INPUT_OUTPUT",
                    "function_data": {
                        "function_type": "LINEAR",
                        "proportional_term": 1.0 - efficiency,
                        "constant_term": 0.0,
                    },
                    "input_at_zero": None,
                },
            }
        )

    def _line_by_name(self, name: str) -> dict[str, Any]:
        for line in self._lines:
            if line["name"] == name:
                return line
        raise KeyError(f"no Line {name!r} added yet")

    def _link_by_name(self, name: str) -> dict[str, Any]:
        for link in self._links:
            if link["name"] == name:
                return link
        raise KeyError(f"no TwoTerminalGenericHVDCLine {name!r} added yet")

    def set_line_available(self, name: str, available: bool) -> None:
        self._check_not_saved(f"availability for Line {name!r}")
        self._line_by_name(name)["available"] = available

    def set_line_angle_limits(self, name: str, min_rad: float, max_rad: float) -> None:
        self._check_not_saved(f"angle_limits for Line {name!r}")
        self._line_by_name(name)["angle_limits"] = {"min": min_rad, "max": max_rad}

    def set_link_available(self, name: str, available: bool) -> None:
        self._check_not_saved(f"availability for HVDC line {name!r}")
        self._link_by_name(name)["available"] = available

    def add_time_series(
        self, owner_type: str, owner_name: str, name: str, values: list[float]
    ) -> None:
        self._check_not_saved(f"time series {name!r} for {owner_name!r}")
        self._time_series.append(single_time_series(owner_type, owner_name, name, values))

    def add_ext(self, owner_type: str, owner_name: str, ext: dict[str, Any]) -> None:
        """Add (and merge) extensions.json fields for one component, keyed by owner."""
        self._check_not_saved(f"ext for {owner_name!r}")
        self._ext.setdefault((owner_type, owner_name), {}).update(ext)

    def save(self, path: Path) -> None:
        if self._saved:
            raise RuntimeError("System already saved. Cannot call save() twice.")
        sections: dict[str, list[dict[str, Any]]] = {}
        if self._areas:
            sections["areas"] = self._areas
        sections["buses"] = self._buses
        if self._generators:
            sections["generators"] = self._generators
        if self._storage:
            sections["storage"] = self._storage
        if self._loads:
            sections["loads"] = self._loads
        if self._arcs:
            sections["arcs"] = self._arcs
        if self._lines:
            sections["lines"] = self._lines
        if self._links:
            sections["links"] = self._links
        if self._time_series:
            sections["time_series"] = self._time_series
        if self._ext:
            sections["ext"] = [
                {"owner_type": owner_type, "owner_name": owner_name, "ext": ext}
                for (owner_type, owner_name), ext in self._ext.items()
            ]
        write_sienna_system(path, sections)
        self._saved = True
