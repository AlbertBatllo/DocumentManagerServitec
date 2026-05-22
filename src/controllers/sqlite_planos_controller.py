"""
SQLite-backed Planos Controller
Replaces JSON-based PlanosController with SQLite operations while maintaining same API.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from models.sqlite_document import SQLiteDocument
from models.plano_document import PLANO_STATES, STATE_DISPLAY_NAMES
from utils.project_database_manager import ensure_project_database
from utils.file_manager import FileManager
from utils.project_utils import ProjectUtils
from utils.lock_manager import get_project_lock_manager
from config.settings import StatusConfig, UserConfig, CloudConfig
from utils.cloud_exceptions import (
    CloudSyncError, CloudAuthenticationError, CloudValidationError,
    CloudUploadError, CloudConnectionError
)
from utils.filename_state_manager import FilenameStateManager
from utils.file_type_upload_router import FileTypeUploadRouter
from utils.folder_structure_manager import FolderStructureManager, FileType
from utils.unified_xref_manager_async import AsyncXrefManager
from services.document_file_service import DocumentFileService
from utils.folder_resolver import FolderResolver
from utils.trash import move_to_trash


class SQLitePlanosController:
    """
    SQLite-backed planos controller.
    
    Provides the same API as PlanosController but uses SQLite instead of JSON.
    """
    
    def __init__(self, project_path: Path = None, enable_cloud_sync: bool = None):
        # Ensure project_path is always a Path object
        if project_path is None:
            self.project_path = Path.cwd()
        elif isinstance(project_path, str):
            self.project_path = Path(project_path)
        else:
            self.project_path = project_path
        
        # Set up storage path for planos (dynamic resolution)
        self.storage_path = FolderResolver.resolve_planos(self.project_path)
        # Compatibility: some UI code expects a doc_folder attribute
        self.doc_folder = str(self.storage_path)
        
        # Ensure directory exists and create proper folder structure
        ProjectUtils.ensure_directory_exists(self.storage_path)
        self._ensure_proper_folder_structure()
        
        # Initialize SQLite database (replaces JSON manifest)
        self.db_manager = ensure_project_database(self.project_path)
        
        # Initialize other components
        self.file_manager = FileManager()
        
        # Initialize file type upload router for organized structure
        self.upload_router = FileTypeUploadRouter(self.storage_path, self.file_manager)
        
        # XREF manager initialized later after cloud sync
        self.xref_manager = None

        # Initialize folder structure manager
        self.folder_manager = FolderStructureManager(self.storage_path)

        # Initialize document file service (filesystem as source of truth)
        self.file_service = DocumentFileService(self.storage_path)
        
        # Get current user name for database operations
        self.user_config = UserConfig()
        self.current_user = self.user_config.get_user_name() or "Unknown User"
        
        # Initialize lock manager for safe concurrent operations
        self.lock_manager = get_project_lock_manager(self.project_path)
        
        # Initialize filename state manager for consistent file naming
        self.filename_manager = FilenameStateManager(self.project_path)
        
        # Initialize cloud sync (optional, non-breaking)
        self.cloud_sync = None
        try:
            self.cloud_config = CloudConfig(self.project_path)
            
            # Determine if cloud sync should be enabled
            cloud_sync_enabled = False
            if enable_cloud_sync is not None:
                # Explicit parameter overrides config
                cloud_sync_enabled = enable_cloud_sync and self.cloud_config.is_cloud_sync_enabled()
            else:
                # Use config setting
                cloud_sync_enabled = self.cloud_config.is_cloud_sync_enabled()
            
            if cloud_sync_enabled:
                from utils.enhanced_cloud_sync import EnhancedCloudSyncManager
                self.cloud_sync = EnhancedCloudSyncManager(self.cloud_config)
                print(f"[SQLitePlanosController] Cloud sync enabled for project: {self.project_path.name}")
            else:
                print(f"[SQLitePlanosController] Cloud sync disabled")
                
        except Exception as e:
            print(f"[SQLitePlanosController] Warning: Could not initialize cloud sync: {e}")
            # Cloud sync failure should not break the controller
            self.cloud_sync = None
        
        # Initialize XREF manager for CAD reference tracking
        try:
            self.xref_manager = AsyncXrefManager(
                self.db_manager.db_path,
                progress_callback=self._on_xref_progress
            )
            print(f"[SQLitePlanosController] XREF manager initialized")

            # Process any existing documents that haven't been XREF-processed yet
            # This runs in background and handles documents created before XREF was added
            stats = self.xref_manager.process_unprocessed_documents(self.storage_path)
            if stats['queued'] > 0:
                print(f"[SQLitePlanosController] Queued {stats['queued']} documents for XREF processing")
            elif stats['skipped_no_dwg'] > 0:
                print(f"[SQLitePlanosController] Marked {stats['skipped_no_dwg']} documents as processed (no DWG)")

        except Exception as e:
            print(f"[SQLitePlanosController] Warning: Could not initialize XREF manager: {e}")
            # XREF failure should not break the controller
            self.xref_manager = None

    def add_new_document(self, name: str, state: str, version: str,
                        file_paths: List[Path], author: str, rev_tecnica: str = "",
                        rev_gerencia: str = "", notes: str = "", dwg_name: str = "",
                        entry_timestamp: str = None) -> List[str]:
        """Add a new plano document. Returns list of success messages.

        Args:
            dwg_name: Custom name for uploaded DWG file (if different from entry name)
            entry_timestamp: Optional ISO timestamp for the initial entry. Bulk
                upload passes the source file mtime so the dashboard "Fecha"
                column reflects the file's date instead of the upload moment.
        """

        # Accept legacy/human-readable states for backward compatibility

        # Check if document already exists
        if self.document_exists(name):
            raise ValueError(f"Ya existe un documento con nombre '{name}'")

        # Create SQLite document
        document = SQLiteDocument.create_new(name, "planos", self.db_manager, self.current_user)

        # Add initial entry (file paths will be updated during processing)
        document.add_entry(version, state, author, notes=notes, file_path="",
                           timestamp=entry_timestamp)

        # Set document-level autor field from the entry author (for dashboard display)
        document.autor = author

        # Set revision fields if provided
        if rev_tecnica:
            document.rev_tecnica = rev_tecnica
        if rev_gerencia:
            document.rev_gerencia = rev_gerencia

        messages = []

        # Process each file using the new upload router
        for file_path in file_paths:
            # Use upload router to determine proper destination and filename
            # For DWG files, use custom dwg_name if provided
            file_ext = file_path.suffix.lower()
            doc_name_for_file = dwg_name if (file_ext == '.dwg' and dwg_name) else name

            document_info = {
                'name': doc_name_for_file,
                'version': version,
                'state': state,
                'author': author
            }

            success, destination, message = self.upload_router.route_file_upload(
                file_path,
                document_info
            )

            if not success:
                messages.append(f"Error routing file {file_path.name}: {message}")
                continue

            # Track the file in document's file_paths
            document.add_file_path(str(destination))
            messages.append(f"✓ Archivo creado: {destination.name}")
            if "⚠" in message or "no encontradas" in message:
                messages.append(f"⚠ {destination.name}: {message}")

            # Process XREF references for DWG files (asynchronous)
            file_extension = destination.suffix.lower()
            if file_extension == '.dwg':
                self.process_plano_xrefs(name, destination)
        
        # Save document to database with locking protection (metadata update)
        with self.lock_manager.database_transaction_lock(name):
            document.save_to_database()
        
        return messages

    def add_new_version(self, doc_name: str, version: str, state: str, file_paths: List[Path],
                       author: str, rev_tecnica: str = "", rev_gerencia: str = "",
                       notes: str = "", dwg_name: str = "",
                       entry_timestamp: str = None) -> List[str]:
        """Add a new version to an existing document. Returns list of success messages.

        Args:
            dwg_name: Custom name for uploaded DWG file (if different from doc_name)
            entry_timestamp: Optional ISO timestamp for the new entry (preserves
                source file mtime when called from bulk upload).
        """

        # Accept legacy/human-readable states for backward compatibility

        # Get existing document
        document = self.get_document(doc_name)
        if not document:
            raise ValueError(f"No existe el documento con nombre '{doc_name}'")
        
        messages = []
        primary_file_path = None

        # Process each file using the upload router
        # This will archive old PDFs and route to correct folders
        for i, file_path in enumerate(file_paths):
            # Use upload router to determine proper destination and filename
            # For DWG files, use custom dwg_name if provided
            file_ext = file_path.suffix.lower()
            doc_name_for_file = dwg_name if (file_ext == '.dwg' and dwg_name) else document.name

            document_info = {
                'name': doc_name_for_file,
                'version': version,
                'state': state,
                'author': author
            }
            # Default operation is 'new_version' which archives old PDFs
            success, destination, message = self.upload_router.route_file_upload(
                file_path,
                document_info
            )

            if not success:
                messages.append(f"Error routing file {file_path.name}: {message}")
                continue

            # Store the first file as primary file path for the entry
            if i == 0:
                primary_file_path = destination.name

            # Track the file in document's file_paths
            document.add_file_path(str(destination))
            messages.append(f"✓ Nueva versión creada: {destination.name}")
            # Surface XREF warnings (missing references) so they reach the UI
            if "⚠" in message or "no encontradas" in message:
                messages.append(f"⚠ {destination.name}: {message}")

            # Process XREF references for DWG files (asynchronous)
            file_extension = destination.suffix.lower()
            if file_extension == '.dwg':
                self.process_plano_xrefs(doc_name, destination)

        # Add new entry to document with primary file path
        document.add_entry(version, state, author, notes=notes, file_path=primary_file_path,
                           timestamp=entry_timestamp)

        # Update revision fields if provided
        if rev_tecnica:
            document.rev_tecnica = rev_tecnica
        if rev_gerencia:
            document.rev_gerencia = rev_gerencia

        # Save to database with locking protection (metadata update)
        with self.lock_manager.database_transaction_lock(doc_name):
            document.save_to_database()
        
        return messages

    def update_document_state(self, doc_name: str, new_state: str, author: str, 
                             rev_tecnica: str = "", rev_gerencia: str = "", 
                             notes: str = "", file_paths: Optional[List[Path]] = None) -> str:
        """
        Update document state with filename consistency.
        
        ENHANCED BEHAVIOR:
        1. Update database state
        2. Rename file to reflect new state
        3. Sync to cloud with updated filename
        4. Maintain perfect consistency between database ↔ filesystem ↔ cloud
        """
        
        print(f"[Enhanced State Update] Starting state transition: {doc_name} → {new_state}")
        
        # Get existing document
        document = self.get_document(doc_name)
        if not document:
            raise ValueError(f"No existe el documento con nombre '{doc_name}'")
        
        # Get current file path before any changes
        current_file_path = self._resolve_file_path(doc_name)
        if not current_file_path:
            print(f"⚠️ No file found for {doc_name}, proceeding with database update only")
            current_filename = None
        else:
            current_filename = current_file_path.name
            print(f"📁 Current file: {current_filename}")
        
        # Step 1: Archive old PDFs and create new state files
        new_filenames = []
        if current_file_path and current_file_path.exists():
            print(f"🔄 Processing state change: archiving old files and creating new state files...")

            # Get all current PDF files for this document in Working folder
            pdf_working_folder = self.storage_path / "PDF" / "Working"
            pdf_old_folder = self.storage_path / "PDF" / "Old"
            pdf_old_folder.mkdir(parents=True, exist_ok=True)

            # Find all PDFs for this document
            doc_name_patterns = [doc_name, doc_name.replace(' ', '_')]
            pdfs_to_process = []

            for pattern in doc_name_patterns:
                pdfs_to_process.extend(pdf_working_folder.glob(f"*{pattern}*"))

            # Remove duplicates
            pdfs_to_process = list(set(pdfs_to_process))
            print(f"   Found {len(pdfs_to_process)} PDF(s) in Working folder")

            for pdf_path in pdfs_to_process:
                if not pdf_path.is_file():
                    continue

                try:
                    # Step 1a: Archive old file to Old folder (keep original name)
                    archived_path = pdf_old_folder / pdf_path.name
                    if archived_path.exists():
                        # Add timestamp to avoid conflicts
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        archived_name = f"{pdf_path.stem}_{timestamp}{pdf_path.suffix}"
                        archived_path = pdf_old_folder / archived_name

                    import shutil
                    shutil.copy2(pdf_path, archived_path)
                    print(f"   📦 Archived: {pdf_path.name} → Old/{archived_path.name}")

                    # Step 1b: Rename the file in Working with new state
                    new_filename = self.filename_manager.update_filename_for_state_change(pdf_path.name, new_state)
                    if new_filename and new_filename != pdf_path.name:
                        new_path = pdf_working_folder / new_filename
                        pdf_path.rename(new_path)
                        new_filenames.append(str(new_path))  # Store full path
                        print(f"   ✅ Renamed: {pdf_path.name} → {new_filename}")
                    else:
                        new_filenames.append(str(pdf_path))  # Store full path
                        print(f"   ⚠️ Could not generate new filename, keeping: {pdf_path.name}")

                except Exception as e:
                    print(f"   ❌ Error processing {pdf_path.name}: {e}")
                    new_filenames.append(str(pdf_path))  # Store full path

            if not new_filenames:
                new_filenames = [str(current_file_path)] if current_file_path else []
        
        # Step 2: Update database with new state and filenames
        current_version = document.current_version
        
        # Create new database entry
        document.add_entry(current_version, new_state, author, notes=notes)
        
        # Update the current entry with new filenames if changed
        if new_filenames:
            current_entry = document.current_entry
            if current_entry:
                # Use the first filename as primary file_path for compatibility
                primary_filename = new_filenames[0] if new_filenames else None
                if primary_filename:
                    current_entry.file_path = primary_filename
                    print(f"📝 Database updated with primary filename: {primary_filename}")
                
                # Store all filenames in file_paths for multi-file tracking
                if hasattr(document, 'file_paths'):
                    document.file_paths = new_filenames
                    print(f"📝 Database updated with all {len(new_filenames)} filenames in file_paths")
        
        # Update revision fields if provided
        if rev_tecnica:
            document.rev_tecnica = rev_tecnica
        if rev_gerencia:
            document.rev_gerencia = rev_gerencia
        
        # Step 3: Save to database with locking protection
        with self.lock_manager.database_transaction_lock(doc_name):
            document.save_to_database()
            print(f"💾 Database state updated: {doc_name} → {new_state}")
        
        # Step 4: Trigger cloud sync with updated filename
        if self.is_cloud_sync_enabled():
            try:
                # Sync when document reaches states that require cloud sync:
                # S2 → SharePoint upload only
                # S3 → BOTH SharePoint AND Google Drive upload
                # A → Google Drive upload only
                should_sync = new_state in ['S2', 'S3', 'A']
                
                if should_sync:
                    print(f"☁️ Triggering cloud sync for state {new_state}...")
                    
                    # Show which services will be triggered based on END STATE
                    sync_targets = []
                    if new_state in ['S2', 'S3']:  # SharePoint for S2 and S3
                        sync_targets.append("SharePoint")
                    if new_state in ['S3', 'A']:   # Google Drive for S3 and A
                        sync_targets.append("Google Drive")
                    
                    print(f"🎯 Target services: {', '.join(sync_targets)}")
                    
                    sync_result = self.sync_document_to_cloud(doc_name, auto_cleanup=True)
                    
                    if sync_result.get('uploaded_to'):
                        uploaded_services = ', '.join(sync_result['uploaded_to'])
                        print(f"✅ Cloud sync successful: {uploaded_services}")
                        uploaded_filename = new_filenames[0] if new_filenames else current_filename
                        print(f"📂 Uploaded filename: {uploaded_filename}")
                    else:
                        print(f"⚠️ Cloud sync completed with issues: {sync_result}")
                else:
                    print(f"⏸️ Cloud sync not required for state {new_state}")
                    
            except CloudAuthenticationError as e:
                print(f"🔐 Cloud authentication required for {doc_name}: {e}")
                print("   Please re-authenticate to continue cloud synchronization")
                print("   Document state updated locally - cloud sync will resume after authentication")
            except CloudValidationError as e:
                print(f"⚠️ Cloud validation warning for {doc_name}: {e}")
                print("   Document state updated locally, cloud sync skipped due to validation issues")
            except CloudConnectionError as e:
                print(f"🌐 Cloud connection issue for {doc_name}: {e}")
                print("   Document state updated locally, will retry cloud sync when connection restored")
            except CloudUploadError as e:
                print(f"📤 Cloud upload failed for {doc_name}: {e}")
                print("   Document state updated locally, check cloud storage capacity/permissions")
            except CloudSyncError as e:
                print(f"☁️ Cloud sync error for {doc_name}: {e}")
                print("   Document state updated locally, cloud sync can be retried manually")
            except Exception as e:
                print(f"⚠️ Unexpected cloud sync error for {doc_name}: {e}")
                print("   Document state updated locally, contact support if cloud sync issues persist")
        
        # Step 5: Verify final consistency
        if new_filenames:
            primary_filename = new_filenames[0] if new_filenames else None
            if primary_filename:
                final_path = self.storage_path / primary_filename
                file_exists = final_path.exists()
                
                print(f"🔍 Final consistency check:")
                print(f"   Database state: {new_state}")
                print(f"   Primary filename: {primary_filename}")
                print(f"   Total files: {len(new_filenames)}")
                print(f"   File exists: {'✅' if file_exists else '❌'}")
                print(f"   Filename/state consistent: {'✅' if self.filename_manager.validate_filename_consistency(primary_filename, new_state) else '❌'}")
        
        # Handle optional file uploads (if provided)
        uploaded_files = []
        if file_paths:
            print(f"📤 Processing {len(file_paths)} additional files for upload...")
            uploaded_files = self._upload_additional_files(doc_name, document.display_name, current_version, new_state, file_paths)
        
        # Success message with filename info
        success_message = f"✓ Estado del documento '{doc_name}' actualizado a {STATE_DISPLAY_NAMES.get(new_state, new_state)}"
        if new_filenames and len(new_filenames) > 0:
            if len(new_filenames) == 1:
                success_message += f" (archivo renombrado: {new_filenames[0]})"
            else:
                success_message += f" ({len(new_filenames)} archivos renombrados)"
        
        # Add uploaded files info to success message
        if uploaded_files:
            if len(uploaded_files) == 1:
                success_message += f" + 1 archivo adicional subido"
            else:
                success_message += f" + {len(uploaded_files)} archivos adicionales subidos"
        
        return success_message

    def get_all_documents(self) -> List["PlanoView"]:
        """
        Devuelve la lista de planos del proyecto leyendo del modelo
        nuevo (tablas `planos` + `archivos` de Fase 1).

        Fase 5.5: antes esto leia de la tabla legacy `documents`, lo
        que para proyectos creados post-refactor devolvia [] (el
        dashboard mostraba "Total: 0 documentos"). Ahora delegamos en
        PlanoView que lee de la fuente correcta.

        Los uploads legacy huerfanos (subidas hechas via los controllers
        actuales que aun escriben a documents/document_entries) son
        portados automaticamente al nuevo schema por
        `bridge_legacy_uploads`, ejecutado en cada
        `ensure_project_database`. Asi el dashboard ve toda la historia
        del proyecto sin importar por que ruta entro cada archivo.
        """
        from models.plano_view import PlanoView
        return PlanoView.load_all_for_project(self.db_manager)

    def get_document(self, doc_name: str) -> Optional[SQLiteDocument]:
        """Get specific document by name."""
        return SQLiteDocument.load_from_database(
            self.db_manager, "planos", doc_name, self.current_user
        )

    def document_exists(self, name: str) -> bool:
        """Check if a document exists."""
        return self.get_document(name) is not None

    def get_documents_by_state(self, state: str) -> List[SQLiteDocument]:
        """Get all documents in a specific state."""
        all_docs = self.get_all_documents()
        return [doc for doc in all_docs if doc.current_state == state]

    def refresh_documents(self) -> List[SQLiteDocument]:
        """Refresh and return all documents."""
        # SQLite documents are always fresh, no need to reload like JSON
        return self.get_all_documents()

    def get_state_status_summary(self) -> Dict[str, int]:
        """Get summary of document counts per state."""
        all_docs = self.get_all_documents()
        summary = {}
        
        for doc in all_docs:
            state = doc.current_state
            summary[state] = summary.get(state, 0) + 1
        
        return summary

    def get_document_statistics(self) -> Dict[str, Any]:
        """Get statistics about plano documents."""
        all_docs = self.get_all_documents()
        
        stats = {
            "total": len(all_docs),
            "by_state": {}
        }
        
        for doc in all_docs:
            state = doc.current_state or "Sin Estado"
            stats["by_state"][state] = stats["by_state"].get(state, 0) + 1
        
        return stats

    def _resolve_file_path(self, doc_name: str) -> Optional[Path]:
        """
        Resolve the file path for a plano using the DocumentFileService.
        Filesystem is the source of truth.
        """
        return self.file_service.get_primary_file(doc_name)

    def get_document_file_extensions(self, doc_name: str) -> set:
        """
        Get the set of file extensions for a document.

        Uses document's tracked files only (no filesystem scanning):
        1. Document's file_paths field (tracked associated files)
        2. Associated DWG field

        Note: Does not check if files exist - extracts extensions from stored paths.
        This allows filtering to work even when files are on network shares.

        Args:
            doc_name: The document name

        Returns:
            Set of extensions like {'.pdf', '.dwg'}
        """
        extensions = set()

        document = self.get_document(doc_name)
        if document:
            # Check file_paths field for tracked associated files
            if document.file_paths:
                for file_path in document.file_paths:
                    if file_path:
                        path = Path(file_path)
                        ext = path.suffix.lower()
                        if ext in ['.pdf', '.dwg', '.rvt']:
                            extensions.add(ext)

            # Also check for associated DWG
            if document.associated_dwg:
                extensions.add('.dwg')

        return extensions

    def open_specific_file(self, doc_name: str, preferred_extension: str = None) -> None:
        """
        Open a specific file for a document, optionally preferring a certain type.

        Uses document's tracked files only (no filesystem scanning):
        1. Check associated_dwg for DWG preference
        2. Check file_paths for matching extension
        3. Fallback to document folder

        Args:
            doc_name: Document name
            preferred_extension: Optional extension to prefer (e.g. '.dwg', '.pdf')
        """
        try:
            # For DWG, check associated_dwg first
            if preferred_extension == '.dwg':
                associated_path = self.get_associated_dwg_path(doc_name)
                if associated_path and associated_path.exists():
                    self.file_manager.open_file_location(associated_path)
                    return

            # Build priority list based on preference
            if preferred_extension:
                priority = [preferred_extension]
                for ext in ['.pdf', '.dwg', '.rvt']:
                    if ext not in priority:
                        priority.append(ext)
            else:
                priority = ['.pdf', '.dwg', '.rvt']

            # Check document's file_paths for tracked associated files
            document = self.get_document(doc_name)
            if document and document.file_paths:
                for ext in priority:
                    for file_path_str in document.file_paths:
                        if file_path_str:
                            # Cross-platform path normalization:
                            # Convert Windows backslashes to forward slashes (works on both platforms)
                            normalized_path = file_path_str.replace('\\', '/')
                            path = Path(normalized_path)
                            if not path.is_absolute():
                                path = (self.storage_path / normalized_path).resolve()
                            if path.exists() and path.suffix.lower() == ext:
                                self.file_manager.open_file_location(path)
                                return

                    # After checking file_paths for current ext, check associated_dwg if looking for DWG
                    # This ensures DWG preference is fully exhausted before falling back to other types
                    if ext == '.dwg' and document and document.associated_dwg:
                        normalized_dwg = document.associated_dwg.replace('\\', '/')
                        dwg_path = Path(normalized_dwg)
                        if not dwg_path.is_absolute():
                            dwg_path = (self.storage_path / normalized_dwg).resolve()
                        if dwg_path.exists():
                            self.file_manager.open_file_location(dwg_path)
                            return

            # Check associated_dwg as final fallback (when no file_paths exist)
            if document and document.associated_dwg:
                # Cross-platform path normalization
                normalized_dwg = document.associated_dwg.replace('\\', '/')
                dwg_path = Path(normalized_dwg)
                if not dwg_path.is_absolute():
                    dwg_path = (self.storage_path / normalized_dwg).resolve()
                if dwg_path.exists():
                    self.file_manager.open_file_location(dwg_path)
                    return

            # Final fallback: open document folder
            self.open_document_location(doc_name)

        except Exception as e:
            print(f"Error opening file for {doc_name}: {e}")
            self.open_document_location(doc_name)

    def open_document_location(self, doc_name: str) -> None:
        """Open the folder containing the document files."""
        import subprocess
        import platform
        
        # Try to resolve a specific file to reveal
        file_path = self._resolve_file_path(doc_name)
        if file_path:
            self.file_manager.open_file_location(file_path)
            return
        
        # Fallback: open the planos folder
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

    def update_document_info(self, old_name: str, new_name: str, new_display_name: str, 
                           new_version: str, new_state: str, author: str, notes: str,
                           autor: str = "", rev_tecnica: str = "", rev_gerencia: str = "") -> str:
        """Update plano document general information. Returns success message."""
        
        document = self.get_document(old_name)
        if not document:
            raise ValueError(f"No se encontró el documento con nombre {old_name}")
        
        # Validate new state
        if new_state not in PLANO_STATES:
            raise ValueError(f"Estado '{new_state}' no válido")
        
        old_filename = None
        old_path = None
        
        # Find existing files for this document
        import glob
        sanitized_old_name = self.file_manager.sanitize_for_filename(old_name)
        file_pattern = str(self.storage_path / f"*{sanitized_old_name}*")
        matching_files = glob.glob(file_pattern)
        
        if matching_files:
            # Use the first matching file to determine extension
            old_filename = Path(matching_files[0]).name
            old_path = Path(matching_files[0])
            extension = self.file_manager.get_file_extension(old_filename)
        else:
            # No existing files found, use a default extension
            extension = "pdf"
        
        # Generate new filename based on new information (without state)
        from utils.file_manager import FileManager
        sanitized_name = FileManager.sanitize_for_filename(new_display_name)
        sanitized_version = FileManager.sanitize_for_filename(new_version)
        new_filename = f"{sanitized_name}_{sanitized_version}.{extension}"
        new_path = self.storage_path / new_filename
        
        # Check if new file already exists (only if we have a current file to rename)
        if old_path and new_path.exists() and old_path != new_path:
            raise FileExistsError(f"El archivo {new_filename} ya existe")
        
        # Rename file if needed and if old file exists
        if old_path and old_path.exists() and old_path != new_path:
            self.file_manager.rename_file(old_path, new_path)
        
        # Handle name changes by creating new document record
        if old_name != new_name:
            # Create new document with new name
            new_document = SQLiteDocument.create_new(new_name, "planos", self.db_manager, self.current_user)
            
            # Copy all entries from old document
            new_document.entries = document.entries.copy()
            new_document.rev_tecnica = document.rev_tecnica
            new_document.rev_gerencia = document.rev_gerencia
            
            # Add new entry for the correction
            new_document.add_entry(new_version, new_state, author, notes=notes)
            
            # Always update revision fields (allow clearing by passing empty string)
            new_document.autor = autor
            new_document.rev_tecnica = rev_tecnica
            new_document.rev_gerencia = rev_gerencia

            # Save new document with locking protection (metadata update)
            with self.lock_manager.database_transaction_lock(new_name):
                new_document.save_to_database()

            # Delete old document from database
            if document.db_id:
                self.db_manager.delete_document(document.db_id)

        else:
            # Just update existing document (name stays the same)
            document.add_entry(new_version, new_state, author, notes=notes)

            # Always update revision fields (allow clearing by passing empty string)
            document.autor = autor
            document.rev_tecnica = rev_tecnica
            document.rev_gerencia = rev_gerencia
            
            # Save to database with locking protection
            with self.lock_manager.database_transaction_lock(old_name):
                document.save_to_database()
        
        return "Información actualizada correctamente"

    def _upload_additional_files(self, doc_id: str, doc_display_name: str, version: str, state: str, file_paths: List[Path]) -> List[str]:
        """
        Upload additional files using file-type-aware routing.
        
        Args:
            doc_id: Document identifier 
            doc_display_name: Human-readable document name
            version: Document version
            state: New document state
            file_paths: List of file paths to upload
            
        Returns:
            List of successfully uploaded filenames
        """
        uploaded_files = []
        
        # Prepare file uploads for the router
        file_uploads = []
        for file_path in file_paths:
            document_info = {
                "name": doc_id,
                "display_name": doc_display_name, 
                "version": version,
                "state": state
            }
            file_uploads.append((file_path, document_info))
        
        # Use the file type upload router
        results = self.upload_router.route_multiple_files(
            file_uploads, 
            upload_context={"operation": "additional_files", "document_id": doc_id}
        )
        
        # Process results
        for upload_result in results["successful_uploads"]:
            final_path = Path(upload_result["destination"])
            uploaded_files.append(final_path.name)
            print(f"✅ {upload_result['message']}")
            
            # Trigger cloud sync if enabled
            if hasattr(self, 'cloud_sync') and self.cloud_sync:
                try:
                    self.cloud_sync.sync_file_upload(final_path)
                    print(f"☁️ Archivo sincronizado a la nube: {final_path.name}")
                except Exception as e:
                    print(f"⚠️ Error en sincronización de nube para {final_path.name}: {e}")
                    # Don't fail the entire operation for cloud sync issues
        
        # Report any failures
        for failure in results["failed_uploads"]:
            print(f"❌ Error uploading {Path(failure['source']).name}: {failure['error']}")
        
        # Print summary
        summary = results["summary"]
        if summary["total_files"] > 0:
            print(f"📊 Upload summary: {summary['successful']}/{summary['total_files']} files uploaded successfully")
        
        return uploaded_files

    def check_document_lock_status(self, name: str) -> Dict[str, Any]:
        """Check if a document is locked and by whom."""
        document = self.get_document(name)
        if not document or not document.db_id:
            return {"is_locked": False, "locked_by": None}
        
        return self.db_manager.check_lock_status(document.db_id)

    def acquire_document_lock(self, name: str) -> bool:
        """Acquire a lock on a document for editing."""
        document = self.get_document(name)
        if not document or not document.db_id:
            return False
        
        return self.db_manager.acquire_simple_lock(document.db_id, self.current_user)

    def release_document_lock(self, name: str) -> bool:
        """Release a lock on a document."""
        document = self.get_document(name)
        if not document or not document.db_id:
            return False
        
        return self.db_manager.release_simple_lock(document.db_id, self.current_user)

    def get_project_path(self) -> Path:
        """Get the current project path."""
        return self.project_path
    
    # Cloud sync methods (Phase 1.3)
    def is_cloud_sync_enabled(self) -> bool:
        """Check if cloud sync is available and enabled for this controller."""
        return self.cloud_sync is not None
    
    def sync_document_to_cloud(self, doc_name: str, auto_cleanup: bool = True) -> dict:
        """
        Sync ALL PDFs for a document to cloud storage.

        When a document has multiple associated PDFs (numbered copies like _S1 1.pdf, _S1 2.pdf),
        all of them are uploaded. Cleanup runs once after all uploads.

        Returns:
            dict: Sync results or message if cloud sync disabled
        """
        if not self.is_cloud_sync_enabled():
            return {"message": "Cloud sync not enabled"}

        try:
            document = self.get_document(doc_name)
            if not document:
                return {"error": f"Document {doc_name} not found"}

            # Get ALL PDF files for this document from Working folder
            working_files = self.file_service.get_working_files(doc_name)
            pdf_files = [f.path for f in working_files if f.extension == '.pdf']

            if not pdf_files:
                return {"error": f"No PDF files found for document {doc_name}"}

            print(f"[SQLitePlanosController] Found {len(pdf_files)} PDF(s) to sync for {doc_name}")
            for pdf in pdf_files:
                print(f"  - {pdf.name}")

            # Sync ALL files to cloud (cleanup runs after last file)
            result = self.cloud_sync.sync_multiple_files(
                document,
                pdf_files,
                auto_cleanup=auto_cleanup
            )
            print(f"[SQLitePlanosController] Cloud sync result for {doc_name}: {result}")

            return result

        except Exception as e:
            error_msg = f"Cloud sync failed for {doc_name}: {e}"
            print(f"[SQLitePlanosController] {error_msg}")
            return {"error": error_msg}
    
    def get_cloud_sync_status(self) -> dict:
        """Get current cloud sync configuration status."""
        if not hasattr(self, 'cloud_config'):
            return {"enabled": False, "error": "Cloud config not available"}
        
        return {
            "enabled": self.is_cloud_sync_enabled(),
            "cloud_sync_configured": self.cloud_config.is_cloud_sync_enabled(),
            "sharepoint_enabled": self.cloud_config.is_sharepoint_enabled(),
            "google_drive_enabled": self.cloud_config.is_google_drive_enabled()
        }

    def close(self):
        """Close database connections."""
        if self.db_manager:
            self.db_manager.close()

    # --- Deletion APIs (SQLite-based) ---
    def delete_documents(self, doc_names: List[str]) -> str:
        """Delete multiple plano documents and their files (SQLite-backed)."""
        if not doc_names:
            raise ValueError("No se proporcionaron documentos para eliminar")

        deleted_count = 0
        errors: List[str] = []

        for name in doc_names:
            try:
                with self.lock_manager.database_transaction_lock(name):
                    document = self.get_document(name)
                    if not document:
                        errors.append(f"Documento {name} no encontrado")
                        continue

                    # Delete physical files - use tracked file paths first (new approach)
                    files_deleted = []
                    
                    # Method 1: Use tracked file paths (for documents with tracked files)
                    if hasattr(document, 'file_paths') and document.file_paths:
                        for tracked_path in document.file_paths:
                            file_path = self.storage_path / tracked_path
                            if file_path.exists():
                                try:
                                    move_to_trash(file_path, self.project_path)
                                    files_deleted.append(tracked_path)
                                except OSError as e:
                                    errors.append(f"Error al mover archivo rastreado {tracked_path} a la papelera: {e}")

                    # Method 2: Fallback to pattern matching (for old documents)
                    if not files_deleted:
                        import glob
                        sanitized = self.file_manager.sanitize_for_filename(name)
                        pattern = str(self.storage_path / f"*{sanitized}*")
                        for match in glob.glob(pattern):
                            try:
                                move_to_trash(Path(match), self.project_path)
                                files_deleted.append(Path(match).name)
                            except OSError as e:
                                errors.append(f"Error al mover archivo {match} a la papelera: {e}")

                    # Delete from database
                    if getattr(document, 'db_id', None):
                        self.db_manager.delete_document(document.db_id)
                        deleted_count += 1
            except Exception as e:
                errors.append(f"Error al eliminar documento {name}: {e}")

        parts: List[str] = []
        if deleted_count > 0:
            parts.append(f"Se eliminaron {deleted_count} documento(s) exitosamente")
        if errors:
            parts.append("Errores encontrados:\n" + "\n".join(f"• {err}" for err in errors))
        return "\n\n".join(parts) if parts else "No se eliminó ningún documento"

    def delete_document_entries(self, entry_specs: List[Dict[str, str]]) -> str:
        """
        Delete specific version/state entries (SQLite-backed).

        SIMPLIFIED LOGIC:
        1. Always delete the database entry first
        2. Try to delete files (best effort - don't fail if files don't exist)
        """
        if not entry_specs:
            raise ValueError("No se proporcionaron entradas para eliminar")

        deleted_count = 0
        files_deleted_count = 0
        warnings: List[str] = []
        errors: List[str] = []
        docs_to_update: Dict[str, SQLiteDocument] = {}

        for spec in entry_specs:
            try:
                name = spec['doc_id']
                version = spec['version']
                state = spec['state']

                # IMPORTANT: Reuse already-modified document if we've seen it before
                # This allows deleting multiple entries from the same document in one batch
                if name in docs_to_update:
                    document = docs_to_update[name]
                else:
                    document = self.get_document(name)
                    if not document:
                        errors.append(f"Documento {name} no encontrado")
                        continue

                # Step 1: Remove entry from document (always try this first)
                removed = False
                for i, entry in enumerate(document.entries):
                    if entry.version == version and entry.state == state:
                        document.entries.pop(i)
                        removed = True
                        deleted_count += 1
                        docs_to_update[name] = document
                        break

                if not removed:
                    errors.append(f"Entrada v{version}-{state} no encontrada para documento {name}")
                    continue

                # Step 2: Try to delete files (best effort - don't fail if not found)
                files_deleted = self._try_delete_files_for_entry(name, version, state)
                files_deleted_count += len(files_deleted)

            except Exception as e:
                errors.append(f"Error al procesar {name}: {e}")

        # Persist database changes
        for name, document in docs_to_update.items():
            try:
                if not document.entries:
                    # No more entries - delete entire document
                    if getattr(document, 'db_id', None):
                        self.db_manager.delete_document(document.db_id)
                else:
                    document.save_to_database()
            except Exception as e:
                errors.append(f"Error al guardar {name}: {e}")

        # Build result message
        parts: List[str] = []
        if deleted_count > 0:
            msg = f"Se eliminaron {deleted_count} versión(es)/estado(s)"
            if files_deleted_count > 0:
                msg += f" y {files_deleted_count} archivo(s)"
            parts.append(msg)
        if errors:
            parts.append("Errores:\n" + "\n".join(f"• {err}" for err in errors))
        return "\n\n".join(parts) if parts else "No se eliminaron entradas"

    def _try_delete_files_for_entry(self, doc_name: str, version: str, state: str) -> List[str]:
        """
        Try to delete files for a specific entry.
        Best effort - returns list of deleted files.
        Also removes deleted paths from document's file_paths.
        """
        files_deleted = []

        # Get document to access and clean up file_paths
        document = self.get_document(doc_name)
        if not document:
            return files_deleted

        # Filter files that match this version and state
        version_clean = version.replace('v', '') if version.startswith('v') else version
        paths_to_remove = []

        for file_path_str in document.file_paths[:]:  # Iterate over copy
            file_path = Path(file_path_str)
            filename = file_path.name.lower()

            # Check if filename contains this version and state
            has_version = f"_{version}_" in filename or f"_v{version_clean}_" in filename or f"_{version_clean}_" in filename
            has_state = f"_{state}." in filename or f"_{state}_" in filename

            if has_version and has_state:
                try:
                    if file_path.exists():
                        move_to_trash(file_path, self.project_path)
                        files_deleted.append(file_path.name)
                        print(f"   🗑️ Moved to trash: {file_path.name}")
                    paths_to_remove.append(file_path_str)
                except OSError as e:
                    print(f"   ⚠️ Could not move {file_path.name} to trash: {e}")

        # Remove deleted paths from file_paths
        for path in paths_to_remove:
            document.remove_file_path(path)

        return files_deleted

    def get_fresh_documents(self) -> List[SQLiteDocument]:
        """Get all documents with fresh reload from database - useful for smart refresh."""
        # SQLite documents are always fresh, no need to reload like JSON
        return self.get_all_documents()
    
    # --- Preset Management Methods ---
    
    def get_preset_manager(self):
        """Get or create preset manager instance."""
        if not hasattr(self, '_preset_manager') or self._preset_manager is None:
            from utils.plano_preset_manager import PlanoPresetManager
            self._preset_manager = PlanoPresetManager(self.project_path)
        return self._preset_manager
    
    def get_available_preset_templates(self) -> Dict:
        """Get all available preset templates."""
        return self.get_preset_manager().get_available_presets()
    
    def get_project_phases(self) -> List[str]:
        """Get list of available project phases."""
        return self.get_preset_manager().PROJECT_PHASES.copy()
    
    def create_preset_planos(self, template_name: str, selected_presets: List[str] = None) -> List[str]:
        """
        Create preset planos from a template.
        
        Args:
            template_name: Name of the template to use
            selected_presets: List of specific preset names to create (if None, creates all)
            
        Returns:
            List of created plano names
        """
        preset_manager = self.get_preset_manager()
        return preset_manager.create_preset_planos(
            self.db_manager, self.current_user, template_name, selected_presets
        )
    
    def create_custom_preset_plano(self, plano_name: str, phase: str) -> bool:
        """
        Create a single custom preset plano.
        
        Args:
            plano_name: Name of the plano to create
            phase: Project phase for the plano
            
        Returns:
            True if created successfully, False if already exists
        """
        preset_manager = self.get_preset_manager()
        return preset_manager.create_custom_preset(
            self.db_manager, self.current_user, plano_name, phase
        )
    
    def get_phase_completion_status(self) -> Dict[str, Dict[str, int]]:
        """Get completion status for each project phase."""
        preset_manager = self.get_preset_manager()
        return preset_manager.get_phase_completion_status(self.db_manager, self.current_user)
    
    def get_phase_completion_summary(self) -> str:
        """Get a human-readable summary of phase completion status."""
        preset_manager = self.get_preset_manager()
        return preset_manager.get_phase_completion_summary(self.db_manager, self.current_user)
    
    def get_planos_by_phase(self, phase: str) -> List[SQLiteDocument]:
        """Get all planos for a specific project phase."""
        all_planos = self.get_all_documents()
        return [plano for plano in all_planos if getattr(plano, 'project_phase', 'Implantación') == phase]
    
    def update_plano_phase(self, plano_name: str, new_phase: str) -> bool:
        """
        Update the project phase of an existing plano.
        
        Args:
            plano_name: Name of the plano to update
            new_phase: New project phase
            
        Returns:
            True if updated successfully, False if plano not found
        """
        if new_phase not in self.get_project_phases():
            raise ValueError(f"Invalid phase '{new_phase}'. Must be one of: {', '.join(self.get_project_phases())}")
        
        document = self.get_document(plano_name)
        if not document:
            return False
        
        document.project_phase = new_phase
        document.save_to_database()
        return True

    def _ensure_proper_folder_structure(self):
        """
        Ensure the proper Working/Old/REF/Links folder structure exists.
        Creates the standard folder hierarchy for new projects.
        """
        folders_to_create = [
            # PDF folder structure
            self.storage_path / "PDF" / "Working",
            self.storage_path / "PDF" / "Old",

            # CAD folder structure
            self.storage_path / "CAD" / "Working",
            self.storage_path / "CAD" / "Working" / "REF",
            self.storage_path / "CAD" / "Old",

            # RVT folder structure
            self.storage_path / "RVT" / "Working",
            self.storage_path / "RVT" / "Old",
            self.storage_path / "RVT" / "Links"
        ]
        
        for folder in folders_to_create:
            folder.mkdir(parents=True, exist_ok=True)
            
        print(f"✅ Folder structure ensured for project: {self.project_path.name}")
    
    def _on_xref_progress(self, message: str):
        """Handle XREF processing progress updates."""
        # This will be called by the async XREF manager
        # Can be used to update status bars, logs, etc.
        print(f"🔍 XREF Progress: {message}")
        
        # Emit signal for UI updates if needed
        if hasattr(self, 'xref_progress_callback'):
            self.xref_progress_callback(message)
    
    def set_xref_progress_callback(self, callback):
        """Set callback for XREF progress updates."""
        self.xref_progress_callback = callback
    
    def get_plano_xref_status(self, plano_name: str) -> dict:
        """
        Get XREF reference status for a plano.
        
        Returns:
            Dict with reference status information
        """
        try:
            document = self.get_document(plano_name)
            if not document:
                return {'error': 'Plano not found'}
            
            # Get plano ID from database
            with self.db_manager.connection() as conn:
                cursor = conn.execute('SELECT id FROM planos WHERE name = ?', (plano_name,))
                row = cursor.fetchone()
                if not row:
                    return {'error': 'Plano not found in database'}
                
                plano_id = row[0]
            
            # Get XREF status from manager
            return self.xref_manager.get_processing_status(plano_id)
            
        except Exception as e:
            return {'error': str(e)}
    
    def get_missing_references(self, plano_name: str = None) -> list:
        """Get missing XREF references for a specific plano or all planos."""
        try:
            if plano_name:
                # Get missing references for specific plano
                with self.db_manager.connection() as conn:
                    cursor = conn.execute('SELECT id FROM planos WHERE name = ?', (plano_name,))
                    row = cursor.fetchone()
                    if not row:
                        return []
                    
                    plano_id = row[0]
                    cursor = conn.execute('SELECT xref_references FROM planos WHERE id = ?', (plano_id,))
                    row = cursor.fetchone()
                    if not row or not row[0]:
                        return []
                    
                    # Parse references and check which are missing
                    import json
                    references = json.loads(row[0])
                    missing = []
                    for ref in references:
                        # Check if reference file exists in project
                        cursor = conn.execute('SELECT COUNT(*) FROM planos WHERE name LIKE ?', (ref.replace('.dwg', ''),))
                        count = cursor.fetchone()[0]
                        if count == 0:
                            missing.append(ref)
                    return missing
            else:
                # Get all missing references in project
                # This would be implemented if needed
                return []
        except Exception as e:
            print(f"Error getting missing references: {e}")
            return []
    
    def process_plano_xrefs(self, plano_name: str, file_path):
        """
        Process XREF references for an uploaded plano file.
        
        This is called automatically during file upload for DWG files.
        """
        try:
            document = self.get_document(plano_name)
            if not document:
                print(f"Warning: Plano {plano_name} not found for XREF processing")
                return
            
            # Get plano ID
            with self.db_manager.connection() as conn:
                cursor = conn.execute('SELECT id FROM planos WHERE name = ?', (plano_name,))
                row = cursor.fetchone()
                if not row:
                    print(f"Warning: Plano {plano_name} not found in database")
                    return
                
                plano_id = row[0]
            
            # Process with async XREF manager
            result = self.xref_manager.process_plano_upload(plano_id, file_path)
            print(f"XREF processing result for {plano_name}: {result}")
            
            return result
            
        except Exception as e:
            print(f"Error processing XREFs for {plano_name}: {e}")
            return {'error': str(e)}

    def promote_file_to_last(self, doc_name: str, file_path: str) -> Tuple[bool, str]:
        """
        Promote a file currently in <type>/Working/ to <type>/Last/.
        The previous Last/ file (and its sidecar references) are archived to
        Old/<timestamp>-<stem>/. file_paths is updated to point at the new Last
        location.

        Args:
            doc_name: Document name (used to update tracked file_paths)
            file_path: Absolute or storage-relative path to a file in Working/.
        """
        try:
            document = self.get_document(doc_name)
            if not document:
                return False, f"Documento '{doc_name}' no encontrado"

            src = Path(file_path)
            if not src.is_absolute():
                src = self.storage_path / file_path

            success, message = self.upload_router.promote_to_last(src)
            if not success:
                return False, message

            # Update document.file_paths: replace the old Working entry with
            # the new Last path. Done under the same DB lock as other writes.
            file_type = self.upload_router.folder_manager.detect_file_type(src)
            if file_type is not None:
                base_folder = self.upload_router.folder_manager.get_folder_path(file_type)
                new_last = base_folder / "Last" / src.name
                src_resolved = src.resolve()
                with self.lock_manager.database_transaction_lock(doc_name):
                    new_paths = []
                    seen_old = False
                    for p in (document.file_paths or []):
                        try:
                            candidate = Path(p)
                            if not candidate.is_absolute():
                                candidate = self.storage_path / p
                            same = candidate.resolve() == src_resolved
                        except Exception:
                            same = False
                        if not seen_old and same:
                            new_paths.append(str(new_last))
                            seen_old = True
                        else:
                            new_paths.append(p)
                    if not seen_old:
                        new_paths.append(str(new_last))
                    document.file_paths = new_paths
                    document.save_to_database()
            return True, message
        except Exception as e:
            return False, f"Error promoviendo archivo: {e}"

    def replace_file_for_document(self, doc_name: str, old_file_path: str, new_file_path: Path) -> Dict[str, Any]:
        """
        Replace a specific file for a document while maintaining version/state.
        
        Args:
            doc_name: Name of the document
            old_file_path: Current file path to replace (relative to storage)
            new_file_path: New file to use as replacement
            
        Returns:
            Dict with 'success' bool and 'message' string
        """
        try:
            # Get existing document
            document = self.get_document(doc_name)
            if not document:
                return {'success': False, 'message': f"Documento '{doc_name}' no encontrado"}
            
            # Build full path for old file
            # Handle both absolute and relative paths
            old_path = Path(old_file_path)
            if old_path.is_absolute():
                old_full_path = old_path
            else:
                old_full_path = self.storage_path / old_file_path

            # Check if old file exists (but don't fail if missing - allow recovery)
            old_file_exists = old_full_path.exists()
            if not old_file_exists:
                print(f"DEBUG replace_file: Original file missing at {old_full_path}, will create at this location")

            # Verify new file exists
            if not new_file_path.exists():
                return {'success': False, 'message': f"Archivo de reemplazo no encontrado: {new_file_path}"}

            # Ensure parent directory exists (in case file was deleted and dir was cleaned up)
            old_full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Replace the file content (keep same name/path)
            try:
                with self.lock_manager.database_transaction_lock(doc_name):
                    self.file_manager.copy_file(new_file_path, old_full_path)

                    # Ensure this path is tracked in file_paths
                    document.add_file_path(str(old_full_path))
                    document.save_to_database()

                    # If this is a CAD file, process XREFs
                    if old_full_path.suffix.lower() == '.dwg':
                        self.process_plano_xrefs(doc_name, old_full_path)
                
                action = "reemplazado" if old_file_exists else "restaurado"
                return {
                    'success': True,
                    'message': f"Archivo {action} exitosamente: {old_full_path.name}"
                }
                
            except Exception as e:
                return {'success': False, 'message': f"Error reemplazando archivo: {e}"}
                
        except Exception as e:
            return {'success': False, 'message': f"Error inesperado: {e}"}

    def add_file_to_document(self, doc_name: str, new_file_path: Path, file_type: str = None,
                               dwg_name: str = None) -> Dict[str, Any]:
        """
        Add a new file to an existing document while maintaining version/state.

        Args:
            doc_name: Name of the document
            new_file_path: Path to the new file to add
            file_type: Optional file type hint (PDF, DWG, RVT, etc.)
            dwg_name: Optional custom name for DWG files (default: document name)

        Returns:
            Dict with 'success' bool, 'message' string, and 'new_path' if successful
        """
        try:
            # Get existing document
            document = self.get_document(doc_name)
            if not document:
                return {'success': False, 'message': f"Documento '{doc_name}' no encontrado"}

            # Verify new file exists
            if not new_file_path.exists():
                return {'success': False, 'message': f"Archivo no encontrado: {new_file_path}"}

            # Validate document has version/state before routing
            if not document.current_version or not document.current_state:
                return {'success': False, 'message': f"El documento '{doc_name}' no tiene versión/estado. Registre una versión primero."}

            # Get file extension for proper routing
            file_extension = self.file_manager.get_file_extension(new_file_path.name).lower()

            # Use upload router to determine proper destination and generate filename
            try:
                # For DWG files, use custom dwg_name if provided
                file_name_for_routing = dwg_name if (file_extension == '.dwg' and dwg_name) else document.name

                # Route the file to appropriate folder
                document_info = {
                    'name': file_name_for_routing,
                    'version': document.current_version,
                    'state': document.current_state,
                    'author': document.autor
                }
                print(f"DEBUG add_file_to_document: routing '{new_file_path.name}' for doc='{doc_name}', "
                      f"version='{document.current_version}', state='{document.current_state}', "
                      f"file_name_for_routing='{file_name_for_routing}'")
                # Use 'add_file' operation to indicate this is adding alongside existing files
                # (don't archive existing PDFs, support multiple PDFs with numbering)
                upload_context = {'operation': 'add_file'}
                success, destination, message = self.upload_router.route_file_upload(
                    new_file_path,
                    document_info,
                    upload_context
                )
                
                if not success:
                    return {'success': False, 'message': f"Error en routing: {message}"}

                # Track the file in document's file_paths
                document.add_file_path(str(destination))
                document.save_to_database()

                # If this is a CAD file, process XREFs
                if file_extension == '.dwg':
                    self.process_plano_xrefs(doc_name, destination)

                relative_path = str(destination.relative_to(self.storage_path))

                # If document is already in a cloud-sync state and we added a PDF,
                # upload ALL files (including the new one) and clean up old ones
                if file_extension == '.pdf' and self.is_cloud_sync_enabled():
                    current_state = document.current_state
                    if current_state in ['S2', 'S3', 'S3A', 'A']:
                        print(f"[CloudSync] Document in {current_state} state - syncing all PDFs to cloud")
                        sync_result = self.sync_document_to_cloud(doc_name, auto_cleanup=True)
                        if sync_result.get('uploaded_to'):
                            print(f"[CloudSync] Sync successful: {sync_result.get('uploaded_files', [])}")

                return {
                    'success': True,
                    'message': f"Archivo agregado exitosamente: {destination.name}",
                    'new_path': relative_path
                }

            except Exception as e:
                return {'success': False, 'message': f"Error procesando archivo: {e}"}
                
        except Exception as e:
            return {'success': False, 'message': f"Error inesperado: {e}"}

    def get_document_files_info(self, doc_name: str, only_working: bool = True) -> Dict[str, Any]:
        """
        Get detailed information about files associated with a document.
        Uses filesystem as source of truth via DocumentFileService.

        Args:
            doc_name: Name of the document
            only_working: If True, only return files from Working folders (default: True)

        Returns:
            Dict with document info and list of file details
        """
        try:
            # Get existing document for metadata
            document = self.get_document(doc_name)
            if not document:
                return {'success': False, 'message': f"Documento '{doc_name}' no encontrado"}

            # Get files from filesystem (source of truth)
            if only_working:
                # Only current Working files (for file management panel)
                doc_files = self.file_service.get_working_files(doc_name)
            else:
                # All files including Old (for history view)
                doc_files = self.file_service.get_document_files(doc_name)

            file_details = []
            existing_paths = set()
            for doc_file in doc_files:
                file_info = {
                    'path': str(doc_file.path),  # Full absolute path for reliable file operations
                    'name': doc_file.name,
                    'extension': doc_file.extension,
                    'exists': True,  # Already confirmed by filesystem scan
                    'size': doc_file.size,
                    'modified': doc_file.modified_time.timestamp(),
                    'type': self._get_file_type_display(doc_file.extension),
                    'is_working': doc_file.is_in_working
                }
                file_details.append(file_info)
                existing_paths.add(str(doc_file.path))

            # Include associated DWG in file list (if not already present)
            if document.associated_dwg:
                dwg_path = Path(document.associated_dwg)
                # Handle relative or absolute paths
                if not dwg_path.is_absolute():
                    dwg_path = self.storage_path / "CAD" / "Working" / dwg_path.name

                if dwg_path.exists() and str(dwg_path) not in existing_paths:
                    try:
                        stat = dwg_path.stat()
                        from datetime import datetime
                        file_info = {
                            'path': str(dwg_path),
                            'name': dwg_path.name,
                            'extension': dwg_path.suffix.lower(),
                            'exists': True,
                            'size': stat.st_size,
                            'modified': stat.st_mtime,
                            'type': self._get_file_type_display(dwg_path.suffix.lower()),
                            'is_working': True,
                            'is_associated': True  # Mark as associated DWG
                        }
                        file_details.append(file_info)
                    except Exception as e:
                        print(f"Error adding associated DWG to file list: {e}")

            return {
                'success': True,
                'document': {
                    'name': document.name,
                    'version': document.current_version,
                    'state': document.current_state,
                    'creation_date': document.creation_date
                },
                'files': file_details
            }

        except Exception as e:
            return {'success': False, 'message': f"Error obteniendo información: {e}"}

    def _get_file_type_display(self, extension: str) -> str:
        """Get display name for file type based on extension."""
        type_map = {
            '.pdf': 'PDF',
            '.dwg': 'AutoCAD DWG',
            '.dxf': 'AutoCAD DXF', 
            '.rvt': 'Revit Model',
            '.rfa': 'Revit Family',
            '.rte': 'Revit Template',
            '.ifc': 'IFC Model',
            '.dwf': 'Design Web Format',
            '.dgn': 'MicroStation'
        }
        return type_map.get(extension.lower(), 'Archivo')

    def _get_timestamp(self) -> str:
        """Get current timestamp in standard format."""
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def populate_missing_file_paths(self, doc_name: str = None) -> Dict[str, Any]:
        """
        Report on files found in filesystem for documents.
        NOTE: With filesystem as source of truth, this no longer writes to database.
        It just scans and reports what files exist.

        Args:
            doc_name: Optional specific document name. If None, processes all documents.

        Returns:
            Dict with success status and file counts
        """
        try:
            if doc_name:
                # Single document
                files = self.file_service.get_document_files(doc_name)
                return {
                    'success': True,
                    'message': f"Found {len(files)} files for '{doc_name}'",
                    'processed_count': 1,
                    'found_files_count': len(files)
                }
            else:
                # All documents - use service's batch method
                all_docs = self.file_service.get_all_documents_with_files()
                total_files = sum(len(exts) for exts in all_docs.values())
                return {
                    'success': True,
                    'message': f"Found {total_files} files across {len(all_docs)} documents",
                    'processed_count': len(all_docs),
                    'found_files_count': total_files
                }

        except Exception as e:
            error_msg = f"Error scanning files: {e}"
            print(error_msg)
            return {'success': False, 'message': error_msg}

    def get_available_dwgs(self) -> List[str]:
        """
        Get list of DWG files available in CAD/Working folder.

        Returns:
            List of absolute paths to DWG files
        """
        try:
            cad_working = self.storage_path / "CAD" / "Working"
            if not cad_working.exists():
                return []

            dwg_files = []
            for dwg_path in cad_working.glob("*.dwg"):
                if dwg_path.is_file():
                    dwg_files.append(str(dwg_path))

            # Sort alphabetically by filename
            dwg_files.sort(key=lambda p: Path(p).name.lower())
            return dwg_files

        except Exception as e:
            print(f"Error getting available DWGs: {e}")
            return []

    def set_associated_dwg(self, doc_name: str, dwg_path: str) -> Tuple[bool, str]:
        """
        Set the associated DWG file for a document.

        Args:
            doc_name: Name of the document
            dwg_path: Path to the DWG file (can be absolute or relative), or empty to clear

        Returns:
            Tuple of (success, message)
        """
        try:
            # Get the document
            document = self.get_document(doc_name)
            if not document:
                return False, f"Documento '{doc_name}' no encontrado"

            # Check if trying to set a new DWG when one already exists
            current_dwg = getattr(document, 'associated_dwg', '') or ''
            if dwg_path and current_dwg:
                # Entry already has a DWG - must clear it first
                current_name = Path(current_dwg).name
                return False, f"Este documento ya tiene un DWG asociado ({current_name}). Debe quitar la asociación actual antes de asociar otro."

            # Set the associated DWG
            document.associated_dwg = dwg_path

            # Save to database
            document.save_to_database()

            if dwg_path:
                dwg_name = Path(dwg_path).name
                return True, f"DWG '{dwg_name}' asociado correctamente"
            else:
                return True, "Asociación de DWG eliminada"

        except Exception as e:
            error_msg = f"Error setting associated DWG: {e}"
            print(error_msg)
            return False, error_msg

    def get_associated_dwg_path(self, doc_name: str) -> Optional[Path]:
        """
        Get the full path to the associated DWG file for a document.

        Args:
            doc_name: Name of the document

        Returns:
            Path to DWG file if found, None otherwise
        """
        try:
            document = self.get_document(doc_name)
            if not document or not document.associated_dwg:
                return None

            # Cross-platform path normalization
            normalized_dwg = document.associated_dwg.replace('\\', '/')
            dwg_path = Path(normalized_dwg)

            # If absolute path exists, return it
            if dwg_path.is_absolute() and dwg_path.exists():
                return dwg_path

            # Try relative to CAD/Working
            cad_working = self.storage_path / "CAD" / "Working"
            potential_path = cad_working / dwg_path.name
            if potential_path.exists():
                return potential_path

            # Try as stored (might be relative path)
            relative_path = self.storage_path / normalized_dwg
            if relative_path.exists():
                return relative_path

            return None

        except Exception as e:
            print(f"Error getting associated DWG path: {e}")
            return None


# Compatibility alias - allows existing code to import PlanosController and get SQLite version
PlanosController = SQLitePlanosController