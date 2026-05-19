from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from models.document import Document, DocumentRepository
from utils.file_manager import FileManager
from utils.project_utils import ProjectUtils
from config.settings import StatusConfig, CloudConfig
from utils.cloud_sync import CloudSyncManager
from utils.cloud_exceptions import (
    CloudSyncError, CloudAuthenticationError, CloudValidationError, 
    CloudUploadError, CloudConnectionError
)
# from controllers.notification_controller import NotificationController  # Removed


class DocumentController:
    def __init__(self, doc_type: str, doc_folder: str, project_path: Path = None):
        self.doc_type = doc_type
        self.doc_folder = doc_folder
        
        # Si se proporciona project_path, usarlo; si no, usar directorio actual
        self.project_path = project_path if project_path else Path.cwd()
        self.storage_path = self.project_path / doc_folder
        from utils.path_helper import PathHelper
        pm_path = PathHelper.get_project_manager_path(self.project_path)
        self.manifest_path = pm_path / doc_type / "manifest.json"
        
        # Ensure directories exist
        ProjectUtils.ensure_directory_exists(self.storage_path)
        ProjectUtils.ensure_directory_exists(self.manifest_path.parent)
        
        self.repository = DocumentRepository(self.manifest_path)
        self.status_config = StatusConfig(self.project_path)
        self.file_manager = FileManager()
        self.cloud_config = CloudConfig(self.project_path)
        self.cloud_sync = CloudSyncManager(self.cloud_config)
        # self.notification_controller = NotificationController(self.project_path)  # Removed

    def add_new_version(self, doc_id: str, name: str, version: str, state: str, 
                       file_paths: List[Path], author: str, notes: str) -> List[str]:
        """Add a new document version. Returns list of success messages."""
        messages = []
        
        for file_path in file_paths:
            extension = self.file_manager.get_file_extension(file_path.name)
            filename = self.file_manager.generate_filename(doc_id, name, version, extension)
            destination = self.storage_path / filename
            
            # Check if file already exists
            if destination.exists():
                raise FileExistsError(f"El archivo {filename} ya existe")
            
            # Copy file
            self.file_manager.copy_file(file_path, destination)
            
            # Create or update document record
            if self.repository.document_exists(doc_id):
                document = self.repository.get_document(doc_id)
                old_values = {
                    "version": document.current_version,
                    "current_state": document.current_state,
                    "filename": document.filename
                }
                new_values = {
                    "version": version,
                    "current_state": state,
                    "filename": filename
                }
                document.add_entry(version, state, author, notes)
                self.repository.update_document(doc_id, document)
            else:
                document = Document(
                    id=doc_id,
                    name=name,
                    autor=author  # Set the author as the original autor
                )
                # Add the first entry for this document
                document.add_entry(version, state, author, notes)
                self.repository.add_document(document)
            
            messages.append(f"✓ {filename}")
            
            # Sync to cloud if enabled and document is in sync-eligible state
            try:
                if self.cloud_config.is_cloud_sync_enabled():
                    document = self.repository.get_document(doc_id)
                    if document:
                        self.cloud_sync.sync_document(document, destination)
            except CloudAuthenticationError as e:
                # Authentication failures require user intervention
                raise RuntimeError(f"Error de autenticación en la nube: {e}")
            except CloudValidationError as e:
                # Validation errors can be logged but shouldn't block operation
                print(f"Advertencia: Error de validación en la nube: {e}")
            except CloudConnectionError as e:
                # Connection errors are temporary
                print(f"Advertencia: Error de conexión a la nube: {e}")
            except CloudUploadError as e:
                # Upload errors may indicate storage issues
                print(f"Advertencia: Error de subida a la nube: {e}")
            except CloudSyncError as e:
                # General cloud sync errors - decide whether to block or continue
                print(f"Advertencia: Error de sincronización en la nube: {e}")
            except Exception as e:
                # Unexpected errors - raise as before for backward compatibility
                raise RuntimeError(f"Error inesperado de sincronización en la nube: {e}")
        
        return messages

    def update_document_state(self, doc_id: str, new_state: str, author: str, notes: str, 
                             file_paths: Optional[List[Path]] = None) -> str:
        """Update document state with optional file uploads. Returns success message."""
        document = self.repository.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        # Handle file operations based on whether files are being uploaded
        uploaded_files = []
        if file_paths:
            # Scenario 2: Files uploaded - leave original file alone, create new ones
            try:
                uploaded_files = self._upload_additional_files(doc_id, document.name, 
                                                             document.current_version, new_state, file_paths)
            except Exception as e:
                # If file upload fails, log warning but don't fail the state change
                print(f"Advertencia: Error al subir archivos adicionales: {e}")
        else:
            # Scenario 1: No files uploaded - rename existing file to reflect new state
            old_filename = document.filename
            old_path = self.storage_path / old_filename
            
            if not old_path.exists():
                raise FileNotFoundError(f"El archivo {old_filename} no existe")
            
            # Generate new filename with new state
            from utils.filename_state_manager import FilenameStateManager
            state_manager = FilenameStateManager()
            extension = self.file_manager.get_file_extension(old_filename)
            new_filename = state_manager.build_simple_filename(
                document.name, document.current_version, new_state, extension
            )
            new_path = self.storage_path / new_filename
            
            # Check if new file already exists
            if new_path.exists() and old_path != new_path:
                raise FileExistsError(f"El archivo {new_filename} ya existe")
            
            # Rename file if needed
            if old_path != new_path:
                self.file_manager.rename_file(old_path, new_path)
        
        # Auto-assign reviewers based on state transitions with validation
        if not author or not author.strip():
            raise ValueError("Author cannot be empty for state transitions")
        
        old_state = document.current_state
        
        # Atomic assignment with race condition protection
        if new_state == "S2" and not document.rev_tecnica:
            # S2: "Revisado por Técnico Especialista" - assign Rev. Téc.
            document.rev_tecnica = author.strip()
        elif new_state == "S3" and not document.rev_gerencia:
            # S3: "Revisado por Director Proyecto" - assign Rev. Ger.  
            document.rev_gerencia = author.strip()
        
        # Update document
        old_values = {"current_state": document.current_state, "filename": document.filename}
        new_values = {"current_state": new_state, "filename": new_filename}
        
        # Add new entry with same version but new state
        document.add_entry(document.current_version, new_state, author, notes)
        
        self.repository.update_document(doc_id, document)
        
        # Auto-complete any pending assignments for this document/state
        # completed_assignments = self.notification_controller.complete_assignments_on_state_change(
        #     doc_id, new_state
        # )  # Removed
        
        # Sync to cloud if enabled and document is in sync-eligible state
        try:
            if self.cloud_config.is_cloud_sync_enabled():
                if file_paths:
                    # Scenario 2: Sync uploaded files
                    # The _upload_additional_files method already handles cloud sync for each file
                    pass
                else:
                    # Scenario 1: Sync renamed file
                    self.cloud_sync.sync_document(document, new_path)
        except Exception as e:
            # Cloud sync error - raise it as specified in requirements
            raise RuntimeError(f"Error de sincronización en la nube: {e}")
        
        # Prepare success message
        message = f"Estado actualizado: {self.status_config.STATE_MAP[new_state]}"
        if uploaded_files:
            message += f"\n✓ {len(uploaded_files)} archivo(s) adicional(es) subido(s)"
        
        return message

    def _upload_additional_files(self, doc_id: str, doc_name: str, version: str, 
                               state: str, file_paths: List[Path]) -> List[str]:
        """Upload additional files related to state change. Returns list of uploaded filenames."""
        uploaded_files = []
        
        for file_path in file_paths:
            if not file_path.exists():
                print(f"Advertencia: Archivo no encontrado: {file_path}")
                continue
                
            # Generate filename following standard pattern: {doc_name}_v{version}_{state}.{ext}
            extension = self.file_manager.get_file_extension(file_path.name)
            
            from utils.filename_state_manager import FilenameStateManager
            state_manager = FilenameStateManager()
            
            # For multiple files, add counter to make each unique
            base_filename = state_manager.build_simple_filename(
                doc_name, version, state, extension
            )
            
            destination = self.storage_path / base_filename
            
            # If file exists, add counter to make it unique
            counter = 1
            while destination.exists():
                # Insert counter before extension: Document_v1.2_S2_1.pdf
                name_without_ext = base_filename.rsplit('.', 1)[0]
                ext_with_dot = f".{extension}"
                numbered_filename = f"{name_without_ext}_{counter}{ext_with_dot}"
                destination = self.storage_path / numbered_filename
                base_filename = numbered_filename
                counter += 1
            
            try:
                # Copy file to destination
                self.file_manager.copy_file(file_path, destination)
                uploaded_files.append(base_filename)
                
                # Sync to cloud if enabled
                if self.cloud_config.is_cloud_sync_enabled():
                    document = self.repository.get_document(doc_id)
                    if document:
                        self.cloud_sync.sync_document(document, destination)
                        
            except Exception as e:
                print(f"Error al subir archivo {file_path.name}: {e}")
                continue
        
        return uploaded_files

    def update_document_info(self, old_name: str, new_name: str, new_display_name: str, 
                           new_version: str, new_state: str, author: str, notes: str,
                           autor: str = "", rev_tecnica: str = "", rev_gerencia: str = "") -> str:
        """Update document general information. Returns success message.
        
        Note: old_name/new_name are actually document names (the primary identifier),
        new_display_name is for display purposes but stored in the name field.
        This maintains compatibility with the correction form that passes old_id/new_id.
        """
        document = self.repository.get_document(old_name)
        if not document:
            raise ValueError(f"No se encontró el documento con nombre {old_name}")
        
        old_filename = document.filename
        old_path = self.storage_path / old_filename
        
        if not old_path.exists():
            raise FileNotFoundError(f"El archivo {old_filename} no existe")
        
        # Generate new filename based on new information (matching Document model format)
        extension = self.file_manager.get_file_extension(old_filename)
        from utils.file_manager import FileManager
        sanitized_name = FileManager.sanitize_for_filename(new_display_name)
        sanitized_version = FileManager.sanitize_for_filename(new_version)
        sanitized_state = FileManager.sanitize_for_filename(new_state)
        new_filename = f"{sanitized_name}_{sanitized_version}_{sanitized_state}.{extension}"
        new_path = self.storage_path / new_filename
        
        # Check if new file already exists
        if new_path.exists() and old_path != new_path:
            raise FileExistsError(f"El archivo {new_filename} ya existe")
        
        # Rename file if needed
        if old_path != new_path:
            self.file_manager.rename_file(old_path, new_path)
        
        # If name changed, we need to delete old and create new document record
        if old_name != new_name:
            # Remove old document from repository
            del self.repository.documents[old_name]
            
            # Update document info and add new entry
            document.name = new_name  # Use new_name as both key and internal name
            document.autor = autor if autor else document.autor
            document.rev_tecnica = rev_tecnica if rev_tecnica else document.rev_tecnica
            document.rev_gerencia = rev_gerencia if rev_gerencia else document.rev_gerencia
            
            # Add new entry for the correction
            document.add_entry(new_version, new_state, author, notes)
            
            # Add document with new name as key
            self.repository.documents[new_name] = document
            self.repository.save()
        else:
            # Just update existing document (name stays the same)
            document.name = new_name  # Use new_name as both key and internal name
            document.autor = autor if autor else document.autor
            document.rev_tecnica = rev_tecnica if rev_tecnica else document.rev_tecnica
            document.rev_gerencia = rev_gerencia if rev_gerencia else document.rev_gerencia
            
            # Add new entry for the correction
            document.add_entry(new_version, new_state, author, notes)
            
            self.repository.update_document(old_name, document)
        
        self.repository.save()
        return "Información actualizada correctamente"

    def get_all_documents(self) -> List[Document]:
        """Get all documents."""
        return self.repository.get_all_documents()
    
    def get_fresh_documents(self) -> List[Document]:
        """Get all documents with fresh reload from file - useful for smart refresh."""
        self.repository.reload()
        return self.repository.get_all_documents()

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a specific document."""
        return self.repository.get_document(doc_id)


    def open_document_location(self, doc_id: str) -> None:
        """Open the file location of a document."""
        document = self.repository.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        file_path = self.storage_path / document.filename
        self.file_manager.open_file_location(file_path)

    def delete_documents(self, doc_ids: List[str]) -> str:
        """Delete multiple documents and their files. Returns success message."""
        if not doc_ids:
            raise ValueError("No se proporcionaron documentos para eliminar")
        
        deleted_count = 0
        errors = []
        
        for doc_id in doc_ids:
            try:
                document = self.repository.get_document(doc_id)
                if not document:
                    errors.append(f"Documento {doc_id} no encontrado")
                    continue
                
                # Delete physical file
                file_path = self.storage_path / document.filename
                if file_path.exists():
                    try:
                        file_path.unlink()  # Delete the file
                    except OSError as e:
                        errors.append(f"Error al eliminar archivo {document.filename}: {e}")
                        continue
                
                # Delete document record from repository
                if doc_id in self.repository.documents:
                    del self.repository.documents[doc_id]
                    deleted_count += 1
                else:
                    errors.append(f"Registro del documento {doc_id} no encontrado en la base de datos")
                
            except Exception as e:
                errors.append(f"Error al procesar documento {doc_id}: {e}")
        
        # Save repository changes
        if deleted_count > 0:
            self.repository.save()
        
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
                filename = entry_spec['filename']
                
                # Get the document
                document = self.repository.get_document(doc_id)
                if not document:
                    errors.append(f"Documento {doc_id} no encontrado")
                    continue
                
                # Delete physical file
                file_path = self.storage_path / filename
                if file_path.exists():
                    try:
                        file_path.unlink()  # Delete the file
                    except OSError as e:
                        errors.append(f"Error al eliminar archivo {filename}: {e}")
                        continue
                
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
                    errors.append(f"Entrada v{version}-{state} no encontrada para documento {doc_id}")
                
            except Exception as e:
                errors.append(f"Error al procesar entrada {doc_id} v{version}-{state}: {e}")
        
        # Update or remove documents as needed
        for doc_id, document in documents_to_update.items():
            if not document.entries:
                # If no entries left, remove the entire document record
                if doc_id in self.repository.documents:
                    del self.repository.documents[doc_id]
            else:
                # Update the document with remaining entries
                self.repository.update_document(doc_id, document)
        
        # Save repository changes
        if deleted_count > 0:
            self.repository.save()
        
        # Prepare result message
        result_parts = []
        if deleted_count > 0:
            result_parts.append(f"Se eliminaron {deleted_count} versión(es)/estado(s) exitosamente")
        
        if errors:
            result_parts.append(f"Errores encontrados:\n" + "\n".join(f"• {error}" for error in errors))
        
        if not result_parts:
            return "No se eliminó ninguna versión/estado"
        
        return "\n\n".join(result_parts)

    def create_assignment(self, document_id: str, document_name: str, 
                         from_state: str, to_state: str, 
                         assigned_users: List[str], notes: str = "") -> str:
        """Create assignment for document state transition - DISABLED"""
        # return self.notification_controller.create_assignment(
        #     document_id, document_name, from_state, to_state, assigned_users, notes
        # )  # Removed
        return "Assignment functionality disabled"
    
    def get_user_notifications(self, username: str = None) -> List[Dict[str, Any]]:
        """Get notifications for user - DISABLED"""
        # return self.notification_controller.get_user_notifications(username)  # Removed
        return []
    
    def get_document_assignment_history(self, document_id: str) -> List[Dict[str, Any]]:
        """Get assignment history for document - DISABLED"""
        # return self.notification_controller.get_document_assignment_history(document_id)  # Removed
        return []
    
    def can_user_complete_assignment(self, document_id: str, state: str, username: str = None) -> bool:
        """Check if user can complete assignment for document/state - DISABLED"""
        # return self.notification_controller.can_user_complete_assignment(document_id, state, username)  # Removed
        return False
    
    def get_available_users_for_assignment(self) -> List[Dict[str, Any]]:
        """Get available users for assignment - DISABLED"""
        # return self.notification_controller.get_available_users_for_assignment()  # Removed
        return []