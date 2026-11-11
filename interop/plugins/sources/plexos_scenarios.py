"""The Scenario overlay: which ``t_data`` rows one PLEXOS Model reads, and how they rank.

A ``t_data`` row tagged (``t_tag``) to a Scenario is an override, and the Scenario's
``Read Order`` attribute is its priority. An untagged row is the base value, and loses to
any active override. A row tagged only to Scenarios that the Model does not read is not
read at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from interop.plugins.shared.plexos_constants import PlexosClass
from interop.plugins.sources.plexos_tables import (
    CHILD_OBJECT_ID,
    CLASS_ID,
    DATA_ID,
    MEMBERSHIP_TABLE,
    NAME,
    OBJECT_ID,
    OBJECT_TABLE,
    TAG_TABLE,
    VALUE,
    RowsByTable,
    class_id_of,
    objects_of_class,
)

_ATTRIBUTE_TABLE = "t_attribute"
_ATTRIBUTE_DATA_TABLE = "t_attribute_data"
_ATTRIBUTE_ID = "attribute_id"
_PARENT_OBJECT_ID = "parent_object_id"
_CHILD_CLASS_ID = "child_class_id"
_READ_ORDER_ATTRIBUTE = "Read Order"

# A priority ranks the override above the base value first, and only then by Read Order,
# so an active Scenario that states no Read Order still wins.
_BASE_RANK = 0
_OVERRIDE_RANK = 1
_UNRANKED_READ_ORDER = 0.0
Priority = tuple[int, float]
_BASE_PRIORITY: Priority = (_BASE_RANK, _UNRANKED_READ_ORDER)


@dataclass(frozen=True)
class ScenarioOverlay:
    """The Scenario overrides one Model reads, and how they rank against each other."""

    scenario_tags: dict[str, list[str]]
    active: set[str]
    read_orders: dict[str, float]

    def find_priority(self, data_id: str) -> Priority | None:
        """A t_data row's priority: base if untagged, else its highest active Read Order.

        A row tagged only to Scenarios the model does not read is no candidate at all
        (None). A row carrying several tags counts as active when any one of them is.
        """
        tags = self.scenario_tags.get(data_id)
        if tags is None:
            return _BASE_PRIORITY
        active_tags = [tag for tag in tags if tag in self.active]
        if not active_tags:
            return None
        return (_OVERRIDE_RANK, max(self._get_read_order(tag) for tag in active_tags))

    def _get_read_order(self, scenario: str) -> float:
        return self.read_orders.get(scenario, _UNRANKED_READ_ORDER)


def build_scenario_overlay(tables: RowsByTable, model: str | None) -> ScenarioOverlay:
    """The overlay of one Model. No Model reads no Scenario, so only the base values apply."""
    return ScenarioOverlay(
        scenario_tags=_build_scenario_tags(tables),
        active=_list_active_scenarios(tables, model),
        read_orders=_build_read_orders(tables),
    )


def _list_active_scenarios(tables: RowsByTable, model: str | None) -> set[str]:
    """Scenario object ids that the selected model reads, via its Model->Scenario memberships."""
    if model is None:
        return set()
    model_class = class_id_of(tables, PlexosClass.MODEL)
    scenario_class = class_id_of(tables, PlexosClass.SCENARIO)
    model_ids = {
        row[OBJECT_ID]
        for row in tables.get(OBJECT_TABLE, [])
        if row[CLASS_ID] == model_class and row[NAME] == model
    }
    return {
        row[CHILD_OBJECT_ID]
        for row in tables.get(MEMBERSHIP_TABLE, [])
        if row[_PARENT_OBJECT_ID] in model_ids and row[_CHILD_CLASS_ID] == scenario_class
    }


def _build_read_orders(tables: RowsByTable) -> dict[str, float]:
    """Map each Scenario object id to its Read Order attribute value (higher reads later)."""
    attribute_ids = {
        row[_ATTRIBUTE_ID]
        for row in tables.get(_ATTRIBUTE_TABLE, [])
        if row[NAME] == _READ_ORDER_ATTRIBUTE
    }
    return {
        row[OBJECT_ID]: float(row[VALUE])
        for row in tables.get(_ATTRIBUTE_DATA_TABLE, [])
        if row[_ATTRIBUTE_ID] in attribute_ids
    }


def _build_scenario_tags(tables: RowsByTable) -> dict[str, list[str]]:
    """Map each tagged t_data id to the Scenarios it overrides, ignoring non-scenario tags."""
    scenario_ids = objects_of_class(tables, PlexosClass.SCENARIO)
    tags: dict[str, list[str]] = {}
    for row in tables.get(TAG_TABLE, []):
        if row[OBJECT_ID] in scenario_ids:
            tags.setdefault(row[DATA_ID], []).append(row[OBJECT_ID])
    return tags
