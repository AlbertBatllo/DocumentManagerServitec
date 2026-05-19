"""
Document File Service
Centralized file operations with filesystem as the single source of truth.

This service eliminates the need to track file_paths in the database.
Instead, it scans the filesystem directly to determine what files belong to a document.
"""

from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from datetime import datetime
import logging

from utils.folder_structure_manager import FolderStructureManager, FileType
from utils.file_type_upload_router import FileTypeUploadRouter
from utils.file_manager import FileManager
from utils.folder_resolver import FolderResolver


@dataclass
class DocumentFile:
    """Represents a file belonging to a document."""
    path: Path
    extension: str
    file_type: FileType
    size: int
    modified_time: datetime
    is_in_working: bool  # True if in Working folder (current), False if in Old

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def relative_path(self) -> str:
        """Get path relative to planos base (for display)."""
        try:
            # Find the planos folder part and return relative from there
            parts = self.path.parts
            for i, part in enumerate(parts):
                if FolderResolver.is_planos_folder(part):
                    return str(Path(*parts[i+1:]))
            return self.path.name
        except Exception:
            return self.path.name


class DocumentFileService:
    """
    Centralized file operations service.

    Filesystem is the ONLY source of truth for document files.
    No database tracking of file_paths required.

    Folder structure:
        02_Planos/
        ├── PDF/
        │   ├── Working/         # Current PDFs: {doc_name}_v{version}_{state}.pdf
        │   └── Old/             # Archived PDFs
        ├── CAD/
        │   ├── Working/         # Current DWG: {doc_name}.dwg
        │   │   └── REF/         # XREF references
        │   └── Old/             # Archived versions
        └── RVT/
            ├── Working/         # Current RVT: {doc_name}.rvt
            └── Old/             # Archived versions
    """

    # Extensions to scan
    SUPPORTED_EXTENSIONS = {'.pdf', '.dwg', '.rvt'}

    # Search locations for each file type (relative to planos base)
    SEARCH_PATHS = {
        '.pdf': ['PDF/Working', 'PDF/Last', 'PDF/Old'],
        '.dwg': ['CAD/Working', 'CAD/Working/REF', 'CAD/Last', 'CAD/Last/REF', 'CAD/Old'],
        '.rvt': ['RVT/Working', 'RVT/Last', 'RVT/Old'],
    }

    def __init__(self, planos_base_path: Path):
        """
        Initialize with planos base path (02_Planos folder).

        Args:
            planos_base_path: Path to the 02_Planos folder
        """
        self.base_path = Path(planos_base_path)
        self.folder_manager = FolderStructureManager(self.base_path)
        self.file_manager = FileManager()
        self.upload_router = FileTypeUploadRouter(self.base_path, self.file_manager)
        self.logger = logging.getLogger(__name__)

        # Ensure folder structure exists
        self.folder_manager.ensure_folder_structure()

    # ========== CORE QUERY METHODS ==========

    def get_document_files(self, doc_name: str) -> List[DocumentFile]:
        """
        Scan filesystem for all files belonging to a document.

        Args:
            doc_name: Document name to search for

        Returns:
            List of DocumentFile objects sorted by modification time (newest first)
        """
        files = []

        for extension, search_paths in self.SEARCH_PATHS.items():
            for rel_path in search_paths:
                folder = self.base_path / rel_path
                if not folder.exists():
                    continue

                # Search for files matching document name
                matches = self._find_matching_files(folder, doc_name, extension)

                for file_path in matches:
                    doc_file = self._create_document_file(file_path, extension, rel_path)
                    if doc_file:
                        files.append(doc_file)

        # Sort by modification time (newest first)
        files.sort(key=lambda f: f.modified_time, reverse=True)
        return files

    def get_files_by_type(self, doc_name: str, extension: str) -> List[Path]:
        """
        Get files of a specific type for a document.

        Args:
            doc_name: Document name
            extension: File extension (e.g., '.pdf', '.dwg')

        Returns:
            List of file paths matching the type
        """
        extension = extension.lower() if not extension.startswith('.') else extension.lower()
        if not extension.startswith('.'):
            extension = f'.{extension}'

        files = []
        search_paths = self.SEARCH_PATHS.get(extension, [])

        for rel_path in search_paths:
            folder = self.base_path / rel_path
            if folder.exists():
                files.extend(self._find_matching_files(folder, doc_name, extension))

        return files

    def file_exists(self, doc_name: str, extension: str) -> bool:
        """
        Quick check if document has a file of specific type.

        Args:
            doc_name: Document name
            extension: File extension (e.g., '.pdf', '.dwg')

        Returns:
            True if at least one file of this type exists
        """
        files = self.get_files_by_type(doc_name, extension)
        return len(files) > 0

    def get_file_extensions(self, doc_name: str) -> Set[str]:
        """
        Get all file extensions for a document.

        Args:
            doc_name: Document name

        Returns:
            Set of extensions (e.g., {'.pdf', '.dwg'})
        """
        files = self.get_document_files(doc_name)
        return {f.extension for f in files}

    def get_primary_file(self, doc_name: str,
                         preferred_extensions: List[str] = None,
                         only_working: bool = True) -> Optional[Path]:
        """
        Get the primary (most important) file for a document.

        Priority order (customizable):
        1. PDF (most commonly needed for viewing)
        2. DWG (CAD source)
        3. RVT (BIM source)

        Args:
            doc_name: Document name
            preferred_extensions: Optional custom priority order
            only_working: If True, only search Working folders (default: True)

        Returns:
            Path to primary file, or None if no files exist
        """
        priority = preferred_extensions or ['.pdf', '.dwg', '.rvt']

        if only_working:
            # Only search in Working folders - for main dashboard double-click
            working_files = self.get_working_files(doc_name)
            for ext in priority:
                ext_lower = ext.lower() if ext.startswith('.') else f'.{ext.lower()}'
                matching = [f for f in working_files if f.extension == ext_lower]
                if matching:
                    # Return newest working file of this type
                    newest = max(matching, key=lambda f: f.modified_time)
                    return newest.path
        else:
            # Search both Working and Old folders
            for ext in priority:
                files = self.get_files_by_type(doc_name, ext)
                if files:
                    # Return newest file of this type
                    return max(files, key=lambda p: p.stat().st_mtime)

        return None

    def get_working_files(self, doc_name: str) -> List[DocumentFile]:
        """
        Get only current/working files (not archived).

        Args:
            doc_name: Document name

        Returns:
            List of DocumentFile objects from Working folders
        """
        all_files = self.get_document_files(doc_name)
        return [f for f in all_files if f.is_in_working]

    # ========== FILE OPERATIONS ==========

    def add_file(self, doc_name: str, source_path: Path,
                 document_info: Dict[str, str] = None) -> Tuple[bool, Optional[Path], str]:
        """
        Add a file to a document (routes to correct folder).

        Args:
            doc_name: Document name
            source_path: Path to file to add
            document_info: Optional document metadata (version, state, author)

        Returns:
            Tuple of (success, destination_path, message)
        """
        try:
            source_path = Path(source_path)
            if not source_path.exists():
                return False, None, f"Source file not found: {source_path}"

            # Build document info for router
            info = document_info or {}
            info['name'] = doc_name

            # Use existing router for proper placement
            success, dest_path, message = self.upload_router.route_file_upload(
                source_path, info
            )

            return success, dest_path, message

        except Exception as e:
            self.logger.error(f"Error adding file for {doc_name}: {e}")
            return False, None, f"Error adding file: {e}"

    def remove_file(self, file_path: Path) -> Tuple[bool, str]:
        """
        Remove a specific file.

        Args:
            file_path: Path to file to remove

        Returns:
            Tuple of (success, message)
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return False, f"File not found: {file_path}"

            file_path.unlink()
            return True, f"Removed: {file_path.name}"

        except Exception as e:
            self.logger.error(f"Error removing file {file_path}: {e}")
            return False, f"Error removing file: {e}"

    def get_file_info(self, file_path: Path) -> Optional[DocumentFile]:
        """
        Get detailed info for a specific file.

        Args:
            file_path: Path to file

        Returns:
            DocumentFile object or None if file doesn't exist
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return None

        extension = file_path.suffix.lower()

        # Determine relative path for is_in_working check
        try:
            rel_path = str(file_path.relative_to(self.base_path))
        except ValueError:
            rel_path = ""

        return self._create_document_file(file_path, extension, rel_path)

    # ========== BATCH OPERATIONS ==========

    def get_all_documents_with_files(self) -> Dict[str, List[str]]:
        """
        Scan filesystem and return all documents with their file extensions.

        Returns:
            Dict mapping document names to list of extensions they have
        """
        documents = {}

        for extension, search_paths in self.SEARCH_PATHS.items():
            for rel_path in search_paths:
                folder = self.base_path / rel_path
                if not folder.exists():
                    continue

                for file_path in folder.glob(f'*{extension}'):
                    if file_path.is_file():
                        # Extract document name from filename
                        doc_name = self._extract_doc_name(file_path.stem, extension)
                        if doc_name:
                            if doc_name not in documents:
                                documents[doc_name] = set()
                            documents[doc_name].add(extension)

        # Convert sets to sorted lists
        return {name: sorted(exts) for name, exts in documents.items()}

    # ========== HELPER METHODS ==========

    def _find_matching_files(self, folder: Path, doc_name: str,
                             extension: str) -> List[Path]:
        """
        Find files in a folder matching document name and extension.

        Handles various naming patterns:
        - Exact match: document_name.dwg
        - Versioned: document_name_v1.0_S2.pdf
        - With timestamp: document_name-20241212.pdf
        """
        matches = []

        if not folder.exists():
            return matches

        # Normalize doc_name for matching
        doc_name_lower = doc_name.lower()
        doc_name_normalized = self._normalize_name(doc_name)

        for file_path in folder.glob(f'*{extension}'):
            if not file_path.is_file():
                continue

            filename_lower = file_path.stem.lower()
            filename_normalized = self._normalize_name(file_path.stem)

            # Check various matching strategies
            if self._names_match(doc_name_normalized, filename_normalized):
                matches.append(file_path)

        return matches

    def _names_match(self, doc_name: str, filename: str) -> bool:
        """
        Check if a filename matches a document name.

        Handles:
        - Exact match
        - Filename starts with doc_name (for versioned files)
        """
        # Exact match
        if doc_name == filename:
            return True

        # Filename starts with doc_name (handles versioning like _v1.0_S2)
        if filename.startswith(doc_name):
            remainder = filename[len(doc_name):]
            if not remainder or remainder[0] in ('_', '-', '.', 'v', ' '):
                return True

        return False

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison."""
        import re
        # Remove common separators and lowercase
        normalized = name.lower().replace(' ', '_').replace('-', '_')
        # Collapse multiple underscores into one
        normalized = re.sub(r'_+', '_', normalized)
        return normalized

    def _create_document_file(self, file_path: Path, extension: str,
                              rel_path: str) -> Optional[DocumentFile]:
        """Create a DocumentFile object from a file path."""
        try:
            stat = file_path.stat()

            # Determine file type
            file_type = FileType.from_extension(extension)
            if not file_type:
                return None

            # Determine if in working/current folder (Working or Last = current versions)
            is_working = 'Working' in rel_path or 'Last' in rel_path

            return DocumentFile(
                path=file_path,
                extension=extension.lower(),
                file_type=file_type,
                size=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime),
                is_in_working=is_working
            )
        except Exception as e:
            self.logger.warning(f"Could not create DocumentFile for {file_path}: {e}")
            return None

    def _extract_doc_name(self, filename_stem: str, extension: str) -> Optional[str]:
        """
        Extract document name from filename.

        Handles patterns like:
        - document_name.dwg -> document_name
        - document_name_v1.0_S2.pdf -> document_name
        - document_name-20241212.pdf -> document_name
        """
        name = filename_stem

        # Remove version patterns: _v1.0, _v2.1, etc.
        import re
        name = re.sub(r'_v\d+(\.\d+)?', '', name)

        # Remove state patterns: _S0, _S1, _S2, etc.
        name = re.sub(r'_S\d+', '', name)

        # Remove timestamp patterns: -20241212, _20241212, etc.
        name = re.sub(r'[-_]\d{8,14}', '', name)

        # Remove trailing underscores
        name = name.rstrip('_')

        return name if name else None
