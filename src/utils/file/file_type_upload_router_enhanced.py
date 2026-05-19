"""
Enhanced File Type Upload Router with Upload-Time XREF Detection

Integrates background XREF processing into the file upload workflow
for seamless CAD reference management.
"""

from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import shutil
import json
from enum import Enum
import threading
import sqlite3
import hashlib
from datetime import datetime

from .folder_structure_manager import FolderStructureManager, FileType
from .file_manager import FileManager


class NamingStrategy(Enum):
    """Naming strategies for different file types"""
    FULL_VERSIONING = "full_versioning"  # PDFs: Document_v1.1_S2.pdf
    STABLE_BASE = "stable_base"          # CAD/RVT: document_name.dwg


class XrefUploadManager:
    """Manages XREF detection during file uploads."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / '.document_manager' / 'upload_xrefs.db'
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_database()
        self._processing_queue = []
        self._lock = threading.Lock()
    
    def _init_database(self):
        """Initialize XREF database."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS file_xrefs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_hash TEXT NOT NULL,
                    xrefs TEXT NOT NULL,  -- JSON array of XREFs
                    processed_time TEXT NOT NULL,
                    processing_duration REAL NOT NULL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON file_xrefs(file_path)')
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Get file hash for change detection."""
        stat = file_path.stat()
        return hashlib.md5(f"{file_path}_{stat.st_size}_{stat.st_mtime}".encode()).hexdigest()
    
    def queue_for_processing(self, file_path: Path):
        """Queue DWG file for background XREF processing."""
        if file_path.suffix.lower() == '.dwg':
            with self._lock:
                self._processing_queue.append(file_path)
    
    def get_cached_xrefs(self, file_path: Path) -> Optional[List[str]]:
        """Get cached XREF results if available and up-to-date."""
        if not file_path.exists() or file_path.suffix.lower() != '.dwg':
            return None
        
        current_hash = self._get_file_hash(file_path)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                'SELECT xrefs, file_hash FROM file_xrefs WHERE file_path = ?',
                (str(file_path),)
            )
            result = cursor.fetchone()
            
            if result and result[1] == current_hash:
                # File hasn't changed, return cached XREFs
                return json.loads(result[0])
        
        return None
    
    def store_xrefs(self, file_path: Path, xrefs: List[str], duration: float):
        """Store XREF results in database."""
        file_hash = self._get_file_hash(file_path)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO file_xrefs 
                (file_path, file_hash, xrefs, processed_time, processing_duration)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                str(file_path),
                file_hash,
                json.dumps(xrefs),
                datetime.now().isoformat(),
                duration
            ))
    
    def process_pending_files(self):
        """Process queued files in background thread."""
        def worker():
            from utils.cad.dwg_xref import extract_dwg_references as get_xrefs_fast
            import time
            
            while True:
                file_to_process = None
                
                with self._lock:
                    if self._processing_queue:
                        file_to_process = self._processing_queue.pop(0)
                
                if file_to_process:
                    try:
                        start_time = time.time()
                        xrefs = get_xrefs_fast(file_to_process)
                        duration = time.time() - start_time
                        
                        self.store_xrefs(file_to_process, xrefs, duration)
                        
                    except Exception as e:
                        # Log error but continue processing
                        print(f"XREF processing error for {file_to_process}: {e}")
                else:
                    time.sleep(1)  # No files to process, wait
        
        # Start background thread if not already running
        if not hasattr(self, '_worker_thread') or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(target=worker, daemon=True)
            self._worker_thread.start()


class EnhancedFileTypeUploadRouter:
    """
    Enhanced File Type Upload Router with integrated XREF processing.
    
    Automatically detects and stores XREF relationships during DWG uploads
    for instant access later.
    """
    
    # Define naming strategies for each file type
    NAMING_STRATEGIES = {
        FileType.PDF: NamingStrategy.FULL_VERSIONING,
        FileType.DWG: NamingStrategy.STABLE_BASE,
        FileType.RVT: NamingStrategy.STABLE_BASE
    }
    
    def __init__(self, planos_base_path: Path, file_manager: FileManager = None):
        """Initialize with planos base path and XREF manager."""
        self.planos_path = Path(planos_base_path)
        self.folder_manager = FolderStructureManager(self.planos_path)
        self.file_manager = file_manager or FileManager()
        self.xref_manager = XrefUploadManager()
        
        # Ensure organized folder structure exists
        self.folder_manager.ensure_folder_structure()
        
        # Start background XREF processing
        self.xref_manager.process_pending_files()
    
    def route_file_upload(self, source_path: Path, document_info: Dict[str, str], 
                         upload_context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Path, str]:
        """
        Route a file upload with integrated XREF processing.
        
        Args:
            source_path: Path to the file being uploaded
            document_info: Dictionary with document metadata
            upload_context: Optional context for upload
            
        Returns:
            Tuple of (success, final_path, message)
        """
        try:
            # Detect file type
            file_type = self.folder_manager.detect_file_type(source_path)
            if not file_type:
                return False, source_path, f"Unsupported file type: {source_path.suffix}"
            
            # Get naming strategy for this file type
            naming_strategy = self.NAMING_STRATEGIES[file_type]
            
            # Generate target filename based on strategy
            target_filename = self._generate_target_filename(
                source_path, document_info, file_type, naming_strategy, upload_context
            )
            
            # Get target folder for this file type
            target_folder = self.folder_manager.get_folder_path(file_type)
            target_path = target_folder / target_filename
            
            # Handle file conflicts
            final_path, conflict_message = self._handle_file_conflicts(
                source_path, target_path, file_type, naming_strategy
            )
            
            # Copy file to final location
            self.file_manager.copy_file(source_path, final_path)
            
            # Enhanced XREF processing for DWG files
            xref_message = ""
            if file_type == FileType.DWG:
                xref_message = self._handle_dwg_xref_processing(final_path, document_info)
            elif file_type == FileType.RVT:
                xref_message = "📁 RVT reference processing not yet implemented"
            
            # Prepare success message
            message = f"✅ {file_type.value.upper()} uploaded: {final_path.name}"
            if conflict_message:
                message += f" ({conflict_message})"
            if xref_message:
                message += f" {xref_message}"
            
            return True, final_path, message
            
        except Exception as e:
            return False, source_path, f"Upload failed: {e}"
    
    def _handle_dwg_xref_processing(self, dwg_path: Path, document_info: Dict[str, str]) -> str:
        """Handle XREF processing for uploaded DWG files."""
        try:
            # Check if we have cached XREF data
            cached_xrefs = self.xref_manager.get_cached_xrefs(dwg_path)
            
            if cached_xrefs is not None:
                # We have up-to-date XREF data
                if len(cached_xrefs) == 0:
                    return "📁 No external references (cached)"
                else:
                    # Try to organize references
                    organized_count = self._organize_xref_files(dwg_path, cached_xrefs, document_info)
                    return f"📁 {len(cached_xrefs)} references found, {organized_count} organized (cached)"
            else:
                # No cached data - queue for background processing
                self.xref_manager.queue_for_processing(dwg_path)
                return "📁 Queued for reference analysis"
                
        except Exception as e:
            return f"⚠️ XREF processing error: {e}"
    
    def _organize_xref_files(self, dwg_path: Path, xref_names: List[str], document_info: Dict[str, str]) -> int:
        """Organize XREF files into appropriate folders."""
        organized_count = 0
        
        try:
            # Determine target references folder
            state = document_info.get("state", "S0")
            base_folder = self.folder_manager.get_folder_path(FileType.DWG)
            
            # Determine subfolder based on state
            if state in ["S0", "S1", "S2"]:
                subfolder = "Working"
            else:
                subfolder = "Old"
            
            refs_folder = base_folder / subfolder / "REF"
            refs_folder.mkdir(parents=True, exist_ok=True)
            
            # Look for XREF files in common locations
            search_paths = [
                self.planos_path / "REF",
                dwg_path.parent / "REF",
                self.planos_path.parent / "REF",
                dwg_path.parent,  # Same directory as DWG
            ]
            
            for xref_name in xref_names:
                found = False
                for search_path in search_paths:
                    if search_path.exists():
                        xref_file = search_path / xref_name
                        if xref_file.exists():
                            try:
                                dest_file = refs_folder / xref_name
                                if not dest_file.exists():
                                    shutil.copy2(xref_file, dest_file)
                                    organized_count += 1
                                    found = True
                                    break
                            except Exception:
                                continue
                
                if not found:
                    # XREF file not found - this is normal for some cases
                    continue
                    
        except Exception as e:
            # Non-critical error in file organization
            pass
        
        return organized_count
    
    def get_file_xrefs(self, file_path: Path) -> Dict[str, Any]:
        """
        Get XREF information for a file (instant if processed during upload).
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with XREF information
        """
        if file_path.suffix.lower() != '.dwg':
            return {
                'success': False,
                'references': [],
                'reference_count': 0,
                'error': 'Not a DWG file'
            }
        
        # Try cached data first
        cached_xrefs = self.xref_manager.get_cached_xrefs(file_path)
        if cached_xrefs is not None:
            return {
                'success': True,
                'references': cached_xrefs,
                'reference_count': len(cached_xrefs),
                'source': 'cached_upload_processing'
            }
        
        # Not in cache - process now (fallback)
        try:
            from utils.cad.dwg_xref import extract_dwg_references as get_xrefs_fast
            import time
            
            start_time = time.time()
            xrefs = get_xrefs_fast(file_path)
            duration = time.time() - start_time
            
            # Store for future use
            self.xref_manager.store_xrefs(file_path, xrefs, duration)
            
            return {
                'success': True,
                'references': xrefs,
                'reference_count': len(xrefs),
                'source': 'processed_on_demand',
                'processing_time': duration
            }
            
        except Exception as e:
            return {
                'success': False,
                'references': [],
                'reference_count': 0,
                'error': str(e)
            }
    
    # ... (rest of the methods from original FileTypeUploadRouter)
    
    def _generate_target_filename(self, source_path: Path, document_info: Dict[str, str], 
                                 file_type: FileType, naming_strategy: NamingStrategy,
                                 upload_context: Optional[Dict[str, Any]] = None) -> str:
        """Generate target filename based on file type and naming strategy"""
        
        doc_name = document_info.get("name", "")
        version = document_info.get("version", "1.0")
        state = document_info.get("state", "S0")
        display_name = document_info.get("display_name", doc_name)
        
        file_extension = source_path.suffix.lower()
        
        if naming_strategy == NamingStrategy.FULL_VERSIONING:
            # PDFs: Full versioning like existing system
            clean_name = self._sanitize_filename(display_name or doc_name)
            return f"{clean_name}_v{version}_{state}{file_extension}"
            
        elif naming_strategy == NamingStrategy.STABLE_BASE:
            # CAD/RVT: Stable base names to preserve Xrefs
            clean_name = self._sanitize_filename(display_name or doc_name)
            return f"{clean_name}{file_extension}"
            
        else:
            # Fallback to source filename
            return source_path.name
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename for file system compatibility"""
        # Replace problematic characters
        sanitized = name.replace(" ", "_").replace("-", "_")
        
        # Remove other problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            sanitized = sanitized.replace(char, "_")
        
        # Remove multiple consecutive underscores
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        
        return sanitized
    
    def _handle_file_conflicts(self, source_path: Path, target_path: Path, 
                              file_type: FileType, naming_strategy: NamingStrategy) -> Tuple[Path, str]:
        """Handle file conflicts based on file type and naming strategy."""
        if not target_path.exists():
            return target_path, ""
        
        if naming_strategy == NamingStrategy.STABLE_BASE:
            return self._handle_stable_name_conflict(source_path, target_path)
        elif naming_strategy == NamingStrategy.FULL_VERSIONING:
            return self._handle_versioned_name_conflict(source_path, target_path)
        else:
            return self._create_timestamped_backup(target_path), "replaced existing file"
    
    def _handle_stable_name_conflict(self, source_path: Path, target_path: Path) -> Tuple[Path, str]:
        """Handle conflicts for files with stable names (CAD/RVT)."""
        if target_path.exists():
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{target_path.stem}_backup_{timestamp}{target_path.suffix}"
            backup_path = target_path.parent / backup_name
            
            shutil.move(str(target_path), str(backup_path))
            return target_path, f"previous version backed up as {backup_name}"
        
        return target_path, ""
    
    def _handle_versioned_name_conflict(self, source_path: Path, target_path: Path) -> Tuple[Path, str]:
        """Handle conflicts for files with versioning (PDFs)."""
        if target_path.exists():
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
            backup_name = f"{target_path.stem}_replaced_{timestamp}{target_path.suffix}"
            backup_path = target_path.parent / backup_name
            
            shutil.move(str(target_path), str(backup_path))
            return target_path, f"existing file backed up as {backup_name}"
        
        return target_path, ""
    
    def _create_timestamped_backup(self, target_path: Path) -> Path:
        """Create a timestamped backup and return the original path"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{target_path.stem}_backup_{timestamp}{target_path.suffix}"
        backup_path = target_path.parent / backup_name
        
        shutil.move(str(target_path), str(backup_path))
        return target_path