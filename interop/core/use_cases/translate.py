from __future__ import annotations

import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from interop.core.composition.addressing import read_param
from interop.core.composition.document import (
    load_leg_spec,
    load_pipeline_document,
    validate_frameworks,
)
from interop.core.composition.planning import (
    CompositionRequest,
    PlannedLeg,
    TranslationPlan,
    plan_translation,
)
from interop.core.factories import (
    InteriorFilesystemFactory,
    ReporterBuilder,
    SinkFactoryBuilder,
    SourceFactoryBuilder,
    StepFactoryBuilder,
    ValidatorFactoryBuilder,
    WriteTrackingFilesystemFactory,
)
from interop.core.reporting import EventLog, ScopedRecorder
from interop.core.runner import run_pipeline
from interop.core.user_mappings import UserMappings, UserMappingsLookup
from interop.core.user_mappings_loader import (
    LabelledSpec,
    MappingsFile,
    MappingsProducer,
    UserMappingsLoader,
)
from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.inbound.translate import FileWrite, TranslateResult, TranslateUseCase
from interop.ports.outbound.filesystem import FilesystemPort, Location, OnWrite, to_location
from interop.ports.outbound.validation import EnergyModelValidationError
from interop.ports.outbound.validation_report import (
    DEFAULT_VALIDATION_REPORT_PATH,
    ValidationReportPort,
)


class _Scratch:
    """The run's interior hand-offs, one directory each, created only once a leg asks for
    one: a lone pipeline has no interior and would otherwise leave an empty directory
    behind under `--keep-staging`.
    """

    def __init__(self) -> None:
        self._root: Path | None = None

    def create_directory_for(self, handoff: str) -> Path:
        if self._root is None:
            self._root = Path(tempfile.mkdtemp(prefix="interop-compose-"))
        return self._root / handoff

    def discard(self) -> None:
        if self._root is not None:
            shutil.rmtree(self._root, ignore_errors=True)


@contextmanager
def _run_scratch(*, keep_staging: bool) -> Generator[_Scratch, None, None]:
    scratch = _Scratch()
    try:
        yield scratch
    finally:
        if not keep_staging:
            scratch.discard()


@dataclass(frozen=True)
class RunFilesystems:
    """Where a run reads and writes: the configured port at its own boundary, a local
    filesystem at each interior hand-off, and a tracker to report what it wrote.
    """

    configured: FilesystemPort
    interior_factory: InteriorFilesystemFactory
    tracker_factory: WriteTrackingFilesystemFactory


@dataclass(frozen=True)
class LegFactories:
    """How to build the nodes of one leg."""

    source: SourceFactoryBuilder
    step: StepFactoryBuilder
    sink: SinkFactoryBuilder
    validator: ValidatorFactoryBuilder


@dataclass
class _Run:
    """One event log and one list of writes per run, not per leg, so a chain's decisions
    report and reported writes cover the whole run.
    """

    filesystems: RunFilesystems
    scratch: _Scratch
    user_mappings_path: Location | None
    keep_staging: bool
    event_log: EventLog = field(default_factory=EventLog)
    writes: list[FileWrite] = field(default_factory=list)
    errors: list[EnergyModelValidationError] = field(default_factory=list)
    mappings: dict[type[UserMappings], MappingsFile] = field(default_factory=dict)
    producers: dict[type[UserMappings], MappingsProducer] = field(default_factory=dict)
    _interior_filesystems: dict[str, FilesystemPort] = field(default_factory=dict)

    @property
    def configured_filesystem(self) -> FilesystemPort:
        return self.filesystems.configured

    def filesystem_for(self, handoff_directory: str | None) -> FilesystemPort:
        """One filesystem per hand-off, so the port that writes a file into it and the port
        that reads that file back are the same object.
        """
        if handoff_directory is None:
            return self.configured_filesystem
        if handoff_directory not in self._interior_filesystems:
            self._interior_filesystems[handoff_directory] = self.filesystems.interior_factory(
                self.scratch.create_directory_for(handoff_directory)
            )
        return self._interior_filesystems[handoff_directory]

    def track(self, handoff_directory: str | None) -> FilesystemPort:
        return self.filesystems.tracker_factory(
            self.filesystem_for(handoff_directory), self._on_write_for(handoff_directory)
        )

    def recorder_for(self, leg: PlannedLeg) -> ScopedRecorder:
        return ScopedRecorder(self.event_log, pipeline=leg.pipeline)

    def _on_write_for(self, handoff_directory: str | None) -> OnWrite:
        if handoff_directory is None:
            return self._record_project_write
        return self._record_handoff_write

    def _record_project_write(self, location: Location, size_bytes: int) -> None:
        self.writes.append(FileWrite(location, size_bytes))

    def _record_handoff_write(self, location: Location, size_bytes: int) -> None:
        self.writes.append(FileWrite(location, size_bytes, is_handoff=True))


class TranslateUsingPipeline(TranslateUseCase):
    def __init__(
        self,
        factories: LegFactories,
        reporter_builder: ReporterBuilder,
        filesystems: RunFilesystems,
        user_mappings_loader: UserMappingsLoader,
        validation_report: ValidationReportPort,
    ) -> None:
        self._factories = factories
        self._reporter_builder = reporter_builder
        self._filesystems = filesystems
        self._user_mappings_loader = user_mappings_loader
        self._validation_report = validation_report

    def __call__(
        self,
        source_framework: str,
        destination_framework: str,
        pipeline: str,
        *,
        overrides: NodeOverrides,
        keep_staging: bool = False,
        user_mappings_path: Location | None = None,
    ) -> TranslateResult:
        document = load_pipeline_document(pipeline)
        validate_frameworks(document, source_framework, destination_framework)
        request = CompositionRequest(pipeline=pipeline, document=document, overrides=overrides)
        with _run_scratch(keep_staging=keep_staging) as scratch:
            run = _Run(
                filesystems=self._filesystems,
                scratch=scratch,
                user_mappings_path=user_mappings_path,
                keep_staging=keep_staging,
            )
            # The decisions report is a run output, so it goes through the configured port.
            reporter = self._reporter_builder(run.track(handoff_directory=None))
            try:
                plan = plan_translation(request, load_leg_spec)
                self._run_plan(plan, run)
            finally:
                reporter.render(run.event_log.events)
            return TranslateResult(writes=list(run.writes))

    def _run_plan(self, plan: TranslationPlan, run: _Run) -> None:
        # Folded before any leg runs, so two legs writing one schema stop the run at the start.
        run.producers = self._user_mappings_loader.fold_produced_mappings(
            [LabelledSpec(leg.spec, leg.pipeline) for leg in plan.in_run_order]
        )
        for leg in plan.in_run_order:
            run.errors += self._run_leg(leg, run)
            run.mappings.update(self._derived_mappings(leg, run))

    def _derived_mappings(
        self, leg: PlannedLeg, run: _Run
    ) -> dict[type[UserMappings], MappingsFile]:
        """Each derived file carries the filesystem that wrote it, since it sits in the
        run's scratch space rather than anywhere the configured port can address.
        """
        filesystem = run.filesystem_for(leg.writes_handoff_to)
        return {
            schema: MappingsFile(
                to_location(read_param(leg.pipeline, leg.spec, producer.address)), filesystem
            )
            for schema, producer in run.producers.items()
            if producer.pipeline == leg.pipeline
        }

    def _run_leg(self, leg: PlannedLeg, run: _Run) -> list[EnergyModelValidationError]:
        user_mappings_lookup = self._load_user_mappings(leg, run)
        errors_so_far = list(run.errors)
        return run_pipeline(
            leg.spec,
            self._factories.source(run.track(leg.reads_handoff_from), user_mappings_lookup),
            self._factories.step(run.recorder_for(leg), user_mappings_lookup),
            self._factories.sink(run.track(leg.writes_handoff_to)),
            self._factories.validator(user_mappings_lookup),
            keep_staging=run.keep_staging,
            on_validators_complete=lambda found: self._validation_report.render(
                errors_so_far + found, DEFAULT_VALIDATION_REPORT_PATH
            ),
        )

    def _load_user_mappings(self, leg: PlannedLeg, run: _Run) -> UserMappingsLookup:
        """A derived file wins over the user's own, since the user never wrote the derived one."""
        files = dict(run.mappings)
        if run.user_mappings_path is not None:
            own = MappingsFile(run.user_mappings_path, run.configured_filesystem)
            for schema in self._user_mappings_loader.collect_schemas_for_translate(leg.spec):
                files.setdefault(schema, own)
        return self._user_mappings_loader.load_by_schema(leg.spec, files)
