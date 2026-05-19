"""
SQLite-backed Document Controller
Replaces JSON-based DocumentController with SQLite operations while maintaining same API.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from models.sqlite_document import SQLiteDocument
from utils.project_database_manager import ensure_project_database
from utils.file_manager import FileManager
from utils.project_utils import ProjectUtils
from utils.lock_manager import get_project_lock_manager, safe_database_operation
from config.settings import StatusConfig, CloudConfig, UserConfig
from utils.cloud_sync import CloudSyncManager


class SQLiteDocumentController:
    """
    SQLite-backed document controller.
    
    Provides the same API as DocumentController but uses SQLite instead of JSON.
    Simple replacement - just swap the controller and everything else works the same.
    """
    
    def __init__(self, doc_type: str, doc_folder: str, project_path: Path = None):
        self.doc_type = doc_type
        self.doc_folder = doc_folder
        
        # Set up paths
        self.project_path = project_path if project_path else Path.cwd()
        self.storage_path = self.project_path / doc_folder
        
        # Ensure storage directory exists
        ProjectUtils.ensure_directory_exists(self.storage_path)
        
        # Initialize SQLite database (replaces JSON manifest)
        self.db_manager = ensure_project_database(self.project_path)
        
        # Initialize other components (same as original)
        self.status_config = StatusConfig(self.project_path)
        self.file_manager = FileManager()
        self.cloud_config = CloudConfig(self.project_path)
        self.cloud_sync = CloudSyncManager(self.cloud_config)
        
        # Get current user name for database operations
        self.user_config = UserConfig()
        self.current_user = self.user_config.get_user_name() or "Unknown User"
        
        # Initialize lock manager for safe operations
        self.lock_manager = get_project_lock_manager(self.project_path)

    def add_new_version(self, doc_id: str, name: str, version: str, state: str, 
                       file_paths: List[Path], author: str, notes: str) -> List[str]:
        """Add a new document version. Returns list of success messages."""
        messages = []
        
        # Process files and prepare for database operation
        copied_file_paths = []
        for file_path in file_paths:
            extension = self.file_manager.get_file_extension(file_path.name)
            filename = self.file_manager.generate_filename(doc_id, doc_id, version, f".{extension}")
            destination = self.storage_path / filename
            
            # Check if file already exists
            if destination.exists():
                raise FileExistsError(f"El archivo {filename} ya existe")
            
            # Copy file (no locking needed for new file creation)
            self.file_manager.copy_file(file_path, destination)
            # Track the file path (relative to storage path for portability)
            copied_file_paths.append(str(destination.relative_to(self.storage_path)))
            
        # Database operations with transaction lock (metadata update)
        with self.lock_manager.database_transaction_lock(doc_id):
            # Create or update document record in SQLite
            # In the original system, doc_id is used as the document identifier
            # We'll use doc_id as the name field in SQLite for consistency
            existing_document = SQLiteDocument.load_from_database(
                self.db_manager, self.doc_type, doc_id, self.current_user
            )
            
            if existing_document:
                # Update existing document
                document = existing_document
                document.add_entry(version, state, author, notes=notes)
                # Add new file paths to existing ones
                for file_path in copied_file_paths:
                    document.add_file_path(file_path)
            else:
                # Create new document using doc_id as the name (for consistency with original)
                document = SQLiteDocument.create_new(doc_id, self.doc_type, self.db_manager, self.current_user)
                document.autor = author  # Set the original author
                document.add_entry(version, state, author, notes=notes)
                # Set initial file paths
                document.file_paths = copied_file_paths
            
            # Save to database
            document.save_to_database()
        
        # Add success messages for files
        for file_path in file_paths:
            extension = self.file_manager.get_file_extension(file_path.name)
            filename = self.file_manager.generate_filename(doc_id, doc_id, version, f".{extension}")
            messages.append(f"✓ {filename}")
        
        # Cloud sync (same as original)
        try:
            if self.cloud_config.is_cloud_sync_enabled():
                destination = self.storage_path / filename  # Use last filename
                self.cloud_sync.sync_document(document, destination)
        except Exception as e:
            raise RuntimeError(f"Error de sincronización en la nube: {e}")
        
        return messages

    def update_document_state(self, doc_id: str, new_state: str, author: str, notes: str) -> str:
        """Update document state. Returns success message."""
        
        # Clean up expired locks first (Windows-specific locking issues)
        try:
            self.db_manager.cleanup_expired_locks()
        except Exception:
            pass  # Don't fail if cleanup fails
        
        document = SQLiteDocument.load_from_database(
            self.db_manager, self.doc_type, doc_id, self.current_user
        )
        
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        # Get current file information for renaming
        old_filename = document.filename
        old_path = self.storage_path / old_filename
        
        if not old_path.exists():
            raise FileNotFoundError(f"El archivo {old_filename} no existe")
        
        # Generate new filename based on new state
        extension = self.file_manager.get_file_extension(old_filename)
        new_filename = self.file_manager.generate_filename(
            doc_id, doc_id, document.current_version, new_state, f".{extension}"
        )
        new_path = self.storage_path / new_filename
        
        # Rename file if filename changed
        if old_filename != new_filename:
            if new_path.exists():
                raise FileExistsError(f"El archivo {new_filename} ya existe")
            
            old_path.rename(new_path)
        
        # Database operations with transaction lock (metadata update)
        with self.lock_manager.database_transaction_lock(doc_id):
            # Add new entry with updated state
            current_version = document.current_version
            document.add_entry(current_version, new_state, author, notes=notes)
            
            # Save document to database
            document.save_to_database()
        
        return f"✓ Estado actualizado a {new_state}"

    def get_all_documents(self) -> List[SQLiteDocument]:
        """Get all documents of this type from SQLite database."""
        return SQLiteDocument.load_all_from_database(
            self.db_manager, self.doc_type, self.current_user
        )

    def get_document(self, doc_id: str) -> Optional[SQLiteDocument]:
        """Get a specific document by ID."""
        return SQLiteDocument.load_from_database(
            self.db_manager, self.doc_type, doc_id, self.current_user
        )

    def document_exists(self, doc_id: str) -> bool:
        """Check if a document exists."""
        return self.get_document(doc_id) is not None

    def delete_document(self, doc_id: str) -> str:
        """Delete a document and its files."""
        document = self.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        # Delete physical files - use tracked file paths first (new approach)
        deleted_files = []
        
        # Method 1: Use tracked file paths (for documents with tracked files)
        if hasattr(document, 'file_paths') and document.file_paths:
            for tracked_path in document.file_paths:
                file_path = self.storage_path / tracked_path
                if file_path.exists():
                    try:
                        file_path.unlink()
                        deleted_files.append(tracked_path)
                    except OSError as e:
                        print(f"Error deleting tracked file {tracked_path}: {e}")
        
        # Method 2: Fallback to pattern matching (for old documents)
        if not deleted_files:
            for file_path in self.storage_path.glob(f"*{doc_id}*"):
                try:
                    file_path.unlink()
                    deleted_files.append(file_path.name)
                except OSError as e:
                    print(f"Error deleting file {file_path}: {e}")
        
        # Delete from database
        if document.db_id:
            self.db_manager.delete_document(document.db_id)
        
        return f"✓ Documento eliminado: {', '.join(deleted_files)}"

    def get_documents_by_state(self, state: str) -> List[SQLiteDocument]:
        """Get all documents with a specific state."""
        all_docs = self.get_all_documents()
        return [doc for doc in all_docs if doc.current_state == state]

    def get_document_statistics(self) -> Dict[str, int]:
        """Get statistics about documents."""
        all_docs = self.get_all_documents()
        
        stats = {
            "total": len(all_docs),
            "by_state": {}
        }
        
        for doc in all_docs:
            state = doc.current_state or "Sin Estado"
            stats["by_state"][state] = stats["by_state"].get(state, 0) + 1
        
        return stats

    def check_document_lock_status(self, doc_id: str) -> Dict[str, Any]:
        """Check if a document is locked and by whom."""
        document = self.get_document(doc_id)
        if not document or not document.db_id:
            return {"is_locked": False, "locked_by": None}
        
        return self.db_manager.check_lock_status(document.db_id)

    def acquire_document_lock(self, doc_id: str) -> bool:
        """Acquire a lock on a document for editing."""
        document = self.get_document(doc_id)
        if not document or not document.db_id:
            return False
        
        return self.db_manager.acquire_simple_lock(document.db_id, self.current_user)

    def release_document_lock(self, doc_id: str) -> bool:
        """Release a lock on a document."""
        document = self.get_document(doc_id)
        if not document or not document.db_id:
            return False
        
        return self.db_manager.release_simple_lock(document.db_id, self.current_user)

    def update_document_info(self, old_name: str, new_name: str, new_display_name: str, 
                           new_version: str, new_state: str, author: str, notes: str,
                           autor: str = "", rev_tecnica: str = "", rev_gerencia: str = "") -> str:
        """Update document general information. Returns success message."""
        
        document = self.get_document(old_name)
        if not document:
            raise ValueError(f"No se encontró el documento con nombre {old_name}")
        
        # Validate new state
        from config.settings import StatusConfig
        status_config = StatusConfig()
        valid_states = status_config.default_states.keys()
        if new_state not in valid_states:
            raise ValueError(f"Estado '{new_state}' no válido")
        
        # Handle file renaming using tracked file paths - much simpler!
        updated_file_paths = []
        
        for tracked_path in document.file_paths:
            old_file_path = self.storage_path / tracked_path
            if old_file_path.exists():
                # Generate new filename based on the original extension
                extension = self.file_manager.get_file_extension(old_file_path.name)
                new_filename = self.file_manager.generate_filename(
                    new_name, new_display_name, new_version, new_state, f".{extension}"
                )
                new_file_path = self.storage_path / new_filename
                
                # Check if new file already exists
                if new_file_path.exists() and old_file_path != new_file_path:
                    raise FileExistsError(f"El archivo {new_filename} ya existe")
                
                # Rename file if needed
                if old_file_path != new_file_path:
                    self.file_manager.rename_file(old_file_path, new_file_path)
                    updated_file_paths.append(str(new_file_path.relative_to(self.storage_path)))
                else:
                    updated_file_paths.append(tracked_path)
            else:
                # File doesn't exist anymore, don't include in updated paths
                pass
        
        # Handle name changes by creating new document record
        if old_name != new_name:
            # Create new document with new name
            new_document = SQLiteDocument.create_new(new_name, self.doc_type, self.db_manager, self.current_user)
            
            # Copy all entries from old document
            new_document.entries = document.entries.copy()
            new_document.autor = document.autor
            new_document.rev_tecnica = document.rev_tecnica  
            new_document.rev_gerencia = document.rev_gerencia
            new_document.file_paths = updated_file_paths  # Set updated file paths
            
            # Add new entry for the correction
            new_document.add_entry(new_version, new_state, author, notes=notes)
            
            # Always update fields (allow clearing by passing empty string)
            new_document.autor = autor
            new_document.rev_tecnica = rev_tecnica
            new_document.rev_gerencia = rev_gerencia

            # Save new document
            new_document.save_to_database()

            # Delete old document from database
            if document.db_id:
                self.db_manager.delete_document(document.db_id)

        else:
            # Just update existing document (name stays the same)
            document.add_entry(new_version, new_state, author, notes=notes)
            document.file_paths = updated_file_paths  # Update file paths

            # Always update fields (allow clearing by passing empty string)
            document.autor = autor
            document.rev_tecnica = rev_tecnica
            document.rev_gerencia = rev_gerencia
            
            # Save to database
            document.save_to_database()
        
        return "Información actualizada correctamente"

    def get_fresh_documents(self) -> List[SQLiteDocument]:
        """Get all documents with fresh reload from database - useful for smart refresh."""
        # SQLite documents are always fresh, no need to reload like JSON
        return self.get_all_documents()

    def open_document_location(self, doc_id: str) -> None:
        """Open the file location of a document."""
        document = self.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        # Use tracked file paths for direct file access - much simpler and reliable!
        import subprocess
        import platform
        
        if document.file_paths:
            # Use the first tracked file path
            first_file_path = self.storage_path / document.file_paths[0]
            if first_file_path.exists():
                self.file_manager.open_file_location(first_file_path)
                return
        
        # Fallback: open the document folder if no tracked files or they don't exist
            folder_path = str(self.storage_path)
            
            try:
                if platform.system() == "Darwin":  # macOS
                    subprocess.Popen(["open", folder_path])
                elif platform.system() == "Windows":
                    subprocess.Popen(["explorer", folder_path])
                else:  # Unsupported platform
                    subprocess.Popen(["explorer", folder_path])
            except Exception as e:
                raise RuntimeError(f"No se pudo abrir la ubicación del documento: {e}")

    def delete_documents(self, doc_ids: List[str]) -> str:
        """Delete multiple documents and their files. Returns success message."""
        if not doc_ids:
            raise ValueError("No se proporcionaron documentos para eliminar")
        
        deleted_count = 0
        errors = []
        
        # Use project access lock for bulk deletion to ensure consistency
        with self.lock_manager.project_access_lock():
            for doc_id in doc_ids:
                try:
                    # Use document modification lock for each document
                    with self.lock_manager.database_transaction_lock(doc_id):
                        # Get the document
                        document = self.get_document(doc_id)
                        if not document:
                            errors.append(f"Documento {doc_id} no encontrado")
                            continue
                        
                        # Delete physical files - use tracked file paths first (new approach)
                        files_deleted = []
                        
                        # Method 1: Use tracked file paths (for documents with tracked files)
                        if hasattr(document, 'file_paths') and document.file_paths:
                            for tracked_path in document.file_paths:
                                file_path = self.storage_path / tracked_path
                                if file_path.exists():
                                    try:
                                        file_path.unlink()
                                        files_deleted.append(tracked_path)
                                    except OSError as e:
                                        errors.append(f"Error al eliminar archivo rastreado {tracked_path}: {e}")
                        
                        # Method 2: Fallback to pattern matching (for old documents)
                        if not files_deleted:
                            import glob
                            sanitized_name = self.file_manager.sanitize_for_filename(doc_id)
                            file_pattern = str(self.storage_path / f"*{sanitized_name}*")
                            matching_files = glob.glob(file_pattern)
                            
                            for file_path in matching_files:
                                try:
                                    file_path_obj = Path(file_path)
                                    file_path_obj.unlink()  # Delete the file
                                    files_deleted.append(file_path_obj.name)
                                except OSError as e:
                                    errors.append(f"Error al eliminar archivo {file_path}: {e}")
                        
                        # Delete from database with transaction lock
                        with self.lock_manager.database_transaction_lock(doc_id):
                            if document.db_id:
                                self.db_manager.delete_document(document.db_id)
                                deleted_count += 1
                
                except Exception as e:
                    errors.append(f"Error al eliminar documento {doc_id}: {e}")
        
        # Prepare result message
        result_parts = []
        if deleted_count > 0:
            result_parts.append(f"Se eliminaron {deleted_count} documento(s) exitosamente")
        
        if errors:
            result_parts.append(f"Errores encontrados:\n" + "\n".join(f"• {error}" for error in errors))
        
        if not result_parts:
            return "No se eliminó ningún documento"
        
        return "\n\n".join(result_parts)

    def delete_document_entries(self, entry_specs: List[Dict[str, str]]) -> str:
        """Delete specific version/state entries. Returns success message."""
        if not entry_specs:
            raise ValueError("No se proporcionaron entradas para eliminar")
        
        deleted_count = 0
        errors = []
        documents_to_update = {}  # Track which documents need updating
        
        for entry_spec in entry_specs:
            try:
                doc_id = entry_spec['doc_id']
                version = entry_spec['version']
                state = entry_spec['state']
                filename = entry_spec.get('filename', '')
                
                # Get the document
                document = self.get_document(doc_id)
                if not document:
                    errors.append(f"Documento {doc_id} no encontrado")
                    continue
                
                # Delete ALL physical files associated with this specific version/state
                files_deleted = []
                
                # Method 1: Use tracked file paths (for new documents) 
                # Filter tracked paths to match this specific version/state
                if hasattr(document, 'file_paths') and document.file_paths:
                    # Find files that match this version/state pattern
                    version_safe = self.file_manager.sanitize_for_filename(version)
                    state_safe = self.file_manager.sanitize_for_filename(state)
                    
                    # Check each tracked path to see if it belongs to this version/state
                    files_to_remove = []
                    for tracked_path in document.file_paths:
                        # Check if this file belongs to the version/state being deleted
                        if (f"_{version_safe}_{state_safe}" in tracked_path or 
                            f"_{version}_{state}" in tracked_path):
                            file_path = self.storage_path / tracked_path
                            if file_path.exists():
                                try:
                                    file_path.unlink()
                                    files_deleted.append(tracked_path)
                                    files_to_remove.append(tracked_path)
                                except OSError as e:
                                    errors.append(f"Error al eliminar archivo {tracked_path}: {e}")
                    
                    # Remove deleted files from document's tracked paths
                    for file_path in files_to_remove:
                        document.remove_file_path(file_path)
                
                # Method 2: Fallback pattern matching for old documents or when no tracked files found
                if not files_deleted:
                    import glob
                    search_patterns = [
                        # Pattern 1: Standard FileManager pattern - ALL files matching version/state
                        f"{doc_id}_{self.file_manager.sanitize_for_filename(document.name)}_{self.file_manager.sanitize_for_filename(version)}_{self.file_manager.sanitize_for_filename(state)}.*",
                        # Pattern 2: Legacy pattern with raw version/state - ALL files
                        f"{doc_id}_{self.file_manager.sanitize_for_filename(document.name)}_{version}_{state}.*",
                        # Pattern 3: Broad pattern matching doc_id and version - ALL files
                        f"{doc_id}_*{version}*{state}*",
                    ]
                    
                    for pattern in search_patterns:
                        pattern_path = str(self.storage_path / pattern)
                        matching_files = glob.glob(pattern_path)
                        if matching_files:
                            # Delete ALL matching files for this version/state
                            for file_path_str in matching_files:
                                try:
                                    file_path_obj = Path(file_path_str)
                                    file_path_obj.unlink()
                                    files_deleted.append(file_path_obj.name)
                                except OSError as e:
                                    errors.append(f"Error al eliminar archivo {file_path_obj.name}: {e}")
                            break  # Stop after first successful pattern match
                
                # Find and remove the specific entry from the document
                entry_removed = False
                for i, entry in enumerate(document.entries):
                    if entry.version == version and entry.state == state:
                        document.entries.pop(i)
                        entry_removed = True
                        deleted_count += 1
                        documents_to_update[doc_id] = document
                        break
                
                if not entry_removed:
                    errors.append(f"Entrada versión {version}/{state} no encontrada para documento {doc_id}")
                
            except Exception as e:
                errors.append(f"Error al procesar entrada {doc_id} versión {version}: {e}")
        
        # Update or remove documents as needed
        for doc_id, document in documents_to_update.items():
            try:
                if not document.entries:
                    # If no entries left, remove the entire document
                    if document.db_id:
                        self.db_manager.delete_document(document.db_id)
                else:
                    # Update the document with remaining entries
                    document.save_to_database()
            except Exception as e:
                errors.append(f"Error al actualizar documento {doc_id}: {e}")
        
        # Prepare result message
        result_parts = []
        if deleted_count > 0:
            result_parts.append(f"Se eliminaron {deleted_count} entrada(s) exitosamente")
        
        if errors:
            result_parts.append(f"Errores encontrados:\n" + "\n".join(f"• {error}" for error in errors))
        
        if not result_parts:
            return "No se eliminó ninguna entrada"
        
        return "\n\n".join(result_parts)

    def create_assignment(self, document_id: str, document_name: str, 
                         from_state: str, to_state: str, 
                         assigned_users: List[str], notes: str = "") -> str:
        """Create assignment for document state transition - DISABLED"""
        # Workflow system is disabled in SQLite controllers
        return "Workflow system disabled"

    def get_user_notifications(self, username: str = None) -> List[Dict[str, Any]]:
        """Get notifications for user - DISABLED"""
        # Workflow system is disabled in SQLite controllers
        return []
    
    def get_document_assignment_history(self, document_id: str) -> List[Dict[str, Any]]:
        """Get assignment history for document - DISABLED"""
        # Workflow system is disabled in SQLite controllers
        return []
    
    def can_user_complete_assignment(self, document_id: str, state: str, username: str = None) -> bool:
        """Check if user can complete assignment for document/state - DISABLED"""
        # Workflow system is disabled in SQLite controllers
        return False
    
    def get_available_users_for_assignment(self) -> List[Dict[str, Any]]:
        """Get available users for assignment - DISABLED"""
        # Workflow system is disabled in SQLite controllers
        return []

    def close(self):
        """Close database connections."""
        if self.db_manager:
            self.db_manager.close()


# Compatibility alias - allows existing code to import DocumentController and get SQLite version
DocumentController = SQLiteDocumentController