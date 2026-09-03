"""The relational plumbing under every PLEXOS fixture: ids, rows and the tables they fill.

A PLEXOS input file is a normalised relational schema: classes (``t_class``), objects
(``t_object``), the relationships between them (``t_membership``), and property values
hung off those relationships (``t_property`` / ``t_data``). Everything here mints an id
or appends a row; nothing here knows what a generator or a line is.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import NamedTuple

from interop_testing.builders.plexos_vocabulary import (
    DATA_FILE_CLASS,
    DATA_FILES_COLLECTION,
    DEFAULT_CATEGORY,
    FILENAME_PROPERTY,
    PROFILE_PROPERTY,
    READ_ORDER_ATTRIBUTE,
    SCENARIO_CLASS,
    SYSTEM_CLASS,
    SYSTEM_OBJECT,
    VARIABLE_CLASS,
    VARIABLES_COLLECTION,
)


class LineEndpoints(NamedTuple):
    """The Nodes a line runs between, under its Node From / Node To memberships."""

    node_from: str
    node_to: str


class DateBand(NamedTuple):
    """When a property value applies. An absent end runs from its start onwards."""

    date_from: date
    date_to: date | None = None


class PendingCsv(NamedTuple):
    """One CSV the model states but has not written yet.

    ``stated_path`` is the path as the model writes it, which is resolved against the
    saved XML's own directory; ``write`` puts one layout at the resolved path.
    """

    stated_path: str
    write: Callable[[Path], None]


class PlexosTables:
    """Holds every ``t_*`` row a fixture has written so far, and mints the ids they use."""

    def __init__(self) -> None:
        self._classes: dict[str, int] = {}
        self._categories: dict[str, int] = {}
        self._collections: dict[tuple[str, str, str], int] = {}
        self._objects: dict[tuple[str, str], int] = {}
        self._object_rows: list[dict[str, object]] = []
        self._memberships: dict[tuple[int, int, int], int] = {}
        self._membership_rows: list[dict[str, object]] = []
        self._properties: dict[tuple[int, str], int] = {}
        self._property_rows: list[dict[str, object]] = []
        self._property_units: dict[str, str] = {}
        self._units: dict[str, int] = {}
        self._units_setting: str | None = None
        self._data_rows: list[dict[str, object]] = []
        self._date_from_rows: list[dict[str, object]] = []
        self._date_to_rows: list[dict[str, object]] = []
        self._band_rows: list[dict[str, object]] = []
        self._tag_rows: list[dict[str, object]] = []
        self._text_rows: list[dict[str, object]] = []
        self._filename_data_ids: dict[str, int] = {}
        self._attribute_id: int | None = None
        self._attribute_data_rows: list[dict[str, object]] = []
        # One entry per registered CSV, whatever its layout: the path the model states, and
        # the call that writes that layout. ``save`` resolves each path and runs the call.
        self._pending_csv_writes: list[PendingCsv] = []
        self._attribute_ids: dict[tuple[str, str], int] = {}
        self._next_id: dict[str, int] = {}
        self._saved = False

    def _check_not_saved(self, component_desc: str) -> None:
        if self._saved:
            raise RuntimeError(f"Cannot add {component_desc}: model already saved.")

    def _next(self, sequence: str) -> int:
        value = self._next_id.get(sequence, 0) + 1
        self._next_id[sequence] = value
        return value

    def _class_id(self, class_name: str) -> int:
        if class_name not in self._classes:
            self._classes[class_name] = self._next("class")
        return self._classes[class_name]

    def _category_id(self, name: str) -> int:
        if name not in self._categories:
            self._categories[name] = self._next("category")
        return self._categories[name]

    def _collection_id(self, parent_class: str, child_class: str, name: str) -> int:
        key = (parent_class, child_class, name)
        if key not in self._collections:
            self._collections[key] = self._next("collection")
        return self._collections[key]

    def _object_id(self, class_name: str, name: str, category: str = DEFAULT_CATEGORY) -> int:
        key = (class_name, name)
        if key not in self._objects:
            object_id = self._next("object")
            self._objects[key] = object_id
            self._object_rows.append(
                {
                    "object_id": object_id,
                    "class_id": self._class_id(class_name),
                    "name": name,
                    "category_id": self._category_id(category),
                    "description": "",
                    "GUID": f"00000000-0000-0000-0000-{object_id:012d}",
                }
            )
        return self._objects[key]

    def _membership_id(
        self,
        parent_class: str,
        parent_name: str,
        child_class: str,
        child_name: str,
        collection: str,
    ) -> int:
        parent = self._object_id(parent_class, parent_name)
        child = self._object_id(child_class, child_name)
        collection_id = self._collection_id(parent_class, child_class, collection)
        key = (parent, child, collection_id)
        if key not in self._memberships:
            membership_id = self._next("membership")
            self._memberships[key] = membership_id
            self._membership_rows.append(
                {
                    "membership_id": membership_id,
                    "parent_class_id": self._class_id(parent_class),
                    "parent_object_id": parent,
                    "child_class_id": self._class_id(child_class),
                    "child_object_id": child,
                    "collection_id": collection_id,
                }
            )
        return self._memberships[key]

    def _property_id(self, collection_id: int, name: str) -> int:
        key = (collection_id, name)
        if key not in self._properties:
            property_id = self._next("property")
            self._properties[key] = property_id
            self._property_rows.append(
                {"property_id": property_id, "collection_id": collection_id, "name": name}
            )
        return self._properties[key]

    def state_property_unit(self, property_name: str, unit: str) -> None:
        """The unit the model declares a property in, wherever that property appears.

        A real export declares it per collection; one declaration is enough for a test.
        """
        self._check_not_saved(f"unit {unit!r} for property {property_name!r}")
        self._property_units[property_name] = unit

    def measure_in(self, units_setting: str) -> None:
        """Metric or Imperial, which is what the model's own energy unit stands for."""
        self._check_not_saved(f"units setting {units_setting!r}")
        self._units_setting = units_setting

    def _unit_id(self, unit: str) -> int:
        if unit not in self._units:
            self._units[unit] = self._next("unit")
        return self._units[unit]

    def _add_property(
        self,
        parent_class: str,
        parent_name: str,
        child_class: str,
        child_name: str,
        collection: str,
        property_name: str,
        value: float,
        scenarios: list[str] | None = None,
        data_file: str | None = None,
        band: int | None = None,
        variable: str | None = None,
        dates: DateBand | None = None,
    ) -> None:
        membership_id = self._membership_id(
            parent_class, parent_name, child_class, child_name, collection
        )
        collection_id = self._collection_id(parent_class, child_class, collection)
        data_id = self._next("data")
        self._data_rows.append(
            {
                "data_id": data_id,
                "membership_id": membership_id,
                "property_id": self._property_id(collection_id, property_name),
                "value": value,
            }
        )
        if dates is not None:
            self._date_rows(data_id, dates)
        if band is not None:
            self._band_rows.append({"data_id": data_id, "band_id": band})
        for scenario in scenarios or []:
            self._tag_rows.append(
                {"data_id": data_id, "object_id": self._object_id(SCENARIO_CLASS, scenario)}
            )
        if data_file is not None:
            self._tag_rows.append(
                {"data_id": data_id, "object_id": self._object_id(DATA_FILE_CLASS, data_file)}
            )
        if variable is not None:
            self._tag_rows.append(
                {"data_id": data_id, "object_id": self._object_id(VARIABLE_CLASS, variable)}
            )

    def _add_system_object(self, class_name: str, name: str, collection: str) -> None:
        self._membership_id(SYSTEM_CLASS, SYSTEM_OBJECT, class_name, name, collection)

    def _add_system_property(
        self,
        class_name: str,
        name: str,
        collection: str,
        property_name: str,
        value: float,
        scenarios: list[str] | None = None,
        data_file: str | None = None,
        band: int | None = None,
        variable: str | None = None,
        dates: DateBand | None = None,
    ) -> None:
        self._add_property(
            SYSTEM_CLASS,
            SYSTEM_OBJECT,
            class_name,
            name,
            collection,
            property_name,
            value,
            scenarios,
            data_file,
            band,
            variable,
            dates,
        )

    def _register_csv(self, path: str, write: Callable[[Path], None]) -> None:
        """Hold one CSV to write when the model is saved, whatever layout it takes."""
        self._pending_csv_writes.append(PendingCsv(path, write))

    def _add_variable_profile(self, name: str, text: str, text_class: str) -> None:
        """Add a Variable's Profile; its t_text row carries the class of what the text is,
        not the class of the Variable that owns it.
        """
        data_id = self._add_profile_row(name)
        self._text_rows.append(
            {"data_id": data_id, "class_id": self._class_id(text_class), "value": text}
        )

    def _add_profile_row(self, name: str) -> int:
        membership_id = self._membership_id(
            SYSTEM_CLASS, SYSTEM_OBJECT, VARIABLE_CLASS, name, VARIABLES_COLLECTION
        )
        collection_id = self._collection_id(SYSTEM_CLASS, VARIABLE_CLASS, VARIABLES_COLLECTION)
        data_id = self._next("data")
        self._data_rows.append(
            {
                "data_id": data_id,
                "membership_id": membership_id,
                "property_id": self._property_id(collection_id, PROFILE_PROPERTY),
                "value": 0,
            }
        )
        return data_id

    def _add_filename(self, data_file: str, path: str) -> None:
        membership_id = self._membership_id(
            SYSTEM_CLASS, SYSTEM_OBJECT, DATA_FILE_CLASS, data_file, DATA_FILES_COLLECTION
        )
        collection_id = self._collection_id(SYSTEM_CLASS, DATA_FILE_CLASS, DATA_FILES_COLLECTION)
        data_id = self._next("data")
        self._data_rows.append(
            {
                "data_id": data_id,
                "membership_id": membership_id,
                "property_id": self._property_id(collection_id, FILENAME_PROPERTY),
                "value": 0,
            }
        )
        self._text_rows.append(
            {"data_id": data_id, "class_id": self._class_id(DATA_FILE_CLASS), "value": path}
        )
        self._filename_data_ids[data_file] = data_id

    def _set_attribute(
        self, class_name: str, name: str, attribute_name: str, value: float | str
    ) -> None:
        self._attribute_data_rows.append(
            {
                "object_id": self._object_id(class_name, name),
                "attribute_id": self._attribute_id_for(class_name, attribute_name),
                "value": value,
            }
        )

    def _attribute_id_for(self, class_name: str, attribute_name: str) -> int:
        key = (class_name, attribute_name)
        if key not in self._attribute_ids:
            self._attribute_ids[key] = self._next("attribute")
        return self._attribute_ids[key]

    def _rows_by_table(self) -> dict[str, list[dict[str, object]]]:
        # Insertion order is the table order in the emitted file: classes,
        # categories, and collections before the objects and data that
        # reference them, matching a real PLEXOS export.
        properties = self._property_table_rows()
        return {
            "t_config": self._config_rows(),
            "t_class": [{"class_id": i, "name": n} for n, i in self._classes.items()],
            "t_category": self._category_rows(),
            "t_collection": self._collection_rows(),
            "t_attribute": self._attribute_rows(),
            "t_unit": [{"unit_id": i, "value": u} for u, i in self._units.items()],
            "t_object": self._object_rows,
            "t_membership": self._membership_rows,
            "t_property": properties,
            "t_data": self._data_rows,
            "t_date_from": self._date_from_rows,
            "t_date_to": self._date_to_rows,
            "t_band": self._band_rows,
            "t_tag": self._tag_rows,
            "t_text": self._text_rows,
            "t_attribute_data": self._attribute_data_rows,
        }

    def _attribute_rows(self) -> list[dict[str, object]]:
        named = [
            {
                "attribute_id": attribute_id,
                "class_id": self._class_id(class_name),
                "name": attribute_name,
            }
            for (class_name, attribute_name), attribute_id in self._attribute_ids.items()
        ]
        if self._attribute_id is None:
            return named
        return [
            *named,
            {
                "attribute_id": self._attribute_id,
                "class_id": self._class_id(SCENARIO_CLASS),
                "name": READ_ORDER_ATTRIBUTE,
            },
        ]

    def _category_rows(self) -> list[dict[str, object]]:
        return [
            {"category_id": category_id, "name": name}
            for name, category_id in self._categories.items()
        ]

    def _collection_rows(self) -> list[dict[str, object]]:
        return [
            {
                "collection_id": collection_id,
                "parent_class_id": self._class_id(parent_class),
                "child_class_id": self._class_id(child_class),
                "name": name,
            }
            for (parent_class, child_class, name), collection_id in self._collections.items()
        ]

    def _config_rows(self) -> list[dict[str, object]]:
        if self._units_setting is None:
            return []
        return [{"element": "Units", "value": self._units_setting}]

    def _date_rows(self, data_id: int, dates: DateBand) -> None:
        self._date_from_rows.append({"data_id": data_id, "date": _as_plexos_date(dates.date_from)})
        if dates.date_to is not None:
            self._date_to_rows.append({"data_id": data_id, "date": _as_plexos_date(dates.date_to)})

    def _property_table_rows(self) -> list[dict[str, object]]:
        """Each property row, given the unit it was declared in after it was first used."""
        return [{**row, **self._unit_column(str(row["name"]))} for row in self._property_rows]

    def _unit_column(self, property_name: str) -> dict[str, object]:
        unit = self._property_units.get(property_name)
        return {} if unit is None else {"unit_id": self._unit_id(unit)}


def append_row(root: ET.Element, table: str, row: dict[str, object]) -> None:
    element = ET.SubElement(root, table)
    for column, value in row.items():
        ET.SubElement(element, column).text = str(value)


def _as_plexos_date(day: date) -> str:
    """PLEXOS writes a date band's edge as an ISO-8601 timestamp at midnight."""
    return f"{day.isoformat()}T00:00:00"
