from __future__ import annotations

from pathlib import Path

from dishka import Container, Provider, Scope, provide
from dishka import make_container as _make_container

from interop.adapters.outbound.highs_network_solver import HighsNetworkSolver
from interop.adapters.outbound.local_filesystem import LocalFilesystem, LocalFilesystemConfig
from interop.adapters.outbound.markdown_comparison_report import MarkdownComparisonReport
from interop.adapters.outbound.markdown_validation_report import MarkdownValidationReport
from interop.adapters.outbound.write_tracking_filesystem import WriteTrackingFilesystem
from interop.core.adapters_config import AdaptersConfig, load_adapters_config
from interop.core.factories import (
    AdapterFactory,
    InteriorFilesystemFactory,
    ReporterBuilder,
    SchemaCatalog,
    SinkFactoryBuilder,
    SourceFactoryBuilder,
    StepFactoryBuilder,
    ValidatorFactoryBuilder,
    WriteTrackingFilesystemFactory,
)
from interop.core.reporting import MultiReport
from interop.core.use_cases.compare import CompareUsingPort
from interop.core.use_cases.init_project import InitializeProjectDirectory
from interop.core.use_cases.pipeline_catalog import PipelineCatalog
from interop.core.use_cases.solve import SolveUsingPort
from interop.core.use_cases.translate import (
    LegFactories,
    RunFilesystems,
    TranslateUsingPipeline,
)
from interop.core.use_cases.validate import ValidateUsingPipeline
from interop.core.user_mappings import NodeLookups
from interop.core.user_mappings_loader import UserMappingsLoader
from interop.di.discovery import Registry, discover
from interop.di.factories import (
    UnknownAdapterBindingError,
    make_adapter_factory,
    make_node_lookups,
    make_schema_catalog,
    make_sink_factory,
    make_source_factory,
    make_step_factory,
    make_validator_factory,
)
from interop.logging_setup import configure_logging
from interop.ports.inbound.compare import CompareUseCase
from interop.ports.inbound.init_project import InitProjectUseCase
from interop.ports.inbound.pipeline_catalog import PipelineCatalogUseCase
from interop.ports.inbound.solve import SolveUseCase
from interop.ports.inbound.translate import TranslateUseCase
from interop.ports.inbound.validate import ValidateUseCase
from interop.ports.outbound.comparison_report import ComparisonReportPort
from interop.ports.outbound.filesystem import FilesystemPort
from interop.ports.outbound.network_solver import NetworkSolverPort
from interop.ports.outbound.reporting import ReportingPort
from interop.ports.outbound.solver import SolverPort
from interop.ports.outbound.validation_report import ValidationReportPort

# The default `filesystem` binding when adapters.yaml names none.
_LOCAL_FILESYSTEM = "local_filesystem"


class PluginProvider(Provider):
    scope = Scope.APP

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        configure_logging()
        self._project_root = project_root

    @provide
    def registry(self) -> Registry:
        return discover(self._project_root)

    @provide
    def adapters_config(self) -> AdaptersConfig:
        return load_adapters_config(self._project_root)

    @provide
    def filesystem(self, registry: Registry, adapters_config: AdaptersConfig) -> FilesystemPort:
        binding_key = "filesystem"
        name = adapters_config.bindings.get(binding_key, _LOCAL_FILESYSTEM)
        bucket = registry.adapter_bucket(FilesystemPort)
        if name not in bucket:
            raise UnknownAdapterBindingError(FilesystemPort, binding_key, name, list(bucket))
        return make_adapter_factory(
            registry,
            FilesystemPort,  # type: ignore[type-abstract]
            adapters_config.adapter_configs,
        )(name)

    @provide
    def source_factory_builder(self, registry: Registry) -> SourceFactoryBuilder:
        return lambda fs, umf: make_source_factory(registry, fs, umf)

    @provide
    def interior_filesystem_factory(self) -> InteriorFilesystemFactory:
        """A composed run's interior hand-offs always use the local filesystem, whatever
        adapters.yaml binds `filesystem` to.

        Do not make this configurable. A deployment may bind the configured port to signed
        URLs, and nobody mints a URL for a hand-off the user never named, so an interior
        boundary that reached the configured port would break the chain.
        """
        return lambda root: LocalFilesystem(LocalFilesystemConfig(root=root))

    @provide
    def write_tracking_filesystem_factory(self) -> WriteTrackingFilesystemFactory:
        return lambda inner, on_write: WriteTrackingFilesystem(inner, on_write)

    @provide
    def run_filesystems(
        self,
        fs: FilesystemPort,
        interior_filesystem_factory: InteriorFilesystemFactory,
        write_tracking_filesystem_factory: WriteTrackingFilesystemFactory,
    ) -> RunFilesystems:
        return RunFilesystems(
            configured=fs,
            interior_factory=interior_filesystem_factory,
            tracker_factory=write_tracking_filesystem_factory,
        )

    @provide
    def node_lookups(self, registry: Registry) -> NodeLookups:
        return make_node_lookups(registry)

    @provide
    def user_mappings_loader(self, node_lookups: NodeLookups) -> UserMappingsLoader:
        return UserMappingsLoader(node_lookups)

    @provide
    def step_factory_builder(self, registry: Registry) -> StepFactoryBuilder:
        # Builder rather than direct factory: each translation run constructs its own
        # EventLog and threads it through here so each step gets a ScopedRecorder
        # tagged with its own name. Sharing one log across runs would mix events.
        return lambda recorder, umf: make_step_factory(registry, recorder, umf)

    @provide
    def sink_factory_builder(self, registry: Registry) -> SinkFactoryBuilder:
        return lambda fs: make_sink_factory(registry, fs)

    @provide
    def validator_factory_builder(self, registry: Registry) -> ValidatorFactoryBuilder:
        return lambda umf: make_validator_factory(registry, umf)

    @provide
    def reporter_builder(
        self, registry: Registry, adapters_config: AdaptersConfig
    ) -> ReporterBuilder:
        def build(fs: FilesystemPort) -> ReportingPort:
            binding_key = "reporter"
            multi = adapters_config.multi_bindings.get(binding_key)
            names = (
                multi
                if multi is not None
                else [adapters_config.bindings.get(binding_key, "markdown_report")]
            )
            factory = make_adapter_factory(
                registry,
                ReportingPort,  # type: ignore[type-abstract]
                adapters_config.adapter_configs,
                fs=fs,
            )
            bucket = registry.adapter_bucket(ReportingPort)
            for name in names:
                if name not in bucket:
                    raise UnknownAdapterBindingError(ReportingPort, binding_key, name, list(bucket))
            reporters = [factory(name) for name in names]
            if len(reporters) == 1:
                return reporters[0]
            return MultiReport(reporters)

        return build

    @provide
    def filesystem_factory(
        self, registry: Registry, adapters_config: AdaptersConfig
    ) -> AdapterFactory[FilesystemPort]:
        # mypy flags Protocol types as abstract; the runtime check below works fine.
        return make_adapter_factory(
            registry,
            FilesystemPort,  # type: ignore[type-abstract]
            adapters_config.adapter_configs,
        )

    @provide
    def schema_catalog(self, registry: Registry) -> SchemaCatalog:
        return make_schema_catalog(registry)

    @provide
    def pipeline_catalog_use_case(
        self, schema_catalog: SchemaCatalog, user_mappings_loader: UserMappingsLoader
    ) -> PipelineCatalogUseCase:
        return PipelineCatalog(schema_catalog, user_mappings_loader)

    @provide
    def leg_factories(
        self,
        source_factory_builder: SourceFactoryBuilder,
        step_factory_builder: StepFactoryBuilder,
        sink_factory_builder: SinkFactoryBuilder,
        validator_factory_builder: ValidatorFactoryBuilder,
    ) -> LegFactories:
        return LegFactories(
            source=source_factory_builder,
            step=step_factory_builder,
            sink=sink_factory_builder,
            validator=validator_factory_builder,
        )

    @provide
    def translate_use_case(
        self,
        factories: LegFactories,
        reporter_builder: ReporterBuilder,
        filesystems: RunFilesystems,
        user_mappings_loader: UserMappingsLoader,
        validation_report: ValidationReportPort,
    ) -> TranslateUseCase:
        return TranslateUsingPipeline(
            factories,
            reporter_builder,
            filesystems,
            user_mappings_loader,
            validation_report,
        )

    @provide
    def validation_report(self, fs: FilesystemPort) -> ValidationReportPort:
        return MarkdownValidationReport(fs)

    @provide
    def validate_use_case(
        self,
        source_factory_builder: SourceFactoryBuilder,
        validator_factory_builder: ValidatorFactoryBuilder,
        validation_report: ValidationReportPort,
        user_mappings_loader: UserMappingsLoader,
        fs: FilesystemPort,
    ) -> ValidateUseCase:
        return ValidateUsingPipeline(
            source_factory_builder,
            validator_factory_builder,
            validation_report,
            user_mappings_loader,
            fs,
        )

    @provide
    def solver(self, registry: Registry, adapters_config: AdaptersConfig) -> SolverPort:
        binding_key = "solver"
        name = adapters_config.bindings.get(binding_key, "julia_solver")
        bucket = registry.adapter_bucket(SolverPort)
        if name not in bucket:
            raise UnknownAdapterBindingError(SolverPort, binding_key, name, list(bucket))
        return make_adapter_factory(
            registry,
            SolverPort,  # type: ignore[type-abstract]
            adapters_config.adapter_configs,
        )(name)

    @provide
    def network_solver(self) -> NetworkSolverPort:
        # HiGHS ships with the package, so unlike SolverPort this needs no adapter
        # binding through adapters.yaml: there is exactly one implementation.
        return HighsNetworkSolver()

    @provide
    def solve_use_case(self, solver: SolverPort, network_solver: NetworkSolverPort) -> SolveUseCase:
        return SolveUsingPort(solver, network_solver)

    @provide
    def comparison_report(self, fs: FilesystemPort) -> ComparisonReportPort:
        return MarkdownComparisonReport(fs)

    @provide
    def compare_use_case(
        self,
        translate: TranslateUseCase,
        comparison_report: ComparisonReportPort,
        fs: FilesystemPort,
        catalog: PipelineCatalogUseCase,
    ) -> CompareUseCase:
        return CompareUsingPort(translate, comparison_report, fs, catalog)

    @provide
    def init_project_use_case(self) -> InitProjectUseCase:
        # init bootstraps the project, including adapters.yaml itself, so it
        # cannot depend on the configured FilesystemPort (loading
        # adapters.yaml would fail before init had a chance to write one).
        # local_filesystem is the only built-in FilesystemPort adapter and
        # the only one a user could plausibly configure pre-init anyway.
        return InitializeProjectDirectory(LocalFilesystem())


def make_container(project_root: Path | None = None) -> Container:
    return _make_container(PluginProvider(project_root=project_root))
