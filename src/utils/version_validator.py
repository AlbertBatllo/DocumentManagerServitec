"""
Version validation utilities for document management system.
Ensures version format follows integer.integer pattern (e.g., 1.0, 2.1, 10.15).
"""
import re
from typing import Dict, Any


class VersionValidator:
    """Validator for version format: integer.integer (e.g., 1.0, 2.1, 10.15)"""
    
    # Regex pattern for integer.integer format
    VERSION_PATTERN = re.compile(r'^(\d+)\.(\d+)$')
    
    @classmethod
    def validate_version(cls, version: str) -> Dict[str, Any]:
        """
        Validate version format and return validation result.
        
        Args:
            version: Version string to validate
            
        Returns:
            Dict containing:
            - is_valid: bool - whether version is valid
            - message: str - validation message
            - normalized: str - normalized version (if valid)
            - major: int - major version number (if valid)  
            - minor: int - minor version number (if valid)
        """
        if not version or not version.strip():
            return {
                'is_valid': False,
                'message': 'La versión no puede estar vacía',
                'normalized': '',
                'major': None,
                'minor': None
            }
        
        version = version.strip()
        
        # Check if matches integer.integer pattern
        match = cls.VERSION_PATTERN.match(version)
        if not match:
            return {
                'is_valid': False,
                'message': 'La versión debe tener formato número.número (ej: 1.0, 2.1, 10.15)',
                'normalized': '',
                'major': None,
                'minor': None
            }
        
        try:
            major = int(match.group(1))
            minor = int(match.group(2))
            
            # Additional validation rules
            if major < 0 or minor < 0:
                return {
                    'is_valid': False,
                    'message': 'Los números de versión deben ser positivos',
                    'normalized': '',
                    'major': None,
                    'minor': None
                }
            
            # Success
            normalized = f"{major}.{minor}"
            return {
                'is_valid': True,
                'message': f'Versión válida: {normalized}',
                'normalized': normalized,
                'major': major,
                'minor': minor
            }
            
        except ValueError:
            return {
                'is_valid': False,
                'message': 'Error al procesar los números de versión',
                'normalized': '',
                'major': None,
                'minor': None
            }
    
    @classmethod
    def is_valid_version(cls, version: str) -> bool:
        """Quick check if version is valid format."""
        return cls.validate_version(version)['is_valid']
    
    @classmethod
    def normalize_version(cls, version: str) -> str:
        """
        Get normalized version string (e.g., "01.00" -> "1.0").
        Returns empty string if invalid.
        """
        result = cls.validate_version(version)
        return result['normalized'] if result['is_valid'] else ''
    
    @classmethod
    def suggest_next_version(cls, current_version: str, increment_type: str = 'minor') -> str:
        """
        Suggest next version based on current version.
        
        Args:
            current_version: Current version string
            increment_type: 'major' or 'minor' (default: 'minor')
            
        Returns:
            Suggested next version string, or '1.0' if current is invalid
        """
        result = cls.validate_version(current_version)
        
        if not result['is_valid']:
            return '1.0'
        
        major = result['major']
        minor = result['minor']
        
        if increment_type == 'major':
            return f"{major + 1}.0"
        else:  # minor
            return f"{major}.{minor + 1}"
    
    @classmethod
    def compare_versions(cls, version1: str, version2: str) -> int:
        """
        Compare two versions.
        
        Returns:
            -1 if version1 < version2
             0 if version1 == version2
             1 if version1 > version2
            None if either version is invalid
        """
        v1_result = cls.validate_version(version1)
        v2_result = cls.validate_version(version2)
        
        if not (v1_result['is_valid'] and v2_result['is_valid']):
            return None
        
        v1_major, v1_minor = v1_result['major'], v1_result['minor']
        v2_major, v2_minor = v2_result['major'], v2_result['minor']
        
        if v1_major < v2_major:
            return -1
        elif v1_major > v2_major:
            return 1
        else:  # same major version
            if v1_minor < v2_minor:
                return -1
            elif v1_minor > v2_minor:
                return 1
            else:
                return 0


def validate_version_input(version: str) -> Dict[str, Any]:
    """
    Convenience function for form validation.
    Alias for VersionValidator.validate_version()
    """
    return VersionValidator.validate_version(version)


# Example usage and test cases
if __name__ == "__main__":
    # Test cases
    test_versions = [
        "1.0",      # Valid
        "2.1",      # Valid  
        "10.15",    # Valid
        "0.1",      # Valid
        "1",        # Invalid - missing minor
        "1.0.1",    # Invalid - too many parts
        "v1.0",     # Invalid - has prefix
        "1.0a",     # Invalid - has suffix
        "",         # Invalid - empty
        "1.a",      # Invalid - non-numeric
        "-1.0",     # Invalid - negative
        "1.-1",     # Invalid - negative
    ]
    
    print("🧪 Testing version validation:")
    for version in test_versions:
        result = VersionValidator.validate_version(version)
        status = "✅" if result['is_valid'] else "❌"
        print(f"{status} '{version}' -> {result['message']}")
    
    print("\n🔄 Testing version comparison:")
    pairs = [("1.0", "1.1"), ("2.0", "1.9"), ("1.0", "1.0")]
    for v1, v2 in pairs:
        comparison = VersionValidator.compare_versions(v1, v2)
        if comparison == -1:
            print(f"📊 {v1} < {v2}")
        elif comparison == 0:
            print(f"📊 {v1} = {v2}")
        elif comparison == 1:
            print(f"📊 {v1} > {v2}")
    
    print("\n➡️ Testing next version suggestions:")
    for version in ["1.0", "2.5", "invalid"]:
        minor_next = VersionValidator.suggest_next_version(version, 'minor')
        major_next = VersionValidator.suggest_next_version(version, 'major')
        print(f"📈 {version} -> minor: {minor_next}, major: {major_next}")