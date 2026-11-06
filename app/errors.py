"""Domain exceptions. The API layer turns these into ``{"error": "<message>"}`` JSON responses."""


class AppError(Exception):
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequest(AppError):
    status_code = 400


class Unauthorized(AppError):
    status_code = 401


class NotFound(AppError):
    status_code = 404


class Gone(AppError):
    status_code = 410


class TooManyRequests(AppError):
    status_code = 429


class BadGateway(AppError):
    """An upstream service (e.g. Shopify) failed or rejected our request."""

    status_code = 502
