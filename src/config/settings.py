from pathlib import Path
import json
from typing import Dict, Any

class StatusConfig:
    def __init__(self, project_path: Path = None):
        self.default_states = {
            "S0": "Borrador",
            "S1": "Revisado por Delineación", 
            "S2": "Revisado por Técnico Especialista",
            "S3": "Revisado por Director Proyecto",
            "S3A": "Aprobado por propiedad/promotor"
        }
        self.default_colors = {
            "S0": "#FFFFFF",  # Pure White - Borrador
            "S1": "#FFFF00",  # Yellow - Revisado por Delineación
            "S2": "#00AAE4",  # Blue - Revisado por Técnico Especialista
            "S3": "#B19CD9",  # Purple - Revisado por Director Proyecto
            "S3A": "#008F39"  # Green - Aprobado por propiedad/promotor
        }
        # Use centralized path helper for proper directory management
        from utils.path_helper import PathHelper
        self.config_path = PathHelper.get_config_file_path("config_estados.json", project_path)
        self.STATE_MAP = {}
        self.STATUS_COLORS = {}
        self.REVERSE_STATE_MAP = {}
        self.load()

    def load(self) -> None:
        if not self.config_path.exists():
            self._create_default_config()
        else:
            self._load_from_file()
        
        self.REVERSE_STATE_MAP = {v: k for k, v in self.STATE_MAP.items()}

    def _create_default_config(self) -> None:
        try:
            from utils.file_manager import FileManager
            self.config_path.parent.mkdir(exist_ok=True)
            data = {
                "STATE_MAP": self.default_states,
                "STATUS_COLORS": self.default_colors
            }
            FileManager.safe_json_write(str(self.config_path), data)
            self.STATE_MAP = self.default_states
            self.STATUS_COLORS = self.default_colors
        except OSError as e:
            raise RuntimeError(f"No se pudo crear el archivo de configuración de estados: {e}")

    def _load_from_file(self) -> None:
        try:
            from utils.file_manager import FileManager
            config = FileManager.safe_json_read(str(self.config_path))
            self.STATE_MAP = config.get("STATE_MAP", self.default_states)
            self.STATUS_COLORS = config.get("STATUS_COLORS", self.default_colors)
        except (json.JSONDecodeError, OSError) as e:
            self.STATE_MAP = self.default_states
            self.STATUS_COLORS = self.default_colors


class UserConfig:
    def __init__(self):
        self.config_path = self._get_config_path()
        self.config = self.load()

    def _get_config_path(self) -> Path:
        return Path.home() / ".project_file_manager_config.json"

    def load(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                from utils.file_manager import FileManager
                return FileManager.safe_json_read(str(self.config_path))
            except Exception as e:
                from utils.error_logger import logger
                logger.error(f"Failed to load user configuration", e, {"config_path": str(self.config_path)})
                return {}
        return {}

    def save(self, name: str) -> None:
        """Save user configuration with validation and sanitization info."""
        from utils.username_helper import UsernameHelper
        
        # Validate the username and get sanitization info
        validation = UsernameHelper.validate_username(name)
        
        config = {
            "user_name": name,
            "validation_info": {
                "is_valid": validation['valid'],
                "issues": validation['issues'],
                "sanitized_version": validation['sanitized']
            }
        }
        
        try:
            from utils.file_manager import FileManager
            FileManager.safe_json_write(str(self.config_path), config)
        except Exception as e:
            raise RuntimeError(f"No se pudo guardar la configuración del usuario: {e}")

    def get_user_name(self) -> str:
        """Get the configured username."""
        return self.config.get("user_name", "")
    
    def get_safe_user_name(self) -> str:
        """Get a safe, sanitized version of the username for file operations."""
        from utils.username_helper import UsernameHelper
        
        username = self.get_user_name()
        if username:
            return UsernameHelper.sanitize_username(username)
        else:
            return UsernameHelper.get_safe_username()
    
    def has_username_issues(self) -> bool:
        """Check if the current username has compatibility issues."""
        validation_info = self.config.get("validation_info", {})
        return not validation_info.get("is_valid", True)
    
    def get_username_issues(self) -> list:
        """Get list of issues with the current username."""
        validation_info = self.config.get("validation_info", {})
        return validation_info.get("issues", [])


class CloudConfig:
    """Configuration for cloud sync (SharePoint and Google Drive)"""
    
    def __init__(self, project_path: Path = None):
        self.user_config_path = Path.home() / ".project_file_manager_cloud_config.json"
        
        # Use centralized path helper for proper directory management
        from utils.path_helper import PathHelper
        self.project_config_path = PathHelper.get_config_file_path("cloud_sync.json", project_path)
        
        # Legacy path for migration
        if project_path:
            self.legacy_config_path = project_path / ".document_manager" / "cloud_sync.json"
        else:
            self.legacy_config_path = Path(".") / ".document_manager" / "cloud_sync.json"
        
        self.user_config = self.load_user_config()
        self.project_config = self.load_project_config()
    
    def load_user_config(self) -> Dict[str, Any]:
        """Load user-level cloud credentials"""
        if self.user_config_path.exists():
            try:
                from utils.file_manager import FileManager
                return FileManager.safe_json_read(str(self.user_config_path))
            except Exception as e:
                from utils.error_logger import logger
                logger.error(f"Failed to load sync configuration", e, {"config_path": str(self.user_config_path)})
                return {}
        return {}
    
    def load_project_config(self) -> Dict[str, Any]:
        """Load project-level cloud sync settings with automatic migration"""
        
        # Check if unified config exists
        if self.project_config_path.exists():
            try:
                from utils.file_manager import FileManager
                return FileManager.safe_json_read(str(self.project_config_path))
            except Exception as e:
                from utils.error_logger import logger
                logger.error(f"Failed to load project configuration", e, {"config_path": str(self.project_config_path)})
                # Don't return default immediately, try migration first
        
        # Check for legacy config and migrate if found
        if self.legacy_config_path.exists():
            try:
                from utils.file_manager import FileManager
                legacy_config = FileManager.safe_json_read(str(self.legacy_config_path))
                
                # Migrate the config to the new location
                self._migrate_legacy_config(legacy_config)
                
                return legacy_config
            except Exception as e:
                from utils.error_logger import logger
                logger.warning(f"Failed to migrate legacy cloud config", {"legacy_path": str(self.legacy_config_path), "error": str(e)})
        
        return self._get_default_project_config()
    
    def _migrate_legacy_config(self, legacy_config: Dict[str, Any]) -> None:
        """Migrate legacy .document_manager config to .project_manager"""
        try:
            import time
            import shutil
            from utils.file_manager import FileManager
            
            # Ensure the new directory exists
            self.project_config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save to new location
            FileManager.safe_json_write(str(self.project_config_path), legacy_config)
            
            # Create backup of legacy file
            backup_path = self.legacy_config_path.parent / f"cloud_sync_migrated_backup_{int(time.time())}.json"
            shutil.copy2(str(self.legacy_config_path), str(backup_path))
            
            print(f"✓ Migrated cloud config from .document_manager to .project_manager")
            print(f"  Legacy backup created: {backup_path}")
            
        except Exception as e:
            print(f"Warning: Failed to migrate cloud config: {e}")
    
    def _get_default_project_config(self) -> Dict[str, Any]:
        """Default project cloud sync configuration"""
        return {
            "enabled": False,
            "sharepoint": {
                "site_url": "",
                "folder_path": "",
                "enabled": False
            },
            "google_drive": {
                "folder_id": "",
                "enabled": False
            }
        }
    
    def save_user_config(self, config: Dict[str, Any]) -> None:
        """Save user-level cloud credentials"""
        try:
            from utils.file_manager import FileManager
            FileManager.safe_json_write(str(self.user_config_path), config)
            self.user_config = config
        except Exception as e:
            raise RuntimeError(f"No se pudo guardar la configuración de nube del usuario: {e}")
    
    def save_project_config(self, config: Dict[str, Any]) -> None:
        """Save project-level cloud sync settings"""
        try:
            from utils.file_manager import FileManager
            self.project_config_path.parent.mkdir(exist_ok=True)
            FileManager.safe_json_write(str(self.project_config_path), config)
            self.project_config = config
        except Exception as e:
            raise RuntimeError(f"No se pudo guardar la configuración de nube del proyecto: {e}")
    
    def is_cloud_sync_enabled(self) -> bool:
        """Check if cloud sync is enabled for this project"""
        return self.project_config.get("enabled", False)
    
    def is_sharepoint_enabled(self) -> bool:
        """Check if SharePoint sync is enabled"""
        return (self.project_config.get("sharepoint", {}).get("enabled", False) 
                and self.project_config.get("enabled", False))
    
    def is_google_drive_enabled(self) -> bool:
        """Check if Google Drive sync is enabled"""
        return (self.project_config.get("google_drive", {}).get("enabled", False) 
                and self.project_config.get("enabled", False))
    
    def get_sharepoint_config(self) -> Dict[str, Any]:
        """Get SharePoint configuration"""
        return self.project_config.get("sharepoint", {})
    
    def get_google_drive_config(self) -> Dict[str, Any]:
        """Get Google Drive configuration"""
        return self.project_config.get("google_drive", {})
    
    def get_user_credentials(self, service: str) -> Dict[str, Any]:
        """Get user credentials for specified service (sharepoint or google_drive)"""
        return self.user_config.get(service, {})
    
    # Folder configuration methods
    def get_google_drive_folder_id(self) -> str:
        """Get Google Drive folder ID"""
        return self.project_config.get("google_drive", {}).get("folder_id", "")
    
    def set_google_drive_folder_id(self, folder_id: str) -> None:
        """Set Google Drive folder ID"""
        if "google_drive" not in self.project_config:
            self.project_config["google_drive"] = {}
        self.project_config["google_drive"]["folder_id"] = folder_id
        self.save_project_config(self.project_config)
    
    def get_sharepoint_site_url(self) -> str:
        """Get SharePoint site URL"""
        return self.project_config.get("sharepoint", {}).get("site_url", "")
    
    def set_sharepoint_site_url(self, site_url: str) -> None:
        """Set SharePoint site URL"""
        if "sharepoint" not in self.project_config:
            self.project_config["sharepoint"] = {}
        self.project_config["sharepoint"]["site_url"] = site_url
        self.save_project_config(self.project_config)
    
    def get_sharepoint_folder_path(self) -> str:
        """Get SharePoint folder path"""
        return self.project_config.get("sharepoint", {}).get("folder_path", "")
    
    def set_sharepoint_folder_path(self, folder_path: str) -> None:
        """Set SharePoint folder path"""
        if "sharepoint" not in self.project_config:
            self.project_config["sharepoint"] = {}
        self.project_config["sharepoint"]["folder_path"] = folder_path
        self.save_project_config(self.project_config)