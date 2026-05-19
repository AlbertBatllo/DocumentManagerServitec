"""
SQLite-backed Licitacion Controller
Replaces JSON-based LicitacionController with SQLite operations while maintaining same API.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from models.sqlite_document import SQLiteDocument
from models.licitacion_document import (
    LOTES_ESTANDAR,
    LICITACION_STAGES,
    STAGE_DISPLAY_NAMES,
    PRESUPUESTO_TYPES,
    PRESUPUESTO_STATUSES
)
from utils.project_database_manager import ensure_project_database
from utils.file_manager import FileManager
from utils.project_utils import ProjectUtils
from utils.lock_manager import get_project_lock_manager
from config.settings import StatusConfig, UserConfig
from utils.trash import move_to_trash


class SQLiteLicitacionDocument(SQLiteDocument):
    """
    Extended SQLite document for licitaciones with additional metadata.
    Stores licitacion-specific fields in the notes or uses a simple JSON approach.
    """
    
    def __init__(self, **data):
        super().__init__(**data)
        self._licitacion_metadata = {}
        self._original_autor = ""  # Store the actual author separately
    
    @property
    def lote(self) -> str:
        return self._licitacion_metadata.get('lote', '')
    
    @lote.setter
    def lote(self, value: str):
        self._licitacion_metadata['lote'] = value
    
    @property
    def company(self) -> str:
        return self._licitacion_metadata.get('company', '')
    
    @company.setter
    def company(self, value: str):
        self._licitacion_metadata['company'] = value
    
    @property
    def licitacion_document_type(self) -> str:
        return self._licitacion_metadata.get('licitacion_document_type', '')
    
    @licitacion_document_type.setter
    def licitacion_document_type(self, value: str):
        self._licitacion_metadata['licitacion_document_type'] = value
    
    @property
    def parent_licitacion_name(self) -> Optional[str]:
        return self._licitacion_metadata.get('parent_licitacion_name')
    
    @parent_licitacion_name.setter
    def parent_licitacion_name(self, value: Optional[str]):
        self._licitacion_metadata['parent_licitacion_name'] = value
    
    @property
    def importe_adicional(self) -> Optional[float]:
        return self._licitacion_metadata.get('importe_adicional')
    
    @importe_adicional.setter
    def importe_adicional(self, value: Optional[float]):
        self._licitacion_metadata['importe_adicional'] = value
    
    @property
    def valor(self) -> Optional[float]:
        """Get the valor/budget amount for presupuesto and adicional types"""
        return self._licitacion_metadata.get('valor')
    
    @valor.setter
    def valor(self, value: Optional[float]):
        """Set the valor/budget amount"""
        self._licitacion_metadata['valor'] = value
    
    @property
    def document_autor(self) -> str:
        """Get the actual document author (not the metadata)"""
        return self._original_autor
    
    @document_autor.setter
    def document_autor(self, value: str):
        """Set the actual document author"""
        self._original_autor = value
    
    @property
    def autor_display(self) -> str:
        """Get the author for display purposes"""
        return self._original_autor
    
    @property
    def autor(self) -> str:
        """Get the document autor (alias for autor_display)"""
        return self._original_autor
    
    @autor.setter
    def autor(self, value: str):
        """Set the document autor"""
        self._original_autor = value
    
    @property
    def rev_tecnica(self) -> str:
        """Get the user who moved document to S2 (Revisado por Técnico Especialista)"""
        return self._licitacion_metadata.get('rev_tecnica', '')
    
    @rev_tecnica.setter
    def rev_tecnica(self, value: str):
        """Set the user who moved document to S2"""
        self._licitacion_metadata['rev_tecnica'] = value
    
    @property
    def rev_gerencia(self) -> str:
        """Get the user who moved document to S3 (Revisado por Director Proyecto)"""
        return self._licitacion_metadata.get('rev_gerencia', '')
    
    @rev_gerencia.setter
    def rev_gerencia(self, value: str):
        """Set the user who moved document to S3"""
        self._licitacion_metadata['rev_gerencia'] = value
    
    @property
    def current_stage(self) -> str:
        """Get current stage - for licitaciones this maps from document type and state"""
        # For SQLite licitaciones, map document type to stage folder
        doc_type = self.licitacion_document_type
        stage_mapping = {
            "licitacion": "licitaciones",
            "presupuesto": "presupuestos",
            "adicional": "adicionales"
        }
        return stage_mapping.get(doc_type, "licitaciones")

    def save_to_database(self) -> None:
        """Save with licitacion metadata and author stored separately"""
        import json
        
        # Store metadata and author in the autor field as JSON with separate author field
        data_to_store = {
            'metadata': self._licitacion_metadata,
            'document_autor': self._original_autor
        }
        self.autor = json.dumps(data_to_store)
        
        super().save_to_database()
    
    @classmethod
    def load_from_database(cls, db_manager, doc_type: str, name: str, user_name: str) -> Optional['SQLiteLicitacionDocument']:
        """Load and parse licitacion metadata"""
        import json
        
        base_doc = super().load_from_database(db_manager, doc_type, name, user_name)
        if not base_doc:
            return None
        
        # Create licitacion document instance
        lic_doc = cls(
            name=base_doc.name,
            document_type=base_doc.document_type,
            entries=base_doc.entries,
            autor=base_doc.autor,
            rev_tecnica=base_doc.rev_tecnica,
            rev_gerencia=base_doc.rev_gerencia
        )
        lic_doc.db_id = base_doc.db_id
        lic_doc.db_manager = base_doc.db_manager
        lic_doc.user_name = base_doc.user_name
        
        # Parse metadata and author from autor field
        if base_doc.autor:
            try:
                data = json.loads(base_doc.autor)
                if isinstance(data, dict) and 'metadata' in data:
                    # New format with separate author
                    lic_doc._licitacion_metadata = data.get('metadata', {})
                    lic_doc._original_autor = data.get('document_autor', '')
                else:
                    # Old format - treat as metadata only
                    lic_doc._licitacion_metadata = data if isinstance(data, dict) else {}
                    lic_doc._original_autor = ''
            except (json.JSONDecodeError, TypeError):
                # If it's not JSON, treat as regular autor field
                lic_doc._licitacion_metadata = {}
                lic_doc._original_autor = base_doc.autor
        
        # Format entries for dashboard compatibility
        formatted_entries = lic_doc._format_entries_for_dashboard()
        if formatted_entries:
            lic_doc.__dict__['entries'] = formatted_entries
        
        return lic_doc
    
    @classmethod
    def load_all_from_database(cls, db_manager, doc_type: str, user_name: str) -> List['SQLiteLicitacionDocument']:
        """Load all licitacion documents"""
        base_docs = super().load_all_from_database(db_manager, doc_type, user_name)
        licitacion_docs = []
        
        for base_doc in base_docs:
            lic_doc = cls.load_from_database(db_manager, doc_type, base_doc.name, user_name)
            if lic_doc:
                licitacion_docs.append(lic_doc)
        
        return licitacion_docs
    
    def get_status_display_name(self) -> str:
        """Get human-readable status name"""
        from models.licitacion_document import STATUS_DISPLAY_NAMES
        return STATUS_DISPLAY_NAMES.get(self.current_state, self.current_state)
    
    def get_type_display_name(self) -> str:
        """Get human-readable type name"""
        from models.licitacion_document import TYPE_DISPLAY_NAMES
        return TYPE_DISPLAY_NAMES.get(self.licitacion_document_type, self.licitacion_document_type)
    
    @property
    def current_status(self) -> str:
        """Alias for current_state to maintain compatibility with LicitacionDocument"""
        return self.current_state
    
    @property  
    def current_stage(self) -> str:
        """Get current stage from document type"""
        if self.licitacion_document_type == "adicional":
            return "adicionales"
        elif self.licitacion_document_type in ["presupuesto", "licitacion"]:
            return "presupuestos"
        else:
            return "mediciones"
    
    @property
    def current_version(self) -> str:
        """Get current version"""
        return super().current_version
    
    def _format_entries_for_dashboard(self):
        """Convert SQLite document entries to expected format for history display"""
        from datetime import datetime
        
        # Convert SQLite entries to the format expected by the dashboard
        formatted_entries = []
        
        # Access the base class entries directly from the __dict__
        base_entries = self.__dict__.get('entries', [])
        
        if base_entries:
            for entry in base_entries:
                # Create entry object with expected attributes for both dashboard and base class
                state_value = getattr(entry, 'state', self.current_state)
                formatted_entry = type('Entry', (), {
                    'version': getattr(entry, 'version', '1.0'),
                    'timestamp': getattr(entry, 'timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    'state': state_value,  # Keep 'state' for base class compatibility
                    'stage': self.current_stage,  # For dashboard
                    'status': state_value,  # For dashboard (alias of state)
                    'document_type': self.licitacion_document_type,  # For dashboard
                    'notes': getattr(entry, 'notes', ''),
                    'author': getattr(entry, 'author', '')
                })()
                formatted_entries.append(formatted_entry)
        
        return formatted_entries
    


class SQLiteLicitacionController:
    """
    SQLite-backed licitacion controller.
    
    Provides the same API as LicitacionController but uses SQLite instead of JSON.
    """
    
    def __init__(self, project_path: Path = None):
        self.project_path = project_path if project_path else Path.cwd()
        
        # Set up storage paths for each stage
        self.base_path = self.project_path / "03_Presupuestos"
        self.stage_paths = {
            "licitaciones": self.base_path / "licitaciones",
            "presupuestos": self.base_path / "presupuestos", 
            "adicionales": self.base_path / "adicionales"
        }
        
        # Ensure all directories exist
        for stage_path in self.stage_paths.values():
            ProjectUtils.ensure_directory_exists(stage_path)
        
        # Initialize SQLite database (replaces JSON manifest)
        self.db_manager = ensure_project_database(self.project_path)
        
        # Initialize other components
        self.file_manager = FileManager()
        
        # Get current user name for database operations
        self.user_config = UserConfig()
        self.current_user = self.user_config.get_user_name() or "Unknown User"
        
        # Initialize lock manager for safe concurrent operations
        self.lock_manager = get_project_lock_manager(self.project_path)

    def add_new_document(self, name: str, lote: str, company: str, 
                        document_type: str, status: str, version: str, file_paths: Union[Path, List[Path]], author: str, 
                        notes: str = "", valor: Optional[float] = None,
                        parent_licitacion_name: Optional[str] = None,
                        parent_presupuesto_id: Optional[str] = None,
                        importe_adicional: Optional[float] = None,
                        # Legacy parameter for backward compatibility
                        stage: str = None) -> str:
        """Add a new licitacion document. Returns success message."""
        
        # Handle legacy stage parameter
        if stage and not document_type:
            document_type = "adicional" if stage == "adicionales" else "licitacion"
        
        # Validate inputs
        if lote not in LOTES_ESTANDAR:
            raise ValueError(f"Lote '{lote}' no está en la lista estándar")
        
        if document_type not in PRESUPUESTO_TYPES:
            raise ValueError(f"Document type '{document_type}' no válido")
        
        if status not in PRESUPUESTO_STATUSES:
            raise ValueError(f"Status '{status}' no válido")
        
        # Validate valor for presupuesto and adicional types
        if document_type in ["presupuesto", "adicional"]:
            if valor is None or valor <= 0:
                raise ValueError(f"El campo Valor es obligatorio y debe ser mayor que 0 para documentos de tipo {document_type}")
        
        # Check if document already exists
        if self.document_exists(name):
            raise ValueError(f"Ya existe un documento con nombre '{name}'")
        
        # Validate author before document creation
        if not author or not author.strip():
            raise ValueError("Author cannot be empty when creating documents")
        
        # Create SQLite licitacion document
        document = SQLiteLicitacionDocument.create_new(name, "licitaciones", self.db_manager, self.current_user)
        document.lote = lote
        document.company = company
        document.licitacion_document_type = document_type
        document.autor = author.strip()  # Set the document autor (original uploader)
        
        # Set valor for presupuesto and adicional types
        if document_type in ["presupuesto", "adicional"] and valor is not None:
            document.valor = valor
        
        # Set parent and importe for adicionales
        if document_type == "adicional":
            # Use parent_presupuesto_id if provided, otherwise fall back to parent_licitacion_name
            if parent_presupuesto_id:
                document.parent_licitacion_name = parent_presupuesto_id
            elif parent_licitacion_name:
                document.parent_licitacion_name = parent_licitacion_name
            if importe_adicional is not None:
                document.importe_adicional = importe_adicional
        
        # Convert single file to list for uniform processing
        if isinstance(file_paths, Path):
            file_paths = [file_paths]
        
        # Add initial entry
        document.add_entry(version, status, author, notes=notes)
        
        # Map document_type to stage folder
        stage_mapping = {
            "licitacion": "licitaciones",
            "presupuesto": "presupuestos",
            "adicional": "adicionales"
        }
        
        stage_folder = stage_mapping.get(document_type, "presupuestos")
        destination_dir = self.stage_paths[stage_folder]
        
        # Process all files with numbered naming
        messages = []
        lote_number = lote[:2]
        sanitized_company = self.file_manager.sanitize_for_filename(company)
        sanitized_name = self.file_manager.sanitize_for_filename(name)
        
        for file_index, file_path in enumerate(file_paths, 1):
            # Generate filename with proper extension
            file_extension = self.file_manager.get_file_extension(file_path.name)
            
            # Create a cleaner filename with smart redundancy detection
            clean_name = self.file_manager._clean_redundant_patterns(sanitized_name)
            base_filename = f"{clean_name}_{version}.{file_extension}"
            
            # Start with base filename (no numbering for single files)
            filename = base_filename
            destination = destination_dir / filename
            
            # Check if file already exists and generate numbered filename if needed
            if destination.exists():
                file_number = self.file_manager.get_next_file_number(destination_dir, filename)
                filename = self.file_manager.generate_numbered_filename(filename, file_number)
                destination = destination_dir / filename
            
            # Special handling: For multiple files of same extension, apply index-based numbering
            elif file_index > 1:
                # Only apply index numbering if we have multiple files with same extension
                same_extension_count = sum(1 for fp in file_paths 
                                         if self.file_manager.get_file_extension(fp.name) == file_extension)
                if same_extension_count > 1:
                    filename = self.file_manager.generate_numbered_filename(base_filename, file_index)
                    destination = destination_dir / filename
            
            # Copy file to destination (no locking needed for new file creation)
            self.file_manager.copy_file(file_path, destination)
            messages.append(f"✓ Archivo creado: {filename}")
        
        # Save document to database with locking protection (metadata update)
        with self.lock_manager.database_transaction_lock(name):
            document.save_to_database()
        
        # If created directly as approved presupuesto (state A), auto-create certificacion
        certificacion_created = False
        try:
            if (document_type == "presupuesto" and status == "A" and valor and valor > 0):
                from controllers.certificacion_controller import CertificacionController
                cert_path = self.project_path / "04_Certificaciones"
                cert_controller = CertificacionController(str(cert_path), self.project_path)
                certificacion_created = bool(cert_controller.create_from_licitacion(name, valor))
        except Exception as e:
            # Log but do not block creation flow
            print(f"WARNING: Failed to auto-create certificacion on creation for {name}: {e}")
        
        # Build final message
        message_parts = [f"✓ Documento '{name}' creado exitosamente"] + messages
        if certificacion_created:
            message_parts.append("✓ Certificación creada automáticamente (versión 0)")
        return '\n'.join(message_parts)

    def get_all_documents(self) -> List[SQLiteLicitacionDocument]:
        """Get all licitacion documents from SQLite database."""
        return SQLiteLicitacionDocument.load_all_from_database(
            self.db_manager, "licitaciones", self.current_user
        )

    def get_document(self, name: str) -> Optional[SQLiteLicitacionDocument]:
        """Get a specific document by name."""
        return SQLiteLicitacionDocument.load_from_database(
            self.db_manager, "licitaciones", name, self.current_user
        )

    def document_exists(self, name: str) -> bool:
        """Check if a document exists."""
        return self.get_document(name) is not None

    def get_documents_by_lote(self, lote: str) -> List[SQLiteLicitacionDocument]:
        """Get all documents for a specific lote."""
        all_docs = self.get_all_documents()
        return [doc for doc in all_docs if doc.lote == lote]

    def get_documents_by_company(self, company: str) -> List[SQLiteLicitacionDocument]:
        """Get all documents for a specific company."""
        all_docs = self.get_all_documents()
        return [doc for doc in all_docs if doc.company == company]

    def get_documents_by_type(self, document_type: str) -> List[SQLiteLicitacionDocument]:
        """Get all documents of a specific type."""
        all_docs = self.get_all_documents()
        return [doc for doc in all_docs if doc.licitacion_document_type == document_type]

    def get_accepted_presupuestos_by_lote(self, lote: str) -> List[SQLiteLicitacionDocument]:
        """Get all accepted presupuestos (status A) for a specific lote"""
        all_docs = self.get_documents_by_lote(lote)
        accepted_presupuestos = []
        
        for doc in all_docs:
            # Include presupuesto and licitacion types that are approved (status A)
            if (doc.licitacion_document_type in ["presupuesto", "licitacion"] and 
                doc.current_state == "A"):
                accepted_presupuestos.append(doc)
        
        return accepted_presupuestos

    def get_adicionales_for_parent(self, parent_name: str) -> List[SQLiteLicitacionDocument]:
        """Get all adicionales for a specific parent licitacion."""
        all_docs = self.get_all_documents()
        return [doc for doc in all_docs if 
                doc.licitacion_document_type == "adicional" and 
                doc.parent_licitacion_name == parent_name]

    def update_document_status(self, name: str, new_status: str, author: str, notes: str = "",
                               presupuesto_contratado: Optional[float] = None,
                               parent_licitacion_name: Optional[str] = None,
                               importe_adicional: Optional[float] = None,
                               create_certificacion: bool = True,
                               file_paths: Optional[List[Path]] = None) -> str:
        """Update document status with optional file uploads. Returns success message."""
        document = self.get_document(name)
        if not document:
            raise ValueError(f"No se encontró el documento con nombre '{name}'")
        
        # Auto-assign reviewers based on state transitions with validation
        if not author or not author.strip():
            raise ValueError("Author cannot be empty for status transitions")
        
        # Atomic assignment with race condition protection and database locking
        with self.lock_manager.database_transaction_lock(name):
            # Re-fetch document to ensure latest state before assignment
            document = self.get_document(name)
            if not document:
                raise ValueError(f"No se encontró el documento con nombre '{name}'")
            
            if new_status == "S2" and not document.rev_tecnica:
                # S2: "Revisado por Técnico Especialista" - assign Rev. Téc.
                document.rev_tecnica = author.strip()
            elif new_status == "S3" and not document.rev_gerencia:
                # S3: "Revisado por Director Proyecto" - assign Rev. Ger.
                document.rev_gerencia = author.strip()
            
            # Add new entry with updated status
            current_version = document.current_version or "1.0"
            document.add_entry(current_version, new_status, author, notes=notes)
        
        # If approving presupuesto type, store presupuesto_contratado
        if new_status == "A" and document.licitacion_document_type == "presupuesto" and presupuesto_contratado is not None:
            document._licitacion_metadata['presupuesto_contratado'] = presupuesto_contratado
        
        # If this is an adicional being approved, store parent_licitacion_name and importe_adicional
        if new_status == "A" and document.licitacion_document_type == "adicional":
            if parent_licitacion_name is not None:
                document.parent_licitacion_name = parent_licitacion_name
            if importe_adicional is not None:
                document.importe_adicional = importe_adicional
        
        # Save to database with locking protection (metadata update)
        with self.lock_manager.database_transaction_lock(name):
            document.save_to_database()
        
        # If approving presupuesto inicial and create_certificacion is True, create Certificacion automatically
        certificacion_created = False
        if new_status == "A" and document.licitacion_document_type == "presupuesto" and create_certificacion:
            try:
                # Use valor from the document, or presupuesto_contratado as override
                valor_to_use = presupuesto_contratado if presupuesto_contratado else document.valor
                print(f"DEBUG: Certificacion creation attempt for {name}")
                print(f"DEBUG: presupuesto_contratado={presupuesto_contratado}, document.valor={document.valor}")
                print(f"DEBUG: valor_to_use={valor_to_use}")
                
                if not valor_to_use or valor_to_use <= 0:
                    print(f"Warning: No valid valor found for presupuesto {name} (valor={valor_to_use}), cannot create certificacion")
                else:
                    from controllers.certificacion_controller import CertificacionController
                    cert_path = self.project_path / "04_Certificaciones"
                    cert_controller = CertificacionController(str(cert_path), self.project_path)
                    
                    print(f"DEBUG: Creating certificacion with valor={valor_to_use}")
                    creation_result = cert_controller.create_from_licitacion(name, valor_to_use)
                    print(f"DEBUG: Certificacion creation result: {creation_result}")
                    
                    if creation_result:
                        certificacion_created = True
                        print(f"SUCCESS: Certificacion created successfully for presupuesto {name}")
                    else:
                        print(f"WARNING: Certificacion creation returned False for presupuesto {name}")
            except Exception as e:
                print(f"ERROR: Failed to create certificación automática for {name}: {e}")
                import traceback
                traceback.print_exc()
        
        # Handle file operations based on whether files are being uploaded
        uploaded_files = []
        renamed_files = []
        
        if file_paths:
            # Scenario 1: Files uploaded - create new files with new state
            try:
                uploaded_files = self._upload_additional_files(name, document.name, 
                                                             document.current_version, new_status, file_paths)
            except Exception as e:
                # If file upload fails, log warning but don't fail the state change
                print(f"Advertencia: Error al subir archivos adicionales: {e}")
        else:
            # Scenario 2: No files uploaded - move existing files to correct stage directory
            print(f"🔄 No new files uploaded, checking if existing files need state-based relocation...")
            try:
                # Find existing files for this document across all stage directories
                files_to_move = self._find_document_files(document)
                
                if files_to_move:
                    print(f"   Found {len(files_to_move)} existing files to check...")
                    
                    # Determine target directory based on new state
                    target_stage = self._get_stage_from_status(new_status)
                    target_dir = self.stage_paths.get(target_stage)
                    
                    if not target_dir:
                        print(f"   ⚠️  No target directory found for state {new_status}")
                    else:
                        print(f"   Target stage: {target_stage} → {target_dir}")
                        
                        for file_path in files_to_move:
                            current_dir = file_path.parent
                            
                            # Check if file is already in the correct directory
                            if current_dir == target_dir:
                                print(f"   ✅ File already in correct location: {file_path.name}")
                                renamed_files.append(file_path.name)
                                continue
                            
                            # Move file to target directory
                            target_path = target_dir / file_path.name
                            
                            # Check if target already exists
                            if target_path.exists():
                                print(f"   ⚠️  Target already exists: {target_path.name}")
                                continue
                            
                            try:
                                # Move the file
                                self.file_manager.move_file(file_path, target_path)
                                print(f"   ✅ Moved: {file_path.name} → {target_stage}/")
                                renamed_files.append(file_path.name)
                            except Exception as move_error:
                                print(f"   ❌ Move failed: {move_error}")
                else:
                    print(f"   No existing files found for document {name}")
                    
            except Exception as e:
                print(f"Advertencia: Error al mover archivos existentes: {e}")
                import traceback
                traceback.print_exc()
        
        from models.licitacion_document import STATUS_DISPLAY_NAMES
        status_display = STATUS_DISPLAY_NAMES.get(new_status, new_status)
        result = f"✓ Estado actualizado a {status_display}"
        
        if certificacion_created:
            result += "\n✓ Certificación creada automáticamente (versión 0)"
        
        if uploaded_files:
            result += f"\n✓ {len(uploaded_files)} archivo(s) adicional(es) subido(s)"
        
        if renamed_files:
            result += f"\n✓ {len(renamed_files)} archivo(s) actualizado(s) para estado {new_status}"
        
        return result

    def _upload_additional_files(self, doc_id: str, doc_name: str, version: str, 
                               state: str, file_paths: List[Path]) -> List[str]:
        """Upload additional files related to state change. Returns list of uploaded filenames."""
        uploaded_files = []
        
        for file_path in file_paths:
            if not file_path.exists():
                print(f"Advertencia: Archivo no encontrado: {file_path}")
                continue
                
            # Generate filename following standard pattern: {doc_name}_v{version}.{ext}
            # Note: For licitaciones, we don't include state in filename (unlike planos)
            extension = self.file_manager.get_file_extension(file_path.name)
            
            # Build simple filename without state (licitacion convention)
            clean_name = self.file_manager._clean_redundant_patterns(doc_name)
            if not version.startswith('v'):
                version = f'v{version}'
            base_filename = f"{clean_name}_{version}.{extension}"
            
            # Determine destination based on status
            target_stage = self._get_stage_from_status(state)
            current_stage_path = self.stage_paths.get(target_stage)
            if not current_stage_path:
                current_stage_path = self.stage_paths["presupuestos"]  # fallback
            
            destination = current_stage_path / base_filename
            
            # If file exists, add counter to make it unique
            counter = 1
            while destination.exists():
                # Insert counter before extension: Document_v1.2_S2_1.pdf
                name_without_ext = base_filename.rsplit('.', 1)[0]
                ext_with_dot = f".{extension}"
                numbered_filename = f"{name_without_ext}_{counter}{ext_with_dot}"
                destination = current_stage_path / numbered_filename
                base_filename = numbered_filename
                counter += 1
            
            try:
                # Copy file to destination
                self.file_manager.copy_file(file_path, destination)
                uploaded_files.append(base_filename)
                        
            except Exception as e:
                print(f"Error al subir archivo {file_path.name}: {e}")
                continue
        
        return uploaded_files

    def _find_document_files(self, document) -> List[Path]:
        """Find all existing files for a document across all stage directories."""
        files_found = []
        
        # Search in all stage directories for files belonging to this document
        for stage_name, stage_dir in self.stage_paths.items():
            if not stage_dir.exists():
                continue
            
            # Try multiple patterns to find files
            patterns_to_try = [
                f"{document.name}_*.pdf",
                f"{document.name}_*.xlsx", 
                f"{document.name}_*.xls",
                f"{document.name}_*.dwg",
                f"{document.name}_*.rvt"
            ]
            
            # Also try with lote/company patterns for backward compatibility
            if document.lote and document.company:
                lote_number = document.lote[:2] if document.lote else "00"
                sanitized_company = self.file_manager.sanitize_for_filename(document.company)
                legacy_patterns = [
                    f"{document.name}_{lote_number}_{sanitized_company}_*.pdf",
                    f"{document.name}_{lote_number}_{sanitized_company}_*.xlsx",
                    f"{document.name}_{lote_number}_{sanitized_company}_*.xls"
                ]
                patterns_to_try.extend(legacy_patterns)
            
            # Search with each pattern
            for pattern in patterns_to_try:
                matching_files = list(stage_dir.glob(pattern))
                for file_path in matching_files:
                    if file_path not in files_found and file_path.is_file():
                        files_found.append(file_path)
        
        return files_found

    def _get_stage_from_status(self, status: str) -> str:
        """
        Map document status to stage directory.
        
        For licitaciones, the stage directories represent workflow stages,
        but files can be in different stages based on their current status.
        """
        # For most statuses, files stay in the same stage directory they started in
        # This is because status changes (S1→S2→S3→A) don't necessarily mean stage changes
        
        # However, some status changes might require stage movement:
        # - If moving from draft to formal submission
        # - If moving from presupuesto to accepted (different workflow)
        
        # For now, we'll use a simple mapping based on document type and status
        if status == "A":  # Approved - might stay in presupuestos or move to accepted area
            return "presupuestos"  # Keep in presupuestos for now
        elif status in ["S0", "S1", "S2", "S3"]:  # Review statuses
            return "presupuestos"  # Most review happens in presupuestos stage
        elif status == "B":  # Blocked/Rejected
            return "licitaciones"  # Move back to licitaciones for revision
        elif status == "D":  # Draft
            return "licitaciones"  # Drafts start in licitaciones
        else:
            return "presupuestos"  # Default to presupuestos stage

    def get_licitacion_statistics(self) -> Dict[str, Any]:
        """Get statistics about licitacion documents."""
        all_docs = self.get_all_documents()
        
        stats = {
            "total": len(all_docs),
            "by_lote": {},
            "by_company": {},
            "by_type": {},
            "by_status": {}
        }
        
        for doc in all_docs:
            # Count by lote
            lote = doc.lote or "Sin Lote"
            stats["by_lote"][lote] = stats["by_lote"].get(lote, 0) + 1
            
            # Count by company
            company = doc.company or "Sin Empresa"
            stats["by_company"][company] = stats["by_company"].get(company, 0) + 1
            
            # Count by type
            doc_type = doc.licitacion_document_type or "Sin Tipo"
            stats["by_type"][doc_type] = stats["by_type"].get(doc_type, 0) + 1
            
            # Count by status
            status = doc.current_state or "Sin Estado"
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        
        return stats

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

    def get_document_file_path(self, doc_id: str) -> Optional[Path]:
        """Get the current file path for a document"""
        document = self.get_document(doc_id)
        if not document:
            return None
        
        current_stage = document.current_stage
        current_version = document.current_version
        stage_dir = self.stage_paths.get(current_stage)
        
        if not stage_dir:
            return None
        
        lote_number = document.lote[:2] if document.lote else "00"
        sanitized_company = self.file_manager.sanitize_for_filename(document.company) if document.company else "unknown"
        
        # Build possible version variants (with and without leading 'v')
        version_variants = []
        if current_version:
            version_variants.append(current_version)
            # Add variant without leading 'v'
            if current_version.startswith('v'):
                version_variants.append(current_version[1:])
            else:
                version_variants.append(f"v{current_version}")
        else:
            version_variants.append("1.0")
            version_variants.append("v1.0")
        
        stage_dirs_to_search = [stage_dir] + [d for name, d in self.stage_paths.items() if d is not stage_dir]
        
        # 1) Try exact filename matches for each variant and extension across stage dirs
        # First try the new simplified naming pattern, then fall back to old pattern
        for search_dir in stage_dirs_to_search:
            for ext in ['pdf', 'xlsx', 'xls']:
                for ver in version_variants:
                    # Try new simplified pattern first (just name_version)
                    candidate = search_dir / f"{doc_id}_{ver}.{ext}"
                    if candidate.exists():
                        return candidate
                    
                    # Fall back to old pattern (name_lote_company_version) for backward compatibility
                    candidate = search_dir / f"{doc_id}_{lote_number}_{sanitized_company}_{ver}.{ext}"
                    if candidate.exists():
                        return candidate
        
        # 2) Try numbered variants using the base pattern finder for each variant
        from utils.file_manager import FileManager
        for search_dir in stage_dirs_to_search:
            for ver in version_variants:
                # Try new simplified pattern first
                base_stem = f"{doc_id}_{ver}"
                pattern_files = FileManager.find_pattern_files(search_dir, base_stem)
                if pattern_files:
                    return pattern_files[0]
                
                # Fall back to old pattern for backward compatibility
                base_stem = f"{doc_id}_{lote_number}_{sanitized_company}_{ver}"
                matches = FileManager.find_pattern_files(search_dir, base_stem)
                if matches:
                    return matches[0]
        
        # 3) Fallback: loose prefix search ignoring version (grab first match)
        prefix = f"{doc_id}_{lote_number}_{sanitized_company}_"
        for search_dir in stage_dirs_to_search:
            try:
                for file_path in search_dir.iterdir():
                    if file_path.is_file() and file_path.stem.startswith(prefix):
                        return file_path
            except Exception:
                pass
        
        return None

    def open_document_location(self, doc_id: str) -> None:
        """Open the file location for a document in the system file manager"""
        file_path = self.get_document_file_path(doc_id)
        if not file_path:
            raise FileNotFoundError(f"No se encontró el archivo para el documento {doc_id}")
        
        self.file_manager.open_file_location(file_path)

    def delete_documents(self, doc_ids: List[str]) -> str:
        """Delete multiple licitación documents and their files. Returns success message."""
        if not doc_ids:
            raise ValueError("No se proporcionaron documentos para eliminar")

        deleted_count = 0
        errors: List[str] = []

        # Iterate and apply a transaction lock per document for atomicity
        for doc_id in doc_ids:
            try:
                # Lock per document during its deletion
                with self.lock_manager.database_transaction_lock(doc_id):
                    document = self.get_document(doc_id)
                    if not document:
                        errors.append(f"Documento {doc_id} no encontrado")
                        continue

                    # Delete physical files - use tracked file paths first (new approach)
                    files_deleted = []
                    
                    # Method 1: Use tracked file paths (for documents with tracked files)
                    if hasattr(document, 'file_paths') and document.file_paths:
                        for tracked_path in document.file_paths:
                            # Try all stage directories for tracked path
                            for stage_dir in self.stage_paths.values():
                                file_path = stage_dir / tracked_path
                                if file_path.exists():
                                    try:
                                        move_to_trash(file_path, self.project_path)
                                        files_deleted.append(tracked_path)
                                        break  # Stop after finding in one stage
                                    except OSError as e:
                                        errors.append(f"Error al mover archivo rastreado {tracked_path} a la papelera: {e}")

                    # Method 2: Fallback to pattern matching (for old documents)
                    if not files_deleted:
                        lote_number = (document.lote or "")[:2]
                        sanitized_company = self.file_manager.sanitize_for_filename(getattr(document, 'company', '') or "")
                        pattern = f"{doc_id}_{lote_number}_{sanitized_company}_*"

                        for stage_dir in self.stage_paths.values():
                            for fp in stage_dir.glob(pattern):
                                try:
                                    move_to_trash(fp, self.project_path)
                                    files_deleted.append(fp.name)
                                except OSError as e:
                                    errors.append(f"Error al mover archivo {fp} a la papelera: {e}")

                    # Delete from database
                    if getattr(document, 'db_id', None):
                        self.db_manager.delete_document(document.db_id)
                        deleted_count += 1

            except Exception as e:
                errors.append(f"Error al eliminar documento {doc_id}: {e}")

        parts: List[str] = []
        if deleted_count > 0:
            parts.append(f"Se eliminaron {deleted_count} documento(s) exitosamente")
        if errors:
            parts.append("Errores encontrados:\n" + "\n".join(f"• {err}" for err in errors))
        if not parts:
            return "No se eliminó ningún documento"
        return "\n\n".join(parts)

    def add_new_version(self, doc_id: str, version: str, state: str, file_paths: List[Path], 
                       author: str, notes: str = "", valor: Optional[float] = None) -> str:
        """Add a new version to an existing document. Returns success message."""
        
        # Get existing document
        document = self.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        # Validate valor for presupuesto and adicional types when adding new version
        if document.licitacion_document_type in ["presupuesto", "adicional"]:
            if valor is None or valor <= 0:
                raise ValueError(f"El campo Valor es obligatorio y debe ser mayor que 0 para documentos de tipo {document.licitacion_document_type}")
            # Update the valor in the document
            document.valor = valor
        
        # For SQLite, we accept states (like "S3") not stages 
        # The current_stage property handles the mapping to folder names
        
        # Handle multiple files like the planos controller
        messages = []
        current_stage = document.current_stage
        destination_dir = self.stage_paths[current_stage]
        
        # Process each file
        for file_path in file_paths:
            # Generate filename with proper extension  
            file_extension = self.file_manager.get_file_extension(file_path.name)
            # Use simplified naming with smart redundancy detection
            clean_name = self.file_manager._clean_redundant_patterns(doc_id)
            filename = f"{clean_name}_{version}.{file_extension}"
            
            destination = destination_dir / filename
            
            # Check if file already exists and generate numbered filename if needed
            if destination.exists():
                file_number = self.file_manager.get_next_file_number(destination_dir, filename)
                filename = self.file_manager.generate_numbered_filename(filename, file_number)
                destination = destination_dir / filename
            
            # Copy file to destination
            self.file_manager.copy_file(file_path, destination)
            messages.append(f"✓ Archivo creado: {filename}")
        
        # Add entry to document using SQLite operations (use state for the entry)
        document.add_entry(version, state, author, notes=notes)
        
        # Save updated document to database
        with self.lock_manager.database_transaction_lock():
            document.save_to_database()
        
        return '\n'.join(messages)

    def update_document_stage(self, doc_id: str, new_stage: str, author: str, 
                             notes: str = "", presupuesto_contratado: Optional[float] = None,
                             parent_licitacion_name: Optional[str] = None,
                             importe_adicional: Optional[float] = None,
                             create_certificacion: bool = True) -> str:
        """Move document to a new stage (workflow progression). Returns success message."""
        
        # Get existing document
        document = self.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        if new_stage not in LICITACION_STAGES:
            raise ValueError(f"Stage '{new_stage}' no válido")
        
        current_stage = document.current_stage
        current_version = document.current_version
        
        if current_stage == new_stage:
            raise ValueError(f"El documento ya está en stage {new_stage}")
        
        # Find current file
        current_dir = self.stage_paths[current_stage]
        new_dir = self.stage_paths[new_stage]
        
        lote_number = document.lote[:2] if document.lote else "00"
        sanitized_company = self.file_manager.sanitize_for_filename(document.company) if document.company else "unknown"
        
        # Look for existing file (try different extensions and naming patterns)
        current_file = None
        for ext in ['pdf', 'xlsx', 'xls']:
            # Try new simplified pattern first
            filename = f"{doc_id}_{current_version}.{ext}"
            potential_file = current_dir / filename
            if potential_file.exists():
                current_file = potential_file
                break
            
            # Fall back to old pattern for backward compatibility
            filename = f"{doc_id}_{lote_number}_{sanitized_company}_{current_version}.{ext}"
            potential_file = current_dir / filename
            if potential_file.exists():
                current_file = potential_file
                break
        
        if not current_file:
            raise FileNotFoundError(f"No se encontró el archivo actual para el documento {doc_id}")
        
        # Generate new filename (same version, new stage location)
        new_filename = current_file.name
        new_path = new_dir / new_filename
        
        # Check if destination already exists
        if new_path.exists():
            raise FileExistsError(f"Ya existe un archivo en {new_stage}: {new_filename}")
        
        # Move file to new stage directory
        self.file_manager.move_file(current_file, new_path)
        
        # Update document type based on new stage
        stage_to_doc_type = {
            "presupuestos": "presupuesto", 
            "licitaciones": "licitacion",
            "adicionales": "adicional"
        }
        
        new_doc_type = stage_to_doc_type.get(new_stage, document.licitacion_document_type)
        document.licitacion_document_type = new_doc_type
        
        # Add entry for stage change
        document.add_entry(current_version, f"Movido a {new_stage}", author, notes=notes)
        
        # Handle special cases for accepted presupuestos (now based on status instead of stage)
        if new_status == "A" and presupuesto_contratado is not None:
            # Store contracted amount in metadata
            document._licitacion_metadata['presupuesto_contratado'] = presupuesto_contratado
        
        # Save updated document to database
        with self.lock_manager.database_transaction_lock():
            document.save_to_database()
        
        # If status changed to A (approved) and create_certificacion is True, create Certificacion automatically
        certificacion_created = False
        if new_status == "A" and create_certificacion and presupuesto_contratado:
            try:
                from controllers.certificacion_controller import CertificacionController
                cert_path = self.project_path / "04_Certificaciones"
                cert_controller = CertificacionController(str(cert_path), self.project_path)
                
                if cert_controller.create_from_licitacion(doc_id, presupuesto_contratado):
                    certificacion_created = True
            except Exception as e:
                print(f"Advertencia: No se pudo crear certificación automática: {e}")
                import traceback
                traceback.print_exc()
        
        result = f"✓ Documento movido a {new_stage}: {new_filename}"
        
        if certificacion_created:
            result += "\n✓ Certificación creada automáticamente (versión 0)"
        
        return result

    def get_companies_list(self) -> List[str]:
        """Get list of all companies used in documents (for autocomplete)"""
        companies = set()
        for doc in self.get_all_documents():
            if doc.company:
                companies.add(doc.company)
        return sorted(list(companies))

    def get_available_lotes(self) -> List[str]:
        """Get the standard list of available lotes"""
        return LOTES_ESTANDAR.copy()

    def get_document_summaries(self) -> List['LicitacionSummary']:
        """
        Get lightweight document summaries for fast licitacion dashboard loading.
        
        Creates LicitacionSummary objects from SQLite documents for dashboard display.
        """
        try:
            from models.document_summary import LicitacionSummary
            
            summaries = []
            all_documents = self.get_all_documents()
            
            for doc in all_documents:
                # Create LicitacionSummary from SQLiteLicitacionDocument
                summary = LicitacionSummary(
                    name=doc.name,
                    current_status=doc.current_state,
                    company=doc.company,
                    document_type=doc.licitacion_document_type,
                    autor=doc.autor or "",
                    latest_notes=doc.latest_notes,
                    creation_date=doc.creation_date,
                    lote=doc.lote,
                    id=doc.name,  # Use name as ID for compatibility
                    current_stage=doc.current_stage,
                    current_version=doc.current_version
                )
                summaries.append(summary)
            
            return summaries
            
        except Exception as e:
            print(f"Error loading SQLite licitacion summaries: {e}")
            # Fallback to empty list - allows graceful degradation
            return []

    def update_document_info(self, old_name: str, new_name: str, new_display_name: str, 
                           new_version: str, new_state: str, author: str, notes: str,
                           autor: str = "", rev_tecnica: str = "", rev_gerencia: str = "",
                           valor: Optional[float] = None, lote: Optional[str] = None, 
                           empresa: Optional[str] = None, tipo: Optional[str] = None) -> str:
        """Update licitacion document general information. Returns success message."""
        
        document = self.get_document(old_name)
        if not document:
            raise ValueError(f"No se encontró el documento con nombre {old_name}")
        
        # Validate new state  
        from models.licitacion_document import PRESUPUESTO_STATUSES
        if new_state not in PRESUPUESTO_STATUSES:
            raise ValueError(f"Estado '{new_state}' no válido")
        
        old_filename = None
        old_path = None
        
        # Find existing files for this document
        import glob
        sanitized_old_name = self.file_manager.sanitize_for_filename(old_name)
        
        # Search in the document's current stage folder
        current_stage = document.current_stage
        stage_path = self.stage_paths[current_stage]
        file_pattern = str(stage_path / f"*{sanitized_old_name}*")
        matching_files = glob.glob(file_pattern)
        
        if matching_files:
            # Use the first matching file to determine extension
            old_filename = Path(matching_files[0]).name
            old_path = Path(matching_files[0])
            extension = self.file_manager.get_file_extension(old_filename)
        else:
            # Default to PDF if no files found
            extension = "pdf"
        
        # Generate new filename based on new information
        # Use simplified pattern with smart redundancy detection: <name>_<version>.<ext>
        sanitized_name = self.file_manager.sanitize_for_filename(new_name)
        sanitized_version = self.file_manager.sanitize_for_filename(new_version)
        clean_name = self.file_manager._clean_redundant_patterns(sanitized_name)
        new_filename = f"{clean_name}_{sanitized_version}.{extension}"
        new_path = stage_path / new_filename
        
        # Check if new file already exists  
        if new_path.exists() and old_path != new_path:
            raise FileExistsError(f"El archivo {new_filename} ya existe")
        
        # Handle file rename if paths are different and old file exists
        if old_path and old_path.exists() and old_path != new_path:
            try:
                self.file_manager.rename_file(old_path, new_path)
            except Exception as e:
                raise Exception(f"Error al renombrar archivo: {str(e)}")
        
        # Update document metadata
        document.name = new_name  # This is the document ID
        
        # Always update document fields (allow clearing by passing empty string)
        document.document_autor = autor
        document.rev_tecnica = rev_tecnica
        document.rev_gerencia = rev_gerencia
        
        # Update licitacion-specific fields if provided
        if lote and lote in LOTES_ESTANDAR:
            document.lote = lote
        if empresa:
            document.company = empresa
        if tipo and tipo in PRESUPUESTO_TYPES:
            document.licitacion_document_type = tipo
        
        # Update valor for presupuesto and adicional types
        if document.licitacion_document_type in ["presupuesto", "adicional"]:
            if valor is not None:
                if valor <= 0:
                    raise ValueError(f"El campo Valor debe ser mayor que 0 para documentos de tipo {document.licitacion_document_type}")
                document.valor = valor
            elif not hasattr(document, 'valor') or document.valor is None:
                # If no valor provided and document doesn't have one, it's required
                raise ValueError(f"El campo Valor es obligatorio para documentos de tipo {document.licitacion_document_type}")
            
        document.add_entry(new_version, new_state, author, notes=notes)
        
        # Save to database
        with self.lock_manager.database_transaction_lock():
            document.save_to_database()
        
        return f"✓ Información del documento actualizada: {new_filename}"
    
    def push_adicional_to_certificacion(self, adicional_name: str) -> str:
        """Push an approved adicional to certificaciones. Returns success message."""
        # Get the adicional document
        document = self.get_document(adicional_name)
        if not document:
            raise ValueError(f"No se encontró el adicional '{adicional_name}'")
        
        # Validate it can be pushed
        if not self._can_push_to_certificacion(document):
            raise ValueError(
                f"El adicional '{adicional_name}' no se puede transferir. "
                f"Debe estar aprobado (estado A) y no haber sido transferido previamente."
            )
        
        # Import certificacion controller 
        try:
            from controllers.certificacion_controller import CertificacionController
        except ImportError:
            raise ImportError("No se pudo importar el controlador de certificaciones")
        
        # Initialize certificacion controller
        cert_base_path = self.project_path / "04_Certificaciones"
        cert_controller = CertificacionController(str(cert_base_path), self.project_path)
        
        # Create new certificacion from adicional data
        try:
            # Generate certification name based on adicional
            cert_name = f"CERT_{document.name}"
            
            # Create certificacion with adicional data
            cert_message = cert_controller.create_certificacion_from_adicional(
                cert_name=cert_name,
                lote=document.lote,
                company=document.company,
                adicional_name=document.name,
                importe=document.valor or document.importe_adicional or 0.0,
                notes=f"Creado automáticamente desde adicional aprobado: {document.name}"
            )
            
            # Mark adicional as pushed
            document._licitacion_metadata['pushed_to_certificacion'] = True
            with self.lock_manager.database_transaction_lock():
                document.save_to_database()
            
            return f"✓ Adicional '{adicional_name}' transferido a certificaciones como '{cert_name}'"
            
        except Exception as e:
            raise RuntimeError(f"Error al crear certificación: {str(e)}")
    
    def get_approved_adicionales(self) -> List[SQLiteLicitacionDocument]:
        """Get all approved adicionales that can be pushed to certificaciones"""
        approved = []
        for doc in self.get_all_documents():
            if (doc.licitacion_document_type == "adicional" and 
                doc.current_state == "A" and 
                not doc._licitacion_metadata.get('pushed_to_certificacion', False)):
                approved.append(doc)
        return approved
    
    def _can_push_to_certificacion(self, document: SQLiteLicitacionDocument) -> bool:
        """Check if this adicional can be pushed to certificaciones"""
        return (document.licitacion_document_type == "adicional" and 
                document.current_state == "A" and 
                not document._licitacion_metadata.get('pushed_to_certificacion', False))

    def delete_document_entries(self, entry_specs: List[Dict[str, str]]) -> str:
        """Delete specific version/state entries from licitacion documents. Returns success message."""
        if not entry_specs:
            raise ValueError("No se proporcionaron entradas para eliminar")

        deleted_count = 0
        errors: List[str] = []
        docs_to_update: Dict[str, SQLiteLicitacionDocument] = {}

        for spec in entry_specs:
            try:
                doc_id = spec['doc_id']
                version = spec['version']
                state = spec['state']
                filename = spec.get('filename', '')

                # Get the licitacion document
                document = self.get_document(doc_id)
                if not document:
                    errors.append(f"Documento {doc_id} no encontrado")
                    continue

                # Delete physical files (including numbered variants)
                files_deleted = 0
                total_files_found = 0
                
                # Build base patterns for file deletion (try both old and new naming patterns)
                lote_number = document.lote[:2] if document.lote else "00"
                sanitized_company = self.file_manager.sanitize_for_filename(document.company) if document.company else "unknown"
                sanitized_name = self.file_manager.sanitize_for_filename(document.name)
                
                # Patterns to try: new simplified and old full pattern
                patterns_to_try = [
                    f"{sanitized_name}_{version}",  # New simplified pattern
                    f"{sanitized_name}_{lote_number}_{sanitized_company}_{version}"  # Old pattern for backward compatibility
                ]
                
                # Search in all stage directories for pattern-matched files
                for stage_name, stage_dir in self.stage_paths.items():
                    try:
                        if not stage_dir.exists():
                            continue
                        
                        # Try both naming patterns
                        for base_pattern in patterns_to_try:
                            pattern_files = self.file_manager.find_pattern_files(stage_dir, base_pattern)
                            total_files_found += len(pattern_files)
                            
                            for file_path in pattern_files:
                                try:
                                    move_to_trash(file_path, self.project_path)
                                    files_deleted += 1
                                except OSError as e:
                                    errors.append(f"Error al mover archivo {file_path.name} a la papelera: {e}")
                    except Exception as e:
                        errors.append(f"Error buscando archivos en {stage_dir}: {e}")
                
                # If specific filename was provided but no files found, check for exact match as fallback
                if filename and total_files_found == 0:
                    for stage_dir in self.stage_paths.values():
                        file_path = stage_dir / filename
                        if file_path.exists():
                            try:
                                move_to_trash(file_path, self.project_path)
                                files_deleted += 1
                                break
                            except OSError as e:
                                errors.append(f"Error al mover archivo {filename} a la papelera: {e}")
                

                # Remove entry from document
                removed = False
                for i, entry in enumerate(document.entries):
                    if entry.version == version and entry.state == state:
                        document.entries.pop(i)
                        removed = True
                        deleted_count += 1
                        docs_to_update[doc_id] = document
                        break
                
                if not removed:
                    errors.append(f"Entrada v{version}-{state} no encontrada para documento {doc_id}")

            except Exception as e:
                errors.append(f"Error al procesar entrada {spec}: {e}")

        # Persist changes to database
        for doc_id, document in docs_to_update.items():
            try:
                with self.lock_manager.database_transaction_lock(doc_id):
                    if not document.entries:
                        # If no entries left, delete the entire document
                        if getattr(document, 'db_id', None):
                            self.db_manager.delete_document(document.db_id)
                    else:
                        # Otherwise, save the updated document
                        document.save_to_database()
            except Exception as e:
                errors.append(f"Error al actualizar documento {doc_id}: {e}")

        # Build result message
        parts: List[str] = []
        if deleted_count > 0:
            parts.append(f"Se eliminaron {deleted_count} entrada(s) exitosamente")
        if errors:
            parts.append("Errores encontrados:\n" + "\n".join(f"• {err}" for err in errors))
        
        if not parts:
            return "No se eliminó ninguna entrada"
        
        return "\n\n".join(parts)

    def close(self):
        """Close database connections."""
        if self.db_manager:
            self.db_manager.close()


# Compatibility alias - allows existing code to import LicitacionController and get SQLite version
LicitacionController = SQLiteLicitacionController