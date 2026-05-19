"""
Folder Structure Manager for CAD-Friendly Organization
Manages the new file-type-based folder structure in 02_Planos/
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum
import shutil
import logging


class FileType(Enum):
    """Supported file types for planos organization"""
    PDF = "pdf"
    DWG = "dwg"
    RVT = "rvt"
    JPG = "jpg"  # Images go to REF folder

    @classmethod
    def from_extension(cls, extension: str) -> Optional['FileType']:
        """Get FileType from file extension"""
        ext = extension.lower().lstrip('.')
        # Handle jpeg as jpg
        if ext == "jpeg":
            ext = "jpg"
        for file_type in cls:
            if file_type.value == ext:
                return file_type
        return None


class FolderStructureManager:
    """
    Manages the folder structure for planos. Three-stage lifecycle:

    02_Planos/
    ├── PDF/
    │   ├── Working/    # Drafts/editable copies (uploads land here)
    │   ├── Last/       # Current promoted version (one per logical name)
    │   └── Old/        # Previous promoted versions
    ├── CAD/
    │   ├── Working/    # Editable CAD files (uploads land here)
    │   │   └── REF/    # XREF / image references for Working
    │   ├── Last/       # Current promoted version
    │   │   └── REF/    # XREF / image references for Last
    │   └── Old/        # Previous promoted versions
    └── RVT/
        ├── Working/
        │   └── Links/
        ├── Last/
        │   └── Links/
        └── Old/

    JPG/JPEG files uploaded as planos go directly to CAD/Working/REF/
    Promotion (Working → Last, previous Last → Old) is an explicit user action,
    never automatic on upload.
    """

    FOLDER_NAMES = {
        FileType.PDF: "PDF",
        FileType.DWG: "CAD",
        FileType.RVT: "RVT",
        FileType.JPG: "CAD/Working/REF"  # JPGs go directly to REF
    }
    
    def __init__(self, planos_base_path: Path):
        """Initialize with base 02_Planos path"""
        self.base_path = Path(planos_base_path)
        self.logger = logging.getLogger(__name__)
    
    def ensure_folder_structure(self) -> bool:
        """
        Create the required folder structure if it doesn't exist.
        Returns True if successful.
        """
        try:
            # Ensure base directory exists
            self.base_path.mkdir(parents=True, exist_ok=True)
            
            # Create type-specific folders (use parents=True for nested paths like CAD/Working/REF)
            for file_type in FileType:
                folder_path = self.get_folder_path(file_type)
                folder_path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"✅ Ensured folder exists: {folder_path}")
            
            # Create Working/Last/Old subfolders for PDF, CAD, and RVT
            for file_type in [FileType.PDF, FileType.DWG, FileType.RVT]:
                folder_path = self.get_folder_path(file_type)

                working_path = folder_path / "Working"
                last_path = folder_path / "Last"
                old_path = folder_path / "Old"
                working_path.mkdir(exist_ok=True)
                last_path.mkdir(exist_ok=True)
                old_path.mkdir(exist_ok=True)
                self.logger.info(f"✅ Ensured Working/Last/Old structure: {folder_path}")

                # CAD: REF subfolder in both Working and Last
                if file_type == FileType.DWG:
                    (working_path / "REF").mkdir(exist_ok=True)
                    (last_path / "REF").mkdir(exist_ok=True)
                # RVT: Links subfolder in both Working and Last
                elif file_type == FileType.RVT:
                    (working_path / "Links").mkdir(exist_ok=True)
                    (last_path / "Links").mkdir(exist_ok=True)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to create folder structure: {e}")
            return False
    
    def get_folder_path(self, file_type: FileType) -> Path:
        """Get the folder path for a specific file type"""
        folder_name = self.FOLDER_NAMES[file_type]
        return self.base_path / folder_name
    
    def get_file_target_path(self, filename: str, file_type: FileType) -> Path:
        """Get the target path where a file should be stored"""
        folder_path = self.get_folder_path(file_type)
        return folder_path / filename
    
    def detect_file_type(self, file_path: Path) -> Optional[FileType]:
        """Detect file type from file extension"""
        return FileType.from_extension(file_path.suffix)
    
    def get_existing_files_by_type(self) -> Dict[FileType, List[Path]]:
        """Get all existing files organized by type"""
        files_by_type = {file_type: [] for file_type in FileType}
        
        # Scan base directory for files
        if self.base_path.exists():
            for file_path in self.base_path.glob("*"):
                if file_path.is_file():
                    file_type = self.detect_file_type(file_path)
                    if file_type:
                        files_by_type[file_type].append(file_path)
        
        # Also scan existing type folders
        for file_type in FileType:
            folder_path = self.get_folder_path(file_type)
            if folder_path.exists():
                for file_path in folder_path.glob(f"*.{file_type.value}"):
                    if file_path not in files_by_type[file_type]:
                        files_by_type[file_type].append(file_path)
        
        return files_by_type
    
    def move_file_to_organized_structure(self, source_path: Path, file_type: FileType, 
                                       target_filename: Optional[str] = None) -> Tuple[bool, Path, str]:
        """
        Move a file to the organized folder structure.
        
        Args:
            source_path: Current file location
            file_type: Target file type folder
            target_filename: Optional new filename (if None, keeps original)
            
        Returns:
            Tuple of (success, new_path, message)
        """
        try:
            if not source_path.exists():
                return False, source_path, f"Source file does not exist: {source_path}"
            
            # Determine target filename
            if target_filename:
                filename = target_filename
            else:
                filename = source_path.name
            
            # Get target path
            target_path = self.get_file_target_path(filename, file_type)
            
            # Ensure target directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Handle existing file conflicts
            if target_path.exists() and target_path != source_path:
                # Create backup name with timestamp
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{target_path.stem}_backup_{timestamp}{target_path.suffix}"
                backup_path = target_path.parent / backup_name
                shutil.move(str(target_path), str(backup_path))
                self.logger.warning(f"⚠️ Existing file backed up: {backup_path}")
            
            # Move file to new location
            shutil.move(str(source_path), str(target_path))
            self.logger.info(f"✅ Moved {source_path.name} → {target_path}")
            
            return True, target_path, f"Successfully moved to {target_path}"
            
        except Exception as e:
            error_msg = f"Failed to move {source_path.name}: {e}"
            self.logger.error(f"❌ {error_msg}")
            return False, source_path, error_msg
    
    def get_organized_file_path(self, filename: str, file_type: FileType) -> Path:
        """Get the expected path for a file in the organized structure"""
        return self.get_file_target_path(filename, file_type)
    
    def is_file_in_organized_structure(self, file_path: Path) -> bool:
        """Check if a file is already in the organized folder structure"""
        try:
            relative_path = file_path.relative_to(self.base_path)
            folder_name = relative_path.parts[0]
            return folder_name in self.FOLDER_NAMES.values()
        except ValueError:
            # File is not under base_path
            return False
    
    def validate_structure(self) -> Dict[str, any]:
        """
        Validate the current folder structure and return status report.
        
        Returns:
            Dictionary with validation results
        """
        report = {
            "structure_exists": True,
            "folders_created": [],
            "missing_folders": [],
            "files_by_type": {},
            "unorganized_files": [],
            "total_files": 0
        }
        
        # Check if base structure exists
        if not self.base_path.exists():
            report["structure_exists"] = False
            return report
        
        # Check each required folder
        for file_type in FileType:
            folder_path = self.get_folder_path(file_type)
            if folder_path.exists():
                report["folders_created"].append(str(folder_path))
            else:
                report["missing_folders"].append(str(folder_path))
        
        # Analyze current files
        files_by_type = self.get_existing_files_by_type()
        for file_type, files in files_by_type.items():
            report["files_by_type"][file_type.value] = len(files)
            report["total_files"] += len(files)
        
        # Find unorganized files (in base directory)
        if self.base_path.exists():
            for file_path in self.base_path.glob("*"):
                if file_path.is_file() and not self.is_file_in_organized_structure(file_path):
                    file_type = self.detect_file_type(file_path)
                    if file_type:  # Only count supported file types
                        report["unorganized_files"].append(str(file_path))
        
        return report