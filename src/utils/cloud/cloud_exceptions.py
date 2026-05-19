"""
Cloud Sync Exception Classes
Specific error types for cloud operations
"""


class CloudSyncError(Exception):
    """Base exception for cloud sync operations"""
    def __init__(self, message: str, service: str = None, details: dict = None):
        super().__init__(message)
        self.service = service
        self.details = details or {}
    
    def __str__(self):
        if self.service:
            return f"[{self.service}] {super().__str__()}"
        return super().__str__()


class CloudAuthenticationError(CloudSyncError):
    """Raised when cloud authentication fails or tokens are invalid"""
    pass


class CloudUploadError(CloudSyncError):
    """Raised when file upload to cloud storage fails"""
    pass


class CloudDownloadError(CloudSyncError):
    """Raised when file download from cloud storage fails"""
    pass


class CloudDeleteError(CloudSyncError):
    """Raised when file deletion from cloud storage fails"""
    pass


class CloudQuotaExceededError(CloudSyncError):
    """Raised when cloud storage quota is exceeded"""
    pass


class CloudConnectionError(CloudSyncError):
    """Raised when unable to connect to cloud service"""
    pass


class CloudTimeoutError(CloudSyncError):
    """Raised when cloud operation times out"""
    pass


class CloudConfigurationError(CloudSyncError):
    """Raised when cloud configuration is invalid"""
    pass


class CloudFileNotFoundError(CloudSyncError):
    """Raised when requested file is not found in cloud storage"""
    pass


class CloudVersioningError(CloudSyncError):
    """Raised when version management operations fail"""
    pass


class CloudSafetyError(CloudSyncError):
    """Raised when safety checks prevent potentially dangerous operations"""
    pass


class CloudValidationError(CloudSyncError):
    """Raised when file or data validation fails"""
    pass


# Convenience functions for raising specific errors
def raise_auth_error(service: str, message: str, details: dict = None):
    """Raise authentication error with service context"""
    raise CloudAuthenticationError(message, service=service, details=details)


def raise_upload_error(service: str, filename: str, error: str, details: dict = None):
    """Raise upload error with file context"""
    raise CloudUploadError(f"Upload failed for {filename}: {error}", service=service, details=details)


def raise_safety_error(operation: str, reason: str, details: dict = None):
    """Raise safety error for dangerous operations"""
    raise CloudSafetyError(f"Safety check failed for {operation}: {reason}", details=details)


def raise_validation_error(filename: str, reason: str, details: dict = None):
    """Raise validation error for invalid files"""
    raise CloudValidationError(f"Validation failed for {filename}: {reason}", details=details)