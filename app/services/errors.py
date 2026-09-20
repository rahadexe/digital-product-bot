"""Expected, user-facing failures. The API maps them to HTTP status codes."""


class ServiceError(Exception):
    pass


class NotFoundError(ServiceError):
    pass


class InvalidInputError(ServiceError, ValueError):
    pass


class PermissionDeniedError(ServiceError):
    pass

