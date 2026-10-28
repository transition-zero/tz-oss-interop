"""The steps and the prompt stubs of the solve command, for each model type that it runs.

Registered as a pytest plugin from `tests/conftest.py`, so a feature in any directory can solve.
"""

import itertools

import pytest
from interop_testing import write_adapters_config
from pytest_bdd import given, parsers, then, when

from tests.step_defs.conftest import dispatch_solve, stub_questionary_attr


def invoke_solve(
    monkeypatch: pytest.MonkeyPatch,
    sienna_json_path: str,
    network_model: str,
    output_dir: str = "solved",
    model_type: str = "sienna",
    download_consent: bool = True,
    unserved_energy: str = "refused",
    unit_commitment: str = "exact",
    solver: str = "simplex",
    presolve: str = "choose",
    run_crossover: str = "choose",
    time_limit_seconds: str = "",
) -> None:
    """Stub every solve prompt (selects, download consent, paths, text), then dispatch solve."""
    stub_questionary_attr(monkeypatch, "path", iter([sienna_json_path, output_dir]))
    stub_questionary_attr(
        monkeypatch,
        "select",
        iter(
            [
                model_type,
                network_model,
                unserved_energy,
                unit_commitment,
                solver,
                presolve,
                run_crossover,
            ]
        ),
    )
    stub_questionary_attr(monkeypatch, "confirm", iter([download_consent]))
    stub_questionary_attr(monkeypatch, "text", iter([time_limit_seconds]))
    dispatch_solve()


def invoke_expand(
    monkeypatch: pytest.MonkeyPatch,
    portfolio_json_path: str,
    balance_model: str = "multi-region",
    output_dir: str = "expanded",
    download_consent: bool = True,
    investment_treatment: str = "continuous",
    discount_rate: str = "",
    solver: str = "simplex",
    presolve: str = "choose",
    run_crossover: str = "choose",
    time_limit_seconds: str = "",
) -> None:
    """Stub every expansion prompt, then dispatch solve with the investments model type."""
    stub_questionary_attr(monkeypatch, "path", iter([portfolio_json_path, output_dir]))
    stub_questionary_attr(
        monkeypatch,
        "select",
        iter(
            [
                "sienna-investments",
                balance_model,
                investment_treatment,
                solver,
                presolve,
                run_crossover,
            ]
        ),
    )
    stub_questionary_attr(monkeypatch, "confirm", iter([download_consent]))
    stub_questionary_attr(monkeypatch, "text", iter([discount_rate, time_limit_seconds]))
    dispatch_solve()


def invoke_expand_cancelling(
    monkeypatch: pytest.MonkeyPatch, portfolio_json_path: str, selects_before_cancel: list[str]
) -> None:
    """Answer the expansion selects in order, then cancel every select that follows them."""
    stub_questionary_attr(monkeypatch, "path", iter([portfolio_json_path, "expanded"]))
    stub_questionary_attr(
        monkeypatch,
        "select",
        itertools.chain(["sienna-investments", *selects_before_cancel], itertools.repeat(None)),
    )
    stub_questionary_attr(monkeypatch, "confirm", itertools.repeat(True))
    stub_questionary_attr(monkeypatch, "text", itertools.repeat(""))
    dispatch_solve()


def invoke_solve_pypsa(
    monkeypatch: pytest.MonkeyPatch,
    network_path: str,
    output_dir: str,
    start: str = "",
    end: str = "",
    unit_commitment: str = "exact",
    window: str = "month",
    look_ahead_days: str = "",
    unserved_energy: str = "refused",
) -> None:
    """Stub the pypsa solve prompts (model type, paths, dates, UC, window, unserved energy),
    then dispatch."""
    stub_questionary_attr(
        monkeypatch, "select", iter(["pypsa", unit_commitment, window, unserved_energy])
    )
    stub_questionary_attr(monkeypatch, "path", iter([network_path, output_dir]))
    stub_questionary_attr(monkeypatch, "text", iter([start, end, look_ahead_days]))
    dispatch_solve()


@given(parsers.parse('adapters.yaml binds solver to "{name}"'))
def given_solver_binding(name: str) -> None:
    _write_binding("solver", name)


@given(parsers.parse('adapters.yaml binds expansion to "{name}"'))
def given_expansion_binding(name: str) -> None:
    _write_binding("expansion", name)


def _write_binding(port: str, name: str) -> None:
    write_adapters_config(f"bindings:\n  {port}: {name}\nadapters: {{}}\n")


@when(
    parsers.parse('I run solve on "{network_path}" from "{start}" to "{end}" into "{output_dir}"')
)
def run_solve_pypsa(
    monkeypatch: pytest.MonkeyPatch, network_path: str, start: str, end: str, output_dir: str
) -> None:
    invoke_solve_pypsa(monkeypatch, network_path, output_dir, start, end)


@when(
    parsers.parse(
        'I run solve on "{network_path}" from "{start}" to "{end}" in "{window}" windows '
        'with a {look_ahead_days:d} day look-ahead into "{output_dir}"'
    )
)
def run_solve_pypsa_in_windows(
    monkeypatch: pytest.MonkeyPatch,
    network_path: str,
    start: str,
    end: str,
    window: str,
    look_ahead_days: int,
    output_dir: str,
) -> None:
    invoke_solve_pypsa(
        monkeypatch,
        network_path,
        output_dir,
        start,
        end,
        window=window,
        look_ahead_days=str(look_ahead_days),
    )


@when(parsers.parse('I run solve on "{network_path}" from "{start}" onward into "{output_dir}"'))
def run_solve_pypsa_onward(
    monkeypatch: pytest.MonkeyPatch, network_path: str, start: str, output_dir: str
) -> None:
    invoke_solve_pypsa(monkeypatch, network_path, output_dir, start, end="")


@when(
    parsers.parse(
        'I run solve on "{network_path}" from "{start}" to "{end}" '
        'with unit commitment "{unit_commitment}" into "{output_dir}"'
    )
)
def run_solve_pypsa_with_unit_commitment(
    monkeypatch: pytest.MonkeyPatch,
    network_path: str,
    start: str,
    end: str,
    unit_commitment: str,
    output_dir: str,
) -> None:
    invoke_solve_pypsa(
        monkeypatch, network_path, output_dir, start, end, unit_commitment=unit_commitment
    )


@when(
    parsers.parse(
        'I run solve on "{network_path}" from "{start}" to "{end}" '
        'with unserved energy "{unserved_energy}" into "{output_dir}"'
    )
)
def run_solve_pypsa_with_unserved_energy(
    monkeypatch: pytest.MonkeyPatch,
    network_path: str,
    start: str,
    end: str,
    unserved_energy: str,
    output_dir: str,
) -> None:
    invoke_solve_pypsa(
        monkeypatch, network_path, output_dir, start, end, unserved_energy=unserved_energy
    )


@then(parsers.parse('the solved network "{path}" has no generator "{name}"'))
def assert_solved_network_has_no_generator(path: str, name: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    assert name not in network.generators.index, f"expected no generator {name!r} in {path}"


@then(
    parsers.parse('the solved network "{path}" records {mwh:g} MWh of unserved energy at "{bus}"')
)
def assert_solved_network_records_unserved_energy(path: str, mwh: float, bus: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    recorded = network.meta.get("unserved_energy_mwh", {})
    assert abs(recorded.get(bus, 0.0) - mwh) < 1e-6, f"expected {mwh} MWh at {bus}, got {recorded}"


@then(parsers.parse('the solved network "{path}" has dispatch for {count:d} snapshots'))
def assert_solved_network_has_dispatch(path: str, count: int) -> None:
    import pypsa

    network = pypsa.Network(path)
    dispatched = int((network.generators_t["p"] != 0).any(axis=1).sum())
    assert dispatched == count, f"expected dispatch for {count} snapshots, got {dispatched}"


@then(parsers.parse('the solved network "{path}" has generator "{name}" dispatch {values}'))
def assert_solved_network_generator_dispatch(path: str, name: str, values: str) -> None:
    import pypsa

    network = pypsa.Network(path)
    expected = [float(v) for v in values.split()]
    actual = [float(v) for v in network.generators_t["p"][name]]
    assert len(actual) == len(expected), (
        f"expected {len(expected)} dispatch values for {name!r}, got {len(actual)}: {actual}"
    )
    paired = enumerate(zip(actual, expected, strict=True))
    mismatches = [(i, a, e) for i, (a, e) in paired if abs(a - e) > 1e-6]
    assert not mismatches, (
        f"generator {name!r} dispatch mismatch at {mismatches}; expected {expected}, got {actual}"
    )


@then(parsers.parse('the solved network "{path}" has no dispatch on "{day}"'))
def assert_no_dispatch_on(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    dispatch = network.generators_t.p
    on_day = dispatch[dispatch.index.normalize() == pd.Timestamp(day)]
    assert (on_day == 0).all(axis=None), f"expected no dispatch on {day} in {path}; found {on_day}"


@then(parsers.parse('the solved network "{path}" has no bus price on "{day}"'))
def assert_no_bus_price_on(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    price = network.buses_t.marginal_price
    on_day = price[price.index.normalize() == pd.Timestamp(day)]
    assert (on_day == 0).all(axis=None), f"expected no bus price on {day} in {path}; found {on_day}"


@then(parsers.parse('the solved network "{path}" marks "{day}" as reported'))
def assert_day_marked_reported(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    reported = pd.DatetimeIndex(network.meta.get("reported_snapshots", []))
    on_day = reported[reported.normalize() == pd.Timestamp(day)]
    assert not on_day.empty, f"expected {day} marked reported in {path}; reported={list(reported)}"


@then(parsers.parse('the solved network "{path}" marks "{day}" as not reported'))
def assert_day_not_marked_reported(path: str, day: str) -> None:
    import pandas as pd
    import pypsa

    network = pypsa.Network(path)
    reported = pd.DatetimeIndex(network.meta.get("reported_snapshots", []))
    on_day = reported[reported.normalize() == pd.Timestamp(day)]
    assert on_day.empty, f"expected {day} not marked reported in {path}; found {list(on_day)}"


@then("the solve reported success")
def assert_solve_reported_success(printed_messages: list[str]) -> None:
    combined = "\n".join(printed_messages)
    assert "[OK]" in combined, f"expected a successful solve summary, got: {combined!r}"
