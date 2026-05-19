"""
Centralized error logging utility for Document Manager.
Provides consistent logging across the application with proper error tracking.
"""

import logging
import sys
import os
from pathlib import Path
from typing import Optional, Any
from datetime import datetime


class ErrorLogger:
    """Centralized error logging utility."""
    
    _instance: Optional['ErrorLogger'] = None
    _logger: Optional[logging.Logger] = None
    
    def __new__(cls) -> 'ErrorLogger':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._logger is None:
            self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Setup logging configuration."""
        # Create logger
        self._logger = logging.getLogger('document_manager')
        self._logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate handlers
        if self._logger.handlers:
            return
        
        # Create logs directory
        logs_dir = Path(__file__).parent.parent.parent / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # File handler for errors
        error_log_file = logs_dir / "errors.log"
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        
        # File handler for all logs
        all_log_file = logs_dir / "document_manager.log"
        debug_handler = logging.FileHandler(all_log_file, encoding='utf-8')
        debug_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s'
        )
        
        # Set formatters
        error_handler.setFormatter(formatter)
        debug_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers
        self._logger.addHandler(error_handler)
        self._logger.addHandler(debug_handler)
        self._logger.addHandler(console_handler)
    
    def error(self, message: str, exception: Optional[Exception] = None, context: Optional[dict] = None) -> None:
        """Log an error with optional exception and context."""
        if context:
            context_str = f" | Context: {context}"
        else:
            context_str = ""
        
        if exception:
            self._logger.error(f"{message} | Exception: {type(exception).__name__}: {str(exception)}{context_str}", 
                             exc_info=exception)
        else:
            self._logger.error(f"{message}{context_str}")
    
    def warning(self, message: str, context: Optional[dict] = None) -> None:
        """Log a warning with optional context."""
        if context:
            context_str = f" | Context: {context}"
        else:
            context_str = ""
        self._logger.warning(f"{message}{context_str}")
    
    def info(self, message: str, context: Optional[dict] = None) -> None:
        """Log an info message with optional context."""
        if context:
            context_str = f" | Context: {context}"
        else:
            context_str = ""
        self._logger.info(f"{message}{context_str}")
    
    def debug(self, message: str, context: Optional[dict] = None) -> None:
        """Log a debug message with optional context."""
        if context:
            context_str = f" | Context: {context}"
        else:
            context_str = ""
        self._logger.debug(f"{message}{context_str}")
    
    def log_database_error(self, operation: str, exception: Exception, document_id: Optional[int] = None) -> None:
        """Log database-specific errors with consistent format."""
        context = {"operation": operation}
        if document_id:
            context["document_id"] = document_id
        
        self.error(f"Database operation failed: {operation}", exception, context)
    
    def log_file_operation_error(self, operation: str, file_path: str, exception: Exception) -> None:
        """Log file operation errors with consistent format."""
        context = {"operation": operation, "file_path": file_path}
        self.error(f"File operation failed: {operation}", exception, context)
    
    def log_network_error(self, operation: str, endpoint: Optional[str], exception: Exception) -> None:
        """Log network/authentication errors with consistent format."""
        context = {"operation": operation}
        if endpoint:
            context["endpoint"] = endpoint
        
        self.error(f"Network operation failed: {operation}", exception, context)
    
    def log_ui_error(self, component: str, operation: str, exception: Exception) -> None:
        """Log UI-specific errors with consistent format."""
        context = {"component": component, "operation": operation}
        self.error(f"UI operation failed in {component}: {operation}", exception, context)


# Global logger instance
logger = ErrorLogger()


def log_exception_context(operation: str, context: Optional[dict] = None):
    """Decorator to automatically log exceptions with context."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_context = context or {}
                error_context.update({
                    "function": func.__name__,
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys()) if kwargs else []
                })
                logger.error(f"Exception in {operation}", e, error_context)
                raise
        return wrapper
    return decorator