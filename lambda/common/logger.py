"""
Structured logging utility for rewards program Lambda functions.

This module provides structured JSON logging with correlation IDs,
log sampling for high-volume operations, and consistent log formatting
across all Lambda functions.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from functools import wraps
import boto3


class StructuredLogger:
    """
    Structured logger that outputs JSON formatted logs with correlation IDs
    and consistent metadata across all Lambda functions.
    """
    
    def __init__(self, service_name: str, log_level: str = "INFO"):
        self.service_name = service_name
        self.correlation_id = str(uuid.uuid4())
        
        # Configure Python logging
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Remove default handlers and add structured handler
        self.logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter(service_name, self.correlation_id))
        self.logger.addHandler(handler)
        
        # Prevent duplicate logs
        self.logger.propagate = False
    
    def set_correlation_id(self, correlation_id: str) -> None:
        """Set correlation ID for request tracing."""
        self.correlation_id = correlation_id
        # Update formatter with new correlation ID
        for handler in self.logger.handlers:
            if isinstance(handler.formatter, StructuredFormatter):
                handler.formatter.correlation_id = correlation_id
    
    def info(self, message: str, **kwargs) -> None:
        """Log info level message with structured data."""
        self._log(logging.INFO, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error level message with structured data."""
        self._log(logging.ERROR, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning level message with structured data."""
        self._log(logging.WARNING, message, **kwargs)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug level message with structured data."""
        self._log(logging.DEBUG, message, **kwargs)
    
    def _log(self, level: int, message: str, **kwargs) -> None:
        """Internal method to log with structured data."""
        extra = {
            'structured_data': kwargs
        }
        self.logger.log(level, message, extra=extra)


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured JSON logs with consistent metadata.
    """
    
    def __init__(self, service_name: str, correlation_id: str):
        super().__init__()
        self.service_name = service_name
        self.correlation_id = correlation_id
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": self.service_name,
            "correlation_id": self.correlation_id,
            "message": record.getMessage(),
            "logger": record.name,
            "function_name": os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown'),
            "function_version": os.environ.get('AWS_LAMBDA_FUNCTION_VERSION', 'unknown'),
            "request_id": getattr(record, 'aws_request_id', 'unknown'),
        }
        
        # Add structured data if present
        if hasattr(record, 'structured_data'):
            log_entry.update(record.structured_data)
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, default=str)


class LogSampler:
    """
    Log sampling utility for high-volume operations to reduce log noise
    while maintaining visibility into system behavior.
    """
    
    def __init__(self, sample_rate: float = 0.1):
        """
        Initialize log sampler.
        
        Args:
            sample_rate: Fraction of logs to sample (0.0 to 1.0)
        """
        self.sample_rate = sample_rate
        self._counter = 0
    
    def should_log(self) -> bool:
        """Determine if current operation should be logged based on sampling rate."""
        self._counter += 1
        return (self._counter % int(1 / self.sample_rate)) == 0


def with_structured_logging(service_name: str):
    """
    Decorator to add structured logging to Lambda handler functions.
    
    This decorator:
    - Creates a structured logger instance
    - Extracts correlation ID from Lambda context
    - Logs function entry and exit
    - Handles exceptions with structured logging
    """
    def decorator(func):
        @wraps(func)
        def wrapper(event, context):
            # Create logger instance
            logger = StructuredLogger(service_name)
            
            # Extract correlation ID from context or generate new one
            correlation_id = getattr(context, 'aws_request_id', str(uuid.uuid4()))
            logger.set_correlation_id(correlation_id)
            
            # Log function entry
            logger.info(
                f"Lambda function {func.__name__} started",
                event_type=event.get('detail-type') if isinstance(event, dict) else 'unknown',
                function_name=context.function_name if hasattr(context, 'function_name') else 'unknown',
                remaining_time_ms=context.get_remaining_time_in_millis() if hasattr(context, 'get_remaining_time_in_millis') else 0
            )
            
            try:
                # Execute the function with logger available
                result = func(event, context, logger)
                
                # Log successful completion
                logger.info(
                    f"Lambda function {func.__name__} completed successfully",
                    execution_time_ms=context.get_remaining_time_in_millis() if hasattr(context, 'get_remaining_time_in_millis') else 0
                )
                
                return result
                
            except Exception as e:
                # Log exception with structured data
                logger.error(
                    f"Lambda function {func.__name__} failed with exception",
                    exception_type=type(e).__name__,
                    exception_message=str(e),
                    function_name=context.function_name if hasattr(context, 'function_name') else 'unknown'
                )
                raise
        
        return wrapper
    return decorator


def create_xray_subsegment(name: str, metadata: Optional[Dict[str, Any]] = None):
    """
    Create X-Ray subsegment for detailed tracing.
    
    Args:
        name: Subsegment name
        metadata: Additional metadata to include in subsegment
    """
    try:
        from aws_xray_sdk.core import xray_recorder
        
        subsegment = xray_recorder.begin_subsegment(name)
        if metadata:
            subsegment.put_metadata('rewards_program', metadata)
        return subsegment
    except ImportError:
        # X-Ray SDK not available, return dummy context manager
        class DummySubsegment:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return DummySubsegment()


def log_dynamodb_operation(logger: StructuredLogger, operation: str, table_name: str, 
                          key: Optional[Dict] = None, success: bool = True, 
                          error: Optional[str] = None, duration_ms: Optional[float] = None):
    """
    Log DynamoDB operations with consistent structure.
    
    Args:
        logger: Structured logger instance
        operation: DynamoDB operation (get_item, put_item, update_item, etc.)
        table_name: DynamoDB table name
        key: Item key (optional, for privacy may be omitted)
        success: Whether operation succeeded
        error: Error message if operation failed
        duration_ms: Operation duration in milliseconds
    """
    log_data = {
        'operation': 'dynamodb',
        'dynamodb_operation': operation,
        'table_name': table_name,
        'success': success,
    }
    
    if key:
        # Log key structure but not values for privacy
        log_data['key_structure'] = list(key.keys()) if key else None
    
    if error:
        log_data['error'] = error
    
    if duration_ms:
        log_data['duration_ms'] = duration_ms
    
    if success:
        logger.info(f"DynamoDB {operation} completed", **log_data)
    else:
        logger.error(f"DynamoDB {operation} failed", **log_data)


def log_event_processing(logger: StructuredLogger, event_type: str, 
                        member_id: Optional[str] = None, success: bool = True,
                        error: Optional[str] = None, **kwargs):
    """
    Log event processing with consistent structure.
    
    Args:
        logger: Structured logger instance
        event_type: Type of event being processed
        member_id: Member ID (optional, may be masked for privacy)
        success: Whether processing succeeded
        error: Error message if processing failed
        **kwargs: Additional event-specific data
    """
    log_data = {
        'operation': 'event_processing',
        'event_type': event_type,
        'success': success,
    }
    
    if member_id:
        # Mask member ID for privacy (show only first 8 characters)
        log_data['member_id_masked'] = member_id[:8] + '...' if len(member_id) > 8 else member_id
    
    if error:
        log_data['error'] = error
    
    log_data.update(kwargs)
    
    if success:
        logger.info(f"Event processing completed: {event_type}", **log_data)
    else:
        logger.error(f"Event processing failed: {event_type}", **log_data)