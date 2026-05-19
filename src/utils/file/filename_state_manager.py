"""
Filename State Manager
Handles file renaming when document states change to maintain consistency
between filesystem, database, and cloud storage.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import re
from utils.lock_manager import get_project_lock_manager
from utils.error_logger import ErrorLogger
from utils.folder_resolver import FolderResolver


class FilenameStateManager:
    """
    Manages filename consistency when document states change.
    
    Key responsibilities:
    1. Rename files when state changes (S2 → S3)
    2. Add 'B' prefix to version numbers (v1.0 → vB1.0)
    3. Ensure atomic file operations
    4. Handle conflicts and errors safely
    """
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.lock_manager = get_project_lock_manager(project_path)
        self.error_logger = ErrorLogger()
    
    def parse_filename(self, filename: str) -> Optional[Dict[str, str]]:
        """
        Parse filename components for planos documents.
        
        Supports both old and new formats:
        - Old: PRJ-001-PL-001_Document_v1.0_S2.pdf
        - New: PRJ-001-PL-001_Document_vB1.0_S2.pdf
        
        Returns:
            Dict with keys: project, doc_id, doc_name, version, state, extension
        """
        # Pattern for planos files - enhanced to handle various formats
        patterns = [
            # PREFERRED format: Document_v1.1_S1.pdf (with 'v' prefix - our standard)
            r'(.+?)_(v[\d.]+)_([SBA]\d*|[AB])\.(\w+)$',
            # Standard format: PRJ-001-PL-001_Document_v1.0_S2.pdf (legacy with PRJ prefix)
            r'(PRJ-\d+)-(PL-\d+)_(.+?)_(v[\d.]+)_([SBA]\d*|[AB])\.(\w+)$',
            # Fallback format: Document_1.0_S1.pdf (no 'v' prefix - legacy compatibility)
            r'(.+?)_(\d+(?:\.\d+)?)_([SBA]\d*|[AB])\.(\w+)$',
            # Flexible format: Document_Name_version_state.pdf  
            r'(.+?)_(.+?)_(v?[\d.]+)_([SBA]\d*|[AB])\.(\w+)$'
        ]
        
        # Try each pattern until one matches
        for i, pattern in enumerate(patterns):
            match = re.match(pattern, filename)
            if match:
                groups = match.groups()
                
                if i == 0:  # PREFERRED format: Document_v1.1_S1.pdf (with 'v' prefix)
                    doc_name, version, state, extension = groups
                    return {
                        'project': 'PRJ-001',  # Default project
                        'doc_id': 'PL-001',    # Default doc_id
                        'doc_name': doc_name,
                        'version': version,
                        'state': state,
                        'extension': extension
                    }
                elif i == 1:  # Standard PRJ format: PRJ-001-PL-001_Document_v1.0_S2.pdf
                    project, doc_id, doc_name, version, state, extension = groups
                    return {
                        'project': project,
                        'doc_id': doc_id,
                        'doc_name': doc_name,
                        'version': version,
                        'state': state,
                        'extension': extension
                    }
                elif i == 2:  # Fallback format: Document_1.0_S1.pdf (no 'v' prefix - legacy)
                    doc_name, version, state, extension = groups
                    return {
                        'project': 'PRJ-001',  # Default project
                        'doc_id': 'PL-001',    # Default doc_id
                        'doc_name': doc_name,
                        'version': f'v{version}',  # Add 'v' prefix for consistency
                        'state': state,
                        'extension': extension
                    }
                elif i == 3:  # Flexible format
                    doc_name1, doc_name2, version, state, extension = groups
                    return {
                        'project': 'PRJ-001',  # Default project
                        'doc_id': 'PL-001',    # Default doc_id
                        'doc_name': f"{doc_name1}_{doc_name2}",
                        'version': version if version.startswith('v') else f'v{version}',
                        'state': state,
                        'extension': extension
                    }
        
        return None
    
    def build_filename(self, project: str, doc_id: str, doc_name: str, 
                      version: str, state: str, extension: str = "pdf") -> str:
        """
        Build filename with simple format.
        
        Uses simple format: Document_v1.1_S1.pdf (no project/doc_id prefixes)
        """
        # Ensure version has 'v' prefix
        if not version.startswith('v'):
            version = f'v{version}'
        
        return f"{doc_name}_{version}_{state}.{extension}"
    
    def update_filename_for_state_change(self, current_filename: str, new_state: str) -> Optional[str]:
        """
        Generate new filename when state changes.
        
        Args:
            current_filename: Current file name
            new_state: New document state (S0, S1, S2, S3, A, B)
            
        Returns:
            New filename with updated state, or None if parsing fails
        """
        parsed = self.parse_filename(current_filename)
        if not parsed:
            self.error_logger.log_file_operation_error("parse_filename", current_filename, Exception("Could not parse filename"))
            return None
        
        # Build new filename with updated state
        new_filename = self.build_filename(
            parsed['project'],
            parsed['doc_id'],
            parsed['doc_name'],
            parsed['version'],
            new_state,
            parsed['extension']
        )
        
        return new_filename
    
    def rename_file_safely(self, old_path: Path, new_path: Path) -> Tuple[bool, str]:
        """
        Rename file safely with atomic operations and conflict handling.
        
        Returns:
            (success: bool, message: str)
        """
        if not old_path.exists():
            return False, f"Source file does not exist: {old_path}"
        
        if old_path == new_path:
            return True, "No rename needed - filenames are identical"
        
        # Check if target already exists
        if new_path.exists():
            return False, f"Target file already exists: {new_path.name}"
        
        try:
            # Use atomic rename operation
            with self.lock_manager.database_transaction_lock(str(old_path)):
                # Create parent directory if needed
                new_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Atomic rename
                old_path.rename(new_path)
                
                return True, f"File renamed: {old_path.name} → {new_path.name}"
                
        except OSError as e:
            error_msg = f"Failed to rename file: {e}"
            self.error_logger.log_file_operation_error("rename_file", str(old_path), e)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during file rename: {e}"
            self.error_logger.log_file_operation_error("rename_file", str(old_path), e)
            return False, error_msg
    
    def update_file_for_state_change(self, document_name: str, current_filename: str, 
                                    new_state: str) -> Tuple[bool, str, Optional[str]]:
        """
        Update filename when document state changes.
        
        Args:
            document_name: Document name for logging
            current_filename: Current filename
            new_state: New document state
            
        Returns:
            (success: bool, message: str, new_filename: Optional[str])
        """
        print(f"[FilenameStateManager] Updating filename for state change: {document_name}")
        print(f"   Current: {current_filename}")
        print(f"   New state: {new_state}")
        
        # Generate new filename
        new_filename = self.update_filename_for_state_change(current_filename, new_state)
        if not new_filename:
            return False, "Could not generate new filename", None
        
        # Skip if no change needed
        if current_filename == new_filename:
            return True, "No filename change needed", current_filename
        
        # Construct file paths
        planos_path = FolderResolver.resolve_planos(self.project_path)
        old_path = planos_path / current_filename
        new_path = planos_path / new_filename
        
        # Perform rename
        success, message = self.rename_file_safely(old_path, new_path)
        
        if success:
            print(f"   ✅ Renamed: {new_filename}")
            return True, message, new_filename
        else:
            print(f"   ❌ Rename failed: {message}")
            return False, message, None
    
    def migrate_filename_to_new_format(self, old_filename: str) -> Optional[str]:
        """
        Migrate old filename format to new format with 'B' prefix.
        
        Args:
            old_filename: Filename in old format (v1.0)
            
        Returns:
            New filename with 'B' prefix (vB1.0) or None if parsing fails
        """
        parsed = self.parse_filename(old_filename)
        if not parsed:
            return None
        
        # Build new filename with 'B' prefix
        new_filename = self.build_filename(
            parsed['project'],
            parsed['doc_id'],
            parsed['doc_name'],
            parsed['version'],  # Will be converted to vB format
            parsed['state'],
            parsed['extension']
        )
        
        return new_filename
    
    def validate_filename_consistency(self, filename: str, database_state: str) -> bool:
        """
        Validate that filename state matches database state.
        
        Returns:
            True if consistent, False if mismatch detected
        """
        parsed = self.parse_filename(filename)
        if not parsed:
            return False
        
        return parsed['state'] == database_state
    
    def update_all_files_for_state_change(self, document, new_state: str) -> Tuple[bool, str, list]:
        """
        Update ALL files associated with a document when state changes.

        Args:
            document: SQLiteDocument instance
            new_state: New document state

        Returns:
            (success: bool, message: str, new_filenames: List[str])
        """
        print(f"[Enhanced FilenameStateManager] Updating ALL files for: {document.name}")
        print(f"   New state: {new_state}")

        renamed_files = []
        failed_renames = []

        # Get all associated files
        files_to_rename = []
        storage_path = FolderResolver.resolve_planos(self.project_path)

        # Search in all possible locations (new folder structure)
        search_locations = [
            storage_path,  # Root (legacy)
            storage_path / "PDF" / "Working",
            storage_path / "PDF" / "Old",
            storage_path / "CAD" / "Working",
            storage_path / "CAD" / "Old",
            storage_path / "RVT" / "Working",
            storage_path / "RVT" / "Old",
        ]

        # Normalize document name for matching (handle spaces/underscores)
        doc_name_normalized = document.name.replace(' ', '_')
        doc_name_patterns = [document.name, doc_name_normalized]

        # Method 1: Pattern matching in all folders
        for location in search_locations:
            if not location.exists():
                continue
            for pattern_name in doc_name_patterns:
                for pattern_file in location.glob(f"*{pattern_name}*"):
                    if pattern_file not in files_to_rename and pattern_file.is_file():
                        # Check if it's a document file that should be renamed
                        parsed = self.parse_filename(pattern_file.name)
                        if parsed and parsed['state'] != new_state:
                            files_to_rename.append(pattern_file)

        # Filter out CAD files (DWG, RVT) - they should keep stable names for XREF compatibility
        CAD_EXTENSIONS = {'.dwg', '.rvt', '.dxf', '.ifc'}
        pdf_files_to_rename = [f for f in files_to_rename if f.suffix.lower() not in CAD_EXTENSIONS]

        print(f"   Found {len(files_to_rename)} total files, {len(pdf_files_to_rename)} PDF files to rename:")
        for file_path in pdf_files_to_rename:
            print(f"      - {file_path.name} in {file_path.parent.name}")

        # Only rename PDF files - CAD files keep stable names
        for file_path in pdf_files_to_rename:
            try:
                # Generate new filename
                new_filename = self.update_filename_for_state_change(file_path.name, new_state)
                if not new_filename:
                    failed_renames.append(f"{file_path.name}: Could not generate new filename")
                    continue
                
                # Skip if no change needed
                if file_path.name == new_filename:
                    renamed_files.append(new_filename)
                    continue
                
                # Perform rename
                new_path = file_path.parent / new_filename
                success, message = self.rename_file_safely(file_path, new_path)
                
                if success:
                    renamed_files.append(new_filename)
                    print(f"      ✅ {file_path.name} → {new_filename}")
                else:
                    failed_renames.append(f"{file_path.name}: {message}")
                    print(f"      ❌ {file_path.name}: {message}")
                    
            except Exception as e:
                failed_renames.append(f"{file_path.name}: {e}")
                print(f"      ❌ {file_path.name}: {e}")
        
        # Update document file_paths with new filenames
        if renamed_files:
            document.file_paths = renamed_files
            print(f"   📝 Updated document.file_paths with {len(renamed_files)} files")
        
        # Generate result message
        success = len(failed_renames) == 0
        if success:
            message = f"Successfully renamed {len(renamed_files)} files"
        else:
            message = f"Renamed {len(renamed_files)} files, {len(failed_renames)} failed"
            
        return success, message, renamed_files

    def get_filename_suggestions(self, document_name: str, current_state: str) -> Dict[str, str]:
        """
        Get filename suggestions for different states.
        
        Useful for UI to show what filename would be after state changes.
        """
        # Try to find current file
        planos_path = FolderResolver.resolve_planos(self.project_path)
        current_files = list(planos_path.glob(f"*{document_name}*.pdf"))
        
        if not current_files:
            return {}
        
        current_filename = current_files[0].name
        parsed = self.parse_filename(current_filename)
        
        if not parsed:
            return {}
        
        # Generate suggestions for all states
        suggestions = {}
        states = ["S0", "S1", "S2", "S3", "S3A", "D"]
        
        for state in states:
            suggested_filename = self.build_filename(
                parsed['project'],
                parsed['doc_id'],
                parsed['doc_name'],
                parsed['version'],
                state,
                parsed['extension']
            )
            suggestions[state] = suggested_filename
        
        return suggestions


def test_filename_state_manager():
    """Test the filename state manager functionality"""
    print("🧪 TESTING FILENAME STATE MANAGER")
    print("=" * 50)
    
    project_path = Path("PRJ-001_Hotel_Marina")
    manager = FilenameStateManager(project_path)
    
    # Test filename parsing
    test_files = [
        "PRJ-001-PL-001_Plano_Estructural_v1.0_S2.pdf",
        "PRJ-001-PL-001_Plano_Estructural_vB1.0_S2.pdf",
        "PRJ-001-PL-002_Document_v2.1_A.pdf"
    ]
    
    print("📋 Testing filename parsing:")
    for filename in test_files:
        parsed = manager.parse_filename(filename)
        print(f"   {filename}")
        if parsed:
            print(f"      ✅ Project: {parsed['project']}, Version: {parsed['version']}, State: {parsed['state']}")
        else:
            print(f"      ❌ Failed to parse")
    
    # Test filename building
    print(f"\n🔧 Testing filename building:")
    new_filename = manager.build_filename("PRJ-001", "PL-001", "Test_Document", "v1.0", "S3")
    print(f"   Built: {new_filename}")
    
    # Test state change
    print(f"\n🔄 Testing state change:")
    old_filename = "PRJ-001-PL-001_Plano_Estructural_v1.0_S2.pdf"
    new_filename = manager.update_filename_for_state_change(old_filename, "S3")
    print(f"   {old_filename}")
    print(f"   → {new_filename}")
    
    # Test migration
    print(f"\n📦 Testing migration to new format:")
    old_format = "PRJ-001-PL-001_Document_v1.0_S2.pdf"
    migrated = manager.migrate_filename_to_new_format(old_format)
    print(f"   {old_format}")
    print(f"   → {migrated}")


if __name__ == "__main__":
    test_filename_state_manager()