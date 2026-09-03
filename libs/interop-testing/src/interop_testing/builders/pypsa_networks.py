"""``PyPSANetworkBuilder``: assemble a PyPSA network in a test and serialise it.

The builder is plain Python, so it can be driven directly. The matching
pytest-bdd Given vocabulary lives in ``interop_testing.steps.pypsa_network``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import pypsa
import xarray as xr

# Maps a component word used in scenarios to its netCDF class prefix (the `{prefix}_i`
# index coordinate), for forging within-class duplicate names that PyPSA's API refuses.
_COMPONENT_TO_NETCDF_CLASS: dict[str, str] = {
    "bus": "buses",
    "generator": "generators",
    "load": "loads",
    "line": "lines",
    "link": "links",
    "storage unit": "storage_units",
    "store": "stores",
    "transformer": "transformers",
    "shunt impedance": "shunt_impedances",
}


# The netCDF attribute PyPSA writes its own version into, which a scenario may override to
# stand for a file some other version wrote.
_PYPSA_VERSION_ATTR = "network_pypsa_version"


class PyPSANetworkBuilder:
    """Incrementally builds a pypsa.Network and serialises it once."""

    def __init__(self) -> None:
        self._network: pypsa.Network = pypsa.Network()
        self._saved: bool = False
        self._snapshots_set: bool = False
        self._forced_duplicates: list[tuple[str, str]] = []
        self._pypsa_version: str | None = None

    def _check_not_saved(self, component_desc: str) -> None:
        if self._saved:
            raise RuntimeError(f"Cannot add {component_desc}: network already saved.")

    def set_snapshots(self, periods: int, interval_minutes: int, start: str = "2020-01-01") -> None:
        self._check_not_saved("snapshots")
        snapshots = pd.date_range(
            start, periods=periods, freq=pd.Timedelta(minutes=interval_minutes)
        )
        self._network.set_snapshots(list(snapshots))
        self._snapshots_set = True

    def add_bus(
        self,
        name: str,
        carrier: str,
        v_nom: float,
        location: str | None = None,
        control: str | None = None,
        v_mag_pu_set: float | None = None,
        v_mag_pu_min: float | None = None,
        v_mag_pu_max: float | None = None,
    ) -> None:
        self._check_not_saved(f"bus {name!r}")
        extra: dict[str, Any] = {}
        if location is not None:
            extra["location"] = location
        if control is not None:
            extra["control"] = control
        if v_mag_pu_set is not None:
            extra["v_mag_pu_set"] = v_mag_pu_set
        if v_mag_pu_min is not None:
            extra["v_mag_pu_min"] = v_mag_pu_min
        if v_mag_pu_max is not None:
            extra["v_mag_pu_max"] = v_mag_pu_max
        self._network.add("Bus", name, v_nom=v_nom, carrier=carrier, **extra)

    def add_carrier(self, name: str, co2_emissions: float | None = None) -> None:
        """Add a Carrier component. Naming a carrier on a bus or a generator does not."""
        self._check_not_saved(f"carrier {name!r}")
        extra: dict[str, Any] = {}
        if co2_emissions is not None:
            extra["co2_emissions"] = co2_emissions
        self._network.add("Carrier", name, **extra)

    def add_load(
        self,
        name: str,
        bus: str,
        p_set: float | list[float],
        carrier: str | None = None,
        load_type: str | None = None,
    ) -> None:
        self._check_not_saved(f"load {name!r}")
        if isinstance(p_set, list):
            if not self._snapshots_set:
                raise RuntimeError(
                    f"Cannot add time-series load {name!r}: "
                    "set snapshots first with 'the network has N snapshots at M minute intervals'."
                )
            series = pd.Series(p_set, index=self._network.snapshots)
            self._add_load(name, bus, series, carrier, load_type)
        else:
            self._add_load(name, bus, p_set, carrier, load_type)

    def _add_load(
        self,
        name: str,
        bus: str,
        p_set: float | pd.Series,
        carrier: str | None,
        load_type: str | None,
    ) -> None:
        """A label the scenario does not state is left off, so PyPSA's own default stands."""
        labels: dict[str, Any] = {}
        if carrier is not None:
            labels["carrier"] = carrier
        if load_type is not None:
            labels["type"] = load_type
        self._network.add("Load", name, bus=bus, p_set=p_set, **labels)

    def add_generator(
        self,
        name: str,
        bus: str,
        carrier: str,
        p_nom: float = 0.0,
        p_min_pu: float = 0.0,
        p_max_pu: float = 1.0,
        marginal_cost: float = 0.0,
        ramp_limit_up: float | None = None,
        ramp_limit_down: float | None = None,
        p_max_pu_series: list[float] | None = None,
        committable: bool | None = None,
        min_up_time: float | None = None,
        min_down_time: float | None = None,
        up_time_before: float | None = None,
        start_up_cost: float | None = None,
        shut_down_cost: float | None = None,
        p_nom_extendable: bool | None = None,
    ) -> None:
        self._check_not_saved(f"generator {name!r}")
        extra: dict[str, Any] = {}
        if ramp_limit_up is not None:
            extra["ramp_limit_up"] = ramp_limit_up
        if ramp_limit_down is not None:
            extra["ramp_limit_down"] = ramp_limit_down
        if committable is not None:
            extra["committable"] = committable
        if min_up_time is not None:
            extra["min_up_time"] = min_up_time
        if min_down_time is not None:
            extra["min_down_time"] = min_down_time
        if up_time_before is not None:
            extra["up_time_before"] = up_time_before
        if start_up_cost is not None:
            extra["start_up_cost"] = start_up_cost
        if shut_down_cost is not None:
            extra["shut_down_cost"] = shut_down_cost
        if p_nom_extendable is not None:
            extra["p_nom_extendable"] = p_nom_extendable
        self._network.add(
            "Generator",
            name,
            bus=bus,
            carrier=carrier,
            p_nom=p_nom,
            p_min_pu=p_min_pu,
            p_max_pu=p_max_pu,
            marginal_cost=marginal_cost,
            **extra,
        )
        if p_max_pu_series is not None:
            if not self._snapshots_set:
                raise RuntimeError(
                    f"Cannot add time-series p_max_pu for {name!r}: set snapshots first."
                )
            self._network.generators_t["p_max_pu"][name] = pd.Series(
                p_max_pu_series, index=self._network.snapshots
            )

    def set_generator_attribute(self, name: str, attribute: str, value: float) -> None:
        """Set a single static attribute on an already-added generator (e.g. p_nom, efficiency)."""
        self._check_not_saved(f"generator {name!r} attribute {attribute!r}")
        self._network.generators.loc[name, attribute] = value

    def add_storage_unit(
        self,
        name: str,
        bus: str,
        carrier: str,
        p_nom: float = 0.0,
        p_min_pu: float = 0.0,
        p_max_pu: float = 1.0,
        marginal_cost: float = 0.0,
        max_hours: float = 0.0,
        efficiency_store: float = 1.0,
        efficiency_dispatch: float = 1.0,
        state_of_charge_initial: float = 0.0,
        cyclic_state_of_charge: bool | None = None,
        inflow_series: list[float] | None = None,
        p_nom_extendable: bool | None = None,
    ) -> None:
        self._check_not_saved(f"storage unit {name!r}")
        extra: dict[str, Any] = {}
        if cyclic_state_of_charge is not None:
            extra["cyclic_state_of_charge"] = cyclic_state_of_charge
        if p_nom_extendable is not None:
            extra["p_nom_extendable"] = p_nom_extendable
        self._network.add(
            "StorageUnit",
            name,
            bus=bus,
            carrier=carrier,
            p_nom=p_nom,
            p_min_pu=p_min_pu,
            p_max_pu=p_max_pu,
            marginal_cost=marginal_cost,
            max_hours=max_hours,
            efficiency_store=efficiency_store,
            efficiency_dispatch=efficiency_dispatch,
            state_of_charge_initial=state_of_charge_initial,
            **extra,
        )
        if inflow_series is not None:
            if not self._snapshots_set:
                raise RuntimeError(
                    f"Cannot add time-series inflow for {name!r}: set snapshots first."
                )
            self._network.storage_units_t["inflow"][name] = pd.Series(
                inflow_series, index=self._network.snapshots
            )

    def set_storage_unit_attribute(self, name: str, attribute: str, value: float) -> None:
        """Set a single static attribute on an already-added storage unit."""
        self._check_not_saved(f"storage unit {name!r} attribute {attribute!r}")
        self._network.storage_units.loc[name, attribute] = value

    def add_line(
        self,
        name: str,
        bus0: str,
        bus1: str,
        r: float = 0.0,
        x: float = 0.0,
        b: float = 0.0,
        g: float = 0.0,
        s_nom: float = 0.0,
        s_max_pu: float = 1.0,
        s_nom_extendable: bool | None = None,
        s_nom_opt: float | None = None,
        length: float | None = None,
        num_parallel: float | None = None,
        carrier: str | None = None,
        s_max_pu_series: list[float] | None = None,
    ) -> None:
        self._check_not_saved(f"line {name!r}")
        extra: dict[str, Any] = {}
        if s_nom_extendable is not None:
            extra["s_nom_extendable"] = s_nom_extendable
        if length is not None:
            extra["length"] = length
        if num_parallel is not None:
            extra["num_parallel"] = num_parallel
        if carrier is not None:
            extra["carrier"] = carrier
        self._network.add(
            "Line",
            name,
            bus0=bus0,
            bus1=bus1,
            r=r,
            x=x,
            b=b,
            g=g,
            s_nom=s_nom,
            s_max_pu=s_max_pu,
            **extra,
        )
        if s_nom_opt is not None:
            # s_nom_opt is a solver output; set it directly to model a post-LOPF network.
            self._network.lines.loc[name, "s_nom_opt"] = s_nom_opt
        if s_max_pu_series is not None:
            if not self._snapshots_set:
                raise RuntimeError(
                    f"Cannot add time-series s_max_pu for {name!r}: set snapshots first."
                )
            self._network.lines_t["s_max_pu"][name] = pd.Series(
                s_max_pu_series, index=self._network.snapshots
            )

    def add_link(
        self,
        name: str,
        bus0: str,
        bus1: str,
        p_nom: float = 0.0,
        p_min_pu: float = 0.0,
        p_max_pu: float = 1.0,
        efficiency: float = 1.0,
        p_nom_extendable: bool | None = None,
        p_nom_opt: float | None = None,
        carrier: str | None = None,
        bus2: str | None = None,
        efficiency_series: list[float] | None = None,
    ) -> None:
        self._check_not_saved(f"link {name!r}")
        extra: dict[str, Any] = {}
        if p_nom_extendable is not None:
            extra["p_nom_extendable"] = p_nom_extendable
        if carrier is not None:
            extra["carrier"] = carrier
        if bus2 is not None:
            extra["bus2"] = bus2
        self._network.add(
            "Link",
            name,
            bus0=bus0,
            bus1=bus1,
            p_nom=p_nom,
            p_min_pu=p_min_pu,
            p_max_pu=p_max_pu,
            efficiency=efficiency,
            **extra,
        )
        if p_nom_opt is not None:
            # p_nom_opt is a solver output; set it directly to model a post-LOPF network.
            self._network.links.loc[name, "p_nom_opt"] = p_nom_opt
        if efficiency_series is not None:
            if not self._snapshots_set:
                raise RuntimeError(
                    f"Cannot add time-series efficiency for {name!r}: set snapshots first."
                )
            self._network.links_t["efficiency"][name] = pd.Series(
                efficiency_series, index=self._network.snapshots
            )

    def _require_snapshots(self, series_desc: str) -> None:
        if not self._snapshots_set:
            raise RuntimeError(
                f"Cannot set {series_desc}: "
                "set snapshots first with 'the network has N snapshots at M minute intervals'."
            )

    def set_generator_dispatch(self, name: str, values: list[float]) -> None:
        """Write a solved generators_t.p series, modelling a post-solve network."""
        self._check_not_saved(f"dispatch for generator {name!r}")
        self._require_snapshots(f"dispatch for generator {name!r}")
        self._network.generators_t["p"][name] = pd.Series(values, index=self._network.snapshots)

    def set_storage_dispatch(self, name: str, values: list[float]) -> None:
        """Write a solved storage_units_t.p series (positive = discharge into the bus)."""
        self._check_not_saved(f"dispatch for storage unit {name!r}")
        self._require_snapshots(f"dispatch for storage unit {name!r}")
        self._network.storage_units_t["p"][name] = pd.Series(values, index=self._network.snapshots)

    def set_line_flow(self, name: str, values: list[float]) -> None:
        """Write a solved lines_t.p0 series (positive = from bus0 towards bus1)."""
        self._check_not_saved(f"flow for line {name!r}")
        self._require_snapshots(f"flow for line {name!r}")
        self._network.lines_t["p0"][name] = pd.Series(values, index=self._network.snapshots)

    def set_link_flow(self, name: str, values: list[float]) -> None:
        """Write a solved links_t.p0 series (positive = from bus0 towards bus1)."""
        self._check_not_saved(f"flow for link {name!r}")
        self._require_snapshots(f"flow for link {name!r}")
        self._network.links_t["p0"][name] = pd.Series(values, index=self._network.snapshots)

    def set_bus_marginal_price(self, name: str, values: list[float]) -> None:
        """Write a solved buses_t.marginal_price series (cost per MWh at the bus)."""
        self._check_not_saved(f"marginal price for bus {name!r}")
        self._require_snapshots(f"marginal price for bus {name!r}")
        self._network.buses_t["marginal_price"][name] = pd.Series(
            values, index=self._network.snapshots
        )

    def set_snapshot_weightings(self, values: list[float]) -> None:
        """Set the objective (hours) snapshot weightings, exported as snapshots_objective."""
        self._check_not_saved("snapshot weightings")
        self._require_snapshots("snapshot weightings")
        self._network.snapshot_weightings["objective"] = pd.Series(
            values, index=self._network.snapshots
        )

    def set_objective(self, value: float) -> None:
        """Set the solve objective value, exported as the network__objective attribute."""
        self._check_not_saved("network objective")
        # n.objective is a read-only property; the private attribute is what export serialises.
        self._network._objective = value

    def set_pypsa_version(self, version: str) -> None:
        """State the PyPSA version the file records as its writer.

        PyPSA stamps the running version on export, so a file written here would otherwise
        always agree with the version doing the reading. Stating one keeps the two apart.
        """
        self._check_not_saved("a PyPSA version")
        self._pypsa_version = version

    def set_line_attribute(self, name: str, attribute: str, value: float) -> None:
        """Set a single static attribute on an already-added line (e.g. s_nom, r, s_max_pu)."""
        self._check_not_saved(f"line {name!r} attribute {attribute!r}")
        self._network.lines.loc[name, attribute] = value

    def set_link_attribute(self, name: str, attribute: str, value: float) -> None:
        """Set a single static attribute on an already-added link (e.g. p_nom, p_max_pu)."""
        self._check_not_saved(f"link {name!r} attribute {attribute!r}")
        self._network.links.loc[name, attribute] = value

    def add_raw_component(self, class_name: str, name: str, **attributes: Any) -> None:
        """Add a component of any PyPSA class by name, for classes without a bespoke builder.

        Used by uniqueness scenarios that only need a component to exist (store, transformer,
        shunt impedance, ...) before forging a within-class duplicate of it.
        """
        self._check_not_saved(f"{class_name} {name!r}")
        self._network.add(class_name, name, **attributes)

    def deactivate_component(self, component: str, name: str) -> None:
        """Set `active` False on an already-added component, excluding it from translation.

        Separate from the per-class attribute setters, which take a float: `active` is
        boolean, and pandas refuses a float written into a boolean column.
        """
        self._check_not_saved(f"{component} {name!r} active")
        static = getattr(self._network, _netcdf_class(component))
        static.loc[name, "active"] = False

    def duplicate_component(self, component: str, name: str) -> None:
        """Record that `name` should appear twice within its class in the saved netCDF.

        PyPSA's exporter refuses a duplicate component index, so the malformed input is
        forged at the xarray level in save(): a real-world upstream tool could still emit it.
        """
        self._check_not_saved(f"duplicate {component} {name!r}")
        if component not in _COMPONENT_TO_NETCDF_CLASS:
            raise ValueError(f"Unknown component class for duplication: {component!r}")
        self._forced_duplicates.append((component, name))

    def save(self, path: Path) -> None:
        if self._saved:
            raise RuntimeError("Network already saved. Cannot call save() twice.")
        path.parent.mkdir(parents=True, exist_ok=True)
        if self._forced_duplicates or self._pypsa_version is not None:
            self._save_with_overrides(path)
        else:
            self._network.export_to_netcdf(str(path))
        self._saved = True

    def _save_with_overrides(self, path: Path) -> None:
        """Export the network, then rewrite what PyPSA's own exporter will not write.

        A duplicate row is appended at the netCDF level (concatenating along the class's
        `_i` dimension) because PyPSA's exporter aligns on the index and rejects
        duplicates. A stated PyPSA version replaces the running version the exporter
        stamped on.
        """
        with tempfile.TemporaryDirectory() as staging:
            source = Path(staging) / "network.nc"
            self._network.export_to_netcdf(str(source))
            with xr.open_dataset(source) as opened:
                dataset = opened.load()
        for component, name in self._forced_duplicates:
            dimension = f"{_COMPONENT_TO_NETCDF_CLASS[component]}_i"
            position = dataset[dimension].values.tolist().index(name)
            duplicate_row = dataset.isel({dimension: [position]})
            dataset = xr.concat(
                [dataset, duplicate_row],
                dim=dimension,
                data_vars="minimal",
                coords="minimal",
                compat="override",
            )
        if self._pypsa_version is not None:
            dataset.attrs[_PYPSA_VERSION_ATTR] = self._pypsa_version
        dataset.to_netcdf(str(path))

    def save_classic_netcdf(self, path: Path) -> None:
        """Write the network as classic NETCDF3 (scipy), the format our PyPSA sink emits."""
        if self._saved:
            raise RuntimeError("Network already saved. Cannot call save() twice.")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._network.export_to_netcdf(None).to_netcdf(str(path), engine="scipy")
        self._saved = True


def _netcdf_class(component: str) -> str:
    """The static-frame name PyPSA holds a component class under, by its prose name."""
    if component not in _COMPONENT_TO_NETCDF_CLASS:
        raise ValueError(f"Unknown component class: {component!r}")
    return _COMPONENT_TO_NETCDF_CLASS[component]


def read_network(path: str | Path) -> pypsa.Network:
    """Read a written PyPSA network back off disk.

    Each call re-reads the file, so an assertion always sees what is on disk now
    rather than a snapshot taken when the scenario started.
    """
    return pypsa.Network(str(path))
