#!/usr/bin/env python3
"""OAuth configuration management with environment variable support"""

import os
from typing import Dict, Optional


class OAuthConfig:
    """Manages OAuth configuration from environment variables"""
    
    def __init__(self):
        self._load_env_file()
    
    def _load_env_file(self):
        """Load environment variables from .env file if it exists"""
        import sys
        
        # Handle PyInstaller builds
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller --onefile mode
                env_file = os.path.join(sys._MEIPASS, '.env')
            else:
                # PyInstaller --onedir mode or other
                env_file = os.path.join(os.path.dirname(sys.executable), '.env')
        else:
            # Running as script
            env_file = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
        
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
    
    def get_google_credentials(self) -> Dict[str, Optional[str]]:
        """Get Google OAuth credentials from environment"""
        return {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET')
        }
    
    def get_microsoft_credentials(self) -> Dict[str, Optional[str]]:
        """Get Microsoft OAuth credentials from environment"""
        return {
            'client_id': os.getenv('MICROSOFT_CLIENT_ID', ''),
            'client_secret': os.getenv('MICROSOFT_CLIENT_SECRET', '')
        }
    
    def get_legacy_google_credentials(self) -> Dict[str, Optional[str]]:
        """Get legacy Google OAuth credentials from environment"""
        return {
            'client_id': os.getenv('LEGACY_GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('LEGACY_GOOGLE_CLIENT_SECRET')
        }
    
    def validate_credentials(self) -> Dict[str, bool]:
        """Validate that required credentials are available"""
        google_creds = self.get_google_credentials()
        microsoft_creds = self.get_microsoft_credentials()
        
        return {
            'google_valid': bool(google_creds['client_id'] and google_creds['client_secret']),
            'microsoft_valid': bool(microsoft_creds['client_id']),
            'has_env_file': os.path.exists(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
        }