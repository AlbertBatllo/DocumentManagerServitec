"""
File Type Upload Router
Routes file uploads to appropriate folders based on file type and applies appropriate naming strategies.
"""

from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import shutil
import json
import logging
from enum import Enum

from .folder_structure_manager import FolderStructureManager, FileType
from .file_manager import FileManager
from utils.cad.dwg_xref import get_references, extract_all_references, extract_image_references


class NamingStrategy(Enum):
    """Naming strategies for different file types"""
    FULL_VERSIONING = "full_versioning"  # PDFs: Document_v1.1_S2.pdf
    STABLE_BASE = "stable_base"          # CAD/RVT: document_name.dwg


class FileTypeUploadRouter:
    """
    Routes file uploads based on file type with appropriate naming strategies.
    
    Strategies:
    - PDFs: Full versioning with state changes (existing behavior)
    - CAD (.dwg): Stable base names to preserve Xref relationships
    - RVT: Stable base names to preserve Revit linking
    """
    
    # Define naming strategies for each file type
    NAMING_STRATEGIES = {
        FileType.PDF: NamingStrategy.FULL_VERSIONING,
        FileType.DWG: NamingStrategy.STABLE_BASE,
        FileType.RVT: NamingStrategy.STABLE_BASE
    }
    
    def __init__(self, planos_base_path: Path, file_manager: FileManager = None):
        """Initialize with planos base path"""
        self.planos_path = Path(planos_base_path)
        self.folder_manager = FolderStructureManager(self.planos_path)
        self.file_manager = file_manager or FileManager()
        
        # Ensure organized folder structure exists
        self.folder_manager.ensure_folder_structure()
    
    def route_file_upload(self, source_path: Path, document_info: Dict[str, str], 
                         upload_context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Path, str]:
        """
        Route a file upload to the appropriate location with correct naming.
        
        Args:
            source_path: Path to the file being uploaded
            document_info: Dictionary with document metadata:
                - name: Document name 
                - version: Document version
                - state: Document state
                - display_name: Human-readable name
            upload_context: Optional context for upload (e.g., operation type)
            
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
            
            # Get target folder for this file type (uploads always go to Working)
            target_folder = self._get_target_folder(file_type, document_info)
            target_path = target_folder / target_filename

            # Uploads only land in Working. Last/Old are managed via the explicit
            # "Promoure" action (see promote_to_last). Conflicts in Working are
            # resolved by simple overwrite for CAD/RVT (stable names) or by
            # version-suffixed coexistence for PDFs (different filenames already).
            conflict_message = ""
            if target_path.exists() and naming_strategy == NamingStrategy.STABLE_BASE:
                try:
                    target_path.unlink()
                    conflict_message = "sobrescrito en Working"
                except OSError as e:
                    return False, source_path, f"No se pudo sobrescribir en Working ({e}). ¿Está abierto en otra aplicación?"
            final_path = target_path

            # Copy file to final location
            self.file_manager.copy_file(source_path, final_path)
            
            # Extract and organize references for CAD/RVT files.
            # Pass the source's parent so we can locate XREFs that lived next to
            # the original file (e.g. <source_dir>\REF\X_*.dwg) — without this,
            # bulk uploads from network folders never found their references
            # because final_path is in Working/, not the source directory.
            reference_message = ""
            if file_type in [FileType.DWG, FileType.RVT]:
                reference_message = self._extract_and_organize_references(
                    final_path, file_type, document_info,
                    source_dir=source_path.parent
                )
            
            # Prepare success message
            message = f"✅ {file_type.value.upper()} uploaded: {final_path.name}"
            if conflict_message:
                message += f" ({conflict_message})"
            if reference_message:
                message += f" {reference_message}"
            
            return True, final_path, message
            
        except Exception as e:
            return False, source_path, f"Upload failed: {e}"
    
    def route_multiple_files(self, file_uploads: List[Tuple[Path, Dict[str, str]]], 
                           upload_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Route multiple file uploads with file type organization.
        
        Args:
            file_uploads: List of (source_path, document_info) tuples
            upload_context: Optional context for upload operation
            
        Returns:
            Dictionary with upload results organized by file type
        """
        results = {
            "successful_uploads": [],
            "failed_uploads": [],
            "files_by_type": {},
            "warnings": []
        }
        
        for source_path, document_info in file_uploads:
            # Route individual file
            success, final_path, message = self.route_file_upload(
                source_path, document_info, upload_context
            )
            
            # Track results
            if success:
                file_type = self.folder_manager.detect_file_type(source_path)
                type_name = file_type.value if file_type else "unknown"
                
                results["successful_uploads"].append({
                    "source": str(source_path),
                    "destination": str(final_path),
                    "file_type": type_name,
                    "message": message
                })
                
                # Group by file type
                if type_name not in results["files_by_type"]:
                    results["files_by_type"][type_name] = []
                results["files_by_type"][type_name].append(str(final_path))
            else:
                results["failed_uploads"].append({
                    "source": str(source_path),
                    "error": message
                })
        
        # Add summary information
        results["summary"] = {
            "total_files": len(file_uploads),
            "successful": len(results["successful_uploads"]),
            "failed": len(results["failed_uploads"]),
            "success_rate": len(results["successful_uploads"]) / len(file_uploads) if file_uploads else 0
        }
        
        return results
    
    def _generate_target_filename(self, source_path: Path, document_info: Dict[str, str],
                                 file_type: FileType, naming_strategy: NamingStrategy,
                                 upload_context: Optional[Dict[str, Any]] = None) -> str:
        """Generate target filename based on file type and naming strategy"""

        doc_name = document_info.get("name", "")
        version = document_info.get("version", "1.0") or "1.0"
        state = document_info.get("state", "S0") or "S0"
        display_name = document_info.get("display_name", doc_name)

        file_extension = source_path.suffix.lower()

        if naming_strategy == NamingStrategy.FULL_VERSIONING:
            # PDFs: Full versioning like existing system
            # Format: Document_Name_v1.1_S2.pdf (single file)
            # Format: Document_Name-2_v1.1_S2.pdf (second file)
            clean_name = self._sanitize_filename(display_name or doc_name)
            # Only add 'v' prefix if version doesn't already have it
            version_with_v = version if version.startswith('v') else f"v{version}"

            # For add_file operation, check if we need to add a number suffix
            operation = upload_context.get('operation', 'new_version') if upload_context else 'new_version'
            if operation == 'add_file':
                # Count existing PDFs for this document in Working folder
                target_folder = self._get_target_folder(file_type, document_info)
                next_number = self._get_next_pdf_number(target_folder, clean_name, version_with_v, state)
                if next_number > 1:
                    return f"{clean_name}-{next_number}_{version_with_v}_{state}{file_extension}"

            return f"{clean_name}_{version_with_v}_{state}{file_extension}"

        elif naming_strategy == NamingStrategy.STABLE_BASE:
            # CAD/RVT: Stable base names to preserve Xrefs
            # Format: document_name.dwg (no version/state in filename)
            clean_name = self._sanitize_filename(display_name or doc_name)
            return f"{clean_name}{file_extension}"
            
        else:
            # Fallback to source filename
            return source_path.name
    
    def _get_target_folder(self, file_type: FileType, document_info: Dict[str, str]) -> Path:
        """
        Get the target folder for new uploads.
        X_ reference files go to Working/REF, other CAD/RVT files go to Working.
        """
        base_folder = self.folder_manager.get_folder_path(file_type)

        # For PDF files, use Working subfolder
        if file_type == FileType.PDF:
            return base_folder / "Working"

        # For CAD files, check if it's an X_ reference file
        if file_type == FileType.DWG:
            doc_name = document_info.get("name", "")
            if doc_name.startswith('X_'):
                # X_ reference files go to Working/REF
                return base_folder / "Working" / "REF"
        
        # For other CAD/RVT files, new uploads go to Working
        return base_folder / "Working"
    
    def _get_next_pdf_number(self, working_folder: Path, clean_name: str, version: str, state: str) -> int:
        """
        Get the next available number for a PDF file.

        Checks existing PDFs in the Working folder matching the document name.
        Returns 1 if no PDFs exist, otherwise returns the next available number.

        Naming convention:
        - Single PDF: DOC_NAME_v1.0_S0.pdf
        - Multiple PDFs: DOC_NAME_v1.0_S0.pdf, DOC_NAME-2_v1.0_S0.pdf, DOC_NAME-3_v1.0_S0.pdf

        Args:
            working_folder: Path to PDF/Working folder
            clean_name: Sanitized document name
            version: Version string (e.g., "v1.0")
            state: State string (e.g., "S0")

        Returns:
            Next available number (1 means no suffix needed, 2+ means add -N suffix)
        """
        if not working_folder.exists():
            return 1

        # Find all PDFs matching this document's base name
        existing_numbers = set()

        for pdf_file in working_folder.glob("*.pdf"):
            file_stem = pdf_file.stem

            # Check for base pattern: DOC_NAME_vX.Y_SZ
            base_pattern = f"{clean_name}_{version}_{state}"
            if file_stem == base_pattern:
                existing_numbers.add(1)
                continue

            # Check for numbered pattern: DOC_NAME-N_vX.Y_SZ
            import re
            numbered_pattern = rf"^{re.escape(clean_name)}-(\d+)_{re.escape(version)}_{re.escape(state)}$"
            match = re.match(numbered_pattern, file_stem)
            if match:
                existing_numbers.add(int(match.group(1)))

        if not existing_numbers:
            return 1  # No existing PDFs, use base name without number

        # Return next available number
        max_num = max(existing_numbers)
        return max_num + 1

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
    
    def promote_to_last(self, file_path: Path) -> Tuple[bool, str]:
        """
        Promote a file in Working/ to be the canonical Last/ version.

        Steps:
          1. If a file with the same name exists in Last/, move it (and its
             REF/Links sidecars when applicable) to Old/<timestamp>-<stem>/.
          2. Move the Working file to Last/, copying its REF/Links sidecars too.

        Args:
            file_path: Path to the file in CAD/Working/, PDF/Working/, or
                RVT/Working/ that should be promoted.

        Returns:
            Tuple (success, message).
        """
        try:
            if not file_path.exists():
                return False, f"No existe el archivo: {file_path}"

            file_type = self.folder_manager.detect_file_type(file_path)
            if not file_type:
                return False, f"Tipo no soportado: {file_path.suffix}"

            base_folder = self.folder_manager.get_folder_path(file_type)
            working_folder = base_folder / "Working"
            last_folder = base_folder / "Last"
            old_folder = base_folder / "Old"

            if "Working" not in file_path.parts:
                return False, "Sólo se pueden promover archivos que están en Working/"

            last_folder.mkdir(parents=True, exist_ok=True)
            old_folder.mkdir(parents=True, exist_ok=True)

            existing_last = last_folder / file_path.name
            archived_msg = ""
            if existing_last.exists():
                from datetime import datetime
                stamp = datetime.now().strftime("%Y%m%d%H%M%S")
                archive_subfolder = old_folder / f"{stamp}-{existing_last.stem}"
                archive_subfolder.mkdir(parents=True, exist_ok=True)
                archived_main = archive_subfolder / existing_last.name
                shutil.move(str(existing_last), str(archived_main))
                # Move sidecar REF/Links files referenced by the previous Last.
                # Read references from the moved-into-Old copy (existing_last
                # no longer exists at the original path).
                if file_type == FileType.DWG:
                    self._archive_sidecars(archived_main, last_folder / "REF",
                                           archive_subfolder / "REF")
                elif file_type == FileType.RVT:
                    self._archive_sidecars(archived_main, last_folder / "Links",
                                           archive_subfolder / "Links")
                archived_msg = f"anterior archivado en Old/{archive_subfolder.name}"

            # Move file Working → Last
            target_last = last_folder / file_path.name
            shutil.move(str(file_path), str(target_last))

            # Copy sidecars (REF/Links) so the new Last has its references nearby
            sidecars_msg = ""
            if file_type == FileType.DWG:
                count = self._copy_sidecars(target_last, working_folder / "REF",
                                            last_folder / "REF")
                if count:
                    sidecars_msg = f"{count} XREFs copiados a Last/REF"
            elif file_type == FileType.RVT:
                count = self._copy_sidecars(target_last, working_folder / "Links",
                                            last_folder / "Links")
                if count:
                    sidecars_msg = f"{count} Links copiados a Last/Links"

            parts = [f"✅ {target_last.name} promovido a Last"]
            if archived_msg:
                parts.append(archived_msg)
            if sidecars_msg:
                parts.append(sidecars_msg)
            return True, "; ".join(parts)
        except Exception as e:
            return False, f"❌ Promoción falló: {e}"

    def _archive_sidecars(self, dwg_path: Path, src_ref_folder: Path,
                          dst_ref_folder: Path) -> int:
        """Move XREF/image sidecars referenced by dwg_path from src to dst."""
        if not dwg_path.suffix.lower() == '.dwg' or dwg_path.name.startswith('X_'):
            return 0
        if not src_ref_folder.exists():
            return 0
        try:
            refs = self._get_file_all_references(dwg_path)
            names = (refs.get('dwg') or []) + (refs.get('images') or [])
        except Exception:
            return 0
        if not names:
            return 0
        dst_ref_folder.mkdir(parents=True, exist_ok=True)
        moved = 0
        for ref_name in names:
            src = src_ref_folder / ref_name
            if src.exists():
                try:
                    shutil.move(str(src), str(dst_ref_folder / ref_name))
                    moved += 1
                except Exception:
                    pass
        return moved

    def _copy_sidecars(self, dwg_path: Path, src_ref_folder: Path,
                       dst_ref_folder: Path) -> int:
        """Copy XREF/image sidecars referenced by dwg_path from src to dst."""
        if not dwg_path.suffix.lower() == '.dwg' or dwg_path.name.startswith('X_'):
            return 0
        if not src_ref_folder.exists():
            return 0
        try:
            refs = self._get_file_all_references(dwg_path)
            names = (refs.get('dwg') or []) + (refs.get('images') or [])
        except Exception:
            return 0
        if not names:
            return 0
        dst_ref_folder.mkdir(parents=True, exist_ok=True)
        copied = 0
        for ref_name in names:
            src = src_ref_folder / ref_name
            dst = dst_ref_folder / ref_name
            if src.exists() and not dst.exists():
                try:
                    shutil.copy2(src, dst)
                    copied += 1
                except Exception:
                    pass
        return copied

    def _get_file_xref_references(self, dwg_file_path: Path) -> List[str]:
        """
        Get XREF references for a specific DWG file.
        """
        try:
            return get_references(dwg_file_path)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to get XREFs for {dwg_file_path}: {e}")
            return []

    def _get_file_all_references(self, dwg_file_path: Path) -> Dict[str, List[str]]:
        """
        Get all references (XREFs and images) for a specific DWG file.

        Returns:
            Dictionary with 'dwg' and 'images' keys containing lists of filenames
        """
        try:
            return extract_all_references(dwg_file_path)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to get all references for {dwg_file_path}: {e}")
            return {'dwg': [], 'images': []}

    def _get_current_document_info(self, document_name: str) -> Dict[str, str]:
        """
        Get current document info from database.
        
        Args:
            document_name: Name of the document to look up
            
        Returns:
            Dictionary with current document info or defaults
        """
        try:
            import sqlite3
            # Try to find database in the project structure
            # First check .project_manager folder (new location), then fallback to old locations
            db_paths = [
                self.planos_path.parent / ".project_manager" / "documents.db",
                self.planos_path.parent / "documents.db",
                self.planos_path / "documents.db",
                self.planos_path / ".." / "documents.db"
            ]
            
            for db_path in db_paths:
                if db_path.exists():
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # Query for current document info
                    cursor.execute("""
                        SELECT current_version, current_state 
                        FROM documents 
                        WHERE document_type = 'planos' AND name = ?
                    """, (document_name,))
                    
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result:
                        version, state = result
                        return {
                            "name": document_name,
                            "version": version or "1.0",
                            "state": state or "S0"
                        }
                    break
                    
        except Exception as e:
            self.logger.error(f"Failed to get document info from database: {e}")
        
        # Return defaults if database lookup fails
        return {
            "name": document_name,
            "version": "1.0",
            "state": "S0"
        }
    
    def get_file_organization_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get information about how a file would be organized.
        
        Returns:
            Dictionary with organization information
        """
        file_type = self.folder_manager.detect_file_type(file_path)
        if not file_type:
            return {"supported": False, "file_type": None}
        
        naming_strategy = self.NAMING_STRATEGIES[file_type]
        target_folder = self.folder_manager.get_folder_path(file_type)
        
        return {
            "supported": True,
            "file_type": file_type.value,
            "naming_strategy": naming_strategy.value,
            "target_folder": str(target_folder),
            "folder_exists": target_folder.exists(),
            "stable_naming": naming_strategy == NamingStrategy.STABLE_BASE
        }
    
    def update_document_file_paths(self, document_data: Dict[str, Any], 
                                  uploaded_files: List[Path]) -> Dict[str, Any]:
        """
        Update document data with new file paths organized by type.
        
        Args:
            document_data: Existing document data
            uploaded_files: List of newly uploaded file paths
            
        Returns:
            Updated document data with organized file paths
        """
        # Get existing file paths
        existing_paths = document_data.get("file_paths", [])
        if isinstance(existing_paths, str):
            try:
                existing_paths = json.loads(existing_paths)
            except json.JSONDecodeError:
                existing_paths = []
        
        # Add new file paths
        all_paths = existing_paths + [str(path) for path in uploaded_files]
        
        # Organize by file type for tracking
        files_by_type = {}
        primary_file_type = ""
        
        for file_path_str in all_paths:
            file_path = Path(file_path_str)
            file_type = self.folder_manager.detect_file_type(file_path)
            
            if file_type:
                type_name = file_type.value
                if type_name not in files_by_type:
                    files_by_type[type_name] = []
                files_by_type[type_name].append(file_path_str)
                
                # Set primary file type (prefer PDF, then CAD, then RVT)
                if not primary_file_type or (type_name == "pdf" and primary_file_type != "pdf"):
                    primary_file_type = type_name
        
        # Update document data
        updated_data = document_data.copy()
        updated_data["file_paths"] = json.dumps(all_paths)
        updated_data["file_type"] = primary_file_type
        
        # Set folder path for the primary file type
        if primary_file_type:
            primary_type = FileType.from_extension(f".{primary_file_type}")
            if primary_type:
                folder_path = self.folder_manager.get_folder_path(primary_type)
                updated_data["folder_path"] = str(folder_path)
        
        return updated_data
    
    def validate_upload_request(self, file_uploads: List[Tuple[Path, Dict[str, str]]]) -> Dict[str, Any]:
        """
        Validate an upload request before processing.
        
        Returns:
            Dictionary with validation results
        """
        validation = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "file_analysis": []
        }
        
        for source_path, document_info in file_uploads:
            file_analysis = {
                "file": str(source_path),
                "exists": source_path.exists(),
                "supported": False,
                "file_type": None,
                "issues": []
            }
            
            # Check if file exists
            if not source_path.exists():
                file_analysis["issues"].append("File does not exist")
                validation["issues"].append(f"File does not exist: {source_path.name}")
                validation["valid"] = False
            
            # Check if file type is supported
            file_type = self.folder_manager.detect_file_type(source_path)
            if file_type:
                file_analysis["supported"] = True
                file_analysis["file_type"] = file_type.value
            else:
                file_analysis["issues"].append(f"Unsupported file type: {source_path.suffix}")
                validation["warnings"].append(f"Skipping unsupported file: {source_path.name}")
            
            # Validate document info
            required_fields = ["name", "version", "state"]
            for field in required_fields:
                if not document_info.get(field):
                    file_analysis["issues"].append(f"Missing required field: {field}")
                    validation["issues"].append(f"Missing required field '{field}' for file: {source_path.name}")
                    validation["valid"] = False
            
            validation["file_analysis"].append(file_analysis)
        
        return validation
    
    def _extract_and_organize_references(self, file_path: Path, file_type: FileType,
                                       document_info: Dict[str, str],
                                       source_dir: Optional[Path] = None) -> str:
        """
        Extract and organize references for CAD/RVT files.

        Args:
            file_path: Path to the uploaded file (in the project Working folder)
            file_type: Type of file (DWG or RVT)
            document_info: Document metadata
            source_dir: Original directory of the source file. XREFs typically
                live next to the source DWG (e.g. <source_dir>\\REF\\X_*.dwg);
                without this, references uploaded from network folders are
                never found because file_path.parent points at Working/.

        Returns:
            String message about reference extraction results
        """
        try:
            # Determine target references folder based on file type and document state
            base_folder = self.folder_manager.get_folder_path(file_type)

            # Check document state to determine if it goes to Working or Old
            state = document_info.get("state", "S0")

            # Determine subfolder based on state (simplified logic)
            # Active states (S0-S2) go to Working, superseded/archived go to Old
            if state in ["S0", "S1", "S2"]:
                subfolder = "Working"
            else:
                subfolder = "Old"

            # Set target references folder
            if file_type == FileType.DWG:
                refs_folder = base_folder / subfolder / "REF"
            elif file_type == FileType.RVT:
                refs_folder = base_folder / subfolder / "Links"
            else:
                return ""  # No references for other file types

            # Extract references using the new solution
            if file_type == FileType.DWG:
                ref_names = get_references(file_path)
                ref_count = len(ref_names)

                if ref_count == 0:
                    return "📁 No external references found"

                # Try to copy references to refs_folder if they exist
                copied_count = 0
                error_count = 0
                refs_folder.mkdir(parents=True, exist_ok=True)

                # Look for references in common locations.
                # Order matters: source_dir first, since that's where the user's
                # original XREFs live. Project-side paths are fallbacks for
                # references already uploaded to the project tree.
                search_paths = []
                if source_dir is not None:
                    search_paths.extend([
                        source_dir / "REF",
                        source_dir.parent / "REF",  # sibling-of-source
                        source_dir,                 # XREFs alongside the DWG
                    ])
                search_paths.extend([
                    self.planos_path / "REF",
                    file_path.parent / "REF",
                    self.planos_path.parent / "REF",
                ])

                missing_refs: List[str] = []
                for ref_name in ref_names:
                    found = False
                    for search_path in search_paths:
                        if search_path.exists():
                            ref_file = search_path / ref_name
                            if ref_file.exists():
                                try:
                                    dest_file = refs_folder / ref_name
                                    if not dest_file.exists():
                                        shutil.copy2(ref_file, dest_file)
                                    copied_count += 1
                                    found = True
                                    break
                                except Exception:
                                    error_count += 1
                    if not found:
                        error_count += 1
                        missing_refs.append(ref_name)

                if copied_count > 0:
                    msg = f"📁 {copied_count}/{ref_count} referencias copiadas a {subfolder}/REF"
                    if missing_refs:
                        sample = ", ".join(missing_refs[:3])
                        more = f" y {len(missing_refs) - 3} más" if len(missing_refs) > 3 else ""
                        msg += f"; ⚠ no encontradas: {sample}{more}"
                    return msg
                else:
                    sample = ", ".join(missing_refs[:3])
                    more = f" y {len(missing_refs) - 3} más" if len(missing_refs) > 3 else ""
                    return f"⚠ {ref_count} referencias declaradas pero no encontradas en disco: {sample}{more}"
            else:
                # RVT files not yet supported with new solution
                return "📁 Reference extraction not yet implemented for RVT files"
                
        except Exception as e:
            return f"⚠️ Reference processing error: {e}"
    
    def get_file_references(self, file_path: Path) -> Dict[str, Any]:
        """
        Get external references for a file without organizing them.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with reference information
        """
        file_type = self.folder_manager.detect_file_type(file_path)
        
        if file_type == FileType.DWG:
            ref_names = get_references(file_path)
            return {
                'success': True,
                'references': ref_names,
                'reference_count': len(ref_names),
                'file_type': 'DWG'
            }
        else:
            return {
                'success': False,
                'references': [],
                'reference_count': 0,
                'error': f'Reference extraction not yet implemented for {file_type} files'
            }