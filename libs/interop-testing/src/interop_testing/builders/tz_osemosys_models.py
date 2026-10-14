from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_MODEL_ID = "test-model"
_TIME_DEFINITION_ID = "model-time"


@dataclass
class TzOsemosysModelBuilder:
    regions: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    timeslices: list[str] = field(default_factory=list)
    model_fields: dict[str, object] = field(default_factory=dict)
    time_fields: dict[str, object] = field(default_factory=dict)
    commodities: dict[str, dict[str, object]] = field(default_factory=dict)
    technologies: dict[str, dict[str, object]] = field(default_factory=dict)
    storage: dict[str, dict[str, object]] = field(default_factory=dict)
    trade: dict[str, dict[str, object]] = field(default_factory=dict)

    def add_region(self, region_id: str) -> None:
        self.regions.append(region_id)

    def add_years(self, years: list[int]) -> None:
        self.years.extend(years)

    def add_timeslices(self, timeslices: list[str]) -> None:
        self.timeslices.extend(timeslices)

    def set_commodity(self, commodity_id: str, **fields: object) -> None:
        self.commodities.setdefault(commodity_id, {"id": commodity_id}).update(fields)

    def set_technology(self, technology_id: str, **fields: object) -> None:
        default: dict[str, object] = {"id": technology_id, "operating_modes": []}
        self.technologies.setdefault(technology_id, default).update(fields)

    def set_storage(self, storage_id: str, **fields: object) -> None:
        self.storage.setdefault(storage_id, {"id": storage_id}).update(fields)

    def set_trade(self, trade_id: str, commodity: str, **fields: object) -> None:
        default: dict[str, object] = {"id": trade_id, "commodity": commodity}
        self.trade.setdefault(trade_id, default).update(fields)

    def set_model_field(self, name: str, value: object) -> None:
        self.model_fields[name] = value

    def set_time_field(self, name: str, value: object) -> None:
        self.time_fields[name] = value

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._build_document(), indent=2), encoding="utf-8")

    def _build_document(self) -> dict[str, object]:
        return {
            "id": _MODEL_ID,
            "time_definition": self._build_time_definition(),
            "regions": [{"id": region_id} for region_id in self.regions],
            "commodities": list(self.commodities.values()),
            "impacts": [],
            "technologies": list(self.technologies.values()),
            "storage": list(self.storage.values()),
            "trade": list(self.trade.values()),
            **self.model_fields,
        }

    def _build_time_definition(self) -> dict[str, object]:
        return {
            "id": _TIME_DEFINITION_ID,
            "years": self.years,
            "timeslices": self.timeslices,
            **self.time_fields,
        }
