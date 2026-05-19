"""
Username Helper Utility
Provides robust username detection and sanitization for cross-platform compatibility,
with special focus on Windows username handling.
"""

import os
import re
import getpass
from pathlib import Path
from typing import Optional, Dict, Any
from utils.error_logger import logger


class UsernameHelper:
    """Helper class for robust username detection and sanitization."""
    
    @staticmethod
    def sanitize_username(username: str) -> str:
        """
        Sanitize username for safe use in file paths and configuration.
        
        Args:
            username: Raw username to sanitize
            
        Returns:
            Sanitized username safe for file operations
            
        Examples:
            "María García" -> "Maria_Garcia"
            "admin.user" -> "admin_user"
            "José López-Smith" -> "Jose_Lopez_Smith"
        """
        if not username or not isinstance(username, str):
            return "DefaultUser"
        
        # Remove leading/trailing whitespace
        username = username.strip()
        if not username:
            return "DefaultUser"
        
        # Replace accented characters with their base equivalents
        replacements = {
            'á': 'a', 'à': 'a', 'ä': 'a', 'â': 'a', 'ā': 'a', 'ă': 'a', 'ą': 'a', 'å': 'a',
            'é': 'e', 'è': 'e', 'ë': 'e', 'ê': 'e', 'ē': 'e', 'ė': 'e', 'ę': 'e',
            'í': 'i', 'ì': 'i', 'ï': 'i', 'î': 'i', 'ī': 'i', 'į': 'i',
            'ó': 'o', 'ò': 'o', 'ö': 'o', 'ô': 'o', 'ō': 'o', 'ő': 'o', 'ø': 'o',
            'ú': 'u', 'ù': 'u', 'ü': 'u', 'û': 'u', 'ū': 'u', 'ű': 'u', 'ų': 'u',
            'ñ': 'n', 'ń': 'n', 'ň': 'n', 'ņ': 'n',
            'ç': 'c', 'ć': 'c', 'č': 'c', 'ĉ': 'c', 'ċ': 'c',
            'ß': 'ss', 'ý': 'y', 'ÿ': 'y', 'ž': 'z', 'ź': 'z', 'ż': 'z'
        }
        
        # Apply character replacements (both lowercase and uppercase)
        for accented, base in replacements.items():
            username = username.replace(accented, base)
            username = username.replace(accented.upper(), base.upper())
        
        # Check if username contains only ASCII characters after accent replacement
        # If it contains non-Latin scripts (Cyrillic, CJK, etc.), fallback to DefaultUser
        try:
            username.encode('ascii')
        except UnicodeEncodeError:
            # Contains non-ASCII characters that aren't in our replacement map
            # Check if it's mostly non-Latin script
            latin_chars = sum(1 for c in username if c.isascii() and c.isalpha())
            total_alpha = sum(1 for c in username if c.isalpha())
            
            if total_alpha > 0 and latin_chars / total_alpha < 0.5:
                # Mostly non-Latin script, use default
                return "DefaultUser"
        
        # Replace any remaining non-alphanumeric characters with underscores
        # Keep only ASCII letters, numbers, hyphens, and underscores
        sanitized = re.sub(r'[^\w\-]', '_', username, flags=re.ASCII)
        
        # Remove multiple consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_-')
        
        # Ensure we have a valid result
        if not sanitized or len(sanitized) < 1:
            return "DefaultUser"
        
        # Limit length to reasonable maximum
        if len(sanitized) > 50:
            sanitized = sanitized[:50].rstrip('_-')
        
        return sanitized
    
    @staticmethod
    def get_system_username() -> str:
        """
        Get the current system username using multiple detection methods.
        
        Returns:
            System username with proper fallback handling
        """
        methods = [
            # Method 1: getpass.getuser() - cross-platform standard
            lambda: getpass.getuser(),
            
            # Method 2: Environment variables (Windows-specific)
            lambda: os.environ.get('USERNAME'),
            
            # Method 3: Environment variables (Unix-specific)  
            lambda: os.environ.get('USER'),
            
            # Method 4: Extract from USERPROFILE (Windows)
            lambda: Path(os.environ.get('USERPROFILE', '')).name if os.environ.get('USERPROFILE') else None,
            
            # Method 5: Extract from HOME (Unix)
            lambda: Path(os.environ.get('HOME', '')).name if os.environ.get('HOME') else None,
            
            # Method 6: Path.home().name as last resort
            lambda: Path.home().name,
        ]
        
        for method in methods:
            try:
                username = method()
                if username and isinstance(username, str) and username.strip():
                    return username.strip()
            except Exception as e:
                logger.debug(f"Username detection method failed: {e}")
                continue
        
        # Ultimate fallback
        return "DefaultUser"
    
    @staticmethod
    def get_safe_username() -> str:
        """
        Get a safe, sanitized username for use in the application.
        
        Returns:
            Sanitized username safe for file operations and configuration
        """
        raw_username = UsernameHelper.get_system_username()
        return UsernameHelper.sanitize_username(raw_username)
    
    @staticmethod
    def validate_username(username: str) -> Dict[str, Any]:
        """
        Validate a username and provide detailed feedback.
        
        Args:
            username: Username to validate
            
        Returns:
            Dictionary with validation results and suggestions
        """
        result = {
            'valid': True,
            'issues': [],
            'suggestions': [],
            'sanitized': '',
            'original': username
        }
        
        if not username or not isinstance(username, str):
            result['valid'] = False
            result['issues'].append("Username is empty or not a string")
            result['suggestions'].append("Use get_safe_username() for automatic detection")
            return result
        
        original = username.strip()
        if not original:
            result['valid'] = False
            result['issues'].append("Username is empty after trimming whitespace")
            return result
        
        # Check for problematic characters
        problematic_chars = []
        for char in original:
            if char in ' .,-/\\:*?"<>|':
                if char not in problematic_chars:
                    problematic_chars.append(char)
        
        if problematic_chars:
            result['issues'].append(f"Contains problematic characters: {problematic_chars}")
            result['suggestions'].append("Consider using sanitized version for file operations")
        
        # Check for accented characters
        accented_chars = []
        for char in original:
            if ord(char) > 127:  # Non-ASCII characters
                if char not in accented_chars:
                    accented_chars.append(char)
        
        if accented_chars:
            result['issues'].append(f"Contains accented characters: {accented_chars}")
            result['suggestions'].append("Sanitized version will replace with base characters")
        
        # Check length
        if len(original) > 50:
            result['issues'].append("Username is longer than 50 characters")
            result['suggestions'].append("Sanitized version will be truncated")
        
        # Generate sanitized version
        result['sanitized'] = UsernameHelper.sanitize_username(original)
        
        # If sanitized version is different, mark as having issues
        if result['sanitized'] != original:
            result['valid'] = False
            result['suggestions'].append(f"Recommended sanitized version: '{result['sanitized']}'")
        
        return result
    
    @staticmethod
    def get_username_info() -> Dict[str, Any]:
        """
        Get comprehensive information about username detection on current system.
        
        Returns:
            Dictionary with all detected usernames and platform info
        """
        info = {
            'platform': os.name,
            'system': os.uname().sysname if hasattr(os, 'uname') else 'Unknown',
            'detection_methods': {},
            'recommended': '',
            'safe': ''
        }
        
        # Test all detection methods
        methods = {
            'getpass.getuser()': lambda: getpass.getuser(),
            'os.environ[USERNAME]': lambda: os.environ.get('USERNAME'),
            'os.environ[USER]': lambda: os.environ.get('USER'),
            'USERPROFILE_name': lambda: Path(os.environ.get('USERPROFILE', '')).name if os.environ.get('USERPROFILE') else None,
            'HOME_name': lambda: Path(os.environ.get('HOME', '')).name if os.environ.get('HOME') else None,
            'Path.home().name': lambda: Path.home().name,
        }
        
        for method_name, method in methods.items():
            try:
                result = method()
                info['detection_methods'][method_name] = result if result else 'Not available'
            except Exception as e:
                info['detection_methods'][method_name] = f'Error: {e}'
        
        # Get recommended values
        info['recommended'] = UsernameHelper.get_system_username()
        info['safe'] = UsernameHelper.get_safe_username()
        
        return info
    
    @staticmethod
    def suggest_username_for_user(current_user: Optional[str] = None) -> str:
        """
        Suggest a username for user configuration, with smart fallbacks.
        
        Args:
            current_user: Currently configured username (if any)
            
        Returns:
            Suggested username for user configuration
        """
        # If user already has a configured username, validate it
        if current_user and isinstance(current_user, str) and current_user.strip():
            validation = UsernameHelper.validate_username(current_user)
            if validation['valid']:
                return current_user.strip()
            else:
                # Current username has issues, suggest sanitized version
                return validation['sanitized']
        
        # No current user or invalid, get system username
        system_username = UsernameHelper.get_system_username()
        
        # If system username is clean, use it directly
        validation = UsernameHelper.validate_username(system_username)
        if validation['valid']:
            return system_username
        
        # System username has issues, return sanitized version
        return validation['sanitized']