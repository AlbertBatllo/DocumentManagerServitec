"""
Certificaciones Document Handler

Handles Certificaciones (Monthly/Technical Reports) specific operations.
Extends BaseDocumentHandler with Certificaciones-specific functionality.
"""

from pathlib import Path
from typing import Dict, List, Optional
from tkinter import messagebox

from .base_handler import BaseDocumentHandler


class CertificacionesHandler(BaseDocumentHandler):
    """
    Handler for Certificaciones (Monthly/Technical Reports) documents.

    Certificaciones have specific requirements:
    - Monthly reporting cycles
    - Technical certifications
    - Parent-child relationships (adicionales)
    """

    def __init__(self, app_controller, controller, view_factory: Dict = None):
        super().__init__(app_controller, controller, view_factory)
        self._monthly_form = None

    def get_document_type(self) -> str:
        return "certificaciones"

    def get_storage_path(self) -> Path:
        """
        Get the storage path for Certificaciones documents.

        Returns:
            Path to 04_Certificaciones folder within the current project.
            Falls back to current directory if no project is selected.

        Note:
            Use get_validated_storage_path() when you need to ensure
            the path exists before file operations.
        """
        if not self.app.current_project_path:
            return Path(".")

        project_path = Path(self.app.current_project_path)
        if not project_path.exists():
            print(f"[WARNING] Project path does not exist: {project_path}")
            return Path(".")

        return project_path / "04_Certificaciones"

    def get_display_name(self) -> str:
        return "Certificaciones"

    def get_state_map(self) -> Dict[str, str]:
        return {
            'S0': 'Borrador',
            'S1': 'En Revisión',
            'S2': 'Aprobado',
            'S3': 'Enviado',
            'A': 'Certificado',
            'B': 'Rechazado',
        }

    # === Certificaciones-specific Methods ===

    def get_documents(self) -> List:
        """Get all certificacion documents."""
        if not self.controller:
            return []
        if hasattr(self.controller, 'get_all_certificaciones'):
            return self.controller.get_all_certificaciones()
        return []

    def get_document_by_id(self, doc_id: str):
        """Get a specific certificacion by ID."""
        if not self.controller:
            return None
        if hasattr(self.controller, 'get_certificacion'):
            return self.controller.get_certificacion(doc_id)
        return None

    def check_document_exists(self, doc_id: str) -> Optional[tuple]:
        """Check if certificacion exists."""
        document = self.get_document_by_id(doc_id)
        if document:
            return (getattr(document, 'name', doc_id), getattr(document, 'version', '1.0'))
        return None

    def get_all_document_ids(self) -> List[str]:
        """Get all certificacion IDs."""
        documents = self.get_documents()
        return [getattr(doc, 'id', getattr(doc, 'name', '')) for doc in documents]

    def update_document_state(self, doc_id: str, new_state: str, author: str, notes: str) -> str:
        """Update certificacion state."""
        if not self.controller:
            raise Exception("Certificaciones controller not initialized")
        if hasattr(self.controller, 'update_certificacion_state'):
            return self.controller.update_certificacion_state(doc_id, new_state, author, notes)
        raise NotImplementedError("update_certificacion_state not available")

    def delete_entries(self, entry_specs: List[Dict]) -> str:
        """Delete certificacion entries."""
        if not self.controller:
            raise Exception("Certificaciones controller not initialized")
        if hasattr(self.controller, 'delete_certificacion_entries'):
            return self.controller.delete_certificacion_entries(entry_specs)
        raise NotImplementedError("delete_certificacion_entries not available")

    def _get_document_state(self, doc) -> str:
        """Get the current state of a certificacion."""
        return getattr(doc, 'current_state', getattr(doc, 'estado', ''))

    def _annotate_document_by_id(self, doc_id: str):
        """Launch PDF annotation for a certificacion document."""
        document = self.get_document_by_id(doc_id)
        if not document:
            messagebox.showerror("Error", f"Documento no encontrado: {doc_id}")
            return

        pdf_corrector = getattr(self.app, 'pdf_corrector', None)
        if not pdf_corrector:
            messagebox.showerror("Error", "Corrector PDF no disponible")
            return

        # Find PDF file for this document
        storage_path = self.get_storage_path()
        pdf_path = None

        doc_name = getattr(document, 'name', doc_id)
        for pdf_file in storage_path.rglob(f"*{doc_name}*.pdf"):
            pdf_path = pdf_file
            break

        if not pdf_path or not pdf_path.exists():
            messagebox.showerror(
                "Error",
                f"No se encontró el archivo PDF para el documento {doc_name}"
            )
            return

        # Launch annotation
        callbacks = {
            'save_annotations': lambda anns: self._save_annotations(doc_id, anns),
            'back': self.show_dashboard,
        }
        pdf_corrector.annotate_pdf(str(pdf_path), callbacks)

    def _save_annotations(self, doc_id: str, annotations: dict):
        """Save PDF annotations for a certificacion document."""
        pass

    # === Override Dashboard Callbacks ===

    def get_dashboard_callbacks(self) -> Dict:
        """
        Get callbacks for certificaciones dashboard with all certificaciones-specific functionality.
        """
        # Get base callbacks
        callbacks = super().get_dashboard_callbacks()

        # Add certificaciones-specific callbacks
        if self.controller:
            # File management callbacks
            if hasattr(self.controller, 'get_document_files_info'):
                callbacks['get_current_files'] = self.controller.get_document_files_info

            # Document info editing
            if hasattr(self.controller, 'update_certificacion_info'):
                callbacks['edit_document_info'] = self.show_edit_document_info_form

            # Cloud sync
            if hasattr(self.controller, 'sync_document_to_cloud'):
                callbacks['sync_to_cloud'] = self.controller.sync_document_to_cloud
            if hasattr(self.controller, 'is_cloud_sync_enabled'):
                callbacks['is_cloud_enabled'] = self.controller.is_cloud_sync_enabled

            # Certificacion-specific operations
            if hasattr(self.controller, 'open_document_location'):
                callbacks['open_document_location'] = self.controller.open_document_location
            if hasattr(self.controller, 'get_certificacion'):
                callbacks['get_document'] = self.controller.get_certificacion

        # Refresh callback specific to certificaciones
        callbacks['refresh_certificaciones'] = self.refresh_data

        # Monthly certificacion form
        callbacks['monthly_form'] = self.show_monthly_certificacion_form

        # Annotate document
        callbacks['annotate_document'] = self.annotate_selected_document

        return callbacks

    def annotate_selected_document(self, doc_name: str = None):
        """Annotate the selected certificacion document."""
        if doc_name:
            self._annotate_document_by_id(doc_name)
        else:
            messagebox.showwarning("Aviso", "Por favor seleccione un documento para anotar")

    def refresh_data(self):
        """Refresh certificaciones data."""
        if self.controller and hasattr(self.controller, 'refresh_data'):
            return self.controller.refresh_data()
        return self.get_documents()

    def show_edit_document_info_form(self, doc_name: str = None):
        """Show form to edit certificacion document information using CorrectionForm."""
        # Validate that we have a document name
        if not doc_name:
            messagebox.showwarning("Aviso", "Por favor seleccione un documento para editar")
            return

        # Verify document exists
        document = self.get_document_by_id(doc_name)
        if not document:
            messagebox.showerror("Error", f"No se encontró el documento: {doc_name}")
            return

        # Lazy import and create CorrectionForm
        from views.correction_form import CorrectionForm

        # Create form instance if not already created
        if not hasattr(self, '_correction_form') or self._correction_form is None:
            self._correction_form = CorrectionForm(
                self.app.root,
                "certificaciones",
                self.get_state_map()
            )

        # Set up callbacks for the correction form
        callbacks = {
            'back': self._back_to_dashboard,
            'get_document': self._get_document_for_edit,
            'update_document_info': self._update_document_info,
            'navigate_to_document': self._navigate_to_document,
        }

        # Get current user
        user_name = ""
        if hasattr(self.app, 'user_config') and self.app.user_config:
            user_name = self.app.user_config.get_user_name()
        elif hasattr(self.app, 'get_current_user'):
            user_name = self.app.get_current_user()

        # Show the form with the pre-selected document
        self._correction_form.show(callbacks, user_name, pre_selected_document_name=doc_name)

    def _back_to_dashboard(self):
        """Navigate back to certificaciones dashboard."""
        if hasattr(self.app, 'show_certificacion_dashboard'):
            self.app.show_certificacion_dashboard()
        elif hasattr(self.app, '_show_handler_dashboard'):
            self.app._show_handler_dashboard(self)

    def _get_document_for_edit(self, doc_name: str):
        """Get document object for editing."""
        return self.get_document_by_id(doc_name)

    def _navigate_to_document(self, doc_name: str):
        """Navigate to a specific document."""
        if hasattr(self.app, 'navigate_to_document'):
            self.app.navigate_to_document(doc_name)

    def _update_document_info(self, old_name: str, new_name: str, display_name: str,
                              version: str, state: str, author: str, notes: str,
                              autor: str = "", rev_tecnica: str = "", rev_gerencia: str = ""):
        """Update certificacion document information via controller."""
        if not self.controller:
            raise Exception("Controller not initialized")

        if not hasattr(self.controller, 'update_document_info'):
            raise Exception("Controller does not support update_document_info")

        return self.controller.update_document_info(
            old_name, new_name, display_name,
            version, state, author, notes,
            autor, rev_tecnica, rev_gerencia
        )

    # === Monthly Certificacion Form ===

    def show_monthly_certificacion_form(self):
        """Show monthly certificacion form."""
        if not self._monthly_form:
            self._monthly_form = self._create_monthly_form()

        if not self._monthly_form:
            messagebox.showerror("Error", "No se pudo crear el formulario de certificacion mensual")
            return

        callbacks = {
            'back': self.show_dashboard,
            'get_all_certificaciones': self.get_documents,
            'get_available_adicionales': self._get_available_adicionales,
            'add_monthly_certification': self._add_monthly_certification,
            'get_current_user': lambda: self.app.get_current_user() if hasattr(self.app, 'get_current_user') else "",
        }

        user_name = self.app.user_config.get_user_name() if self.app.user_config else ""
        self._monthly_form.show(callbacks, user_name)

    def _create_monthly_form(self):
        """Create the monthly certificacion form."""
        try:
            from views.monthly_certificacion_form import MonthlyCertificacionForm
            return MonthlyCertificacionForm(self.app.root)
        except ImportError as e:
            print(f"Error importing MonthlyCertificacionForm: {e}")
            return None

    def _get_available_adicionales(self):
        """Get available adicionales for monthly certification."""
        if not self.controller:
            return []
        if hasattr(self.controller, 'get_available_adicionales'):
            return self.controller.get_available_adicionales()
        return []

    def _add_monthly_certification(self, *args, **kwargs):
        """Add monthly certification."""
        if not self.controller:
            raise Exception("Certificaciones controller not initialized")
        if hasattr(self.controller, 'add_monthly_certification'):
            return self.controller.add_monthly_certification(*args, **kwargs)
        raise NotImplementedError("add_monthly_certification not available")

    def open_file_by_filename(self, filename: str):
        """Open certificacion file location by filename."""
        try:
            storage_path = self.get_storage_path()
            file_path = storage_path / filename

            if file_path.exists():
                from utils.file_manager import FileManager
                FileManager.open_file_location(file_path)
            else:
                raise Exception(f"El archivo {filename} no existe")
        except Exception as e:
            raise Exception(f"No se pudo abrir la ubicacion del archivo: {str(e)}")

    # === Main Menu Callbacks ===

    def get_main_menu_callbacks(self) -> Dict:
        """Get specialized callbacks for certificaciones main menu."""
        return {
            'view_status': self.show_dashboard,
            'register_new_document': lambda: self.show_new_document_form(back_to_dashboard=False),
            'new_version': lambda: self.show_new_version_form(back_to_dashboard=False),
            'update_state': lambda: self.show_update_state_form(back_to_dashboard=False),
            'annotate_pdf': self.show_pdf_annotation_selector,
            'delete_files': self.show_delete_files_view,
            'monthly_form': self.show_monthly_certificacion_form,
            'config': lambda: self.app.show_config_screen() if hasattr(self.app, 'show_config_screen') else None,
            'get_current_user': lambda: self.app.get_current_user() if hasattr(self.app, 'get_current_user') else "",
            'navigate_to_document': lambda doc_id: self.app.navigate_to_document(doc_id) if hasattr(self.app, 'navigate_to_document') else None,
            'back': lambda: self.app.show_type_selection() if hasattr(self.app, 'show_type_selection') else None,
        }
