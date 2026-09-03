class UserInputError(Exception):
    """Raised when user-supplied input (CLI flags, pipeline YAML, plugin source)
    is invalid in a way the surface should report as a one-line
    message rather than a Python traceback."""


class MissingInputError(UserInputError, FileNotFoundError):
    """A file a source was pointed at that its filesystem cannot read."""

    def __init__(self, node: str, description: str, shown_path: str) -> None:
        super().__init__(
            f"Source node {node!r} cannot read the {description} it was given: "
            f"{shown_path}. Check the path, and that the file exists."
        )
        self.node = node
        self.description = description
        self.shown_path = shown_path
