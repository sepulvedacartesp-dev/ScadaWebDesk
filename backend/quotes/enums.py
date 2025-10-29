from __future__ import annotations

from enum import Enum


class QuoteStatus(str, Enum):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    ACEPTADA = "aceptada"
    ANULADA = "anulada"
    EXPIRADA = "expirada"


FINAL_STATUSES = {QuoteStatus.ACEPTADA, QuoteStatus.ANULADA, QuoteStatus.EXPIRADA}


STATUS_TRANSITIONS = {
    QuoteStatus.BORRADOR: {QuoteStatus.BORRADOR, QuoteStatus.ENVIADA, QuoteStatus.ANULADA},
    QuoteStatus.ENVIADA: {
        QuoteStatus.BORRADOR,
        QuoteStatus.ENVIADA,
        QuoteStatus.ACEPTADA,
        QuoteStatus.ANULADA,
        QuoteStatus.EXPIRADA,
    },
    QuoteStatus.ACEPTADA: {QuoteStatus.ACEPTADA},
    QuoteStatus.ANULADA: {QuoteStatus.ANULADA},
    QuoteStatus.EXPIRADA: {QuoteStatus.EXPIRADA, QuoteStatus.ANULADA},
}


class QuoteEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    PDF_DOWNLOADED = "pdf_downloaded"
