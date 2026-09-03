from __future__ import annotations

import logging

from interop.core.cli_overrides import apply_overrides
from interop.core.composition.document import (
    load_leg_spec,
    load_pipeline_document,
    validate_frameworks,
)
from interop.core.composition.planning import (
    CompositionRequest,
    TranslationPlan,
    load_legs,
)
from interop.core.factories import SourceFactoryBuilder, ValidatorFactoryBuilder
from interop.core.runner import run_validation
from interop.core.user_mappings_loader import MappingsFile, UserMappingsLoader
from interop.ports.errors import UserInputError
from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.inbound.validate import ValidateResult, ValidateUseCase
from interop.ports.outbound.filesystem import FilesystemPort, Location
from interop.ports.outbound.validation_report import (
    DEFAULT_VALIDATION_REPORT_PATH,
    ValidationReportPort,
)

log = logging.getLogger(__name__)


class ValidateUsingPipeline(ValidateUseCase):
    def __init__(
        self,
        source_factory_builder: SourceFactoryBuilder,
        validator_factory_builder: ValidatorFactoryBuilder,
        validation_report: ValidationReportPort,
        user_mappings_loader: UserMappingsLoader,
        filesystem: FilesystemPort,
    ) -> None:
        self._source_factory_builder = source_factory_builder
        self._validator_factory_builder = validator_factory_builder
        self._validation_report = validation_report
        self._user_mappings_loader = user_mappings_loader
        self._filesystem = filesystem

    def __call__(
        self,
        source_framework: str,
        destination_framework: str,
        pipeline: str,
        *,
        overrides: NodeOverrides,
        keep_staging: bool = False,
        user_mappings_path: Location | None = None,
    ) -> ValidateResult:
        document = load_pipeline_document(pipeline)
        validate_frameworks(document, source_framework, destination_framework)
        # A chain's later legs have no input until the legs before them have run, so only
        # the first leg's validators can run without translating anything. The first leg is
        # also the one leg that can hold no reference, so it needs no planning.
        plan = load_legs(CompositionRequest(pipeline=pipeline, document=document), load_leg_spec)
        first_leg = plan.legs[0]
        spec = apply_overrides(first_leg.spec, overrides)
        self._reject_derived_input(pipeline, plan)

        own = (
            MappingsFile(user_mappings_path, self._filesystem)
            if user_mappings_path is not None
            else None
        )
        user_mappings_lookup = self._user_mappings_loader.load_for_validation(spec, own)

        errors = run_validation(
            spec,
            self._source_factory_builder(self._filesystem, user_mappings_lookup),
            self._validator_factory_builder(user_mappings_lookup),
            keep_staging=keep_staging,
            on_validators_complete=lambda found: self._validation_report.render(
                found, DEFAULT_VALIDATION_REPORT_PATH
            ),
        )
        return ValidateResult(errors=errors, validated_pipeline=first_leg.pipeline)

    def _reject_derived_input(self, pipeline: str, plan: TranslationPlan) -> None:
        required = self._user_mappings_loader.choose_validation_input(
            plan.legs[0].spec, [leg.spec for leg in plan.mappings]
        )
        if required.is_derived_elsewhere:
            derived = ", ".join(sorted(schema.__name__ for schema in required.derived_elsewhere))
            raise UserInputError(
                f"Validating {pipeline!r} needs user mappings ({derived}) that its own mapping "
                f"pipelines derive, and validate does not run them. Translate it instead, "
                f"which runs the mapping pipelines first."
            )
