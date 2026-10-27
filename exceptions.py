"""
Custom exception classes for translate_agent.

Provides structured exception hierarchy for better error handling,
logging, and debugging across the translation pipeline.
"""


class TranslationError(Exception):
    """Base exception for translation pipeline errors."""
    
    def __init__(self, message: str, error_code: str = "UNKNOWN_ERROR", details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self):
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ModelCallError(TranslationError):
    """Failed to call LLM (API error, timeout, unavailable model, etc)."""
    
    def __init__(self, message: str, model_name: str = None, details: dict = None):
        error_code = "MODEL_CALL_ERROR"
        if details is None:
            details = {}
        if model_name:
            details["model"] = model_name
        super().__init__(message, error_code, details)


class ModelTimeoutError(ModelCallError):
    """LLM call timed out."""
    
    def __init__(self, model_name: str, timeout_seconds: float):
        message = f"Model {model_name} call timed out after {timeout_seconds}s"
        super().__init__(message, model_name, {"timeout_seconds": timeout_seconds})
        self.error_code = "MODEL_TIMEOUT_ERROR"


class GlossaryGenerationError(TranslationError):
    """Failed to generate glossary."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "GLOSSARY_GENERATION_ERROR", details)


class FileIOError(TranslationError):
    """File read/write operation failed."""
    
    def __init__(self, message: str, file_path: str = None, operation: str = None):
        details = {}
        if file_path:
            details["file_path"] = file_path
        if operation:
            details["operation"] = operation
        super().__init__(message, "FILE_IO_ERROR", details)


class FileConversionError(FileIOError):
    """Failed to convert file format (e.g., .doc to .docx)."""
    
    def __init__(self, message: str, input_format: str, output_format: str, file_path: str = None):
        details = {
            "input_format": input_format,
            "output_format": output_format,
        }
        if file_path:
            details["file_path"] = file_path
        super().__init__(message, file_path, f"convert_{input_format}_to_{output_format}")
        self.error_code = "FILE_CONVERSION_ERROR"


class TranslationQualityError(TranslationError):
    """Translation quality check failed."""
    
    def __init__(self, message: str, quality_report: dict = None):
        details = {"quality_report": quality_report} if quality_report else {}
        super().__init__(message, "TRANSLATION_QUALITY_ERROR", details)


class InvalidConfigError(TranslationError):
    """Configuration is invalid or missing required values."""
    
    def __init__(self, message: str, config_key: str = None):
        details = {}
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, "INVALID_CONFIG_ERROR", details)


class ResourceLimitError(TranslationError):
    """Resource limit exceeded (file size, concurrent tasks, etc)."""
    
    def __init__(self, message: str, limit_type: str = None, current_value: any = None, limit: any = None):
        details = {}
        if limit_type:
            details["limit_type"] = limit_type
        if current_value is not None:
            details["current_value"] = current_value
        if limit is not None:
            details["limit"] = limit
        super().__init__(message, "RESOURCE_LIMIT_ERROR", details)


class ConcurrencyError(TranslationError):
    """Concurrency-related error (race condition, deadlock, etc)."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "CONCURRENCY_ERROR", details)


class TaskNotFoundError(TranslationError):
    """Task with given ID not found."""
    
    def __init__(self, task_id: str):
        message = f"Task {task_id} not found"
        super().__init__(message, "TASK_NOT_FOUND", {"task_id": task_id})


class TaskStateError(TranslationError):
    """Task is in an invalid state for the requested operation."""
    
    def __init__(self, task_id: str, current_state: str, expected_state: str = None):
        message = f"Task {task_id} is in state '{current_state}'"
        if expected_state:
            message += f", expected '{expected_state}'"
        details = {
            "task_id": task_id,
            "current_state": current_state,
        }
        if expected_state:
            details["expected_state"] = expected_state
        super().__init__(message, "TASK_STATE_ERROR", details)


def is_recoverable_error(exc: TranslationError) -> bool:
    """Determine if an error is recoverable (can retry)."""
    recoverable_codes = {
        "MODEL_TIMEOUT_ERROR",
        "MODEL_CALL_ERROR",  # Some model errors are retriable
        "FILE_IO_ERROR",      # Transient file issues might recover
    }
    return exc.error_code in recoverable_codes


def error_message_for_user(exc: TranslationError) -> str:
    """Convert technical error to user-friendly message."""
    user_messages = {
        "MODEL_TIMEOUT_ERROR": "Translation service is busy, please try again later.",
        "MODEL_CALL_ERROR": "Failed to reach translation service, please check your API key.",
        "FILE_IO_ERROR": "Failed to process file, please check file format and permissions.",
        "FILE_CONVERSION_ERROR": "Failed to convert file format, please ensure you have the required software installed.",
        "TRANSLATION_QUALITY_ERROR": "Translation quality check failed, output may be incomplete.",
        "INVALID_CONFIG_ERROR": "Service configuration error, please contact administrator.",
        "RESOURCE_LIMIT_ERROR": "Resource limit exceeded, please try with a smaller file.",
        "TASK_NOT_FOUND": "Task not found, it may have been cleaned up.",
    }
    return user_messages.get(exc.error_code, "An unexpected error occurred.")
