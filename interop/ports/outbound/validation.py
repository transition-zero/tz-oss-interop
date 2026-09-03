from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from interop.ports.errors import UserInputError


class ValidationSeverity(StrEnum):
    """How a validator's finding bears on the translation.

    CRITICAL says the input cannot be translated, so a translate run stops on one.
    WARNING says the input is unusual but translatable, and a run carries on.
    """

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"


class ValidationFailedError(UserInputError):
    """Raised when a translate run's validators found the input untranslatable.

    Carries the findings so a caller can report them, though the validation report is
    written before this is raised and is where a user reads the detail.
    """

    def __init__(self, errors: list[EnergyModelValidationError]) -> None:
        self.errors = errors
        validators = ", ".join(sorted({error.validator for error in errors}))
        issues = "issue" if len(errors) == 1 else "issues"
        super().__init__(
            f"{len(errors)} CRITICAL validation {issues} from {validators}; "
            "the input cannot be translated"
        )


class ValidatorCrashedError(Exception):
    """Raised when a validator itself failed, rather than finding fault with the input.

    Not a `UserInputError`: nothing the user supplied is wrong, so there is nothing for
    them to fix. It names the validator because the traceback of the underlying error
    points into that validator's own code, not at the node the pipeline declared.
    """

    def __init__(self, validator: str, cause: BaseException) -> None:
        self.validator = validator
        super().__init__(f"validator {validator!r} failed to run: {cause}")


@dataclass(frozen=True)
class EnergyModelValidationError:
    validator: str
    severity: ValidationSeverity
    component: str
    name: str
    message: str
    attribute: str | None = None
    value: object = None
