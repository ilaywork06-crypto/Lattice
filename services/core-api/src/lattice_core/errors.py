"""Domain errors shared by every service."""


class DomainError(ValueError):
    """Raised on an invalid domain operation (mapped to HTTP 400).

    ``errors`` optionally carries structured, per-location problems (e.g. the
    cells of an import that failed validation) for the client to render.
    """

    def __init__(self, message: str, errors: list[dict] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []
