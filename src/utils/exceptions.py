"""Custom exceptions for the Data Quality Rules pipeline."""


class DQRBaseException(Exception):
    """Base exception for all Data Quality Rules exceptions."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(DQRBaseException):
    """Raised when there is a configuration error."""

    pass


class PDFProcessingError(DQRBaseException):
    """Raised when PDF processing fails."""

    pass


class EmbeddingError(DQRBaseException):
    """Raised when embedding generation fails."""

    pass


class RetrievalError(DQRBaseException):
    """Raised when document retrieval fails."""

    pass


class AttributeNotFoundError(DQRBaseException):
    """Raised when an attribute is not found in the cross-tab."""

    pass


class RAGRetrievalError(DQRBaseException):
    """Raised when RAG retrieval fails."""

    pass


class RuleGenerationError(DQRBaseException):
    """Raised when rule generation fails."""

    pass


class ExportError(DQRBaseException):
    """Raised when export to JSON/Excel fails."""

    pass
