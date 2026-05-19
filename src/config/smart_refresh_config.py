"""
Smart Refresh Configuration for Network Storage (NAS) Environments

Lightweight network-aware settings that maintain app performance while
providing reliable collaboration over network storage.
"""

# Network-optimized settings for NAS environments
SMART_REFRESH_CONFIG = {
    # Timing - balanced for network storage
    'refresh_interval': 15000,      # 15 seconds (instead of 3) - reduces NAS load
    'network_timeout': 5,           # 5 second timeout - prevents hangs
    
    # Reliability - minimal retry logic
    'max_retries': 2,              # Retry failed requests twice - lightweight
    'fallback_to_cache': True,     # Use cached data on network failure - no blocking
    
    # Performance - simple optimizations
    'batch_updates': True,         # Batch multiple updates together - reduces requests
    'skip_unchanged_files': True,  # Skip files that haven't changed - smart caching
}

# Cross-Platform NAS Detection System
def detect_synology_nas(file_path: str) -> dict:
    """
    Detect if path is on the Synology NAS (192.168.10.2) regardless of platform.
    Returns detailed information about NAS connectivity and platform-specific paths.
    """
    import os
    import time
    import platform
    import socket
    from pathlib import Path
    
    result = {
        'is_synology': False,
        'platform': platform.system(),
        'nas_ip': '192.168.10.2',
        'nas_accessible': False,
        'mount_detected': False,
        'mount_path': None,
        'latency_ms': None,
        'error': None
    }
    
    try:
        # 1. Quick check: if file path is obviously local, skip network test
        file_path_lower = file_path.lower()
        # Check if path looks local (common local path patterns)
        local_path_indicators = ['/users/', '/home/', 'c:\\', 'c:/', '~/']
        nas_indicators = ['/volumes/servitec', '/volumes/synology', '192.168.10.2', '\\\\192.168.10.2']
        
        is_likely_local = any(local_indicator in file_path_lower for local_indicator in local_path_indicators)
        has_nas_indicators = any(nas_indicator in file_path_lower for nas_indicator in nas_indicators)
        
        if is_likely_local and not has_nas_indicators:
            # File is local, skip expensive network checks
            result['error'] = 'Local file detected - skipping NAS connectivity check'
            return result
            
        # Test network connectivity to Synology NAS
        
        try:
            start_time = time.time()
            with socket.create_connection(('192.168.10.2', 445), timeout=1) as sock:  # Reduced timeout to 1 second
                # Connection successful, socket auto-closed by context manager
                pass
            result['nas_accessible'] = True
            result['latency_ms'] = round((time.time() - start_time) * 1000, 2)
        except Exception as e:
            result['error'] = f'Synology NAS not accessible at 192.168.10.2: {str(e)[:50]}'
            return result
        
        # 2. Platform-specific mount point detection
        path_obj = Path(file_path)
        file_path_str = str(path_obj.absolute())
        
        if result['platform'] == 'Darwin':  # macOS
            # Check for Synology mount in /Volumes/
            synology_indicators = [
                '/Volumes/Servitec Ingenieria',
                '/Volumes/Servitec_Ingenieria', 
                '/Volumes/servitec'
            ]
            for mount in synology_indicators:
                if file_path_str.startswith(mount):
                    result['is_synology'] = True
                    result['mount_detected'] = True
                    result['mount_path'] = mount
                    break
                elif Path(mount).exists():
                    result['mount_path'] = mount
                    result['mount_detected'] = True
                    # Check if file path could be translated to this mount
                    if 'PRJ' in file_path_str or 'PROYECTO' in file_path_str.upper():
                        result['is_synology'] = True
        
        elif result['platform'] == 'Windows':  # Windows
            # Check for UNC paths or mapped drives pointing to Synology
            if ('\\\\192.168.10.2' in file_path_str or 
                file_path_str.startswith('\\\\') and 'servitec' in file_path_str.lower()):
                result['is_synology'] = True
                result['mount_detected'] = True
                result['mount_path'] = file_path_str.split('\\')[0:4] if file_path_str.startswith('\\\\') else None
            else:
                # Check mapped drives (could be any drive letter)
                drive_letter = file_path_str[0:2] if len(file_path_str) > 1 and file_path_str[1] == ':' else None
                if drive_letter:
                    # This would require additional Windows-specific checks
                    # For now, use latency-based detection
                    pass
        
        elif result['platform'] == 'Linux':  # Linux
            # Check common Linux mount points
            linux_mounts = ['/mnt/servitec', '/media/servitec', '/mnt/synology', '/media/synology']
            for mount in linux_mounts:
                if file_path_str.startswith(mount) or Path(mount).exists():
                    result['is_synology'] = True
                    result['mount_detected'] = True
                    result['mount_path'] = mount
                    break
        
        # 3. Fallback: Latency-based detection for any platform
        if not result['is_synology']:
            start_time = time.time()
            try:
                parent_dir = path_obj.parent
                if parent_dir.exists():
                    list(parent_dir.iterdir())  # Directory listing
                else:
                    os.path.exists(file_path_str)
            except Exception as e:
                from utils.error_logger import logger
                logger.debug(f"File latency test failed during Synology detection", {"file_path": file_path_str, "error": str(e)})
            
            file_latency = (time.time() - start_time) * 1000
            if file_latency > 300:  # >300ms suggests network storage (increased from 100ms per code review)
                result['is_synology'] = True
                result['latency_ms'] = round(file_latency, 2)
                result['error'] = 'Detected as network storage via latency, but mount point unknown'
    
    except Exception as e:
        result['error'] = f'Detection failed: {str(e)[:100]}'
    
    return result

def is_network_path(file_path: str) -> bool:
    """Cross-platform network path detection with Synology NAS awareness."""
    # Use Synology-aware detection
    synology_info = detect_synology_nas(file_path)
    
    if synology_info['is_synology']:
        return True
    
    # Fallback to general network detection
    import os
    import time
    from pathlib import Path
    
    try:
        path_obj = Path(file_path)
        file_path_str = str(path_obj.absolute())
        
        # General network path patterns (all platforms)
        network_patterns = [
            '/Volumes/',      # macOS
            '/mnt/',          # Linux
            '/media/',        # Linux  
            '\\\\',           # Windows UNC
            '//'              # UNC-style paths
        ]
        
        for pattern in network_patterns:
            if file_path_str.startswith(pattern):
                return True
        
        # Latency-based detection
        start_time = time.time()
        try:
            parent_dir = path_obj.parent
            if parent_dir.exists():
                list(parent_dir.iterdir())
            else:
                os.path.exists(file_path_str)
        except Exception as e:
            from utils.error_logger import logger
            logger.debug(f"Directory latency test failed", {"file_path": file_path_str, "error": str(e)})
            
        latency = time.time() - start_time
        return latency > 0.3  # >300ms suggests network (increased from 50ms per code review)
        
    except Exception as e:
        from utils.error_logger import logger
        logger.debug(f"Network storage detection failed", {"file_path": file_path_str, "error": str(e)})
        return False

def check_nas_connectivity(file_path: str) -> dict:
    """
    Cross-platform NAS connectivity check with Synology-specific diagnostics.
    Provides detailed connectivity information and platform-specific guidance.
    """
    # Quick check: if file path is obviously local, return connected without network checks
    file_path_lower = file_path.lower()
    local_path_indicators = ['/users/', '/home/', 'c:\\', 'c:/', '~/']
    nas_indicators = ['/volumes/servitec', '/volumes/synology', '192.168.10.2', '\\\\192.168.10.2']
    
    is_likely_local = any(local_indicator in file_path_lower for local_indicator in local_path_indicators)
    has_nas_indicators = any(nas_indicator in file_path_lower for nas_indicator in nas_indicators)
    
    if is_likely_local and not has_nas_indicators:
        return {
            'connected': True,
            'latency_ms': 0,
            'readable': True,
            'writable': True,
            'error': None,
            'is_synology': False,
            'platform': 'local',
            'nas_accessible': False,
            'mount_path': None,
            'recommendations': []
        }
    
    # First get Synology-specific detection info
    synology_info = detect_synology_nas(file_path)
    
    result = {
        'connected': False,
        'latency_ms': synology_info.get('latency_ms'),
        'readable': False,
        'writable': False,
        'error': None,
        'is_synology': synology_info['is_synology'],
        'platform': synology_info['platform'],
        'nas_accessible': synology_info['nas_accessible'],
        'mount_path': synology_info.get('mount_path'),
        'recommendations': []
    }
    
    try:
        from pathlib import Path
        import os
        import time
        
        path_obj = Path(file_path)
        
        # If Synology NAS is not accessible, provide specific guidance
        if synology_info['is_synology'] and not synology_info['nas_accessible']:
            result['error'] = 'Synology NAS (192.168.10.2) not accessible'
            result['recommendations'] = _get_mount_instructions(synology_info['platform'])
            return result
        
        # Test 1: File system connectivity
        start_time = time.time()
        exists = path_obj.exists() or path_obj.parent.exists()
        if not result['latency_ms']:  # Only measure if not already measured
            result['latency_ms'] = round((time.time() - start_time) * 1000, 2)
        
        result['connected'] = exists
        
        if not exists:
            if synology_info['is_synology']:
                result['error'] = 'Synology path not accessible - check mount'
                result['recommendations'] = _get_mount_instructions(synology_info['platform'])
            else:
                result['error'] = 'Path not accessible'
            return result
        
        # Test 2: Read access
        try:
            if path_obj.is_file():
                with open(path_obj, 'r') as f:
                    f.read(100)
                result['readable'] = True
            elif path_obj.parent.exists():
                list(path_obj.parent.iterdir())
                result['readable'] = True
        except Exception as e:
            result['error'] = f'Read access failed: {str(e)[:50]}'
        
        # Test 3: Write access
        try:
            test_dir = path_obj.parent if path_obj.is_file() else path_obj
            if test_dir.exists():
                test_file = test_dir / '.nas_connectivity_test'
                with open(test_file, 'w') as f:
                    f.write('connectivity_test')
                test_file.unlink()
                result['writable'] = True
        except Exception as e:
            result['error'] = f'Write access failed: {str(e)[:50]}'
        
        # Add performance recommendations
        if result['connected'] and result['latency_ms']:
            if result['latency_ms'] > 500:
                result['recommendations'].append('High latency detected - consider local caching')
            elif result['latency_ms'] > 200:
                result['recommendations'].append('Moderate latency - using 15s refresh intervals')
            else:
                result['recommendations'].append('Good performance - optimal for real-time collaboration')
            
    except Exception as e:
        result['error'] = f'Connectivity check failed: {str(e)[:50]}'
    
    return result

def _get_mount_instructions(platform: str) -> list:
    """Get platform-specific mounting instructions for Synology NAS."""
    instructions = {
        'Darwin': [  # macOS
            'Open Finder and press Cmd+K',
            'Enter: smb://192.168.10.2/Servitec Ingenieria',
            'Connect with your Synology credentials',
            'The NAS will mount at /Volumes/Servitec Ingenieria'
        ],
        'Windows': [
            'Open File Explorer',
            'Type in address bar: \\\\192.168.10.2\\Servitec Ingenieria',
            'Or map as network drive using the same path',
            'Enter your Synology credentials when prompted'
        ],
        'Linux': [
            'Install cifs-utils: sudo apt install cifs-utils',
            'Create mount point: sudo mkdir /mnt/servitec',
            'Mount: sudo mount -t cifs //192.168.10.2/Servitec\\ Ingenieria /mnt/servitec',
            'Enter credentials when prompted'
        ]
    }
    
    return instructions.get(platform, ['Connect to Synology NAS at 192.168.10.2'])

def get_refresh_interval(file_path: str) -> int:
    """Get appropriate refresh interval based on storage type."""
    if is_network_path(file_path):
        return SMART_REFRESH_CONFIG['refresh_interval']  # 15s for network
    else:
        return 3000  # 3s for local files

def get_network_timeout() -> int:
    """Get network timeout setting."""
    return SMART_REFRESH_CONFIG['network_timeout']

# Platform-Agnostic Path Resolution Functions
def resolve_synology_path(relative_path: str = '') -> str:
    """
    Resolve a path on the Synology NAS for the current platform.
    Returns the full platform-specific path to access Synology files.
    
    Args:
        relative_path: Path relative to the Synology root (e.g., "01 PROYECTOS/PRJ - MyProject")
    
    Returns:
        Full platform-specific path to the Synology location
    """
    import platform
    import os
    from pathlib import Path
    
    system = platform.system()
    
    if system == 'Darwin':  # macOS
        # Try known mount points in order of preference
        possible_mounts = [
            '/Volumes/Servitec Ingenieria',
            '/Volumes/Servitec_Ingenieria',
            '/Volumes/servitec'
        ]
        
        for mount in possible_mounts:
            if Path(mount).exists():
                return os.path.join(mount, relative_path) if relative_path else mount
        
        # Default mount point (may not exist yet)
        return os.path.join('/Volumes/Servitec Ingenieria', relative_path)
    
    elif system == 'Windows':
        # Try UNC path first, then common mapped drives
        unc_path = f'\\\\192.168.10.2\\Servitec Ingenieria'
        if relative_path:
            unc_path = os.path.join(unc_path, relative_path).replace('/', '\\')
        
        # Check if accessible via UNC
        try:
            if os.path.exists(unc_path):
                return unc_path
        except Exception as e:
            from utils.error_logger import logger
            logger.debug(f"UNC path access test failed", {"unc_path": unc_path, "error": str(e)})
        
        # Try common mapped drive letters
        for drive in ['S:', 'N:', 'Z:', 'X:']:
            test_path = os.path.join(drive, relative_path) if relative_path else drive
            try:
                if os.path.exists(drive):
                    return test_path
            except Exception as e:
                from utils.error_logger import logger
                logger.debug(f"Drive letter test failed", {"drive": drive, "error": str(e)})
                continue
                
        return unc_path  # Return UNC path as default
    
    elif system == 'Linux':
        # Try common Linux mount points
        possible_mounts = [
            '/mnt/servitec',
            '/media/servitec', 
            '/mnt/synology',
            '/media/synology'
        ]
        
        for mount in possible_mounts:
            if Path(mount).exists():
                return os.path.join(mount, relative_path) if relative_path else mount
                
        # Default mount point
        return os.path.join('/mnt/servitec', relative_path)
    
    else:
        # Unknown platform - return generic path
        return os.path.join('synology_nas', relative_path) if relative_path else 'synology_nas'

def find_project_on_synology(project_name: str) -> str:
    """
    Find a project directory on the Synology NAS regardless of platform.
    
    Args:
        project_name: Name of the project (e.g., "Hotel_Marina")
    
    Returns:
        Full path to the project directory, or None if not found
    """
    from pathlib import Path
    
    # Common project path patterns
    project_patterns = [
        f'01 PROYECTOS/PRJ-001_{project_name}',
        f'01 PROYECTOS/PRJ - {project_name}', 
        f'01 PROYECTOS/{project_name}',
        f'PROYECTOS/{project_name}'
    ]
    
    synology_base = resolve_synology_path()
    
    for pattern in project_patterns:
        project_path = resolve_synology_path(pattern)
        if Path(project_path).exists():
            return project_path
    
    # Return most likely path even if it doesn't exist
    return resolve_synology_path(f'01 PROYECTOS/PRJ-001_{project_name}')

def get_platform_specific_instructions() -> dict:
    """Get platform-specific instructions for accessing Synology NAS."""
    import platform
    
    system = platform.system()
    
    instructions = {
        'Darwin': {
            'mount_command': 'Cmd+K in Finder',
            'smb_path': 'smb://192.168.10.2/Servitec Ingenieria',
            'mount_location': '/Volumes/Servitec Ingenieria',
            'steps': _get_mount_instructions('Darwin')
        },
        'Windows': {
            'mount_command': 'Map Network Drive',
            'smb_path': '\\\\192.168.10.2\\Servitec Ingenieria',
            'mount_location': 'Mapped drive (e.g., S:)',
            'steps': _get_mount_instructions('Windows')
        },
        'Linux': {
            'mount_command': 'mount -t cifs',
            'smb_path': '//192.168.10.2/Servitec Ingenieria',
            'mount_location': '/mnt/servitec',
            'steps': _get_mount_instructions('Linux')
        }
    }
    
    return instructions.get(system, {
        'mount_command': 'Connect to network share',
        'smb_path': 'smb://192.168.10.2/Servitec Ingenieria',
        'mount_location': 'Platform-specific mount point',
        'steps': ['Connect to Synology NAS at 192.168.10.2']
    })