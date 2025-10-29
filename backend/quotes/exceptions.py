class QuoteError(Exception):
    """Errores base del módulo de cotizaciones."""


class QuoteNotFoundError(QuoteError):
    """Se lanza cuando la cotización no existe o no pertenece a la empresa."""


class InvalidStatusTransition(QuoteError):
    """Transición de estado no permitida."""


class CatalogError(QuoteError):
    """Errores relacionados con el catálogo."""


class ClientExistsError(QuoteError):
    """Ya existe un cliente con el mismo RUT dentro de la empresa."""
