import os
import shutil
from pathlib import Path
from typing import Dict, List, Union, Optional
from models.document import Document
from utils.file_manager import FileManager
from utils.folder_resolver import FolderResolver


class ExportController:
    def __init__(self, project_path: Union[Path, str], doc_type: str = "planos"):
        self.project_path = Path(project_path) if isinstance(project_path, str) else project_path
        self.doc_type = doc_type
        # Map doc_type to correct folder (dynamic resolution)
        type_map = {
            "planos": "planos",
            "certificaciones": "certificaciones",
            "licitaciones": "presupuestos",
        }
        resolver_type = type_map.get(doc_type, "planos")
        resolved_path = FolderResolver.resolve(self.project_path, resolver_type)
        self.doc_folder = resolved_path.name
        
    def export_documents(self, selected_docs: Dict[str, Dict], export_dir: str) -> None:
        """
        Export selected documents to the specified directory.
        
        Args:
            selected_docs: Dict with doc_id -> {document, version, state, selected}
            export_dir: Target directory for export
        """
        export_path = Path(export_dir)
        if not export_path.exists():
            export_path.mkdir(parents=True, exist_ok=True)
            
        exported_files = []
        failed_files = []
        
        for doc_id, doc_data in selected_docs.items():
            if not doc_data.get("selected", False):
                continue
                
            try:
                document = doc_data["document"]
                version = doc_data["version"]
                state = doc_data["state"]
                
                # Get selected file types for this document
                available_files = doc_data.get("available_files", {})
                selected_file_types = [ext for ext, selected in available_files.items() if selected]
                
                if not selected_file_types:
                    failed_files.append(f"{doc_id} - No hay tipos de archivo seleccionados")
                    continue
                
                # Export each selected file type
                exported_count = 0
                for file_ext in selected_file_types:
                    try:
                        # Generate filename for the specific version/state/extension
                        filename = self._generate_filename(document, version, state, file_ext)
                        
                        # Find the source file
                        source_path = self._find_source_file(document, version, state, filename)
                        
                        if source_path and source_path.exists():
                            # Copy file to export directory
                            dest_path = export_path / filename
                            shutil.copy2(source_path, dest_path)
                            exported_files.append(filename)
                            exported_count += 1
                        else:
                            failed_files.append(f"{doc_id} - {file_ext.upper()} (v{version}, {state}) - Archivo no encontrado")
                            
                    except Exception as e:
                        failed_files.append(f"{doc_id} - {file_ext.upper()} - Error: {str(e)}")
                
                # If no files were exported for this document, it's a failure
                if exported_count == 0:
                    failed_files.append(f"{doc_id} - Ningún archivo pudo ser exportado")
                    
            except Exception as e:
                failed_files.append(f"{doc_id} - General error: {str(e)}")
        
        # Report results
        if failed_files:
            error_msg = "Algunos archivos no pudieron ser exportados:\\n" + "\\n".join(failed_files)
            raise Exception(error_msg)
    
    def _generate_filename(self, document: Document, version: str, state: str, file_ext: str = "pdf") -> str:
        """Generate filename for a specific version/state/extension of a document."""
        sanitized_name = FileManager.sanitize_for_filename(document.name)
        sanitized_version = FileManager.sanitize_for_filename(version)
        sanitized_state = FileManager.sanitize_for_filename(state)
        
        # Handle version prefix - version already contains 'v' prefix
        version_part = sanitized_version if sanitized_version.startswith('v') else f"v{sanitized_version}"
        
        # Ensure extension doesn't start with a dot (we add it manually)
        if file_ext.startswith('.'):
            file_ext = file_ext[1:]
        
        return f"{document.id}_{sanitized_name}_{version_part}_{sanitized_state}.{file_ext}"
    
    def _find_source_file(self, document: Document, version: str, state: str, filename: str) -> Optional[Path]:
        """Find the source file for a specific version/state."""
        # Primary location: in the document type folder
        doc_folder_path = self.project_path / self.doc_folder
        
        # Try exact filename match first
        exact_path = doc_folder_path / filename
        if exact_path.exists():
            return exact_path
        
        # Extract file extension from filename
        file_ext = filename.split('.')[-1] if '.' in filename else 'pdf'
        
        # Try to find files that match the pattern with different sanitization
        # This handles cases where filenames might have been sanitized differently
        pattern_candidates = [
            f"{document.id}_{document.name}_{version}_{state}.{file_ext}",
            f"{document.id}_{document.name}_vv{version}_{state}.{file_ext}",  # Some files have 'vv' prefix
            f"{document.id}_{document.name.replace(' ', '_')}_{version}_{state}.{file_ext}",
            f"{document.id}_{document.name.replace(' ', '_')}_vv{version}_{state}.{file_ext}",
        ]
        
        for candidate in pattern_candidates:
            sanitized_candidate = FileManager.sanitize_for_filename(candidate)
            candidate_path = doc_folder_path / sanitized_candidate
            if candidate_path.exists():
                return candidate_path
        
        # If exact match not found, try to find any file that matches the document ID and version/state pattern
        if doc_folder_path.exists():
            for file_path in doc_folder_path.glob(f"{document.id}_*.{file_ext}"):
                file_name = file_path.name
                # Check if this file contains the version and state we're looking for
                if f"v{version}" in file_name and f"_{state}." in file_name:
                    return file_path
                # Also check for 'vv' prefix variant
                if f"vv{version}" in file_name and f"_{state}." in file_name:
                    return file_path
        
        return None
    
    def get_available_documents(self) -> List[Document]:
        """Get list of available documents for export."""
        from controllers.document_controller import DocumentController
        
        # This would typically be injected, but for now we'll create it
        doc_controller = DocumentController(self.project_path, self.doc_type)
        return doc_controller.get_all_documents()