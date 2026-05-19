"""
Base Document Handler

Abstract base class that defines the common interface for all document type handlers.
Eliminates ~95% code duplication between Planos, Licitaciones, and Certificaciones.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import tkinter as tk
from tkinter import messagebox


class BaseDocumentHandler(ABC):
    """
    Abstract base class for document type handlers.

    Each document type (Planos, Licitaciones, Certificaciones) extends this class
    and implements the abstract methods for type-specific behavior.

    Common operations like showing dashboards, forms, and CRUD operations
    are implemented here once and shared across all document types.
    """

    def __init__(self, app_controller, controller, view_factory: Dict[str, Callable] = None):
        """
        Initialize the document handler.

        Args:
            app_controller: Reference to main app controller for navigation
            controller: The SQLite controller for this document type
            view_factory: Dictionary mapping view names to factory functions
        """
        self.app = app_controller
        self.controller = controller
        self.view_factory = view_factory or {}

        # View instances (created on demand)
        self._dashboard = None
        self._new_document_form = None
        self._new_version_form = None
        self._update_state_form = None
        self._delete_files_view = None
        self._correction_form = None

    # === Abstract Methods (must be implemented by subclasses) ===

    @abstractmethod
    def get_document_type(self) -> str:
        """Return the document type identifier (e.g., 'planos', 'licitaciones')."""
        pass

    @abstractmethod
    def get_storage_path(self) -> Path:
        """Return the storage path for this document type."""
        pass

    def validate_project_path(self) -> bool:
        """
        Validate that the current project path is set and exists.

        Returns:
            True if path is valid, False otherwise
        """
        if not self.app.current_project_path:
            return False

        project_path = Path(self.app.current_project_path)
        return project_path.exists() and project_path.is_dir()

    def get_validated_storage_path(self) -> Optional[Path]:
        """
        Get storage path with validation.

        Returns:
            Path object if valid, None if project path is not configured or doesn't exist
        """
        if not self.validate_project_path():
            return None
        return self.get_storage_path()

    @abstractmethod
    def get_display_name(self) -> str:
        """Return human-readable name for this document type."""
        pass

    @abstractmethod
    def get_state_map(self) -> Dict[str, str]:
        """Return the state mapping for this document type."""
        pass

    # === Document Operations (shared implementation) ===

    def get_documents(self) -> List:
        """Get all documents of this type."""
        if not self.controller:
            return []
        return self.controller.get_all_documents()

    def get_document_summaries(self) -> List:
        """Get document summaries for fast dashboard loading."""
        if not self.controller:
            return []
        if hasattr(self.controller, 'get_document_summaries'):
            return self.controller.get_document_summaries()
        return self.get_documents()

    def get_document_by_id(self, doc_id: str):
        """Get a specific document by ID."""
        if not self.controller:
            return None
        return self.controller.get_document(doc_id)

    def check_document_exists(self, doc_id: str) -> Optional[tuple]:
        """Check if document exists and return (name, version) or None."""
        document = self.get_document_by_id(doc_id)
        if document:
            return (document.name, getattr(document, 'version', '1.0'))
        return None

    def get_all_document_ids(self) -> List[str]:
        """Get all document IDs for fuzzy matching."""
        documents = self.get_documents()
        return [doc.id for doc in documents]

    def update_document_state(self, doc_id: str, new_state: str, author: str, notes: str,
                               file_paths: list = None, **kwargs) -> str:
        """Update document state with optional file paths."""
        if not self.controller:
            raise Exception(f"Controller not initialized for {self.get_document_type()}")

        # Check if controller supports file_paths parameter
        if file_paths and hasattr(self.controller, 'update_document_state'):
            import inspect
            sig = inspect.signature(self.controller.update_document_state)
            if 'file_paths' in sig.parameters:
                return self.controller.update_document_state(
                    doc_id, new_state, author, notes, file_paths=file_paths, **kwargs
                )

        # Fallback to basic call without file_paths
        return self.controller.update_document_state(doc_id, new_state, author, notes)

    def delete_entries(self, entry_specs: List[Dict]) -> str:
        """Delete specific document entries."""
        if not self.controller:
            raise Exception(f"Controller not initialized for {self.get_document_type()}")
        return self.controller.delete_document_entries(entry_specs)

    # === Navigation Callbacks ===

    def get_dashboard_callbacks(self) -> Dict[str, Callable]:
        """Get standard callbacks for dashboard views."""
        callbacks = {
            'back': self.app.show_main_menu,
            'new_document': lambda: self.show_new_document_form(back_to_dashboard=True),
            'new_version': lambda pre=None: self.show_new_version_form(back_to_dashboard=True, pre_selected=pre),
            'update_state': lambda pre=None: self.show_update_state_form(back_to_dashboard=True, pre_selected=pre),
            'delete_files': self.show_delete_files_view,
            'annotate_pdf': self.show_pdf_annotation_selector,
            'open_file': self.open_file_by_filename,
            'refresh_data': self.refresh_data,
            'get_document': self.get_document_by_id,
            'get_project_path': lambda: self.app.current_project_path,
            'navigate_to_document': self.app.navigate_to_document if hasattr(self.app, 'navigate_to_document') else None,
            'submit_new_document': self.submit_new_document,
            'submit_new_version': self.submit_new_version,
        }

        # Add controller-specific callbacks if available
        if self.controller:
            if hasattr(self.controller, 'open_document_location'):
                callbacks['open_document_location'] = self.controller.open_document_location
            if hasattr(self.controller, 'open_specific_file'):
                callbacks['open_specific_file'] = self.controller.open_specific_file
            if hasattr(self.controller, 'get_document_file_extensions'):
                callbacks['get_document_file_extensions'] = self.controller.get_document_file_extensions

        return callbacks

    def get_form_callbacks(self) -> Dict[str, Callable]:
        """Get standard callbacks for form views."""
        return {
            'back': self.app.context_aware_back,
            'check_document_exists': self.check_document_exists,
            'get_all_document_ids': self.get_all_document_ids,
            'get_document': self.get_document_by_id,
            'get_project_path': lambda: self.app.current_project_path,
            'navigate_to_document': self.app.navigate_to_document if hasattr(self.app, 'navigate_to_document') else None,
        }

    # === View Display Methods ===

    def show_dashboard(self, scroll_to_document: str = None):
        """Show the dashboard for this document type.

        Args:
            scroll_to_document: Optional document name to scroll to and select after loading
        """
        self.app.navigation_context = "dashboard"
        documents = self.get_document_summaries()
        callbacks = self.get_dashboard_callbacks()
        user_name = self.app.user_config.get_user_name() if self.app.user_config else ""

        dashboard = self._get_or_create_dashboard()
        if dashboard:
            dashboard.show(documents, callbacks, user_name, scroll_to_document=scroll_to_document)

    def show_new_document_form(self, back_to_dashboard: bool = False):
        """Show form to register a new document."""
        callbacks = self.get_form_callbacks()
        if back_to_dashboard:
            callbacks['back'] = self.show_dashboard
        callbacks['submit_new_document'] = self.submit_new_document

        # Add get_available_dwgs callback for DWG association (if controller supports it)
        if self.controller and hasattr(self.controller, 'get_available_dwgs'):
            callbacks['get_available_dwgs'] = self.controller.get_available_dwgs

        user_name = self.app.user_config.get_user_name() if self.app.user_config else ""
        form = self._get_or_create_new_document_form()
        if form:
            form.show(callbacks, user_name)

    def show_new_version_form(self, back_to_dashboard: bool = False, pre_selected: str = None):
        """Show form to register a new version."""
        callbacks = self.get_form_callbacks()
        if back_to_dashboard:
            callbacks['back'] = self.show_dashboard
        callbacks['submit_new_version'] = self.submit_new_version

        # Add get_available_dwgs callback for DWG association (if controller supports it)
        if self.controller and hasattr(self.controller, 'get_available_dwgs'):
            callbacks['get_available_dwgs'] = self.controller.get_available_dwgs

        user_name = self.app.user_config.get_user_name() if self.app.user_config else ""
        form = self._get_or_create_new_version_form()
        if form:
            form.show(callbacks, user_name, pre_selected)

    def show_update_state_form(self, back_to_dashboard: bool = False, pre_selected: str = None):
        """Show form to update document state."""
        callbacks = self.get_form_callbacks()
        if back_to_dashboard:
            callbacks['back'] = self.show_dashboard
        callbacks['update_document_state'] = self.update_document_state

        user_name = self.app.user_config.get_user_name() if self.app.user_config else ""
        form = self._get_or_create_update_state_form()
        if form:
            form.show(callbacks, user_name, pre_selected)

    def show_delete_files_view(self):
        """Show the delete files view."""
        documents = self.get_documents()
        callbacks = {
            'back': self.app.show_main_menu,
            'delete_entries': self.delete_entries,
            'open_file_location': self.open_file_by_filename,
            'refresh_documents': self.get_documents,
            'navigate_to_document': self.app.navigate_to_document if hasattr(self.app, 'navigate_to_document') else None,
        }
        user_name = self.app.user_config.get_user_name() if self.app.user_config else ""

        view = self._get_or_create_delete_files_view()
        if view:
            view.show(documents, callbacks, user_name)

    def show_correction_choice(self):
        """Show correction form."""
        callbacks = {
            'back': self.app.context_aware_back,
            'back_to_document': lambda doc_name: self.show_dashboard(scroll_to_document=doc_name),
            'get_document': self.get_document_by_id,
            'update_document_info': self.update_document_info,
            'navigate_to_document': self.app.navigate_to_document if hasattr(self.app, 'navigate_to_document') else None,
        }
        user_name = self.app.user_config.get_user_name() if self.app.user_config else ""

        form = self._get_or_create_correction_form()
        if form:
            form.show(callbacks, user_name)

    def show_pdf_annotation_selector(self):
        """Show PDF document selector for annotation/correction."""
        # Get documents that need correction
        all_documents = self.get_documents()
        correction_states = ['S1', 'S2', 'S3', 'A', 'B']

        documents = []
        for doc in all_documents:
            state = self._get_document_state(doc)
            if state in correction_states:
                documents.append(doc)

        if not documents:
            messagebox.showinfo(
                "Sin Documentos para Corrección",
                "No hay documentos en estados de corrección (S1, S2, S3, A, B)."
            )
            return

        self._show_pdf_correction_selector(documents)

    # === Helper Methods ===

    def _get_document_state(self, doc) -> str:
        """Get the current state of a document (handles different attribute names)."""
        return getattr(doc, 'current_state', getattr(doc, 'current_status', ''))

    def refresh_data(self):
        """Refresh document data from storage."""
        # Default implementation - can be overridden
        return self.get_documents()

    def open_file_by_filename(self, filename: str):
        """Open file location by filename."""
        try:
            storage_path = self.get_storage_path()
            file_path = storage_path / filename

            if file_path.exists():
                from utils.file_manager import FileManager
                FileManager.open_file_location(file_path)
            else:
                raise Exception(f"El archivo {filename} no existe")
        except Exception as e:
            raise Exception(f"No se pudo abrir la ubicación del archivo: {str(e)}")

    def update_document_info(self, *args, **kwargs):
        """Update document information. Override for type-specific implementation."""
        if hasattr(self.controller, 'update_document_info'):
            return self.controller.update_document_info(*args, **kwargs)
        raise NotImplementedError("update_document_info not implemented for this document type")

    def submit_new_document(self, *args, **kwargs):
        """Submit a new document. Override for type-specific implementation."""
        if hasattr(self.controller, 'add_new_document'):
            return self.controller.add_new_document(*args, **kwargs)
        if hasattr(self.controller, 'add_new_version'):
            return self.controller.add_new_version(*args, **kwargs)
        raise NotImplementedError("submit_new_document not implemented for this document type")

    def submit_new_version(self, *args, **kwargs):
        """Submit a new version. Override for type-specific implementation."""
        if hasattr(self.controller, 'add_new_version'):
            return self.controller.add_new_version(*args, **kwargs)
        raise NotImplementedError("submit_new_version not implemented for this document type")

    # === View Factory Methods (lazy creation) ===

    def _get_or_create_dashboard(self):
        """Get or create the dashboard view."""
        if self._dashboard is None and 'dashboard' in self.view_factory:
            self._dashboard = self.view_factory['dashboard']()
        return self._dashboard

    def _get_or_create_new_document_form(self):
        """Get or create the new document form."""
        if self._new_document_form is None and 'new_document_form' in self.view_factory:
            self._new_document_form = self.view_factory['new_document_form']()
        return self._new_document_form

    def _get_or_create_new_version_form(self):
        """Get or create the new version form."""
        if self._new_version_form is None and 'new_version_form' in self.view_factory:
            self._new_version_form = self.view_factory['new_version_form']()
        return self._new_version_form

    def _get_or_create_update_state_form(self):
        """Get or create the update state form."""
        if self._update_state_form is None and 'update_state_form' in self.view_factory:
            self._update_state_form = self.view_factory['update_state_form']()
        return self._update_state_form

    def _get_or_create_delete_files_view(self):
        """Get or create the delete files view."""
        if self._delete_files_view is None and 'delete_files_view' in self.view_factory:
            self._delete_files_view = self.view_factory['delete_files_view']()
        return self._delete_files_view

    def _get_or_create_correction_form(self):
        """Get or create the correction form."""
        if self._correction_form is None and 'correction_form' in self.view_factory:
            self._correction_form = self.view_factory['correction_form']()
        return self._correction_form

    def _show_pdf_correction_selector(self, documents):
        """Show dialog to select document for PDF correction."""
        dialog = tk.Toplevel(self.app.root)
        dialog.title("Seleccionar Documento para Corrección")
        dialog.geometry("600x400")
        dialog.transient(self.app.root)
        dialog.grab_set()

        def on_cancel():
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        # Header
        header_label = tk.Label(
            dialog,
            text="Selecciona un documento para corregir:",
            font=("Arial", 12, "bold")
        )
        header_label.pack(pady=10)

        # Document list
        frame = tk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=10)

        from tkinter import ttk
        tree = ttk.Treeview(
            frame,
            columns=("ID", "Nombre", "Estado", "Versión"),
            show="headings"
        )
        tree.heading("ID", text="ID")
        tree.heading("Nombre", text="Nombre")
        tree.heading("Estado", text="Estado")
        tree.heading("Versión", text="Versión")

        tree.column("ID", width=100)
        tree.column("Nombre", width=300)
        tree.column("Estado", width=80)
        tree.column("Versión", width=80)

        for doc in documents:
            doc_id = getattr(doc, 'id', getattr(doc, 'name', 'N/A'))
            doc_name = getattr(doc, 'name', 'N/A')
            doc_state = self._get_document_state(doc)
            doc_version = getattr(doc, 'current_version', getattr(doc, 'version', 'N/A'))
            tree.insert("", "end", values=(doc_id, doc_name, doc_state, doc_version))

        tree.pack(fill="both", expand=True)

        # Buttons
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)

        def on_select():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("Selección", "Por favor selecciona un documento.")
                return

            item = tree.item(selection[0])
            doc_id = item['values'][0]
            dialog.destroy()
            self._annotate_document_by_id(doc_id)

        tk.Button(
            button_frame,
            text="Corregir",
            command=on_select,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold")
        ).pack(side="left", padx=10)

        tk.Button(
            button_frame,
            text="Cancelar",
            command=on_cancel
        ).pack(side="left", padx=10)

    def _annotate_document_by_id(self, doc_id: str):
        """Launch PDF annotation for a document. Override for type-specific implementation."""
        # Default implementation - should be overridden by subclasses
        document = self.get_document_by_id(doc_id)
        if not document:
            messagebox.showerror("Error", f"Documento no encontrado: {doc_id}")
            return

        # Try to get PDF corrector from app
        pdf_corrector = getattr(self.app, 'pdf_corrector', None)
        if not pdf_corrector:
            messagebox.showerror("Error", "Corrector PDF no disponible")
            return

        # Get PDF file path
        storage_path = self.get_storage_path()
        # This is a simplified implementation - subclasses should override
        messagebox.showinfo("Info", f"Annotation for {doc_id} - implement in subclass")
