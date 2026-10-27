"""TranslationEvent reporters for the Sienna -> PyPSA pipeline, one module per PyPSA component.

Each reporter wraps ``ScopedRecorder`` with one named method per decision, so step code reads
as a list of decisions made rather than a wall of ``TranslationEvent`` dataclass arguments.
The shared field builders and event append live on ``DestinationReporter``. A value that the
sidecar states and a PyPSA column takes as it is goes through ``record_carried`` on the base.
"""

from interop.plugins.shared.sienna_pypsa_translations.reporters.buses import BusReporter
from interop.plugins.shared.sienna_pypsa_translations.reporters.generators import (
    FuelGeneratorReporter,
    GeneratorReporter,
    ThermalLimit,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters.lines import LineReporter
from interop.plugins.shared.sienna_pypsa_translations.reporters.links import (
    ConversionReporter,
    LinkReporter,
    PlantLinkReporter,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters.loads import LoadReporter
from interop.plugins.shared.sienna_pypsa_translations.reporters.profiles import ProfileReporter
from interop.plugins.shared.sienna_pypsa_translations.reporters.sidecar import (
    ExtensionRelayReporter,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters.storage_units import (
    StorageUnitReporter,
)

__all__ = [
    "BusReporter",
    "ConversionReporter",
    "ExtensionRelayReporter",
    "FuelGeneratorReporter",
    "GeneratorReporter",
    "LineReporter",
    "LinkReporter",
    "LoadReporter",
    "PlantLinkReporter",
    "ProfileReporter",
    "StorageUnitReporter",
    "ThermalLimit",
]
