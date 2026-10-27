"""
Logging configuration for translate_agent.

Provides structured logging with file rotation, console output, and request tracing.
"""

import logging
import logging.handlers
import os
from typing import Optional
from config import config


# Global logger instance
_logger: Optional[logging.Logger] = None


def setup_logging(log_level: str = None, log_dir: str = None) -> logging.Logger:
    """
    Initialize and configure the logging system.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                   Defaults to config.log_level.
        log_dir: Directory for log files. Defaults to config.log_dir.
    
    Returns:
        Configured logger instance.
    """
    global _logger
    
    if _logger is not None:
        return _logger
    
    log_level = (log_level or config.log_level).upper()
    log_dir = log_dir or config.log_dir
    
    # Create logger
    _logger = logging.getLogger("translate_agent")
    _logger.setLevel(getattr(logging, log_level))
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # File handler with rotation (10MB max, keep 5 backups)
    log_file = os.path.join(log_dir, "translate_agent.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
    )
    file_handler.setLevel(getattr(logging, log_level))
    
    # Console handler for immediate feedback
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    
    # Formatter with timestamp, level, logger name, and message
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    _logger.addHandler(file_handler)
    _logger.addHandler(console_handler)
    
    _logger.info("=" * 80)
    _logger.info(f"Logging initialized - Level: {log_level}, Dir: {log_dir}")
    _logger.info("=" * 80)
    
    return _logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get or create a logger instance.
    
    Args:
        name: Logger name (typically __name__ of calling module).
              Defaults to "translate_agent".
    
    Returns:
        Logger instance.
    """
    if _logger is None:
        setup_logging()
    
    if name:
        return logging.getLogger(name)
    return _logger


class LoggerAdapter:
    """
    Adapter to inject request/task context into all logs.
    
    Usage:
        adapter = LoggerAdapter("task_123")
        adapter.info("Processing started")  # Logs with task_id context
    """
    
    def __init__(self, context: str = None, context_type: str = "task_id"):
        """
        Args:
            context: Context value (e.g., task_id, request_id).
            context_type: Type of context (e.g., "task_id", "request_id").
        """
        self.logger = get_logger()
        self.context = context
        self.context_type = context_type
    
    def _format_message(self, message: str) -> str:
        """Add context to message."""
        if self.context:
            return f"[{self.context_type}={self.context}] {message}"
        return message
    
    def debug(self, message: str, *args, **kwargs):
        self.logger.debug(self._format_message(message), *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        self.logger.info(self._format_message(message), *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        self.logger.warning(self._format_message(message), *args, **kwargs)
    
    def error(self, message: str, *args, exc_info=False, **kwargs):
        self.logger.error(self._format_message(message), *args, exc_info=exc_info, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        self.logger.critical(self._format_message(message), *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """Log an exception with full traceback."""
        self.logger.exception(self._format_message(message), *args, **kwargs)


# Convenience function
def get_task_logger(task_id: str) -> LoggerAdapter:
    """Get a logger adapter for a specific task."""
    return LoggerAdapter(task_id, "task_id")
