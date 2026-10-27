"""What both Julia adapters do alike: start Julia, tell HiGHS how to run, and report an error.

The dispatch adapter and the expansion adapter differ in what they run, and in nothing here.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, NamedTuple

from interop.adapters.outbound.julia_packages import JuliaEnvironment, declare_julia_packages
from interop.ports.errors import UserInputError
from interop.ports.outbound.solver import HiGHSOptions

log = logging.getLogger(__name__)

MIP_REL_GAP = 0.01
"""How far from proven optimality a mixed-integer solve may stop, on both Julia paths."""


class HiGHSAttribute(NamedTuple):
    """One attribute that HiGHS is built with, its value written as a Julia expression."""

    name: str
    value: str


MIP_GAP_ATTRIBUTE = HiGHSAttribute("mip_rel_gap", str(MIP_REL_GAP))


def is_julia_provisioned(environment: JuliaEnvironment) -> bool:
    """Report whether Julia and the declared packages are already installed.

    `juliapkg.resolve(dry_run=True)` returns True only when the current declarations match
    the last successful resolution, i.e. nothing would be downloaded; it never installs
    anything itself.
    """
    declare_julia_packages(environment.dev_checkout_paths)
    import juliapkg  # noqa: PLC0415

    return bool(juliapkg.resolve(dry_run=True))


def require_julia(environment: JuliaEnvironment) -> Any:
    """The Julia `Main` module, once the declared packages are installed."""
    os.environ.setdefault("PYTHON_JULIACALL_HANDLE_SIGNALS", "yes")
    declare_julia_packages(environment.dev_checkout_paths)
    log.info(
        "Preparing the Julia environment. The first run downloads Julia and %s and compiles "
        "them. Later runs start much faster.",
        environment.description,
    )
    import faulthandler  # noqa: PLC0415

    faulthandler.disable()
    from juliacall import Main as jl  # noqa: PLC0415

    return jl


def build_highs_args(highs: HiGHSOptions, extra: Sequence[HiGHSAttribute]) -> str:
    """The keyword arguments of `optimizer_with_attributes`, as Julia text."""
    attributes = [
        HiGHSAttribute("log_to_console", "true"),
        HiGHSAttribute("solver", f'"{highs.solver}"'),
        HiGHSAttribute("presolve", f'"{highs.presolve}"'),
        HiGHSAttribute("run_crossover", f'"{highs.run_crossover}"'),
        *extra,
    ]
    if highs.time_limit_seconds is not None:
        attributes.append(HiGHSAttribute("time_limit", str(float(highs.time_limit_seconds))))
    return ", ".join(f'"{attribute.name}" => {attribute.value}' for attribute in attributes)


@contextmanager
def reject_julia_errors(label: str) -> Iterator[None]:
    """Raise a Julia error from the block as a user error whose text starts with ``label``."""
    from juliacall import JuliaError  # noqa: PLC0415

    try:
        yield
    except JuliaError as exc:
        raise UserInputError(f"{label}:\n{exc}") from exc
