"""The resources a PLEXOS model dispatches: generators, storage, lines and reserves.

Each method writes one object with its memberships and property values. The relational
plumbing they call lives on ``PlexosModelBuilder``, which mixes this in; splitting them
apart keeps the topology and the resources readable on their own.
"""

from __future__ import annotations

from interop_testing.builders.plexos_generator_specs import GeneratorSpec
from interop_testing.builders.plexos_tables import DateBand, LineEndpoints, PlexosTables
from interop_testing.builders.plexos_vocabulary import (
    BATTERIES_COLLECTION,
    BATTERY_CLASS,
    CAPACITY_PROPERTY,
    CHARGE_EFFICIENCY_PROPERTY,
    CONSTRAINT_CLASS,
    CONSTRAINTS_COLLECTION,
    DEFAULT_CATEGORY,
    FUEL_CLASS,
    FUELS_COLLECTION,
    GENERATOR_CLASS,
    GENERATORS_COLLECTION,
    HEAD_STORAGE_COLLECTION,
    INITIAL_SOC_PROPERTY,
    INITIAL_VOLUME_PROPERTY,
    LINE_CLASS,
    LINE_EXPANSION_TYPE_DC,
    LINE_TYPE_PROPERTY,
    LINES_COLLECTION,
    MAX_CAPACITY_PROPERTY,
    MAX_FLOW_PROPERTY,
    MAX_POWER_PROPERTY,
    MAX_RATING_PROPERTY,
    MAX_VOLUME_PROPERTY,
    MIN_FLOW_PROPERTY,
    MIN_PROVISION_PROPERTY,
    MUTUALLY_EXCLUSIVE_NO,
    MUTUALLY_EXCLUSIVE_PROPERTY,
    MUTUALLY_EXCLUSIVE_YES,
    NODE_CLASS,
    NODE_FROM_COLLECTION,
    NODE_TO_COLLECTION,
    NODES_COLLECTION,
    OFFTAKE_AT_START_PROPERTY,
    PUMP_EFFICIENCY_PROPERTY,
    REACTANCE_PROPERTY,
    RESERVE_CLASS,
    RESERVE_TYPE_PROPERTY,
    RESERVES_COLLECTION,
    RESISTANCE_PROPERTY,
    START_FUELS_COLLECTION,
    STORAGE_CLASS,
    STORAGES_COLLECTION,
    TAIL_STORAGE_COLLECTION,
    VALUE_OF_RESERVE_SHORTAGE_PROPERTY,
)


class ResourceBuilder(PlexosTables):
    """The resource half of ``PlexosModelBuilder``; never instantiated on its own."""

    def add_generator(self, name: str, spec: GeneratorSpec) -> None:
        """Write one Generator: its memberships, its category, and its property values."""
        self._check_not_saved(f"generator {name!r}")
        self._object_id(GENERATOR_CLASS, name, category=spec.category or DEFAULT_CATEGORY)
        self._add_system_object(GENERATOR_CLASS, name, GENERATORS_COLLECTION)
        self._add_generator_memberships(name, spec)
        for property_name, value in spec.properties.items():
            self._add_generator_property(name, property_name, value)
        for property_name, data_file in spec.file_backed.items():
            self._add_generator_property(name, property_name, 0, data_file=data_file)
        for property_name, share in spec.variable_backed.items():
            self.add_generator_property(name, property_name, share.value, variable=share.variable)

    def _add_generator_memberships(self, name: str, spec: GeneratorSpec) -> None:
        if spec.node is not None:
            self._membership_id(GENERATOR_CLASS, name, NODE_CLASS, spec.node, NODES_COLLECTION)
        for fuel_name in spec.fuels:
            self._membership_id(GENERATOR_CLASS, name, FUEL_CLASS, fuel_name, FUELS_COLLECTION)

    def _add_generator_property(
        self, name: str, property_name: str, value: float, data_file: str | None = None
    ) -> None:
        self._add_system_property(
            GENERATOR_CLASS,
            name,
            GENERATORS_COLLECTION,
            property_name,
            value,
            data_file=data_file,
        )

    def add_reserve(
        self,
        name: str,
        generators: list[str],
        reserve_type: float | None = None,
        requirement: float | None = None,
        variable: str | None = None,
        data_file: str | None = None,
    ) -> None:
        """A reserve product provided by the named generators, carried to the sidecar.

        ``variable`` tags the Min Provision to a Variable, which makes the requirement that
        reserve's share of the Variable's own profile rather than a quantity in megawatts.
        ``data_file`` tags it straight to a Data File carrying its own megawatt columns.
        """
        self._check_not_saved(f"reserve {name!r}")
        self._add_system_object(RESERVE_CLASS, name, RESERVES_COLLECTION)
        for generator in generators:
            self._membership_id(
                RESERVE_CLASS, name, GENERATOR_CLASS, generator, GENERATORS_COLLECTION
            )
        if reserve_type is not None:
            self._add_system_property(
                RESERVE_CLASS, name, RESERVES_COLLECTION, RESERVE_TYPE_PROPERTY, reserve_type
            )
        if requirement is not None:
            self._add_system_property(
                RESERVE_CLASS,
                name,
                RESERVES_COLLECTION,
                MIN_PROVISION_PROPERTY,
                requirement,
                variable=variable,
                data_file=data_file,
            )

    def price_reserve_shortage(self, name: str, price: float) -> None:
        """What a megawatt of unmet requirement costs, PLEXOS's VoRS."""
        self._check_not_saved(f"shortage price of reserve {name!r}")
        self._add_system_property(
            RESERVE_CLASS, name, RESERVES_COLLECTION, VALUE_OF_RESERVE_SHORTAGE_PROPERTY, price
        )

    def mark_reserve_mutually_exclusive(self, name: str) -> None:
        """Marks the reserve as drawing on the same spare capacity as the others so marked."""
        self._set_mutually_exclusive(name, MUTUALLY_EXCLUSIVE_YES)

    def mark_reserve_not_mutually_exclusive(self, name: str) -> None:
        """Marks the reserve as drawing on headroom of its own."""
        self._set_mutually_exclusive(name, MUTUALLY_EXCLUSIVE_NO)

    def _set_mutually_exclusive(self, name: str, code: float) -> None:
        self._check_not_saved(f"exclusivity of reserve {name!r}")
        self._add_system_property(
            RESERVE_CLASS,
            name,
            RESERVES_COLLECTION,
            MUTUALLY_EXCLUSIVE_PROPERTY,
            code,
        )

    def add_constraint(
        self,
        name: str,
        generators: list[str],
        coefficient_property: str,
        coefficient: float,
    ) -> None:
        """A Constraint over a set of generators, each weighted by one coefficient.

        PLEXOS states the coefficient on the Constraint to Generator membership and the
        right-hand side on the Constraint itself, which ``add_constraint_property`` sets.
        """
        self._check_not_saved(f"constraint {name!r}")
        self._add_system_object(CONSTRAINT_CLASS, name, CONSTRAINTS_COLLECTION)
        for generator in generators:
            self._add_property(
                CONSTRAINT_CLASS,
                name,
                GENERATOR_CLASS,
                generator,
                GENERATORS_COLLECTION,
                coefficient_property,
                coefficient,
            )

    def add_constraint_property(self, name: str, property_name: str, value: float) -> None:
        """A Constraint's own property, such as its Sense or one of its right-hand sides."""
        self._check_not_saved(f"property {property_name!r} of constraint {name!r}")
        self._add_system_property(
            CONSTRAINT_CLASS, name, CONSTRAINTS_COLLECTION, property_name, value
        )

    def add_start_fuel(
        self, generator: str, fuel: str, offtake: float, band: int | None = None
    ) -> None:
        """The gigajoules a generator burns to start, on its Generator to Fuel membership."""
        self._check_not_saved(f"start fuel {fuel!r} of generator {generator!r}")
        self._add_property(
            GENERATOR_CLASS,
            generator,
            FUEL_CLASS,
            fuel,
            START_FUELS_COLLECTION,
            OFFTAKE_AT_START_PROPERTY,
            offtake,
            band=band,
        )

    def add_generator_property_band(
        self, generator: str, property_name: str, band: int, value: float
    ) -> None:
        """One band of a banded Generator property.

        PLEXOS exports the bands as repeats of one property, told apart only by band.
        """
        self._check_not_saved(f"band {band} of {property_name!r} on generator {generator!r}")
        self._add_system_property(
            GENERATOR_CLASS,
            generator,
            GENERATORS_COLLECTION,
            property_name,
            value,
            band=band,
        )

    def add_battery(
        self,
        name: str,
        node: str,
        max_power: float,
        capacity: float,
        charge_efficiency: float,
        initial_soc: float,
    ) -> None:
        self.add_bare_battery(name, node)
        self.add_battery_property(name, MAX_POWER_PROPERTY, max_power)
        self.add_battery_property(name, CAPACITY_PROPERTY, capacity)
        self.add_battery_property(name, CHARGE_EFFICIENCY_PROPERTY, charge_efficiency)
        self.add_battery_property(name, INITIAL_SOC_PROPERTY, initial_soc)

    def add_bare_battery(self, name: str, node: str | None = None) -> None:
        """A Battery with only its node, so a scenario states just the properties it needs."""
        self._check_not_saved(f"battery {name!r}")
        self._add_system_object(BATTERY_CLASS, name, BATTERIES_COLLECTION)
        if node is not None:
            self._membership_id(BATTERY_CLASS, name, NODE_CLASS, node, NODES_COLLECTION)

    def add_battery_property(
        self, name: str, property_name: str, value: float, variable: str | None = None
    ) -> None:
        self._check_not_saved(f"property {property_name!r} of battery {name!r}")
        self._add_system_property(
            BATTERY_CLASS, name, BATTERIES_COLLECTION, property_name, value, variable=variable
        )

    def add_storage_property(self, name: str, property_name: str, value: float) -> None:
        self._check_not_saved(f"property {property_name!r} of storage {name!r}")
        self._add_system_property(STORAGE_CLASS, name, STORAGES_COLLECTION, property_name, value)

    def add_pumped_storage(
        self,
        name: str,
        node: str,
        max_capacity: float,
        pump_efficiency: float,
        head: str,
        tail: str,
        max_volume: float,
        initial_volume: float,
    ) -> None:
        self._check_not_saved(f"pumped storage {name!r}")
        self._add_reservoir_generator(name, node, max_capacity, head, max_volume, initial_volume)
        self._add_storage(tail)
        self._membership_id(GENERATOR_CLASS, name, STORAGE_CLASS, tail, TAIL_STORAGE_COLLECTION)
        self.add_generator_property(name, PUMP_EFFICIENCY_PROPERTY, pump_efficiency)

    def add_generator_property(
        self, name: str, property_name: str, value: float, variable: str | None = None
    ) -> None:
        """Set any Generator property, so optional properties compose instead of growing steps."""
        self._check_not_saved(f"property {property_name!r} of generator {name!r}")
        self._add_system_property(
            GENERATOR_CLASS, name, GENERATORS_COLLECTION, property_name, value, variable=variable
        )

    def add_reservoir_hydro(
        self,
        name: str,
        node: str,
        max_capacity: float,
        head: str,
        max_volume: float,
        initial_volume: float,
    ) -> None:
        self._check_not_saved(f"reservoir hydro {name!r}")
        self._add_reservoir_generator(name, node, max_capacity, head, max_volume, initial_volume)

    def add_bare_turbine(
        self, name: str, node: str, head: str, max_capacity: float | None = None
    ) -> None:
        """A turbine and its head Storage, with no volumes stated on the reservoir."""
        self._check_not_saved(f"turbine {name!r}")
        self._add_turbine(name, node, max_capacity)
        self._add_storage(head)
        self._membership_id(GENERATOR_CLASS, name, STORAGE_CLASS, head, HEAD_STORAGE_COLLECTION)

    def add_bare_pumped_storage(
        self, name: str, node: str, max_capacity: float, head: str, tail: str
    ) -> None:
        """A turbine with both reservoirs and no Pump Efficiency, so membership alone classifies."""
        self.add_bare_turbine(name, node, head, max_capacity)
        self._add_storage(tail)
        self._membership_id(GENERATOR_CLASS, name, STORAGE_CLASS, tail, TAIL_STORAGE_COLLECTION)

    def add_tail_only_turbine(self, name: str, node: str, max_capacity: float, tail: str) -> None:
        """A turbine with a Tail Storage and no head, so it has no reservoir to draw from."""
        self._check_not_saved(f"turbine {name!r}")
        self._add_turbine(name, node, max_capacity)
        self._add_storage(tail)
        self._membership_id(GENERATOR_CLASS, name, STORAGE_CLASS, tail, TAIL_STORAGE_COLLECTION)

    def add_orphan_storage(
        self, name: str, max_volume: float | None = None, initial_volume: float | None = None
    ) -> None:
        """A Storage object linked to no turbine, so it maps to nothing and is skipped."""
        self._check_not_saved(f"orphan storage {name!r}")
        self._add_storage(name, max_volume, initial_volume)

    def add_transport_line(
        self, name: str, endpoints: LineEndpoints, max_flow: float, min_flow: float = 0.0
    ) -> None:
        """A line with flow limits and no impedance, which maps to a PyPSA Link."""
        self._add_line_topology(name, endpoints)
        self._add_line_property(name, MAX_FLOW_PROPERTY, max_flow)
        self._add_line_property(name, MIN_FLOW_PROPERTY, min_flow)

    def add_electrical_line(
        self,
        name: str,
        endpoints: LineEndpoints,
        resistance: float,
        reactance: float,
        max_rating: float,
    ) -> None:
        """A line carrying impedance, which maps to a PyPSA Line."""
        self._add_line_topology(name, endpoints)
        self._add_line_property(name, RESISTANCE_PROPERTY, resistance)
        self._add_line_property(name, REACTANCE_PROPERTY, reactance)
        self._add_line_property(name, MAX_RATING_PROPERTY, max_rating)

    def add_dc_expansion_line(self, name: str, endpoints: LineEndpoints, max_flow: float) -> None:
        """A transport line whose LT Plan expansion type is DC."""
        self.add_transport_line(name, endpoints, max_flow=max_flow)
        self._add_line_property(name, LINE_TYPE_PROPERTY, LINE_EXPANSION_TYPE_DC)

    def add_banded_transport_line(
        self,
        name: str,
        endpoints: LineEndpoints,
        max_flow_bands: list[float],
        min_flow_bands: list[float],
    ) -> None:
        """A transport line whose Max Flow and Min Flow each carry several banded values."""
        self._add_line_topology(name, endpoints)
        for band, value in enumerate(max_flow_bands, start=1):
            self._add_line_property(name, MAX_FLOW_PROPERTY, value, band=band)
        for band, value in enumerate(min_flow_bands, start=1):
            self._add_line_property(name, MIN_FLOW_PROPERTY, value, band=band)

    def add_endpointless_line(self, name: str, node_from: str) -> None:
        """A line with only a Node From membership, as a filtered export can leave behind."""
        self._check_not_saved(f"line {name!r}")
        self._add_system_object(LINE_CLASS, name, LINES_COLLECTION)
        self._membership_id(LINE_CLASS, name, NODE_CLASS, node_from, NODE_FROM_COLLECTION)

    def add_unrated_line(self, name: str, endpoints: LineEndpoints) -> None:
        """A line connecting two nodes with neither a flow limit nor an impedance."""
        self._add_line_topology(name, endpoints)

    def add_reverse_only_line(self, name: str, endpoints: LineEndpoints, min_flow: float) -> None:
        """A line carrying a Min Flow and no Max Flow to scale it against."""
        self._add_line_topology(name, endpoints)
        self._add_line_property(name, MIN_FLOW_PROPERTY, min_flow)

    def add_line_property(self, name: str, property_name: str, value: float) -> None:
        """Any other Line property, named as PLEXOS spells it."""
        self._check_not_saved(f"property {property_name!r} on line {name!r}")
        self._add_line_property(name, property_name, value)

    def add_storage_property_from_data_file(
        self, name: str, property_name: str, data_file: str
    ) -> None:
        self._check_not_saved(f"property {property_name!r} of storage {name!r}")
        self._add_system_property(
            STORAGE_CLASS,
            name,
            STORAGES_COLLECTION,
            property_name,
            0,
            data_file=data_file,
        )

    def date_generator_property(
        self, name: str, property_name: str, value: float, dates: DateBand
    ) -> None:
        """State a Generator property for one span of dates rather than for all of time."""
        self._check_not_saved(f"dated property {property_name!r} of generator {name!r}")
        self._add_system_property(
            GENERATOR_CLASS, name, GENERATORS_COLLECTION, property_name, value, dates=dates
        )

    def _add_line_property(
        self, name: str, property_name: str, value: float, band: int | None = None
    ) -> None:
        self._add_system_property(
            LINE_CLASS, name, LINES_COLLECTION, property_name, value, band=band
        )

    def _add_line_topology(self, name: str, endpoints: LineEndpoints) -> None:
        self._check_not_saved(f"line {name!r}")
        self._add_system_object(LINE_CLASS, name, LINES_COLLECTION)
        self._membership_id(LINE_CLASS, name, NODE_CLASS, endpoints.node_from, NODE_FROM_COLLECTION)
        self._membership_id(LINE_CLASS, name, NODE_CLASS, endpoints.node_to, NODE_TO_COLLECTION)

    def _add_reservoir_generator(
        self,
        name: str,
        node: str,
        max_capacity: float,
        head: str,
        max_volume: float,
        initial_volume: float,
    ) -> None:
        self.add_bare_turbine(name, node, head, max_capacity)
        self.add_storage_property(head, MAX_VOLUME_PROPERTY, max_volume)
        self.add_storage_property(head, INITIAL_VOLUME_PROPERTY, initial_volume)

    def _add_storage(
        self, name: str, max_volume: float | None = None, initial_volume: float | None = None
    ) -> None:
        self._add_system_object(STORAGE_CLASS, name, STORAGES_COLLECTION)
        if max_volume is not None:
            self._add_system_property(
                STORAGE_CLASS, name, STORAGES_COLLECTION, MAX_VOLUME_PROPERTY, max_volume
            )
        if initial_volume is not None:
            self._add_system_property(
                STORAGE_CLASS, name, STORAGES_COLLECTION, INITIAL_VOLUME_PROPERTY, initial_volume
            )

    def _add_turbine(self, name: str, node: str, max_capacity: float | None) -> None:
        self._add_system_object(GENERATOR_CLASS, name, GENERATORS_COLLECTION)
        self._membership_id(GENERATOR_CLASS, name, NODE_CLASS, node, NODES_COLLECTION)
        if max_capacity is not None:
            self.add_generator_property(name, MAX_CAPACITY_PROPERTY, max_capacity)
