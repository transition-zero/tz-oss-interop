from __future__ import annotations

from interop.core.composition.document import (
    list_pipelines_by_framework_pair,
    load_leg_spec,
    load_pipeline_document,
)
from interop.core.composition.planning import (
    CompositionRequest,
    TranslationPlan,
    load_legs,
)
from interop.core.factories import SchemaCatalog
from interop.core.runner import NodeSpec, list_results_pipelines_by_framework
from interop.core.user_mappings import UserMappings
from interop.core.user_mappings_loader import UserMappingsLoader
from interop.ports.inbound.pipeline_catalog import (
    FrameworkName,
    NodeStructure,
    PipelineCatalogUseCase,
    PipelineName,
    PipelineStructure,
)


class PipelineCatalog(PipelineCatalogUseCase):
    def __init__(
        self, schema_catalog: SchemaCatalog, user_mappings_loader: UserMappingsLoader
    ) -> None:
        self._schema_catalog = schema_catalog
        self._user_mappings_loader = user_mappings_loader

    def by_framework_pair(
        self,
    ) -> dict[tuple[FrameworkName, FrameworkName], list[PipelineName]]:
        return list_pipelines_by_framework_pair()

    def results_pipelines_by_framework(self) -> dict[FrameworkName, list[PipelineName]]:
        return list_results_pipelines_by_framework()

    def get_structure(self, name: str) -> PipelineStructure:
        """For a chain, the first leg's source and the last leg's sinks. Its interior legs
        take their own defaults or a reference, so they have nothing to ask about.

        The chain rules are the run's business, not the menu's, so the legs are loaded
        rather than planned.
        """
        document = load_pipeline_document(name)
        plan = load_legs(CompositionRequest(pipeline=name, document=document), load_leg_spec)
        first, last = plan.legs[0], plan.final
        return PipelineStructure(
            source_framework=document.source_framework,
            destination_framework=document.destination_framework,
            source=self._node("sources", first.spec.source),
            steps=tuple(self._node("steps", step) for step in _promptable_steps(plan)),
            sinks=tuple(self._node("sinks", sink) for sink in last.spec.sinks),
            needs_user_mappings=self._needs_user_mappings(plan),
            validation_needs_user_mappings=self._validation_needs_user_mappings(plan),
        )

    def _validation_needs_user_mappings(self, plan: TranslationPlan) -> bool:
        return self._user_mappings_loader.choose_validation_input(
            plan.legs[0].spec, [leg.spec for leg in plan.mappings]
        ).should_ask_the_user

    def _needs_user_mappings(self, plan: TranslationPlan) -> bool:
        """Ask the user only for a schema no earlier leg derives. A leg that runs later
        cannot satisfy this one: its file does not exist yet.
        """
        derived: frozenset[type[UserMappings]] = frozenset()
        for leg in plan.in_run_order:
            if self._user_mappings_loader.collect_schemas_for_translate(leg.spec) - derived:
                return True
            derived |= self._user_mappings_loader.collect_produced_mappings(leg.spec).keys()
        return False

    def _node(self, category: str, node: NodeSpec) -> NodeStructure:
        return NodeStructure(
            name=node.name,
            yaml_params=dict(node.params),
            params_schema=self._schema_catalog(category, node.name),
        )


def _promptable_steps(plan: TranslationPlan) -> list[NodeSpec]:
    """A chain's steps all sit in its interior, so only a lone pipeline prompts for any."""
    if len(plan.legs) > 1:
        return []
    return list(plan.legs[0].spec.steps)
