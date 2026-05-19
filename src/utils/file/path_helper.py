"""
Path helper utilities for handling writable directories across different deployment scenarios.
Handles App Translocation and other read-only filesystem issues.
"""
from pathlib import Path
from typing import Optional


class PathHelper:
    """Helper class for managing application paths that work across different deployment scenarios."""
    
    _global_config_base: Optional[Path] = None
    
    @classmethod
    def get_global_config_base(cls) -> Path:
        """
        Get the base directory for global configuration files.
        This handles App Translocation by falling back to home directory when needed.
        """
        if cls._global_config_base is None:
            cls._global_config_base = cls._determine_global_config_base()
        return cls._global_config_base
    
    @classmethod
    def _determine_global_config_base(cls) -> Path:
        """
        Simplified path determination that works consistently across all platforms.
        Uses the same approach for Mac, Windows, and Linux.
        """
        import sys
        
        # SIMPLIFIED: Always use home directory for global configs across all platforms
        # This eliminates Windows-specific path complexity and App Translocation issues
        home_config = Path.home() / ".document_manager" / "global"
        
        try:
            home_config.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = home_config / ".write_test"
            test_file.touch()
            test_file.unlink()
            print(f"DEBUG: Using simplified global config path: {home_config}")
            return home_config
        except OSError as e:
            print(f"DEBUG: Cannot write to home directory {home_config}, using temp fallback")
            # Last resort: use system temp directory
            import tempfile
            temp_config = Path(tempfile.gettempdir()) / ".document_manager" / "global"
            temp_config.mkdir(parents=True, exist_ok=True)
            return temp_config
    
    @classmethod
    def get_project_manager_path(cls, project_path: Optional[Path] = None) -> Path:
        """
        Get the .project_manager directory path - simplified for all platforms.
        
        Args:
            project_path: If provided, use project-specific .project_manager
                         If None, use global configuration location
        
        Returns:
            Path to .project_manager directory
        """
        if project_path:
            # SIMPLIFIED: For project-specific configs, always use the project directory
            # This works consistently across Mac, Windows, and Linux
            pm_path = project_path / ".project_manager"
            pm_path.mkdir(parents=True, exist_ok=True)
            return pm_path
        else:
            # For global configs, use the simplified global location
            return cls.get_global_config_base() / ".project_manager"
    
    @classmethod
    def get_config_file_path(cls, filename: str, project_path: Optional[Path] = None) -> Path:
        """
        Get path for a configuration file.
        
        Args:
            filename: Name of the config file
            project_path: If provided, use project-specific location
        
        Returns:
            Full path to the configuration file
        """
        base_path = cls.get_project_manager_path(project_path)
        return base_path / filename
    
    @classmethod
    def ensure_project_manager_exists(cls, project_path: Optional[Path] = None) -> None:
        """
        Ensure the .project_manager directory exists.
        
        Args:
            project_path: If provided, ensure project-specific directory exists
        """
        pm_path = cls.get_project_manager_path(project_path)
        pm_path.mkdir(parents=True, exist_ok=True)