"""Error types shared across CLI feature modules."""


class UserFacingError(Exception):
    """A concise error intended to be shown directly to CLI users."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics = None
    ) -> None:
        """Store the message together with optional structured diagnostics."""

        super().__init__(message)
        self.diagnostics = diagnostics
