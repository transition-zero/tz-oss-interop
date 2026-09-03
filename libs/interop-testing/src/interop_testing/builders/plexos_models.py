"""``PlexosModelBuilder``: assemble a PLEXOS model in a test and serialise it.

A PLEXOS input file is a normalised relational schema serialised as XML. The builder
hides that behind a domain API (regions, nodes, loads, generators, models, scenarios)
and serialises the whole ``<MasterDataSet>`` once, mirroring ``SiennaSystemBuilder``.

It reads across four sibling modules: ``plexos_tables`` mints the ids and holds the
``t_*`` rows, ``plexos_resources`` writes the resources a model dispatches,
``plexos_csv_files`` writes each Data File layout, and ``plexos_vocabulary`` holds the
PLEXOS names all of them spell.

The builder is plain Python, so it can be driven directly. The matching pytest-bdd
vocabulary lives in ``interop_testing.steps.plexos_model`` and ``.plexos_resources``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from interop_testing.builders.plexos_csv_files import (
    normalise_path,
    write_csv,
    write_csv_by_object,
    write_csv_by_period_column,
    write_csv_with_text_column,
    write_daily_csv,
    write_monthly_csv,
)
from interop_testing.builders.plexos_resources import ResourceBuilder
from interop_testing.builders.plexos_tables import DateBand, append_row
from interop_testing.builders.plexos_vocabulary import (
    CHRONO_DATE_FROM_ATTRIBUTE,
    CHRONO_STEP_COUNT_ATTRIBUTE,
    CHRONO_STEP_TYPE_ATTRIBUTE,
    CHRONO_STEP_TYPE_DAY,
    DATA_FILE_CLASS,
    DATA_FILES_COLLECTION,
    EMISSION_CLASS,
    EMISSIONS_COLLECTION,
    FUEL_CLASS,
    FUELS_COLLECTION,
    HORIZON_CLASS,
    HORIZONS_COLLECTION,
    IS_SLACK_BUS_PROPERTY,
    LOAD_PROPERTY,
    MARKET_CLASS,
    MARKETS_COLLECTION,
    MODEL_CLASS,
    MODELS_COLLECTION,
    NODE_CLASS,
    NODES_COLLECTION,
    OLE_EPOCH,
    PERIODS_PER_DAY_ATTRIBUTE,
    PLEXOS_FALSE,
    PLEXOS_TRUE,
    PRICE_PROPERTY,
    PRODUCTION_RATE_PROPERTY,
    REGION_CLASS,
    REGION_COLLECTION,
    REGIONS_COLLECTION,
    SCENARIO_CLASS,
    SCENARIOS_COLLECTION,
    TIMESLICE_CLASS,
    VARIABLE_CLASS,
    VARIABLES_COLLECTION,
    VOLL_PROPERTY,
    VOLTAGE_PROPERTY,
)

PLEXOS_NAMESPACE = "http://tempuri.org/MasterDataSet.xsd"


class PlexosModelBuilder(ResourceBuilder):
    """Incrementally builds a PLEXOS model and serialises it to XML once."""

    # --- relational plumbing -------------------------------------------------

    # --- domain API ----------------------------------------------------------

    def add_region(self, name: str) -> None:
        self._check_not_saved(f"region {name!r}")
        self._add_system_object(REGION_CLASS, name, REGIONS_COLLECTION)

    def add_node(self, name: str, region: str | None = None, voltage: float | None = None) -> None:
        self._check_not_saved(f"node {name!r}")
        self._add_system_object(NODE_CLASS, name, NODES_COLLECTION)
        if region is not None:
            self._membership_id(NODE_CLASS, name, REGION_CLASS, region, REGION_COLLECTION)
        if voltage is not None:
            self._add_node_property(name, VOLTAGE_PROPERTY, voltage)

    def add_slack_node(self, name: str, region: str | None = None, voltage: float = 0.0) -> None:
        self.add_node(name, region=region, voltage=voltage or None)
        self._add_node_property(name, IS_SLACK_BUS_PROPERTY, PLEXOS_TRUE)

    def add_non_slack_node(
        self, name: str, region: str | None = None, voltage: float = 0.0
    ) -> None:
        """A node whose Is Slack Bus is present and false, which PLEXOS writes as 0."""
        self.add_node(name, region=region, voltage=voltage or None)
        self._add_node_property(name, IS_SLACK_BUS_PROPERTY, PLEXOS_FALSE)

    def _add_node_property(self, node: str, property_name: str, value: float) -> None:
        self._add_system_property(NODE_CLASS, node, NODES_COLLECTION, property_name, value)

    def add_load(
        self,
        node: str,
        peak: float,
        scenarios: list[str] | None = None,
        data_file: str | None = None,
    ) -> None:
        """A Load property on a Node, which the source stages like any other property."""
        self._check_not_saved(f"load on node {node!r}")
        self._add_system_property(
            NODE_CLASS, node, NODES_COLLECTION, LOAD_PROPERTY, peak, scenarios, data_file
        )

    def add_region_load(
        self,
        region: str,
        peak: float,
        scenarios: list[str] | None = None,
        data_file: str | None = None,
    ) -> None:
        """A Load property on a Region, which the PyPSA mapping turns into a Load."""
        self._check_not_saved(f"load on region {region!r}")
        self._add_system_property(
            REGION_CLASS, region, REGIONS_COLLECTION, LOAD_PROPERTY, peak, scenarios, data_file
        )

    def add_region_property(self, region: str, property_name: str, value: float) -> None:
        """Any other Region property, named as PLEXOS spells it."""
        self._check_not_saved(f"property {property_name!r} on region {region!r}")
        self._add_system_property(REGION_CLASS, region, REGIONS_COLLECTION, property_name, value)

    def add_data_file(self, name: str, path: str, hourly_values: list[float]) -> None:
        """Register a Data File object with its Filename, and its CSV to write on save."""
        self._check_not_saved(f"data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)
        self._register_csv(path, lambda target: write_csv(target, [hourly_values]))

    def add_missing_data_file(self, name: str, path: str) -> None:
        """Register a Data File and its Filename without writing the CSV, as a package that
        ships its traces separately does.
        """
        self._check_not_saved(f"missing data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)

    def omit_object_row(self, class_name: str, name: str) -> None:
        """Drop an object's ``t_object`` row, leaving every row that references it in place.

        A filtered or hand-edited export can carry references to objects it no longer holds.
        """
        self._check_not_saved(f"omission of {class_name} {name!r}")
        object_id = self._objects[(class_name, name)]
        self._object_rows = [row for row in self._object_rows if row["object_id"] != object_id]

    def omit_data_file_text(self, name: str) -> None:
        """Drop a Data File's ``t_text`` row, leaving its Filename ``t_data`` row in place."""
        self._check_not_saved(f"omission of the filename text of data file {name!r}")
        data_id = self._filename_data_ids[name]
        self._text_rows = [row for row in self._text_rows if row["data_id"] != data_id]

    def add_fuel(self, name: str, price: float) -> None:
        self._check_not_saved(f"fuel {name!r}")
        self._add_system_property(FUEL_CLASS, name, FUELS_COLLECTION, PRICE_PROPERTY, price)

    def add_emission(self, name: str, price: float, fuel: str, production_rate: float) -> None:
        self._check_not_saved(f"emission {name!r}")
        self._add_system_property(EMISSION_CLASS, name, EMISSIONS_COLLECTION, PRICE_PROPERTY, price)
        self._add_property(
            EMISSION_CLASS,
            name,
            FUEL_CLASS,
            fuel,
            FUELS_COLLECTION,
            PRODUCTION_RATE_PROPERTY,
            production_rate,
        )

    def date_fuel_price(self, name: str, price: float, dates: DateBand) -> None:
        """Price a Fuel for one span of dates, as a model with a seasonal price does."""
        self._check_not_saved(f"dated price of fuel {name!r}")
        self._add_system_property(
            FUEL_CLASS, name, FUELS_COLLECTION, PRICE_PROPERTY, price, dates=dates
        )

    def _add_variable_profile_on_data_file(self, name: str, data_file: str) -> None:
        data_id = self._add_profile_row(name)
        self._tag_rows.append(
            {"data_id": data_id, "object_id": self._object_id(DATA_FILE_CLASS, data_file)}
        )

    def add_data_file_by_object(
        self, name: str, path: str, values_by_object: dict[str, list[float]]
    ) -> None:
        """Register a Data File whose CSV carries a Month/Day/Period trace with one column
        per object, naming no shared Value column and no Name column (the layout PLEXOS
        exports for a file several objects each read their own column of, e.g. MaxCap
        Other.csv).
        """
        self._check_not_saved(f"data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)
        self._register_csv(path, lambda target: write_csv_by_object(target, values_by_object))

    def add_data_file_with_text_column(
        self,
        name: str,
        path: str,
        hourly_values: list[float],
        text_column: str,
        text_values: list[str],
    ) -> None:
        """Register a Data File whose CSV carries a lone Value column plus an unrelated
        text column, the shape PLEXOS exports for a note or comment nobody reads as data.
        """
        self._check_not_saved(f"data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)
        self._register_csv(
            path,
            lambda target: write_csv_with_text_column(
                target, hourly_values, text_column, text_values
            ),
        )

    def add_horizon(
        self, model: str, name: str, start: date, step_count: int, periods_per_day: int
    ) -> None:
        """Attach a chronological Horizon to a Model: a day-stepped span of ``step_count``
        days from ``start``, at ``periods_per_day`` steps within each day.
        """
        self._check_not_saved(f"horizon {name!r}")
        self._add_system_object(HORIZON_CLASS, name, HORIZONS_COLLECTION)
        self._membership_id(MODEL_CLASS, model, HORIZON_CLASS, name, HORIZONS_COLLECTION)
        self._set_attribute(
            HORIZON_CLASS, name, CHRONO_DATE_FROM_ATTRIBUTE, (start - OLE_EPOCH).days
        )
        self._set_attribute(HORIZON_CLASS, name, CHRONO_STEP_COUNT_ATTRIBUTE, step_count)
        self._set_attribute(HORIZON_CLASS, name, CHRONO_STEP_TYPE_ATTRIBUTE, CHRONO_STEP_TYPE_DAY)
        self._set_attribute(HORIZON_CLASS, name, PERIODS_PER_DAY_ATTRIBUTE, periods_per_day)

    def set_horizon_attribute(self, name: str, attribute: str, value: str) -> None:
        """Overwrite one Chrono attribute of an existing Horizon with the text given.

        Takes the value as text so a model can state something no reader can turn into a
        number, which is what a real export sometimes carries.
        """
        self._check_not_saved(f"horizon {name!r}")
        self._set_attribute(HORIZON_CLASS, name, attribute, value)

    def add_market(self, name: str, node: str) -> None:
        """A Market trading at a node, which makes that node a boundary rather than a bus."""
        self._check_not_saved(f"market {name!r}")
        self._add_system_object(MARKET_CLASS, name, MARKETS_COLLECTION)
        self._membership_id(NODE_CLASS, node, MARKET_CLASS, name, MARKETS_COLLECTION)

    def add_monthly_data_file(
        self, name: str, path: str, component: str, monthly_values: list[float]
    ) -> None:
        """Register a Data File whose CSV lists one row per object, keyed by Name, with
        twelve calendar-month columns (``M01``..``M12``) rather than a Year/Period trace.
        """
        self._check_not_saved(f"data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)
        self._register_csv(
            path, lambda target: write_monthly_csv(target, component, monthly_values)
        )

    def add_region_voll(self, region: str, voll: float) -> None:
        self._check_not_saved(f"VoLL on region {region!r}")
        self._add_system_property(REGION_CLASS, region, REGIONS_COLLECTION, VOLL_PROPERTY, voll)

    def add_period_column_data_file(
        self, name: str, path: str, periods_per_day: int, values: list[float]
    ) -> None:
        """Register a Data File whose CSV puts each intra-day period in its own column,
        heading them ``01``..``NN`` with one row per day rather than one row per period.
        """
        self._check_not_saved(f"data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)
        self._register_csv(
            path, lambda target: write_csv_by_period_column(target, periods_per_day, values)
        )

    def add_daily_data_file(
        self, name: str, path: str, value_column: str, daily_values: list[float]
    ) -> None:
        """Register a Data File whose CSV holds one row per day and names its own value column."""
        self._check_not_saved(f"data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)
        self._register_csv(path, lambda target: write_daily_csv(target, value_column, daily_values))

    def add_sampled_data_file(self, name: str, path: str, samples: list[list[float]]) -> None:
        """Register a Data File whose CSV carries one numbered column per replication."""
        self._check_not_saved(f"data file {name!r}")
        self._add_system_object(DATA_FILE_CLASS, name, DATA_FILES_COLLECTION)
        self._add_filename(name, path)
        self._register_csv(path, lambda target: write_csv(target, samples))

    def add_variable(self, name: str, path: str, hourly_values: list[float]) -> None:
        """Register a Variable whose Profile names a CSV, the shared trace a share scales."""
        self._check_not_saved(f"variable {name!r}")
        self._add_system_object(VARIABLE_CLASS, name, VARIABLES_COLLECTION)
        self._add_variable_profile(name, path, DATA_FILE_CLASS)
        self._register_csv(path, lambda target: write_csv(target, [hourly_values]))

    def add_variable_on_data_file(self, name: str, data_file: str) -> None:
        """Register a Variable whose Profile is tagged to a Data File already registered.

        A share of this Variable resolves to the same CSV path as any other reader of that
        Data File, which ``add_variable`` cannot give you: it writes a trace of its own.
        """
        self._check_not_saved(f"variable {name!r}")
        self._add_system_object(VARIABLE_CLASS, name, VARIABLES_COLLECTION)
        self._add_variable_profile_on_data_file(name, data_file)

    def add_timeslice_variable(self, name: str, pattern: str) -> None:
        """Register a Variable whose Profile is a timeslice pattern, which names no file."""
        self._check_not_saved(f"variable {name!r}")
        self._add_system_object(VARIABLE_CLASS, name, VARIABLES_COLLECTION)
        self._add_variable_profile(name, pattern, TIMESLICE_CLASS)

    def add_model(self, name: str, scenarios: list[str] | None = None) -> None:
        self._check_not_saved(f"model {name!r}")
        self._add_system_object(MODEL_CLASS, name, MODELS_COLLECTION)
        for scenario in scenarios or []:
            self._membership_id(MODEL_CLASS, name, SCENARIO_CLASS, scenario, SCENARIOS_COLLECTION)

    def add_scenario(self, name: str, read_order: int | None = None) -> None:
        self._check_not_saved(f"scenario {name!r}")
        self._add_system_object(SCENARIO_CLASS, name, SCENARIOS_COLLECTION)
        if read_order is not None:
            self._set_read_order(name, read_order)

    def _set_read_order(self, scenario: str, read_order: int) -> None:
        self._attribute_data_rows.append(
            {
                "object_id": self._object_id(SCENARIO_CLASS, scenario),
                "attribute_id": self._read_order_attribute_id(),
                "value": read_order,
            }
        )

    def _read_order_attribute_id(self) -> int:
        if self._attribute_id is None:
            self._attribute_id = self._next("attribute")
        return self._attribute_id

    # --- serialisation -------------------------------------------------------

    def save(self, path: Path) -> None:
        if self._saved:
            raise RuntimeError("Model already saved.")
        root = ET.Element("MasterDataSet", {"xmlns": PLEXOS_NAMESPACE})
        for table, rows in self._rows_by_table().items():
            for row in rows:
                append_row(root, table, row)
        path.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        for pending in self._pending_csv_writes:
            pending.write(path.parent / normalise_path(pending.stated_path))
        self._saved = True
