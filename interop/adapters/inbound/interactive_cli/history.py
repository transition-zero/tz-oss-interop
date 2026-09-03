from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, NotRequired, TypedDict

HISTORY_LIMIT = 30


class DetailKey(StrEnum):
    """Keys of an Invocation's ``details`` payload (the answers given at the prompts)."""

    SOURCE_FRAMEWORK = "source_framework"
    DESTINATION_FRAMEWORK = "destination_framework"
    PIPELINE_NAME = "pipeline_name"
    SOURCE_OVERRIDES = "source_overrides"
    STEP_OVERRIDES = "step_overrides"
    SINK_OVERRIDES = "sink_overrides"
    USER_MAPPINGS_PATH = "user_mappings_path"
    TARGET = "target"
    MODEL_TYPE = "model_type"
    SIENNA_JSON_PATH = "sienna_json_path"
    NETWORK_MODEL = "network_model"
    OUTPUT_DIR = "output_dir"
    SOLVER = "solver"
    PRESOLVE = "presolve"
    RUN_CROSSOVER = "run_crossover"
    TIME_LIMIT_SECONDS = "time_limit_seconds"
    NETWORK_PATH = "network_path"
    START_DATE = "start_date"
    END_DATE = "end_date"
    UNIT_COMMITMENT = "unit_commitment"
    SOLVE_WINDOW = "solve_window"
    LOOK_AHEAD_DAYS = "look_ahead_days"
    EXAMPLE = "example"
    SIDE_A_FRAMEWORK = "side_a_framework"
    SIDE_A_PIPELINE = "side_a_pipeline"
    SIDE_A_PARAMS = "side_a_params"
    SIDE_B_FRAMEWORK = "side_b_framework"
    SIDE_B_PIPELINE = "side_b_pipeline"
    SIDE_B_PARAMS = "side_b_params"
    OUTPUT_PATH = "output_path"


class Invocation(TypedDict):
    command: str
    timestamp: str  # ISO-8601 UTC
    details: NotRequired[dict[str, Any]]


def default_history_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "interop" / "interactive_history.json"


@dataclass
class History:
    path: Path
    invocations: list[Invocation] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> History:
        path = path or default_history_path()
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(path=path, invocations=list(data.get("invocations", [])))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"invocations": self.invocations}, indent=2), encoding="utf-8"
        )

    def record(self, command: str, details: dict[str, Any] | None = None) -> None:
        entry: Invocation = {
            "command": command,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        if details is not None:
            entry["details"] = details
        self.invocations.append(entry)
        if len(self.invocations) > HISTORY_LIMIT:
            self.invocations = self.invocations[-HISTORY_LIMIT:]
        self.save()

    def recent(self, limit: int = HISTORY_LIMIT) -> list[Invocation]:
        return list(reversed(self.invocations[-limit:]))
