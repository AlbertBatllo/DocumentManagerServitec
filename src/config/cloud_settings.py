"""
Cloud Sync Configuration Settings
Centralized configuration for cloud operations
"""

from pathlib import Path
import json
from typing import Dict, Any


class CloudSettings:
    """Centralized cloud settings configuration"""
    
    # Default settings
    DEFAULT_SETTINGS = {
        "max_deletions_per_run": 1,      # Maximum files to delete in one operation
        "chunk_size_mb": 4,              # Upload chunk size in MB
        "versions_to_keep": 2,           # Number of versions to keep per document
        "google_drive_chunk_size_mb": 5, # Google Drive specific chunk size
        "sharepoint_chunk_size_mb": 4,   # SharePoint specific chunk size
        "retry_attempts": 3,             # Number of retry attempts for failed operations
        "timeout_seconds": 30            # Timeout for cloud operations
    }
    
    def __init__(self, project_path: Path = None):
        from utils.path_helper import PathHelper
        self.config_path = PathHelper.get_config_file_path("cloud_settings.json", project_path)
        self.settings = self.load_settings()
    
    def load_settings(self) -> Dict[str, Any]:
        """Load settings from config file or use defaults"""
        if self.config_path.exists():
            try:
                from utils.file_manager import FileManager
                return {**self.DEFAULT_SETTINGS, **FileManager.safe_json_read(str(self.config_path))}
            except Exception:
                # Fall back to defaults if config is corrupted
                return self.DEFAULT_SETTINGS.copy()
        else:
            # Create default config file
            self.save_settings(self.DEFAULT_SETTINGS)
            return self.DEFAULT_SETTINGS.copy()
    
    def save_settings(self, settings: Dict[str, Any]) -> None:
        """Save settings to config file"""
        try:
            from utils.file_manager import FileManager
            self.config_path.parent.mkdir(exist_ok=True)
            FileManager.safe_json_write(str(self.config_path), settings)
            self.settings = settings
        except Exception as e:
            raise RuntimeError(f"Could not save cloud settings: {e}")
    
    def get(self, key: str, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)
    
    def set(self, key: str, value) -> None:
        """Set a setting value and save"""
        self.settings[key] = value
        self.save_settings(self.settings)
    
    # Convenience properties
    @property
    def max_deletions_per_run(self) -> int:
        return self.get("max_deletions_per_run", 1)
    
    @property
    def versions_to_keep(self) -> int:
        return self.get("versions_to_keep", 2)
    
    @property
    def google_drive_chunk_size(self) -> int:
        return self.get("google_drive_chunk_size_mb", 5) * 1024 * 1024
    
    @property
    def sharepoint_chunk_size(self) -> int:
        return self.get("sharepoint_chunk_size_mb", 4) * 1024 * 1024
    
    @property
    def retry_attempts(self) -> int:
        return self.get("retry_attempts", 3)
    
    @property
    def timeout_seconds(self) -> int:
        return self.get("timeout_seconds", 30)


# Global instance
_cloud_settings = None

def get_cloud_settings(project_path: Path = None) -> CloudSettings:
    """Get global cloud settings instance"""
    global _cloud_settings
    if _cloud_settings is None:
        _cloud_settings = CloudSettings(project_path)
    return _cloud_settings