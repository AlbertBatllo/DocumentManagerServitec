from pathlib import Path
from typing import List, Dict, Any, Optional
from models.licitacion_document import (
    LicitacionDocument, 
    LicitacionRepository,
    LOTES_ESTANDAR,
    LICITACION_STAGES,
    STAGE_DISPLAY_NAMES,
    PRESUPUESTO_TYPES,
    PRESUPUESTO_STATUSES
)
from models.document_summary import LicitacionSummary, create_licitacion_summaries_from_manifest
from utils.file_manager import FileManager
from utils.project_utils import ProjectUtils
from config.settings import StatusConfig


class LicitacionController:
    """Controller for managing licitacion documents"""
    
    def __init__(self, project_path: Path = None):
        self.project_path = project_path if project_path else Path.cwd()
        
        # Set up storage paths for each stage
        self.base_path = self.project_path / "03_Presupuestos"
        self.stage_paths = {
            "licitaciones": self.base_path / "licitaciones",
            "presupuestos": self.base_path / "presupuestos", 
            "adicionales": self.base_path / "adicionales",
            "licitaciones": self.base_path / "licitaciones"
        }
        
        # Manifest file path
        from utils.path_helper import PathHelper
        pm_path = PathHelper.get_project_manager_path(self.project_path)
        self.manifest_path = pm_path / "presupuestos" / "manifest.json"
        
        # Ensure all directories exist
        ProjectUtils.ensure_directory_exists(self.manifest_path.parent)
        for stage_path in self.stage_paths.values():
            ProjectUtils.ensure_directory_exists(stage_path)
        
        # Initialize repository
        self.repository = LicitacionRepository(self.manifest_path)
        self.file_manager = FileManager()

    def add_new_document(self, name: str, lote: str, company: str, 
                        document_type: str, status: str, version: str, file_path: Path, author: str, 
                        notes: str = "", valor: Optional[float] = None,
                        parent_licitacion_name: Optional[str] = None,
                        parent_presupuesto_id: Optional[str] = None,
                        importe_adicional: Optional[float] = None,
                        # Legacy parameter for backward compatibility
                        stage: str = None) -> str:
        """Add a new licitacion document. Returns success message."""
        
        # Handle legacy stage parameter
        if stage and not document_type:
            # Convert old stage to new document_type for backward compatibility
            from models.licitacion_document import migrate_document_type
            document_type = "adicionales" if stage == "adicionales" else "licitacion"
        
        # Validate inputs
        if lote not in LOTES_ESTANDAR:
            raise ValueError(f"Lote '{lote}' no está en la lista estándar")
        
        if document_type not in PRESUPUESTO_TYPES:
            raise ValueError(f"Document type '{document_type}' no válido")
        
        if status not in PRESUPUESTO_STATUSES:
            raise ValueError(f"Status '{status}' no válido")
        
        # Validate valor field for presupuesto and adicional types
        if document_type in ["presupuesto", "adicional"]:
            if valor is None or valor <= 0:
                raise ValueError(f"El campo Valor es obligatorio y debe ser mayor que 0 para documentos de tipo {document_type}")
        
        # Check if document already exists
        if self.repository.document_exists(name):
            raise ValueError(f"Ya existe un documento con nombre '{name}'")
        
        # Create document with new fields
        document = LicitacionDocument(
            name=name,  # Using name as primary identifier now
            lote=lote,
            company=company,
            document_type=document_type,
            valor=valor  # Add valor field
        )
        
        # If this is an adicional, store parent_licitacion_name and importe_adicional
        if document_type == "adicional":
            # Use parent_presupuesto_id if provided, otherwise fall back to parent_licitacion_name
            if parent_presupuesto_id:
                document.parent_licitacion_name = parent_presupuesto_id
            elif parent_licitacion_name:
                document.parent_licitacion_name = parent_licitacion_name
            if importe_adicional is not None:
                document.importe_adicional = importe_adicional
        
        # Add initial entry with new status field
        document.add_entry(version, status=status, author=author, notes=notes)
        
        # Generate filename with proper extension
        file_extension = self.file_manager.get_file_extension(file_path.name)
        lote_number = lote[:2]
        sanitized_company = self.file_manager.sanitize_for_filename(company)
        sanitized_name = self.file_manager.sanitize_for_filename(name)
        filename = f"{sanitized_name}_{lote_number}_{sanitized_company}_{version}.{file_extension}"
        
        # Map document_type to stage folder for simplified structure
        stage_mapping = {
            "licitacion": "licitaciones",
            "presupuesto": "presupuestos",
            "adicional": "adicionales"
        }
        
        # Use simple mapping regardless of status
        mapped_stage = stage_mapping.get(document_type, "licitaciones")
        
        destination_dir = self.stage_paths[mapped_stage]
        destination = destination_dir / filename
        
        # Check if file already exists
        if destination.exists():
            raise FileExistsError(f"El archivo {filename} ya existe en {mapped_stage}")
        
        # Copy file to destination
        self.file_manager.copy_file(file_path, destination)
        
        # Save document to repository
        self.repository.add_document(document)
        
        return f"✓ Documento {name} creado: {filename}"

    def add_new_version(self, doc_id: str, version: str, status: str, file_paths: List[Path], 
                       author: str, notes: str = "", valor: Optional[float] = None) -> str:
        """Add a new version to an existing document. Returns success message."""
        
        # Get existing document
        document = self.repository.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        # Validate status if provided
        if status and status not in PRESUPUESTO_STATUSES:
            raise ValueError(f"Status '{status}' no válido")
        
        # Validate valor field for presupuesto and adicional types
        if document.document_type in ["presupuesto", "adicional"]:
            if valor is None or valor <= 0:
                raise ValueError(f"El campo Valor es obligatorio y debe ser mayor que 0 para documentos de tipo {document.document_type}")
            # Update document valor
            document.valor = valor
        
        # Use first file path for processing (multiple files not supported in current design)
        file_path = file_paths[0] if file_paths else None
        if not file_path:
            raise ValueError("Al menos un archivo es requerido")
        
        # Generate filename with proper extension  
        file_extension = self.file_manager.get_file_extension(file_path.name)
        lote_number = document.lote[:2]
        sanitized_company = self.file_manager.sanitize_for_filename(document.company)
        filename = f"{doc_id}_{lote_number}_{sanitized_company}_{version}.{file_extension}"
        
        # Determine destination path based on current stage (new versions go to same stage)
        current_stage = document.current_stage
        destination_dir = self.stage_paths[current_stage]
        destination = destination_dir / filename
        
        # Check if file already exists
        if destination.exists():
            raise FileExistsError(f"El archivo {filename} ya existe en {current_stage}")
        
        # Copy file to destination
        self.file_manager.copy_file(file_path, destination)
        
        # Add entry to document with status if provided
        document.add_entry(version, author=author, notes=notes, status=status)
        
        # Update document in repository
        self.repository.update_document(doc_id, document)
        
        return f"✓ Nueva versión añadida: {filename}"

    def update_document_stage(self, doc_id: str, new_stage: str, author: str, 
                             notes: str = "", presupuesto_contratado: Optional[float] = None,
                             parent_licitacion_name: Optional[str] = None,
                             importe_adicional: Optional[float] = None,
                             create_certificacion: bool = True) -> str:
        """Move document to a new stage (workflow progression). Returns success message."""
        
        # Get existing document
        document = self.repository.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        if new_stage not in LICITACION_STAGES:
            raise ValueError(f"Stage '{new_stage}' no válido")
        
        current_stage = document.current_stage
        current_version = document.current_version
        
        if current_stage == new_stage:
            raise ValueError(f"El documento ya está en stage {STAGE_DISPLAY_NAMES[new_stage]}")
        
        # Find current file
        current_dir = self.stage_paths[current_stage]
        new_dir = self.stage_paths[new_stage]
        
        lote_number = document.lote[:2]
        sanitized_company = self.file_manager.sanitize_for_filename(document.company)
        
        # Look for existing file (try different extensions)
        current_file = None
        for ext in ['pdf', 'xlsx', 'xls']:
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
        
        # Add entry for stage change (same version, new stage)
        document.add_entry(current_version, new_stage, author, notes)
        
        # If moving to presupuestos_aceptados stage, store presupuesto_contratado
        if new_stage == "presupuestos_aceptados" and presupuesto_contratado is not None:
            document.presupuesto_contratado = presupuesto_contratado
        
        # If moving to adicionales, store parent_licitacion_name and importe_adicional
        if new_stage == "adicionales":
            if parent_licitacion_name is not None:
                document.parent_licitacion_name = parent_licitacion_name
            if importe_adicional is not None:
                document.importe_adicional = importe_adicional
        
        # Update document in repository
        self.repository.update_document(doc_id, document)
        
        # If moved to presupuestos_aceptados stage and create_certificacion is True, create Certificacion automatically
        certificacion_created = False
        if new_stage == "presupuestos_aceptados" and create_certificacion and presupuesto_contratado:
            try:
                from controllers.certificacion_controller import CertificacionController
                cert_path = self.project_path / "04_Certificaciones"
                cert_controller = CertificacionController(cert_path, self.project_path)
                
                if cert_controller.create_from_licitacion(doc_id, presupuesto_contratado):
                    certificacion_created = True
            except Exception as e:
                print(f"Advertencia: No se pudo crear certificación automática: {e}")
                import traceback
                traceback.print_exc()
        
        stage_from = STAGE_DISPLAY_NAMES[current_stage]
        stage_to = STAGE_DISPLAY_NAMES[new_stage]
        result = f"✓ Documento movido de {stage_from} a {stage_to}"
        
        if certificacion_created:
            result += "\n✓ Certificación creada automáticamente (versión 0)"
        
        return result

    def get_all_documents(self) -> List[LicitacionDocument]:
        """Get all licitacion documents"""
        return self.repository.get_all_documents()
    
    def get_document_summaries(self) -> List[LicitacionSummary]:
        """
        Get lightweight document summaries for fast licitacion dashboard loading.
        
        This method provides significant performance improvement by:
        - Reading JSON only once
        - Skipping full LicitacionDocument object creation  
        - Extracting only current workflow state
        - Avoiding complex workflow history processing
        
        Returns:
            List of LicitacionSummary objects with essential data for dashboard display
        """
        try:
            # Read manifest file directly without creating LicitacionDocument objects
            from utils.file_manager import FileManager
            manifest_data = FileManager.safe_json_read(str(self.manifest_path))
            
            # Create summaries efficiently from raw JSON data
            summaries = create_licitacion_summaries_from_manifest(manifest_data)
            
            return summaries
            
        except Exception as e:
            print(f"Error loading licitacion summaries: {e}")
            # Fallback to empty list - allows graceful degradation
            return []

    def get_document(self, doc_id: str) -> Optional[LicitacionDocument]:
        """Get specific document by ID"""
        return self.repository.get_document(doc_id)

    def get_documents_by_lote(self, lote: str) -> List[LicitacionDocument]:
        """Get all documents for a specific lote"""
        return self.repository.get_documents_by_lote(lote)

    def get_documents_by_stage(self, stage: str) -> List[LicitacionDocument]:
        """Get all documents in a specific stage"""
        return self.repository.get_documents_by_stage(stage)

    def get_lote_status_summary(self) -> Dict[str, Dict[str, int]]:
        """Get summary of document counts per lote and stage"""
        return self.repository.get_lote_status_summary()

    def get_companies_list(self) -> List[str]:
        """Get list of all companies used in documents (for autocomplete)"""
        companies = set()
        for doc in self.repository.get_all_documents():
            if doc.company:
                companies.add(doc.company)
        return sorted(list(companies))

    def get_available_lotes(self) -> List[str]:
        """Get the standard list of available lotes"""
        return LOTES_ESTANDAR.copy()

    def get_available_stages(self) -> List[str]:
        """Get the list of workflow stages"""
        return LICITACION_STAGES.copy()

    def get_stage_display_names(self) -> Dict[str, str]:
        """Get mapping of stage codes to display names"""
        return STAGE_DISPLAY_NAMES.copy()

    def delete_document(self, doc_id: str) -> str:
        """Delete a document and its associated files. Returns success message."""
        # Get document
        document = self.repository.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        # Find and delete all associated files
        deleted_files = []
        for stage, stage_dir in self.stage_paths.items():
            lote_number = document.lote[:2]
            sanitized_company = self.file_manager.sanitize_for_filename(document.company)
            
            # Look for files with this document ID pattern
            pattern = f"{doc_id}_{lote_number}_{sanitized_company}_*"
            for file_path in stage_dir.glob(pattern):
                file_path.unlink()  # Delete file
                deleted_files.append(file_path.name)
        
        # Remove document from repository
        if doc_id in self.repository.documents:
            del self.repository.documents[doc_id]
            self.repository.save()
        
        files_info = f" ({len(deleted_files)} archivos)" if deleted_files else ""
        return f"✓ Documento {doc_id} eliminado{files_info}"

    def get_document_file_path(self, doc_id: str) -> Optional[Path]:
        """Get the current file path for a document using stored file paths"""
        document = self.repository.get_document(doc_id)
        
        # First, try to get the file path from the current entry
        if document and document.current_entry and document.current_entry.file_path:
            file_path = Path(document.current_entry.file_path)
            if file_path.exists():
                return file_path
        
        # If no file path in current entry, check all entries for any valid file path
        if document:
            for entry in document.entries:
                if entry.file_path:
                    file_path = Path(entry.file_path)
                    if file_path.exists():
                        return file_path
        
        # Fallback: try to find files in the expected stage directory
        if document:
            current_stage = document.current_stage
            stage_dir = self.stage_paths[current_stage]
        else:
            # If no document found, try all stage directories
            stage_dir = None
        
        # Use glob pattern matching as last resort
        import glob
        sanitized_name = self.file_manager.sanitize_for_filename(doc_id)
        
        # Try all stage directories if no specific stage
        stage_dirs_to_try = []
        if document and stage_dir:
            stage_dirs_to_try.append(stage_dir)
        else:
            # Try all stage directories
            stage_dirs_to_try = list(self.stage_paths.values())
        
        for stage_dir in stage_dirs_to_try:
            file_pattern = str(stage_dir / f"*{sanitized_name}*")
            matching_files = glob.glob(file_pattern)
            
            if matching_files:
                # Return the first matching file
                return Path(matching_files[0])
        
        # Special case: if document type is "licitacion" and no file found in current stage,
        # also check the "licitaciones" folder
        if (document and document.document_type == "licitacion" and 
            document.current_stage != "licitaciones"):
            licitaciones_dir = self.stage_paths.get("licitaciones")
            if licitaciones_dir and licitaciones_dir.exists():
                file_pattern = str(licitaciones_dir / f"*{sanitized_name}*")
                matching_files = glob.glob(file_pattern)
                if matching_files:
                    # Return the first matching file
                    return Path(matching_files[0])
        
        return None

    def open_document_location(self, doc_id: str) -> None:
        """Open the file location for a document in the system file manager"""
        file_path = self.get_document_file_path(doc_id)
        if not file_path:
            raise FileNotFoundError(f"No se encontró el archivo para el documento {doc_id}")
        
        self.file_manager.open_file_location(file_path)
    
    def push_adicional_to_certificacion(self, adicional_name: str) -> str:
        """Push an approved adicional to certificaciones. Returns success message."""
        # Get the adicional document
        document = self.repository.get_document(adicional_name)
        if not document:
            raise ValueError(f"No se encontró el adicional '{adicional_name}'")
        
        # Validate it can be pushed
        if not document.can_push_to_certificacion():
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
                importe=document.importe_adicional or 0.0,
                notes=f"Creado automáticamente desde adicional aprobado: {document.name}"
            )
            
            # Mark adicional as pushed
            document.pushed_to_certificacion = True
            self.repository.save()
            
            return f"✓ Adicional '{adicional_name}' transferido a certificaciones como '{cert_name}'"
            
        except Exception as e:
            raise RuntimeError(f"Error al crear certificación: {str(e)}")
    
    def get_approved_adicionales(self) -> List[LicitacionDocument]:
        """Get all approved adicionales that can be pushed to certificaciones"""
        return self.repository.get_approved_adicionales()
    
    def get_accepted_presupuestos_by_lote(self, lote: str) -> List[LicitacionDocument]:
        """Get all accepted presupuestos (status A) for a specific lote"""
        all_docs = self.repository.get_documents_by_lote(lote)
        accepted_presupuestos = []
        
        for doc in all_docs:
            # Include presupuesto and licitacion types that are approved (status A)
            if (doc.document_type in ["presupuesto", "licitacion"] and 
                doc.current_status == "A"):
                accepted_presupuestos.append(doc)
        
        return accepted_presupuestos
    
    def update_document_status(self, doc_id: str, new_status: str, author: str, 
                               notes: str = "", presupuesto_contratado: Optional[float] = None,
                               parent_licitacion_name: Optional[str] = None,
                               importe_adicional: Optional[float] = None,
                               create_certificacion: bool = True) -> str:
        """Update document status (for presupuesto type documents that don't move between stages). Returns success message."""
        
        # Get existing document
        document = self.repository.get_document(doc_id)
        if not document:
            raise ValueError(f"No se encontró el documento con ID {doc_id}")
        
        if new_status not in PRESUPUESTO_STATUSES:
            raise ValueError(f"Status '{new_status}' no válido")
        
        current_status = document.current_status
        current_version = document.current_version
        
        if current_status == new_status:
            raise ValueError(f"El documento ya está en estado {new_status}")
        
        # Add entry for status change (same version, new status)
        document.add_entry(current_version, status=new_status, author=author, notes=notes)
        
        # If approving presupuesto type, store presupuesto_contratado
        if new_status == "A" and document.document_type == "presupuesto" and presupuesto_contratado is not None:
            document.presupuesto_contratado = presupuesto_contratado
        
        # If this is an adicional being approved, store parent_licitacion_name and importe_adicional
        if new_status == "A" and document.document_type == "adicionales":
            if parent_licitacion_name is not None:
                document.parent_licitacion_name = parent_licitacion_name
            if importe_adicional is not None:
                document.importe_adicional = importe_adicional
        
        # Update document in repository
        self.repository.update_document(doc_id, document)
        
        # If approving presupuesto inicial and create_certificacion is True, create Certificacion automatically
        certificacion_created = False
        if new_status == "A" and document.document_type == "presupuesto" and create_certificacion and presupuesto_contratado:
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
        
        from models.licitacion_document import STATUS_DISPLAY_NAMES
        status_from = STATUS_DISPLAY_NAMES.get(current_status, current_status)
        status_to = STATUS_DISPLAY_NAMES.get(new_status, new_status)
        result = f"✓ Estado del documento actualizado de {status_from} a {status_to}"
        
        if certificacion_created:
            result += "\n✓ Certificación creada automáticamente (versión 0)"
        
        return result