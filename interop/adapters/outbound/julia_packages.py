"""The Julia packages a Sienna adapter installs, and how it declares them to juliapkg."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from interop.ports.errors import UserInputError

_SIENNA_GITHUB = "https://github.com/NREL-Sienna"


@dataclass(frozen=True)
class JuliaPackage:
    """One package juliapkg installs, by registry version or by git revision."""

    name: str
    uuid: str
    version: str | None = None
    url: str | None = None
    rev: str | None = None

    def state_location(self) -> dict[str, str]:
        """Where juliapkg finds it: a registry version, or a git URL and revision."""
        if self.url is not None and self.rev is not None:
            return {"url": self.url, "rev": self.rev}
        return {"version": self.version} if self.version is not None else {}


# Versions are pinned to the releases the solve pipeline was developed against;
# unpinned packages are constrained transitively by the pinned ones.
JULIA_PACKAGES: tuple[JuliaPackage, ...] = (
    JuliaPackage("PowerSystems", "bcd98974-b02a-5e2f-9ee0-a103f5c450dd", "~5.9"),
    JuliaPackage("PowerSimulations", "e690365d-45e2-57bb-ac84-44ba829e73c4", "~0.34"),
    JuliaPackage("HydroPowerSimulations", "fc1677e0-6ad7-4515-bf3a-bd6bf20a0b1b", "~0.15"),
    JuliaPackage("StorageSystemsSimulations", "e2f1a126-19d0-4674-9252-42b2384f8e3c", "~0.16"),
    JuliaPackage("HiGHS", "87dc4568-4c63-4d18-b0c0-bb2238e4078b"),
    JuliaPackage("InfrastructureSystems", "2cd47ed4-ca9b-11e9-27f2-ab636a7671f1"),
    JuliaPackage("TimeSeries", "9e3dc215-6440-5c97-bce1-76c03772f85e"),
    JuliaPackage("CSV", "336ed68f-0bac-5ca0-87d4-7b16caf5d00b"),
    JuliaPackage("DataFrames", "a93c6f00-e57d-5684-b7b6-d8193f3e46c0"),
    # Neither investments package has a registry release that runs: PowerSystemsInvestments is
    # not in the General registry, and its only branch that calls nothing
    # PowerSystemsInvestmentsPortfolios lacks needs that package ahead of its 0.1.0 release.
    JuliaPackage(
        "PowerSystemsInvestments",
        "bed98974-b02a-5e2f-9ee0-a103f5c450dd",
        url=f"{_SIENNA_GITHUB}/PowerSystemsInvestments.jl",
        rev="f68d202694e17e7a0a0156490d2b7c2e9167bdb7",
    ),
    JuliaPackage(
        "PowerSystemsInvestmentsPortfolios",
        "bed98974-b02a-5e2f-9fe0-a103f8c450dd",
        url=f"{_SIENNA_GITHUB}/PowerSystemsInvestmentsPortfolios.jl",
        rev="d72d61c1be2f7cdd5d54d7464b902973eead77b3",
    ),
)


def declare_julia_packages(dev_checkout_paths: Mapping[str, Path | None]) -> None:
    """Declare the Julia dependencies with juliapkg before juliacall imports.

    juliapkg resolves the declarations on `import juliacall`: it finds a compatible Julia
    (downloading one if none is installed) and installs the declared packages into its
    managed project. Re-declaring an unchanged set is free; juliapkg skips resolution when
    the declarations' hash matches.
    """
    import juliapkg  # noqa: PLC0415

    for package in JULIA_PACKAGES:
        checkout = dev_checkout_paths.get(package.name)
        if checkout is None:
            juliapkg.add(package.name, package.uuid, **package.state_location())
        else:
            juliapkg.add(
                package.name, package.uuid, dev=True, path=_read_checkout(checkout, package.name)
            )


def _read_checkout(checkout: Path, name: str) -> str:
    if not checkout.is_dir():
        raise UserInputError(
            f"{name} checkout not found at {checkout}. Fix the "
            "path in adapters.yaml, or remove it to use the registry release."
        )
    return str(checkout)
