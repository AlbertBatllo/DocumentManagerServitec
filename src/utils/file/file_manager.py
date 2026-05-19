import shutil
from pathlib import Path
import re
import subprocess
import sys
import os
import json
import threading
import logging
try:
    import fcntl
except ImportError:
    # Windows doesn't have fcntl module
    fcntl = None
import time
from typing import Optional, Tuple, Dict, Any, List


class FileManager:
    # Simple directory listing cache to improve performance
    _dir_cache: Dict[str, Tuple[float, List[str]]] = {}
    _cache_ttl = 30.0  # Cache for 30 seconds
    
    # Thread-safe locks for caches and file operations
    _cache_lock = threading.RLock()
    _json_cache_lock = threading.RLock()
    _file_operation_locks: Dict[str, threading.RLock] = {}
    _locks_lock = threading.RLock()
    
    # Logger for file operations
    _logger = logging.getLogger(__name__)
    
    @staticmethod
    def _get_cached_directory_listing(directory: Path) -> Optional[List[str]]:
        """Thread-safe get cached directory listing if available and not stale."""
        with FileManager._cache_lock:
            dir_str = str(directory)
            if dir_str in FileManager._dir_cache:
                cached_time, cached_files = FileManager._dir_cache[dir_str]
                if time.time() - cached_time < FileManager._cache_ttl:
                    return cached_files.copy()  # Return copy to prevent modification
            return None
    
    @staticmethod
    def _cache_directory_listing(directory: Path, files: List[str]) -> None:
        """Thread-safe cache directory listing with timestamp."""
        with FileManager._cache_lock:
            dir_str = str(directory)
            FileManager._dir_cache[dir_str] = (time.time(), files.copy())
    
    @staticmethod
    def get_directory_files(directory: Path, pattern: Optional[str] = None) -> List[Path]:
        """Get files in directory with optional pattern matching, using cache for performance."""
        if not directory.exists():
            return []
        
        # Try to get from cache first
        cached_files = FileManager._get_cached_directory_listing(directory)
        if cached_files is not None:
            files = [directory / f for f in cached_files]
        else:
            # Get fresh listing and cache it
            try:
                files = [f for f in directory.iterdir() if f.is_file()]
                file_names = [f.name for f in files]
                FileManager._cache_directory_listing(directory, file_names)
            except (OSError, PermissionError) as e:
                print(f"Warning: Could not list directory {directory}: {e}")
                return []
        
        # Apply pattern filtering if specified
        if pattern:
            import fnmatch
            files = [f for f in files if fnmatch.fnmatch(f.name, pattern)]
        
        return files
    
    @staticmethod
    def sanitize_for_filename(text: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', text)

    # CAD file extensions that should have stable names (no version/state)
    CAD_EXTENSIONS = {'.dwg', '.rvt', '.dxf', '.ifc'}

    @staticmethod
    def generate_filename(base_name: str, document_name: str, version: str, file_extension: str, state: str = None) -> str:
        # Generate filename with optional state parameter for planos support
        sanitized_base_name = FileManager.sanitize_for_filename(base_name)
        sanitized_document_name = FileManager.sanitize_for_filename(document_name)
        sanitized_version = FileManager.sanitize_for_filename(version)

        # Use base_name as the primary identifier, but clean up redundancy
        clean_base_name = FileManager._clean_redundant_patterns(sanitized_base_name)

        # Ensure extension starts with a dot
        if file_extension and not file_extension.startswith('.'):
            file_extension = f".{file_extension}"

        # CAD files (DWG, RVT, etc.) get stable names without version/state
        # This preserves XREF compatibility - XREFs reference by filename
        if file_extension.lower() in FileManager.CAD_EXTENSIONS:
            return f"{clean_base_name}{file_extension}"

        # Generate filename based on whether state is provided
        if state:
            # Planos PDF format: name_vVersion_state.ext (for state-based files)
            sanitized_state = FileManager.sanitize_for_filename(state)
            # Ensure version has 'v' prefix for planos
            version_with_v = sanitized_version if sanitized_version.startswith('v') else f"v{sanitized_version}"
            return f"{clean_base_name}_{version_with_v}_{sanitized_state}{file_extension}"
        else:
            # Licitaciones format: name_version.ext (no state, as state changes don't create new files)
            return f"{clean_base_name}_{sanitized_version}{file_extension}"
    
    @staticmethod
    def _clean_redundant_patterns(text: str) -> str:
        """Remove redundant patterns from document names"""
        if not text:
            return text
        
        # Split by common separators
        parts = text.replace('_', ' ').replace('-', ' ').split()
        
        # Remove duplicate words (case insensitive) - keep only first occurrence
        seen_words = set()
        cleaned_parts = []
        
        for part in parts:
            if part and part.upper() not in seen_words:
                cleaned_parts.append(part)
                seen_words.add(part.upper())
        
        # Rejoin with underscores for filename
        return '_'.join(cleaned_parts)

    @staticmethod
    def copy_file(source: Path, destination: Path) -> None:
        shutil.copy2(source, destination)

    @staticmethod
    def rename_file(old_path: Path, new_path: Path) -> None:
        if old_path.exists():
            old_path.rename(new_path)

    @staticmethod
    def move_file(source: Path, destination: Path) -> None:
        """
        Move a file from source to destination.
        Creates destination directory if it doesn't exist.
        """
        # Ensure destination directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        if source.exists():
            shutil.move(str(source), str(destination))
        else:
            raise FileNotFoundError(f"Source file does not exist: {source}")

    @staticmethod
    def file_exists(file_path: Path) -> bool:
        return file_path.exists()

    @staticmethod
    def open_file_location(file_path: Path) -> None:
        """
        Open the file location in the system file explorer.

        Args:
            file_path: Path to the file to reveal

        Raises:
            FileNotFoundError: If the file doesn't exist
            OSError: If the file explorer cannot be opened
        """
        # Convert to Path if string
        if isinstance(file_path, str):
            file_path = Path(file_path)

        # Resolve to absolute path
        file_path = file_path.resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"El archivo no existe: {file_path}")

        # Open the folder containing the file
        folder = file_path.parent

        try:
            if sys.platform == "win32":
                # Windows: Use explorer and select the file
                # Note: /select, requires the comma
                subprocess.run(
                    ["explorer", "/select,", str(file_path)],
                    check=False,  # explorer returns non-zero even on success
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
            elif sys.platform == "darwin":
                # macOS: Use open -R to reveal in Finder
                # Run synchronously and check for errors
                result = subprocess.run(
                    ["open", "-R", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    # Fallback: just open the folder
                    FileManager._logger.warning(
                        f"open -R failed ({result.returncode}): {result.stderr}. "
                        f"Falling back to opening folder."
                    )
                    subprocess.run(["open", str(folder)], timeout=10)
            else:
                # Linux: Try xdg-open for the folder
                subprocess.run(["xdg-open", str(folder)], timeout=10)
        except subprocess.TimeoutExpired:
            FileManager._logger.error(f"Timeout opening file location: {file_path}")
            raise OSError(f"Timeout al abrir la ubicación del archivo: {file_path}")
        except Exception as e:
            FileManager._logger.error(f"Error opening file location {file_path}: {e}")
            raise OSError(f"No se pudo abrir la ubicación del archivo: {e}")

    @staticmethod
    def parse_filename(filename: str) -> Optional[Tuple[str, str, str]]:
        """
        Parse a filename to extract ID, version, and state.
        Returns (id, version, state) or None if parsing fails.
        Handles both old format (name_version_state) and new format (name_version).
        """
        # Remove extension first
        name_without_ext = Path(filename).stem
        
        # Try to match the old pattern: ID_vVersion_State
        match = re.match(r'^([^_]+)_v(\d+(?:\.\d+)?)_([^_]+)$', name_without_ext)
        if match:
            return match.groups()
        
        # Try to match the new pattern: ID_vVersion (no state)
        match = re.match(r'^([^_]+)_v(\d+(?:\.\d+)?)$', name_without_ext)
        if match:
            return (match.group(1), match.group(2), "")  # Return empty state
        
        # Try to match without 'v' prefix: ID_Version_State (legacy)
        match = re.match(r'^([^_]+)_(\d+(?:\.\d+)?)_([^_]+)$', name_without_ext)
        if match:
            return match.groups()
        
        # Try to match without 'v' prefix: ID_Version (new format)
        match = re.match(r'^([^_]+)_(\d+(?:\.\d+)?)$', name_without_ext)
        if match:
            return (match.group(1), match.group(2), "")  # Return empty state
        
        return None

    @staticmethod
    def get_file_extension(filename: str) -> str:
        return Path(filename).suffix.lstrip('.')

    @staticmethod
    def generate_numbered_filename(base_filename: str, file_number: int) -> str:
        """
        Generate a numbered filename by inserting _N before the extension.
        e.g., 'document.pdf' with number 2 becomes 'document_2.pdf'
        """
        path = Path(base_filename)
        stem = path.stem
        suffix = path.suffix
        if file_number == 1:
            return base_filename  # First file keeps original name
        return f"{stem}_{file_number}{suffix}"

    @staticmethod
    def find_pattern_files(directory: Path, base_pattern: str) -> List[Path]:
        """
        Find all files matching a base pattern, including numbered variants.
        e.g., for pattern 'DOC_01_Company_v1.0', finds:
        - DOC_01_Company_v1.0.pdf
        - DOC_01_Company_v1.0_1.pdf  
        - DOC_01_Company_v1.0_2.pdf
        """
        if not directory.exists():
            return []
        
        pattern_files = []
        # Look for exact base pattern files
        for file_path in directory.iterdir():
            if file_path.is_file():
                file_stem = file_path.stem
                # Check if file matches base pattern exactly
                if file_stem.startswith(base_pattern):
                    # Either exact match or numbered variant (_N at end)
                    remainder = file_stem[len(base_pattern):]
                    if not remainder or (remainder.startswith('_') and remainder[1:].isdigit()):
                        pattern_files.append(file_path)
        
        return sorted(pattern_files)

    @staticmethod
    def get_next_file_number(directory: Path, base_filename: str) -> int:
        """
        Get the next available file number for a base filename.
        Returns 1 if no files exist, otherwise returns the next number.
        """
        base_path = Path(base_filename)
        base_stem = base_path.stem
        existing_files = FileManager.find_pattern_files(directory, base_stem)
        
        if not existing_files:
            return 1
            
        max_number = 0
        for file_path in existing_files:
            file_stem = file_path.stem
            remainder = file_stem[len(base_stem):]
            if not remainder:
                max_number = max(max_number, 1)  # Base file counts as 1
            elif remainder.startswith('_') and remainder[1:].isdigit():
                max_number = max(max_number, int(remainder[1:]))
        
        return max_number + 1

    # Class-level cache for JSON files
    _json_cache: Dict[str, Tuple[float, Dict]] = {}
    
    @staticmethod
    def _get_file_lock(filepath: str) -> threading.RLock:
        """Get or create a per-file lock for thread-safe operations"""
        with FileManager._locks_lock:
            if filepath not in FileManager._file_operation_locks:
                FileManager._file_operation_locks[filepath] = threading.RLock()
            return FileManager._file_operation_locks[filepath]
    
    @staticmethod
    def safe_json_read(filepath: str, max_retries: int = 3) -> Dict[Any, Any]:
        """
        Thread-safe JSON file reading with caching and non-blocking I/O.
        
        Args:
            filepath: Path to JSON file
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dictionary containing JSON data
            
        Raises:
            FileNotFoundError: If file doesn't exist after retries
            json.JSONDecodeError: If JSON is invalid
            IOError: If file can't be read after retries
        """
        # Get per-file lock to prevent concurrent access to the same file
        file_lock = FileManager._get_file_lock(filepath)
        
        with file_lock:
            # Check cache first (with cache lock)
            with FileManager._json_cache_lock:
                if filepath in FileManager._json_cache:
                    try:
                        file_mtime = os.path.getmtime(filepath)
                        cache_time, cache_data = FileManager._json_cache[filepath]
                        # Return cached data if file hasn't changed
                        if abs(file_mtime - cache_time) < 0.1:  # 100ms tolerance
                            FileManager._logger.debug(f"Using cached data for {filepath}")
                            return cache_data.copy()  # Return copy to prevent modification
                    except OSError:
                        pass  # File might have been deleted, proceed with normal read
            
            for attempt in range(max_retries):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        # Try non-blocking lock first (Unix-like systems only)
                        if fcntl:
                            try:
                                fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                            except IOError:
                                # If can't get lock immediately, read anyway (most reads are safe)
                                pass
                        
                        data = json.load(f)
                        
                        # Cache the data with cache lock
                        with FileManager._json_cache_lock:
                            try:
                                FileManager._json_cache[filepath] = (os.path.getmtime(filepath), data.copy())
                                FileManager._logger.debug(f"Cached data for {filepath}")
                            except OSError:
                                pass
                        
                        # Lock automatically released when file closes
                        return data
                except (IOError, OSError) as e:
                    if attempt == max_retries - 1:
                        FileManager._logger.error(f"Failed to read {filepath} after {max_retries} attempts: {e}")
                        raise
                    # Reduced backoff: wait 0.01, 0.02, 0.04 seconds
                    time.sleep(0.01 * (2 ** attempt))
                except FileNotFoundError:
                    # Return empty dict if file doesn't exist
                    FileManager._logger.debug(f"File not found: {filepath}")
                    return {}
                except json.JSONDecodeError as e:
                    # Re-raise JSON errors immediately
                    FileManager._logger.error(f"JSON decode error in {filepath}: {e}")
                    raise
            
            return {}

    @staticmethod
    def safe_json_write(filepath: str, data: Dict[Any, Any], max_retries: int = 3) -> None:
        """
        Thread-safe JSON file writing with file locking and retry logic.
        
        Args:
            filepath: Path to JSON file
            data: Dictionary to write as JSON
            max_retries: Maximum number of retry attempts
            
        Raises:
            IOError: If file can't be written after retries
        """
        # Get per-file lock to prevent concurrent access to the same file
        file_lock = FileManager._get_file_lock(filepath)
        
        with file_lock:
            # Ensure directory exists
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            
            for attempt in range(max_retries):
                temp_filepath = f"{filepath}.tmp.{threading.current_thread().ident}"
                try:
                    # Write to temporary file first for atomic operation
                    with open(temp_filepath, 'w', encoding='utf-8') as f:
                        # Acquire exclusive lock for writing (Unix-like systems only)
                        if fcntl:
                            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        json.dump(data, f, indent=2, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())  # Force write to disk
                        # Lock automatically released when file closes
                    
                    # Atomic rename (use replace for cross-platform compatibility)
                    # os.replace works on Windows even if destination exists
                    os.replace(temp_filepath, filepath)
                    
                    # Clear cache entry for this file
                    with FileManager._json_cache_lock:
                        FileManager._json_cache.pop(filepath, None)
                    
                    FileManager._logger.debug(f"Successfully wrote {filepath}")
                    return
                    
                except (IOError, OSError) as e:
                    # Clean up temp file if it exists
                    if os.path.exists(temp_filepath):
                        try:
                            os.remove(temp_filepath)
                        except (OSError, FileNotFoundError) as cleanup_error:
                            FileManager._logger.warning(f"Could not remove temp file {temp_filepath}: {cleanup_error}")
                            pass
                            
                    if attempt == max_retries - 1:
                        FileManager._logger.error(f"Failed to write {filepath} after {max_retries} attempts: {e}")
                        raise
                    # Exponential backoff: wait 0.1, 0.2, 0.4 seconds
                    time.sleep(0.1 * (2 ** attempt))
    
    @staticmethod
    def clear_caches():
        """Clear all caches (useful for testing)"""
        with FileManager._cache_lock, FileManager._json_cache_lock:
            FileManager._dir_cache.clear()
            FileManager._json_cache.clear()
            FileManager._logger.info("All file caches cleared")
    
    @staticmethod
    def get_cache_stats() -> Dict[str, int]:
        """Get cache statistics for monitoring"""
        with FileManager._cache_lock, FileManager._json_cache_lock:
            return {
                "dir_cache_entries": len(FileManager._dir_cache),
                "json_cache_entries": len(FileManager._json_cache),
                "file_locks": len(FileManager._file_operation_locks)
            }