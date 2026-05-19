"""
Handler Factory

Creates and manages document handlers based on document type.
Provides a single point of instantiation for all handler types.
"""

from pathlib import Path
from typing import Dict, Optional, Callable, Any
import tkinter as tk

from .base_handler import BaseDocumentHandler
from .planos_handler import PlanosHandler
from .licitaciones_handler import LicitacionesHandler
from .certificaciones_handler import CertificacionesHandler


class HandlerFactory:
    """
    Factory for creating document handlers.

    Centralizes handler creation and view factory configuration.
    """

    # Mapping of document types to handler classes
    HANDLER_CLASSES = {
        'planos': PlanosHandler,
        'licitaciones': LicitacionesHandler,
        'certificaciones': CertificacionesHandler,
    }

    def __init__(self, app_controller):
        """
        Initialize the handler factory.

        Args:
            app_controller: Reference to the main app controller
        """
        self.app = app_controller
        self._handlers: Dict[str, BaseDocumentHandler] = {}

    def get_handler(self, doc_type: str) -> Optional[BaseDocumentHandler]:
        """
        Get or create a handler for the specified document type.

        Args:
            doc_type: The document type ('planos', 'licitaciones', 'certificaciones')

        Returns:
            The handler instance, or None if doc_type is not supported
        """
        if doc_type not in self.HANDLER_CLASSES:
            return None

        # Return cached handler if available and project hasn't changed
        if doc_type in self._handlers:
            handler = self._handlers[doc_type]
            # Check if project path is still the same
            if handler.app.current_project_path == self.app.current_project_path:
                return handler

        # Create new handler
        handler = self._create_handler(doc_type)
        self._handlers[doc_type] = handler
        return handler

    def _create_handler(self, doc_type: str) -> BaseDocumentHandler:
        """
        Create a new handler instance for the specified document type.

        Args:
            doc_type: The document type

        Returns:
            New handler instance
        """
        handler_class = self.HANDLER_CLASSES[doc_type]
        controller = self._get_controller_for_type(doc_type)
        view_factory = self._get_view_factory_for_type(doc_type)

        handler = handler_class(self.app, controller, view_factory)

        # Set up XREF callback for planos
        if doc_type == 'planos' and hasattr(handler, 'set_xref_progress_callback'):
            if hasattr(self.app, '_on_xref_progress'):
                handler.set_xref_progress_callback(self.app._on_xref_progress)

        return handler

    def _get_controller_for_type(self, doc_type: str):
        """
        Get the controller for the specified document type.

        Creates the controller if it doesn't exist.
        """
        project_path = Path(self.app.current_project_path) if self.app.current_project_path else None

        if not project_path:
            return None

        if doc_type == 'planos':
            if not self.app.document_controller:
                from controllers.sqlite_planos_controller import SQLitePlanosController
                self.app.document_controller = SQLitePlanosController(project_path)
            return self.app.document_controller

        elif doc_type == 'licitaciones':
            if not self.app.licitacion_controller:
                from controllers.sqlite_licitacion_controller import SQLiteLicitacionController
                self.app.licitacion_controller = SQLiteLicitacionController(project_path)
            return self.app.licitacion_controller

        elif doc_type == 'certificaciones':
            if not hasattr(self.app, 'certificacion_controller') or not self.app.certificacion_controller:
                cert_path = project_path / "04_Certificaciones"
                from controllers.certificacion_controller import CertificacionController
                self.app.certificacion_controller = CertificacionController(cert_path, project_path)
            return self.app.certificacion_controller

        return None

    def _get_view_factory_for_type(self, doc_type: str) -> Dict[str, Callable]:
        """
        Get view factory functions for the specified document type.

        Returns a dictionary mapping view names to factory functions.
        """
        root = self.app.root
        project_path = Path(self.app.current_project_path) if self.app.current_project_path else None

        if doc_type == 'planos':
            return {
                'dashboard': lambda: self._create_planos_dashboard(root),
                'new_document_form': lambda: self._create_new_document_form(root, doc_type),
                'new_version_form': lambda: self._create_new_version_form(root, doc_type),
                'update_state_form': lambda: self._create_update_state_form(root, doc_type),
                'delete_files_view': lambda: self._create_delete_files_view(root, doc_type, project_path),
                'correction_form': lambda: self._create_correction_form(root, doc_type, project_path),
            }

        elif doc_type == 'licitaciones':
            return {
                'dashboard': lambda: self._create_licitacion_dashboard(root),
                'new_document_form': lambda: self._create_licitacion_form(root),
                'new_version_form': lambda: self._create_licitacion_form(root),
                'delete_files_view': lambda: self._create_delete_files_view(root, doc_type, project_path),
                'correction_form': lambda: self._create_correction_form(root, doc_type, project_path),
            }

        elif doc_type == 'certificaciones':
            return {
                'dashboard': lambda: self._create_certificacion_dashboard(root),
                'delete_files_view': lambda: self._create_delete_files_view(root, doc_type, project_path),
                'correction_form': lambda: self._create_correction_form(root, doc_type, project_path),
            }

        return {}

    # === View Creation Methods ===

    def _create_planos_dashboard(self, root):
        from views.planos_dashboard import PlanosDashboard
        return PlanosDashboard(root)

    def _create_licitacion_dashboard(self, root):
        from views.licitacion_dashboard import LicitacionDashboard
        return LicitacionDashboard(root)

    def _create_certificacion_dashboard(self, root):
        # Certificaciones may use a different dashboard or main menu
        from views.centralized_main_menu_view import CentralizedMainMenuView
        return CentralizedMainMenuView(root, 'certificaciones')

    def _create_new_document_form(self, root, doc_type):
        from views.new_document_form import NewDocumentForm
        return NewDocumentForm(root, doc_type)

    def _create_new_version_form(self, root, doc_type):
        from views.new_version_form import NewVersionForm
        return NewVersionForm(root, doc_type)

    def _create_update_state_form(self, root, doc_type):
        from views.update_state_form import UpdateStateForm
        state_map = self._get_state_map_for_type(doc_type)
        return UpdateStateForm(root, doc_type, state_map)

    def _create_delete_files_view(self, root, doc_type, project_path):
        from views.delete_files_view import DeleteFilesView
        from config.settings import StatusConfig
        status_config = StatusConfig(project_path) if project_path else StatusConfig()
        return DeleteFilesView(root, status_config, doc_type)

    def _create_correction_form(self, root, doc_type, project_path):
        from views.correction_form import CorrectionForm
        from config.settings import StatusConfig
        status_config = StatusConfig(project_path) if project_path else StatusConfig()
        return CorrectionForm(root, doc_type, status_config.STATE_MAP)

    def _create_licitacion_form(self, root):
        from views.licitacion_form import LicitacionForm
        return LicitacionForm(root)

    def _get_state_map_for_type(self, doc_type: str) -> Dict[str, str]:
        """Get the state mapping for a document type."""
        if doc_type == 'planos':
            from models.plano_document import STATE_DISPLAY_NAMES
            return STATE_DISPLAY_NAMES
        else:
            from config.settings import StatusConfig
            project_path = Path(self.app.current_project_path) if self.app.current_project_path else None
            status_config = StatusConfig(project_path) if project_path else StatusConfig()
            return status_config.STATE_MAP

    def clear_handlers(self):
        """Clear all cached handlers (call when project changes)."""
        self._handlers.clear()

    def has_handler(self, doc_type: str) -> bool:
        """Check if a handler exists for the document type."""
        return doc_type in self._handlers
