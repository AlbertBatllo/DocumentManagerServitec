"""
Licitaciones Document Handler

Handles Licitaciones (Presupuestos/Bids) specific operations.
Extends BaseDocumentHandler with Licitaciones-specific functionality.
"""

from pathlib import Path
from typing import Dict, List, Optional
from tkinter import messagebox

from .base_handler import BaseDocumentHandler


class LicitacionesHandler(BaseDocumentHandler):
    """
    Handler for Licitaciones (Presupuestos/Bids) documents.

    Licitaciones have specific requirements:
    - Workflow stages (Borrador, Enviado, Adjudicado, etc.)
    - Budget tracking with valor, lote, empresa fields
    - Technical and management review tracking
    """

    def get_document_type(self) -> str:
        return "licitaciones"

    def get_storage_path(self) -> Path:
        """
        Get the storage path for Licitaciones documents.

        Returns:
            Path to 03_Licitaciones folder within the current project.
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

        return project_path / "03_Licitaciones"

    def get_display_name(self) -> str:
        return "Licitaciones"

    def get_state_map(self) -> Dict[str, str]:
        # Licitaciones use a different state model based on workflow stages
        return {
            'S0': 'Borrador',
            'S1': 'En Revisión',
            'S2': 'Enviado',
            'S3': 'Adjudicado',
            'A': 'Aprobado',
            'B': 'Rechazado',
        }

    # === Licitaciones-specific Methods ===

    def get_documents_for_dashboard(self) -> List:
        """Get documents with fast summary loading for dashboard."""
        if not self.controller:
            return []
        if hasattr(self.controller, 'get_document_summaries'):
            return self.controller.get_document_summaries()
        return self.get_documents()

    def update_document_info(self, old_id: str, new_id: str, name: str, version: str,
                             state: str, author: str, notes: str, autor: str = None,
                             rev_tecnica: str = None, rev_gerencia: str = None,
                             valor: str = None, lote: str = None, empresa: str = None,
                             tipo: str = None):
        """Update licitacion document information with all fields."""
        if not self.controller:
            raise Exception("Licitaciones controller not initialized")
        if hasattr(self.controller, 'update_document_info'):
            return self.controller.update_document_info(
                old_id, new_id, name, version, state, author, notes,
                autor, rev_tecnica, rev_gerencia, valor, lote, empresa, tipo
            )
        raise NotImplementedError("update_document_info not available")

    def refresh_data(self):
        """Refresh licitaciones data."""
        if self.controller and hasattr(self.controller, 'refresh_data'):
            return self.controller.refresh_data()
        return self.get_documents()

    def _annotate_document_by_id(self, doc_id: str):
        """Launch PDF annotation for a licitacion document."""
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

        # Search for PDF files
        for pdf_file in storage_path.rglob(f"*{document.name}*.pdf"):
            pdf_path = pdf_file
            break

        if not pdf_path or not pdf_path.exists():
            messagebox.showerror(
                "Error",
                f"No se encontró el archivo PDF para el documento {document.name}"
            )
            return

        # Launch annotation
        callbacks = {
            'save_annotations': lambda anns: self._save_annotations(doc_id, anns),
            'back': self.show_dashboard,
        }
        pdf_corrector.annotate_pdf(str(pdf_path), callbacks)

    def _save_annotations(self, doc_id: str, annotations: dict):
        """Save PDF annotations for a licitacion document."""
        pass

    # === Override Dashboard Callbacks ===

    def get_dashboard_callbacks(self) -> Dict:
        """
        Get callbacks for licitaciones dashboard with all licitaciones-specific functionality.
        """
        # Get base callbacks
        callbacks = super().get_dashboard_callbacks()

        # Add licitaciones-specific callbacks
        if self.controller:
            # File management callbacks
            if hasattr(self.controller, 'get_document_files_info'):
                callbacks['get_current_files'] = self.controller.get_document_files_info

            # Document info editing
            if hasattr(self.controller, 'update_document_info'):
                callbacks['edit_document_info'] = self.show_edit_document_info_form

            # Cloud sync
            if hasattr(self.controller, 'sync_document_to_cloud'):
                callbacks['sync_to_cloud'] = self.controller.sync_document_to_cloud
            if hasattr(self.controller, 'is_cloud_sync_enabled'):
                callbacks['is_cloud_enabled'] = self.controller.is_cloud_sync_enabled

        # Refresh callback specific to licitaciones
        callbacks['refresh_licitaciones'] = self.refresh_data

        return callbacks

    def show_edit_document_info_form(self, doc_name: str = None):
        """Show form to edit licitacion document information using CorrectionForm."""
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
                "licitaciones",
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
        """Navigate back to licitaciones dashboard."""
        if hasattr(self.app, 'show_licitacion_dashboard'):
            self.app.show_licitacion_dashboard()
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
                              autor: str = "", rev_tecnica: str = "", rev_gerencia: str = "",
                              valor: str = None, lote: str = None, empresa: str = None, tipo: str = None):
        """Update licitacion document information via controller."""
        if not self.controller:
            raise Exception("Controller not initialized")

        if not hasattr(self.controller, 'update_document_info'):
            raise Exception("Controller does not support update_document_info")

        return self.controller.update_document_info(
            old_name, new_name, display_name,
            version, state, author, notes,
            autor, rev_tecnica, rev_gerencia,
            valor=valor, lote=lote, empresa=empresa, tipo=tipo
        )

    def open_file_by_filename(self, filename: str):
        """Open licitacion file location by filename.

        Licitaciones files are organized in stage directories:
        - presupuestos/
        - mediciones/
        - adicionales/
        """
        try:
            from utils.file_manager import FileManager

            # Get base folder for licitaciones (03_Presupuestos in legacy structure)
            base_folder = self.get_storage_path()
            if not base_folder.exists():
                base_folder = Path(self.app.current_project_path) / "03_Presupuestos"

            # Search across all licitacion stage directories
            stage_dirs = [
                base_folder / "presupuestos",
                base_folder / "mediciones",
                base_folder / "adicionales",
                base_folder,  # Also check root folder
            ]

            for stage_dir in stage_dirs:
                file_path = stage_dir / filename
                if file_path.exists():
                    FileManager.open_file_location(file_path)
                    return

            raise Exception(f"El archivo {filename} no existe")
        except Exception as e:
            raise Exception(f"No se pudo abrir la ubicacion del archivo: {str(e)}")

    def delete_entries(self, entry_specs: List[Dict]) -> str:
        """Delete specific licitacion document entries."""
        if not self.controller:
            raise Exception("Licitaciones controller not initialized")
        if hasattr(self.controller, 'delete_document_entries'):
            return self.controller.delete_document_entries(entry_specs)
        raise NotImplementedError("delete_document_entries not available")

    # === Main Menu Callbacks ===

    def get_main_menu_callbacks(self) -> Dict:
        """Get specialized callbacks for licitaciones main menu."""
        return {
            'view_status': self.show_dashboard,
            'register_new_document': lambda: self.show_new_document_form(back_to_dashboard=False),
            'new_version': lambda: self.show_new_version_form(back_to_dashboard=False),
            'update_state': lambda: self.show_update_state_form(back_to_dashboard=False),
            'annotate_pdf': self.show_pdf_annotation_selector,
            'delete_files': self.show_delete_files_view,
            'config': lambda: self.app.show_config_screen() if hasattr(self.app, 'show_config_screen') else None,
            'get_current_user': lambda: self.app.get_current_user() if hasattr(self.app, 'get_current_user') else "",
            'navigate_to_document': lambda doc_id: self.app.navigate_to_document(doc_id) if hasattr(self.app, 'navigate_to_document') else None,
            'back': lambda: self.app.show_type_selection() if hasattr(self.app, 'show_type_selection') else None,
        }

    def annotate_selected_document(self, doc_name: str = None):
        """Annotate the selected licitacion document."""
        if doc_name:
            self._annotate_document_by_id(doc_name)
        else:
            messagebox.showwarning("Aviso", "Por favor seleccione un documento para anotar")
