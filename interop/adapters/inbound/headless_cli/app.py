from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Mapping, Sequence
from typing import ClassVar

from dishka import Container

from interop.adapters.inbound.base import Launcher
from interop.adapters.inbound.headless_cli.overrides import (
    merge_overrides,
    parse_override_env,
    parse_override_flags,
)
from interop.ports.errors import UserInputError
from interop.ports.inbound.pipeline_catalog import PipelineCatalogUseCase
from interop.ports.inbound.translate import TranslateUseCase
from interop.ports.outbound.filesystem import to_location

log = logging.getLogger(__name__)

PIPELINE_ENV_VAR = "INTEROP_PIPELINE"
USER_MAPPINGS_PATH_ENV_VAR = "INTEROP_USER_MAPPINGS_PATH"
KEEP_STAGING_ENV_VAR = "INTEROP_KEEP_STAGING"
_KEEP_STAGING_TRUTHY = {"1", "true", "yes", "y", "on"}


def _parse_bool_env(value: str) -> bool:
    return value.strip().lower() in _KEEP_STAGING_TRUTHY


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interop headless_cli",
        description="Run a single translate pipeline non-interactively (no prompts, no menu).",
    )
    parser.add_argument("--pipeline", default=None)
    parser.add_argument(
        "--override", action="append", default=[], dest="overrides", metavar="KEY=VALUE"
    )
    parser.add_argument("--user-mappings-path", default=None)
    parser.add_argument("--keep-staging", action="store_true", default=False)
    return parser


def run_headless(container: Container, argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Parse argv/env, run the translate use case, and return a process exit code.

    Flags win over environment variables when both set the same value; for
    --override/INTEROP_OVERRIDE_*, env and flags are merged field-by-field with
    flag-sourced entries winning on collision.
    """
    args = _build_arg_parser().parse_args(argv)

    pipeline_name = args.pipeline or env.get(PIPELINE_ENV_VAR)
    if not pipeline_name:
        log.error("headless: --pipeline (or %s) is required", PIPELINE_ENV_VAR)
        return 1

    try:
        overrides = merge_overrides(parse_override_env(env), parse_override_flags(args.overrides))
    except UserInputError as exc:
        log.error("headless: %s", exc)
        return 1

    raw_user_mappings_path = args.user_mappings_path or env.get(USER_MAPPINGS_PATH_ENV_VAR)
    user_mappings_path = to_location(raw_user_mappings_path) if raw_user_mappings_path else None
    if args.keep_staging:
        keep_staging = True
    elif KEEP_STAGING_ENV_VAR in env:
        keep_staging = _parse_bool_env(env[KEEP_STAGING_ENV_VAR])
    else:
        keep_staging = False

    with container() as scope:
        try:
            catalog = scope.get(PipelineCatalogUseCase)
            structure = catalog.get_structure(pipeline_name)
        except Exception as exc:
            log.error("headless: failed to load pipeline %r: %s", pipeline_name, exc)
            return 1

        start = time.monotonic()
        try:
            use_case = scope.get(TranslateUseCase)
            result = use_case(
                structure.source_framework,
                structure.destination_framework,
                pipeline_name,
                overrides=overrides,
                keep_staging=keep_staging,
                user_mappings_path=user_mappings_path,
            )
        except Exception as exc:
            log.error("headless: translate failed: %s", exc)
            return 1

    log.info(result.summary(pipeline_name, time.monotonic() - start))
    return 0


class HeadlessCli(Launcher):
    name: ClassVar[str] = "headless_cli"

    def run(self, container: Container) -> None:
        sys.exit(run_headless(container, sys.argv[1:], os.environ))
