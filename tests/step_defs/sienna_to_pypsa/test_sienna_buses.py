from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interop_testing.builders.sienna_documents import write_empty_companions
from pytest_bdd import given, parsers, scenarios

scenarios("../features/sienna_to_pypsa/buses.feature")


def _write_sienna_system(path: Path, *, buses: list[dict[str, Any]]) -> None:
    """Author a SiennaSchemas system file.

    Each bus dict may carry: name, base_voltage, bustype, area (name or None). An Area
    object is emitted per distinct area name and the ACBus references it by integer id.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    components: dict[str, Any] = {}

    area_id: dict[str, int] = {}
    for area_index, area_name in enumerate(
        sorted({b["area"] for b in buses if b.get("area")}), start=1
    ):
        area_id[area_name] = area_index
        components.setdefault("Area", []).append({"id": area_index, "name": area_name})

    for bus_index, b in enumerate(buses, start=1):
        components.setdefault("ACBus", []).append(
            {
                "id": bus_index,
                "name": b["name"],
                "number": bus_index,
                "bustype": b["bustype"],
                "available": True,
                "base_voltage": float(b["base_voltage"]),
                "area": area_id[b["area"]] if b.get("area") else None,
                "load_zone": None,
            }
        )

    path.write_text(json.dumps({"components": components}), encoding="utf-8")
    write_empty_companions(path)


@given(
    parsers.parse(
        'a Sienna system file "{system_path}" with ACBus "{name}" '
        'base_voltage {base_voltage:g} bustype "{bustype}" in area "{area}"'
    )
)
def given_acbus_with_area(
    system_path: str, name: str, base_voltage: float, bustype: str, area: str
) -> None:
    _write_sienna_system(
        Path(system_path),
        buses=[{"name": name, "base_voltage": base_voltage, "bustype": bustype, "area": area}],
    )


@given(
    parsers.parse(
        'a Sienna system file "{system_path}" with ACBus "{name}" '
        'base_voltage {base_voltage:g} bustype "{bustype}" and no area'
    )
)
def given_acbus_no_area(system_path: str, name: str, base_voltage: float, bustype: str) -> None:
    _write_sienna_system(
        Path(system_path),
        buses=[{"name": name, "base_voltage": base_voltage, "bustype": bustype, "area": None}],
    )
