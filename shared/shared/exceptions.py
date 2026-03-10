from __future__ import annotations


class AppException(Exception):
    """Base class for all application exceptions."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(AppException):
    """Raised when JWT is missing, expired, or invalid."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class AuthorizationError(AppException):
    """Raised when user lacks permission for the action."""

    def __init__(self, message: str = "Not authorized") -> None:
        super().__init__(message, status_code=403)


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found", status_code=404)


class ValidationError(AppException):
    """Raised when business-level validation fails (not Pydantic)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class ServiceUnavailableError(AppException):
    """Raised when a downstream service cannot be reached."""

    def __init__(self, service: str = "Upstream service") -> None:
        super().__init__(f"{service} is unavailable", status_code=503)
