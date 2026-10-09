"""Alan hataları. CLI bunları `code` + `message` olarak arayüze iletir."""

from __future__ import annotations


class EngineError(Exception):
    code = "ENGINE_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationFailed(EngineError):
    code = "VALIDATION"


class NotFound(EngineError):
    code = "NOT_FOUND"


class PermissionDenied(EngineError):
    code = "PERMISSION_DENIED"


class UnsafeUrl(ValidationFailed):
    code = "UNSAFE_URL"


class ProviderUnavailable(EngineError):
    """Dış kaynak yanıt vermiyor; kayıtlar silinmez, durum işaretlenir."""

    code = "PROVIDER_UNAVAILABLE"
