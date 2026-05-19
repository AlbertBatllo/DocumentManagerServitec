"""
Minimal Lock Manager for Document Management System.
Uses the simplest possible cross-platform file locking.
"""

import time
import tempfile
from pathlib import Path
from contextlib import contextmanager

class MinimalFileLock:
    """Ultra-simple file lock using atomic file creation."""
    
    def __init__(self, lock_file: Path, timeout: float = 10.0):
        self.lock_file = Path(lock_file)
        self.timeout = timeout
        
    def __enter__(self):
        # Ensure lock directory exists
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                # Try to create lock file atomically
                with open(self.lock_file, 'x'):
                    pass  # File created, lock acquired
                return self
            except FileExistsError:
                # Check if lock file is stale (older than 2x timeout period for safety)
                try:
                    file_age = time.time() - self.lock_file.stat().st_mtime
                    if file_age > self.timeout * 2:  # Only remove if really old
                        # Stale lock, remove it and try again
                        self.lock_file.unlink(missing_ok=True)
                        continue  # Try again immediately
                except:
                    pass  # If we can't check, just wait normally
                    
                time.sleep(0.1)  # Wait and retry
        
        raise TimeoutError(f"Could not acquire lock {self.lock_file}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.lock_file.unlink(missing_ok=True)
        except:
            pass  # If cleanup fails, ignore it


class ProjectLockManager:
    """Simple project-level lock manager."""
    
    def __init__(self, project_path: Path):
        # Use temp directory for locks
        temp_dir = Path(tempfile.gettempdir())
        project_hash = str(abs(hash(str(project_path.resolve()))))[:8]
        self.lock_dir = temp_dir / f"doc_locks_{project_hash}"
    
    @contextmanager  
    def database_transaction_lock(self, doc_id: str = ""):
        """Lock for database transactions."""
        lock_file = self.lock_dir / "db.lock"
        with MinimalFileLock(lock_file):
            yield
    
# Global lock managers - one per project
_project_managers = {}

def get_project_lock_manager(project_path: Path) -> ProjectLockManager:
    """Get lock manager for a project."""
    key = str(project_path.resolve())
    if key not in _project_managers:
        _project_managers[key] = ProjectLockManager(project_path)
    return _project_managers[key]

@contextmanager  
def safe_database_operation(project_path: Path, doc_id: str = ""):
    """Simple database operation with locking."""
    manager = get_project_lock_manager(project_path)
    with manager.database_transaction_lock(doc_id):
        yield