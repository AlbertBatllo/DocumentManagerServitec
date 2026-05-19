#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App Controller - Main Application Orchestrator

This is the clean entry point for the Document Manager application.
It handles shared infrastructure and delegates document-type-specific
operations to the appropriate handlers.
"""

import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk
import sys
import os
from pathlib import Path
from typing import Optional


def _safe_print(message: str):
    """
    Safe print function that works in Windows GUI apps without console.
    In windowed mode, stdout/stderr may be None, causing print() to fail.
    """
    try:
        if sys.stdout is not None:
            # Use builtins.print directly to avoid any issues
            import builtins
            builtins.print(message)
            sys.stdout.flush()
    except (OSError, AttributeError, TypeError):
        # Silently ignore print errors in GUI mode
        pass


# Set UTF-8 encoding for Windows compatibility (only if stdout exists)
if sys.platform.startswith('win'):
    import codecs
    try:
        if sys.stdout is not None and hasattr(sys.stdout, 'detach'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
        if sys.stderr is not None and hasattr(sys.stderr, 'detach'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
    except (OSError, AttributeError):
        # In windowed mode, stdout/stderr may not be available
        pass


class AppController:
    """
    Main application controller that orchestrates the Document Manager.

    Responsibilities:
    - Initialize shared infrastructure (window, configs)
    - Handle project and document type selection
    - Delegate document operations to type-specific handlers
    """

    # Minimum required version for tkinterdnd2 (if version checking is available)
    TKINTERDND2_MIN_VERSION = "0.3.0"

    def __init__(self):
        """Initialize the application."""
        # Run startup health checks
        self._run_startup_health_checks()

        # Initialize drag-and-drop enabled root window
        self._initialize_root_window()

        # Initialize configurations
        self._initialize_configurations()

        # Initialize handler factory and navigation
        self._initialize_handlers_and_navigation()

        # Initialize state variables
        self._initialize_state()

        # Initialize view references
        self._initialize_view_references()

        # Refresh authentication tokens on startup
        self._refresh_authentication_tokens()

        # Validate configuration
        self._validate_configuration()

        # Ensure user is configured
        self._ensure_user_configured()

    # === Initialization Helper Methods ===

    def _run_startup_health_checks(self):
        """Run health checks for critical dependencies at startup."""
        health_status = {
            'tkinter': False,
            'sqlite3': False,
            'pathlib': False,
        }

        # Check tkinter
        try:
            import tkinter as tk
            health_status['tkinter'] = True
        except ImportError as e:
            _safe_print(f"[CRITICAL] tkinter not available: {e}")

        # Check sqlite3
        try:
            import sqlite3
            health_status['sqlite3'] = True
        except ImportError as e:
            _safe_print(f"[CRITICAL] sqlite3 not available: {e}")

        # Check pathlib
        try:
            from pathlib import Path
            health_status['pathlib'] = True
        except ImportError as e:
            _safe_print(f"[CRITICAL] pathlib not available: {e}")

        # Check optional dependencies
        self._check_optional_dependencies()

        # Fail if critical dependencies are missing
        critical_missing = [dep for dep, status in health_status.items() if not status]
        if critical_missing:
            raise RuntimeError(
                f"Critical dependencies missing: {', '.join(critical_missing)}. "
                "Please install the required dependencies."
            )

        _safe_print("[OK] All critical dependencies available")

    def _check_optional_dependencies(self):
        """Check and report status of optional dependencies."""
        # Check tkinterdnd2 with version validation
        try:
            import tkinterdnd2
            version = getattr(tkinterdnd2, '__version__', None)
            if version:
                print(f"[OK] tkinterdnd2 version {version} available")
                # Version comparison if available
                try:
                    from packaging import version as pkg_version
                    if pkg_version.parse(version) < pkg_version.parse(self.TKINTERDND2_MIN_VERSION):
                        print(f"[WARNING] tkinterdnd2 version {version} is below minimum "
                              f"recommended version {self.TKINTERDND2_MIN_VERSION}")
                except ImportError:
                    pass  # packaging not available, skip version check
            else:
                print("[OK] tkinterdnd2 available (version unknown)")
        except ImportError:
            _safe_print("[INFO] tkinterdnd2 not installed - drag-and-drop will be disabled")

        # Check ezdxf for CAD support
        try:
            import ezdxf
            version = getattr(ezdxf, '__version__', 'unknown')
            _safe_print(f"[OK] ezdxf version {version} available for CAD support")
        except ImportError:
            _safe_print("[INFO] ezdxf not installed - some CAD features may be limited")

    def _initialize_configurations(self):
        """Initialize configuration objects."""
        from config.settings import UserConfig, StatusConfig
        self.user_config = UserConfig()
        self.status_config: Optional[StatusConfig] = None

    def _initialize_handlers_and_navigation(self):
        """Initialize handler factory and navigation manager."""
        from document_handlers import HandlerFactory
        from app.navigation import NavigationManager
        self._handler_factory = HandlerFactory(self)
        self._navigation_manager = NavigationManager()
        self._current_handler = None

    def _initialize_state(self):
        """Initialize application state variables."""
        # Current state
        self.current_project_name: Optional[str] = None
        self.current_project_path: Optional[str] = None
        self.current_doc_type: Optional[str] = None
        self.navigation_context = "main_menu"

        # Controller references (created on demand by handlers)
        self.document_controller = None  # Planos
        self.licitacion_controller = None  # Licitaciones
        self.certificacion_controller = None  # Certificaciones

    def _initialize_view_references(self):
        """Initialize view references (created on demand)."""
        # Shared views
        self._project_selection_view = None
        self._type_selection_view = None
        self._config_view = None

        # PDF corrector (shared across all document types)
        self._pdf_corrector = None

    def _validate_configuration(self):
        """Validate configuration during startup."""
        errors = []

        # Validate UserConfig
        if not self.user_config:
            errors.append("UserConfig not initialized")

        # Check if config directory is writable
        try:
            from pathlib import Path
            config_dir = Path.home() / ".document_manager"
            if config_dir.exists() and not config_dir.is_dir():
                errors.append(f"Config path exists but is not a directory: {config_dir}")
        except Exception as e:
            errors.append(f"Cannot access config directory: {e}")

        if errors:
            for error in errors:
                print(f"[WARNING] Configuration issue: {error}")

    # === Window Initialization ===

    def _initialize_root_window(self):
        """Initialize the root window with optional drag-and-drop support."""
        try:
            import tkinterdnd2
            self.root = tkinterdnd2.Tk()
            _safe_print("[OK] Drag-and-drop support enabled")
        except ImportError:
            self.root = tk.Tk()
            _safe_print("[WARNING] tkinterdnd2 not available - drag-and-drop disabled")
        except Exception as e:
            _safe_print(f"[WARNING] Could not initialize drag-and-drop: {e}")
            self.root = tk.Tk()

        self.root.title("Gestor Centralizado de Documentos")
        self.root.geometry("800x700")
        self.root.resizable(True, True)

        self._apply_platform_styling()

    def _apply_platform_styling(self):
        """Apply platform-specific styling."""
        import platform
        current_platform = platform.system()

        try:
            if current_platform == "Windows":
                self.root.configure(bg="#2C2C2C")
                style = ttk.Style()
                style.theme_use('clam')

                style.configure("TFrame", background="#2C2C2C")
                style.configure("TLabel", background="#2C2C2C", foreground="white")
                style.configure("TButton",
                               background="#404040",
                               foreground="#FFFFFF",
                               borderwidth=2,
                               font=("Arial", 9, "bold"))
                style.map("TButton",
                         background=[('active', '#5A5A5A'), ('pressed', '#2A2A2A')],
                         foreground=[('active', '#FFFFFF'), ('pressed', '#FFFFFF')])
                style.configure("TEntry", fieldbackground="#404040", foreground="white")
                style.configure("Treeview", background="#404040", foreground="white",
                               fieldbackground="#404040")
                style.configure("Treeview.Heading", background="#505050", foreground="white")
                print("[OK] Applied Windows dark theme styling")
            elif current_platform == "Darwin":
                print("[OK] macOS styling preserved")
            else:
                self.root.configure(bg="#2C2C2C")
                print(f"[OK] Applied dark theme for {current_platform}")
        except Exception as e:
            _safe_print(f"[WARNING] Could not apply platform-specific styling: {e}")

    # === UI Helper Methods ===

    def _clear_window(self):
        """Clear all widgets from the window."""
        for widget in self.root.winfo_children():
            widget.destroy()

    def _center_window(self, width: int, height: int):
        """Center the window on the screen."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _create_header(self, parent, title: str):
        """Create a header for the window."""
        header_frame = ttk.Frame(parent, padding="20")
        header_frame.pack(fill="x")

        ttk.Label(
            header_frame,
            text=title,
            font=("Arial", 16, "bold")
        ).pack()

    # === Authentication ===

    def _refresh_authentication_tokens(self):
        """Refresh cloud authentication tokens on startup."""
        try:
            from pathlib import Path
            home_path = Path.home()

            potential_paths = [
                home_path / "Desktop",
                home_path / "Documents",
                home_path,
                Path.cwd()
            ]

            project_path = None
            for base_path in potential_paths:
                if base_path.exists():
                    prj_dirs = list(base_path.glob("PRJ-*"))
                    if prj_dirs:
                        project_path = prj_dirs[0]
                        break

            if project_path:
                from config.settings import CloudConfig
                from utils.token_refresh import TokenRefreshManager
                cloud_config = CloudConfig(project_path)
                token_manager = TokenRefreshManager(cloud_config)
                refresh_results = token_manager.check_and_refresh_tokens()

                if refresh_results.get("sharepoint_refreshed"):
                    print("[OK] SharePoint tokens refreshed automatically")
                if refresh_results.get("google_drive_refreshed"):
                    print("[OK] Google Drive tokens refreshed automatically")
                if not any(refresh_results.values()):
                    print("[OK] Authentication tokens are still valid")
            else:
                print("[INFO] No project found for token refresh - skipping")
        except Exception as e:
            _safe_print(f"[WARNING] Token refresh failed: {e}")

    def _refresh_project_tokens(self, project_path: str):
        """Refresh tokens for a specific project."""
        try:
            from config.settings import CloudConfig
            from utils.token_refresh import TokenRefreshManager

            cloud_config = CloudConfig(Path(project_path))
            token_manager = TokenRefreshManager(cloud_config)
            refresh_results = token_manager.check_and_refresh_tokens()

            refreshed = []
            if refresh_results.get("sharepoint_refreshed"):
                refreshed.append("SharePoint")
            if refresh_results.get("google_drive_refreshed"):
                refreshed.append("Google Drive")

            if refreshed:
                print(f"[OK] Refreshed tokens for: {', '.join(refreshed)}")
            else:
                print("[OK] All authentication tokens are current")
        except Exception as e:
            _safe_print(f"[WARNING] Could not refresh project tokens: {e}")

    # === User Configuration ===

    def _ensure_user_configured(self):
        """Ensure user name is configured."""
        if not self.user_config.get_user_name():
            self._prompt_user_configuration()

    def _prompt_user_configuration(self):
        """Prompt user to configure their name."""
        import tkinter.simpledialog as simpledialog

        user_name = simpledialog.askstring(
            "Configuración de Usuario",
            "Por favor, ingrese su nombre de usuario:",
            parent=self.root
        )

        if user_name and user_name.strip():
            self.user_config.set_user_name(user_name.strip())
            _safe_print(f"[OK] Usuario configurado: {user_name.strip()}")
        else:
            messagebox.showwarning(
                "Configuración Requerida",
                "Se requiere un nombre de usuario para continuar."
            )
            self._prompt_user_configuration()

    def get_current_user(self) -> str:
        """Get the current user name."""
        return self.user_config.get_user_name() if self.user_config else ""

    # === Navigation: Project Selection ===

    def show_project_selection(self):
        """Show the project selection screen."""
        if not self._project_selection_view:
            from views.project_selection_view import ProjectSelectionView
            self._project_selection_view = ProjectSelectionView(self.root)

        user_name = self.get_current_user()
        self._project_selection_view.show(self.on_project_selected, user_name, None)

    def on_project_selected(self, project_name: str, project_path: str):
        """Handle project selection."""
        self.current_project_name = project_name
        self.current_project_path = project_path

        # Ensure .project_manager directory exists
        try:
            from utils.path_helper import PathHelper
            PathHelper.ensure_project_manager_exists(Path(project_path))
        except OSError as e:
            messagebox.showerror(
                "Error de Permisos",
                f"No se pudo crear la carpeta '.project_manager'.\n\nError: {e}"
            )
            return

        # Update window title
        self.root.title(f"Gestor de Documentos - {project_name}")

        # Update navigation state
        self._navigation_manager.set_project(project_name, project_path)
        self._handler_factory.clear_handlers()

        # Refresh tokens for this project
        self._refresh_project_tokens(project_path)

        # Load status config for this project
        from config.settings import StatusConfig
        self.status_config = StatusConfig(Path(project_path))

        self.show_type_selection()

    # === Navigation: Document Type Selection ===

    def show_type_selection(self):
        """Show the document type selection screen."""
        if not self._type_selection_view:
            from views.centralized_type_selection_view import CentralizedTypeSelectionView
            self._type_selection_view = CentralizedTypeSelectionView(self.root)

        self._type_selection_view.set_project_context(
            self.current_project_name,
            self.current_project_path
        )

        user_name = self.get_current_user()
        self._type_selection_view.show(
            self.on_type_selected,
            self.show_project_selection,
            user_name,
            None
        )

    def on_type_selected(self, doc_type: str, doc_folder: str):
        """Handle document type selection."""
        self.current_doc_type = doc_type
        self._navigation_manager.set_doc_type(doc_type)

        # Get handler for this document type
        self._current_handler = self._handler_factory.get_handler(doc_type)

        if self._current_handler:
            # Use handler to show appropriate view
            self.show_main_menu()
        else:
            messagebox.showerror(
                "Error",
                f"No hay manejador disponible para el tipo: {doc_type}"
            )

    # === Navigation: Main Menu ===

    def show_main_menu(self):
        """Show the main menu for the current document type."""
        self.navigation_context = "main_menu"

        if not self._current_handler:
            self.show_type_selection()
            return

        # Get callbacks for the main menu
        callbacks = self._get_main_menu_callbacks()

        # Create main menu view
        from views.centralized_main_menu_view import CentralizedMainMenuView
        main_menu = CentralizedMainMenuView(self.root, self.current_doc_type)
        main_menu.set_project_context(self.current_project_name)
        main_menu.show(callbacks)

    def _get_main_menu_callbacks(self) -> dict:
        """Get callbacks for the main menu based on current document type."""
        handler = self._current_handler

        return {
            'view_status': handler.show_dashboard if handler else None,
            'register_new_document': lambda: handler.show_new_document_form(back_to_dashboard=False) if handler else None,
            'new_version': lambda: handler.show_new_version_form(back_to_dashboard=False) if handler else None,
            'update_state': lambda: handler.show_update_state_form(back_to_dashboard=False) if handler else None,
            'annotate_pdf': handler.show_pdf_annotation_selector if handler else None,
            'delete_files': handler.show_delete_files_view if handler else None,
            'config': self.show_config_screen,
            'get_current_user': self.get_current_user,
            'navigate_to_document': self.navigate_to_document,
            'back': self.show_type_selection,
        }

    # === Navigation Utilities ===

    def context_aware_back(self):
        """Navigate back based on current context."""
        context = self.navigation_context

        if context == "dashboard":
            self.show_main_menu()
        elif context == "form":
            self.show_main_menu()
        elif context == "main_menu":
            self.show_type_selection()
        else:
            self.show_main_menu()

    def context_aware_back_optimized(self):
        """
        Optimized back navigation that avoids recreating heavy views.
        Simply refreshes the dashboard if returning from a form.
        """
        context = self.navigation_context

        if context == "dashboard":
            # If we have an active handler with a dashboard, just refresh it
            if (self._current_handler and
                hasattr(self, '_preserve_current_view') and
                self._preserve_current_view):
                try:
                    # Use optimized refresh instead of recreating the entire view
                    if hasattr(self._current_handler, 'refresh_data'):
                        self._current_handler.refresh_data()
                        # If dashboard has a refresh method, use it
                        if hasattr(self._current_handler, '_dashboard') and self._current_handler._dashboard:
                            if hasattr(self._current_handler._dashboard, 'refresh_documents'):
                                documents = self._current_handler.get_document_summaries()
                                self._current_handler._dashboard.refresh_documents(documents)
                    # Clear preservation flag
                    self._preserve_current_view = False
                    return
                except Exception as e:
                    print(f"Error refreshing dashboard: {e}")
                    # Fall back to full recreation if refresh fails

            # Fall back to showing dashboard
            if self._current_handler:
                self._current_handler.show_dashboard()
            else:
                self.show_main_menu()
        else:
            self.show_main_menu()

    def navigate_to_document(self, document_id: str):
        """Navigate to a specific document."""
        if self._current_handler:
            self._current_handler.show_dashboard()
            # TODO: Implement document focusing in dashboard

    # === Configuration Screen ===

    def show_config_screen(self):
        """Show the full configuration screen with cloud sync settings."""
        self._clear_window()
        self._center_window(900, 700)

        # Header with project context
        header_text = f"Configuracion de Usuario - {self.current_project_name}"
        self._create_header(self.root, header_text)

        # Create scrollable main frame
        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Create main frame inside scrollable area
        main_frame = ttk.Frame(scrollable_frame, padding="40")
        main_frame.pack(fill="both", expand=True)

        # Pack scrollable components
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel to canvas for scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Current name display
        current_name = self.user_config.get_user_name()

        ttk.Label(
            main_frame,
            text="Configuracion de tu nombre de usuario:",
            font=("Arial", 12)
        ).pack(pady=(0, 20))

        if current_name:
            ttk.Label(
                main_frame,
                text=f"Nombre actual: {current_name}",
                font=("Arial", 10),
                foreground="blue"
            ).pack(pady=(0, 10))

        # Name entry
        ttk.Label(main_frame, text="Nuevo nombre:").pack(anchor="w", pady=(0, 5))

        name_entry = ttk.Entry(main_frame, width=30, font=("Arial", 12))
        name_entry.pack(pady=(0, 30))
        if current_name:
            name_entry.insert(0, current_name)

        # Cloud Sync Configuration Section
        self._create_cloud_sync_config_section(main_frame)

        # Preset Management Section (only for planos)
        if self.current_doc_type == "planos":
            self._create_preset_management_section(main_frame)

        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(30, 0))

        def save_config():
            name = name_entry.get().strip()
            if name:
                try:
                    self.user_config.save(name)
                    messagebox.showinfo("Exito", f"Nombre de usuario actualizado a: {name}")
                    self.show_main_menu()
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo guardar la configuracion: {e}")
            else:
                messagebox.showwarning("Advertencia", "Por favor, ingrese un nombre valido.")

        ttk.Button(button_frame, text="Guardar", command=save_config).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame, text="Cancelar", command=self.show_main_menu).pack(side="left")

        # Focus on entry
        name_entry.focus()

        # Bind Enter key to save
        name_entry.bind("<Return>", lambda e: save_config())

        # Add navigation buttons at the bottom
        nav_frame = ttk.Frame(main_frame)
        nav_frame.pack(fill="x", pady=(30, 20))

        ttk.Button(nav_frame, text="[H] Cambiar Proyecto", command=self.show_project_selection).pack(side="left")
        ttk.Button(nav_frame, text="[D] Cambiar Tipo Documento", command=self.show_type_selection).pack(side="left", padx=10)

        # Update scroll region after all content is added
        scrollable_frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _create_cloud_sync_config_section(self, parent_frame):
        """Create cloud sync configuration section."""
        try:
            from config.settings import CloudConfig

            # Cloud sync section
            cloud_frame = ttk.LabelFrame(parent_frame, text="[C] Sincronizacion en la Nube", padding="15")
            cloud_frame.pack(fill="x", pady=(20, 0))

            # Load current cloud config
            cloud_config = CloudConfig(self._get_project_path())

            # Cloud sync enable/disable
            cloud_enabled_var = tk.BooleanVar(value=cloud_config.is_cloud_sync_enabled())

            enable_frame = ttk.Frame(cloud_frame)
            enable_frame.pack(fill="x", pady=(0, 15))

            ttk.Checkbutton(
                enable_frame,
                text="Habilitar sincronizacion automatica en la nube",
                variable=cloud_enabled_var,
                command=lambda: self._toggle_cloud_sync(cloud_enabled_var.get())
            ).pack(side="left")

            # Status section
            status_frame = ttk.Frame(cloud_frame)
            status_frame.pack(fill="x", pady=(0, 15))

            ttk.Label(status_frame, text="Estado de autenticacion:", font=("Arial", 10, "bold")).pack(anchor="w")

            # Create status labels that will be updated
            self._cloud_status_labels = {}

            # Google Drive status
            drive_frame = ttk.Frame(status_frame)
            drive_frame.pack(fill="x", pady=(5, 0))

            ttk.Label(drive_frame, text="[G] Google Drive:", width=15).pack(side="left")
            self._cloud_status_labels["google_drive"] = ttk.Label(
                drive_frame, text="Verificando...", foreground="gray"
            )
            self._cloud_status_labels["google_drive"].pack(side="left", padx=(5, 0))

            ttk.Button(
                drive_frame,
                text="Conectar",
                command=lambda: self._authenticate_service("google_drive"),
                width=10
            ).pack(side="right")

            # SharePoint status
            sharepoint_frame = ttk.Frame(status_frame)
            sharepoint_frame.pack(fill="x", pady=(5, 0))

            ttk.Label(sharepoint_frame, text="[S] SharePoint:", width=15).pack(side="left")
            self._cloud_status_labels["sharepoint"] = ttk.Label(
                sharepoint_frame, text="Verificando...", foreground="gray"
            )
            self._cloud_status_labels["sharepoint"].pack(side="left", padx=(5, 0))

            ttk.Button(
                sharepoint_frame,
                text="Conectar",
                command=lambda: self._authenticate_service("sharepoint"),
                width=10
            ).pack(side="right")

            # Update status immediately
            self._update_cloud_status()

            # Folder configuration section
            folder_frame = ttk.LabelFrame(cloud_frame, text="[F] Configuracion de Carpetas", padding="10")
            folder_frame.pack(fill="x", pady=(15, 0))

            # Google Drive folder configuration
            drive_config_frame = ttk.Frame(folder_frame)
            drive_config_frame.pack(fill="x", pady=(0, 10))

            ttk.Label(drive_config_frame, text="Google Drive Folder ID:", font=("Arial", 9, "bold")).pack(anchor="w")
            drive_folder_var = tk.StringVar(value=cloud_config.get_google_drive_folder_id())
            drive_folder_entry = ttk.Entry(drive_config_frame, textvariable=drive_folder_var, width=50)
            drive_folder_entry.pack(fill="x", pady=(2, 0))

            def save_drive_folder():
                cloud_config.set_google_drive_folder_id(drive_folder_var.get())
                messagebox.showinfo("Guardado", "Configuracion de Google Drive guardada correctamente.")

            ttk.Button(drive_config_frame, text="Guardar", command=save_drive_folder, width=10).pack(anchor="e", pady=(5, 0))

            # SharePoint configuration
            sharepoint_config_frame = ttk.Frame(folder_frame)
            sharepoint_config_frame.pack(fill="x", pady=(10, 0))

            ttk.Label(sharepoint_config_frame, text="SharePoint Site URL:", font=("Arial", 9, "bold")).pack(anchor="w")
            sp_site_var = tk.StringVar(value=cloud_config.get_sharepoint_site_url())
            sp_site_entry = ttk.Entry(sharepoint_config_frame, textvariable=sp_site_var, width=50)
            sp_site_entry.pack(fill="x", pady=(2, 0))

            ttk.Label(sharepoint_config_frame, text="SharePoint Folder Path:", font=("Arial", 9, "bold")).pack(anchor="w", pady=(10, 0))
            sp_folder_var = tk.StringVar(value=cloud_config.get_sharepoint_folder_path())
            sp_folder_entry = ttk.Entry(sharepoint_config_frame, textvariable=sp_folder_var, width=50)
            sp_folder_entry.pack(fill="x", pady=(2, 0))

            def save_sharepoint_config():
                cloud_config.set_sharepoint_site_url(sp_site_var.get())
                cloud_config.set_sharepoint_folder_path(sp_folder_var.get())
                messagebox.showinfo("Guardado", "Configuracion de SharePoint guardada correctamente.")

            ttk.Button(sharepoint_config_frame, text="Guardar", command=save_sharepoint_config, width=10).pack(anchor="e", pady=(5, 0))

            # Help text
            help_frame = ttk.Frame(folder_frame)
            help_frame.pack(fill="x", pady=(15, 0))

            help_text = (
                "[i] Google Drive Folder ID: Se encuentra en la URL de la carpeta\n"
                "[i] SharePoint: URL del sitio y ruta de la carpeta donde subir los archivos"
            )
            ttk.Label(help_frame, text=help_text, font=("Arial", 8), foreground="blue").pack(anchor="w")

        except Exception as e:
            # If cloud sync components aren't available, show a simple message
            error_frame = ttk.LabelFrame(parent_frame, text="[C] Sincronizacion en la Nube", padding="15")
            error_frame.pack(fill="x", pady=(20, 0))

            ttk.Label(
                error_frame,
                text=f"[WARNING] Cloud sync no disponible: {e}",
                foreground="orange"
            ).pack()

    def _create_preset_management_section(self, parent_frame):
        """Create preset management section for planos."""
        try:
            preset_frame = ttk.LabelFrame(parent_frame, text="Gestion de Presets de Planos", padding="15")
            preset_frame.pack(fill="x", pady=(20, 0))

            desc_text = (
                "Los presets permiten crear plantillas de planos predefinidas organizadas por fases del proyecto.\n"
                "Solo los administradores pueden crear presets desde esta configuracion."
            )
            ttk.Label(
                preset_frame,
                text=desc_text,
                font=("Arial", 10),
                foreground="#666666",
                wraplength=700,
                justify="left"
            ).pack(anchor="w", pady=(0, 15))

            button_frame = ttk.Frame(preset_frame)
            button_frame.pack(fill="x", pady=(0, 15))

            ttk.Button(
                button_frame,
                text="Crear Presets de Planos",
                command=self._show_preset_creation_dialog,
                width=25
            ).pack(side="left")

            # Status info
            status_frame = ttk.Frame(preset_frame)
            status_frame.pack(fill="x")

            try:
                if hasattr(self, 'document_controller') and self.document_controller:
                    total_docs = len(self.document_controller.get_all_documents())
                    status_text = f"Planos actuales en el proyecto: {total_docs}"
                else:
                    status_text = "Estado: Controller no disponible"
            except Exception as e:
                status_text = f"Estado: Error al cargar informacion ({e})"

            ttk.Label(
                status_frame,
                text=status_text,
                font=("Arial", 9),
                foreground="gray"
            ).pack(anchor="w")

        except Exception as e:
            error_frame = ttk.LabelFrame(parent_frame, text="Gestion de Presets", padding="15")
            error_frame.pack(fill="x", pady=(20, 0))

            ttk.Label(
                error_frame,
                text=f"[WARNING] Preset management no disponible: {e}",
                foreground="orange"
            ).pack()

    def _show_preset_creation_dialog(self):
        """Show preset creation dialog."""
        try:
            from views.preset_creation_dialog import PresetCreationDialog

            callbacks = {
                'get_preset_templates': self._get_preset_templates,
                'create_presets_from_template': self._create_presets_from_template,
                'create_custom_preset': self._create_custom_preset,
                'get_phase_status': self._get_phase_status,
                'mark_notification_as_read': lambda x: False,
                'refresh_view': lambda: None
            }

            dialog = PresetCreationDialog(self.root)
            dialog.show(callbacks)

        except ImportError as e:
            messagebox.showerror("Error", f"No se pudo cargar el dialogo de presets: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error al mostrar el dialogo de presets: {e}")

    def _get_preset_templates(self):
        """Get available preset templates."""
        try:
            from utils.plano_preset_manager import PlanoPresetManager
            manager = PlanoPresetManager(self._get_project_path())
            return manager.get_available_presets()
        except Exception as e:
            _safe_print(f"Error loading preset templates: {e}")
            return {}

    def _create_presets_from_template(self, template_name: str, selected_presets: list):
        """Create presets from template."""
        try:
            if not hasattr(self, 'document_controller') or not self.document_controller:
                return []

            from utils.plano_preset_manager import PlanoPresetManager
            manager = PlanoPresetManager(self._get_project_path())

            current_user = self.user_config.get_user_name() or "Admin"

            from utils.project_database_manager import ProjectDatabaseManager
            db_manager = ProjectDatabaseManager(self._get_project_path())

            created_presets = manager.create_preset_planos(
                db_manager,
                current_user,
                template_name,
                selected_presets
            )

            return created_presets

        except Exception as e:
            _safe_print(f"Error creating presets from template: {e}")
            return []

    def _create_custom_preset(self, name: str, phase: str):
        """Create a custom preset."""
        try:
            if not hasattr(self, 'document_controller') or not self.document_controller:
                return False

            from utils.plano_preset_manager import PlanoPresetManager
            manager = PlanoPresetManager(self._get_project_path())

            current_user = self.user_config.get_user_name() or "Admin"

            from utils.project_database_manager import ProjectDatabaseManager
            db_manager = ProjectDatabaseManager(self._get_project_path())

            success = manager.create_custom_preset(
                db_manager,
                current_user,
                name,
                phase
            )
            return success

        except Exception as e:
            _safe_print(f"Error creating custom preset: {e}")
            return False

    def _get_phase_status(self):
        """Get phase completion status."""
        try:
            if not hasattr(self, 'document_controller') or not self.document_controller:
                return {}

            documents = self.document_controller.get_all_documents()
            phase_stats = {}

            for doc in documents:
                phase = getattr(doc, 'project_phase', 'Sin fase')
                if phase not in phase_stats:
                    phase_stats[phase] = {'total': 0, 'completed_count': 0, 's3_count': 0, 's3a_count': 0}

                phase_stats[phase]['total'] += 1

                current_state = doc.current_state
                if current_state in ['S3', 'S3A']:
                    phase_stats[phase]['completed_count'] += 1

                if current_state == 'S3':
                    phase_stats[phase]['s3_count'] += 1
                elif current_state == 'S3A':
                    phase_stats[phase]['s3a_count'] += 1

            return phase_stats

        except Exception as e:
            _safe_print(f"Error getting phase status: {e}")
            return {}

    def _toggle_cloud_sync(self, enabled: bool):
        """Toggle cloud sync for the current project."""
        try:
            from config.settings import CloudConfig
            cloud_config = CloudConfig(self._get_project_path())
            project_config = cloud_config.project_config.copy()
            project_config["enabled"] = enabled
            cloud_config.save_project_config(project_config)

            status = "habilitada" if enabled else "deshabilitada"
            messagebox.showinfo("Configuracion", f"Sincronizacion en la nube {status}")

            self._update_cloud_status()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo actualizar la configuracion: {e}")

    def _authenticate_service(self, service: str):
        """Authenticate with cloud service."""
        try:
            from config.settings import CloudConfig
            cloud_config = CloudConfig(self._get_project_path())

            auth_cancelled = False

            def cancel_authentication():
                nonlocal auth_cancelled
                auth_cancelled = True
                progress_window.destroy()

            # Show progress message
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Autenticacion")
            progress_window.geometry("400x200")
            progress_window.transient(self.root)
            progress_window.grab_set()

            progress_window.protocol("WM_DELETE_WINDOW", cancel_authentication)

            # Center the progress window
            progress_window.update_idletasks()
            x = (progress_window.winfo_screenwidth() // 2) - (400 // 2)
            y = (progress_window.winfo_screenheight() // 2) - (200 // 2)
            progress_window.geometry(f"400x200+{x}+{y}")

            ttk.Label(
                progress_window,
                text=f"Conectando con {service.replace('_', ' ').title()}...",
                font=("Arial", 12)
            ).pack(pady=20)

            ttk.Label(
                progress_window,
                text="Se abrira tu navegador para autenticacion.",
                font=("Arial", 10),
                foreground="gray"
            ).pack()

            cancel_button = ttk.Button(
                progress_window,
                text="Cancelar",
                command=cancel_authentication
            )
            cancel_button.pack(pady=20)

            progress_window.bind('<Escape>', lambda e: cancel_authentication())
            progress_window.update()

            from utils.enhanced_cloud_sync import EnhancedCloudSyncManager
            sync_manager = EnhancedCloudSyncManager(cloud_config)

            if auth_cancelled:
                return

            success = False
            try:
                if service == "google_drive":
                    success = sync_manager.authenticate_drive()
                else:
                    success = sync_manager.authenticate_sharepoint()
            except Exception as auth_error:
                try:
                    progress_window.destroy()
                except:
                    pass
                if not auth_cancelled:
                    messagebox.showerror("Error", f"Error durante la autenticacion: {auth_error}")
                return

            try:
                progress_window.destroy()
            except:
                pass

            if not auth_cancelled:
                if success:
                    messagebox.showinfo("Exito", f"Conectado exitosamente con {service.replace('_', ' ').title()}!")
                else:
                    messagebox.showerror("Error", f"No se pudo conectar con {service.replace('_', ' ').title()}")

                self._update_cloud_status()

        except Exception as e:
            try:
                progress_window.destroy()
            except:
                pass
            messagebox.showerror("Error", f"Error de autenticacion: {e}")

    def _update_cloud_status(self):
        """Update cloud authentication status display."""
        try:
            if not hasattr(self, '_cloud_status_labels'):
                return

            from config.settings import CloudConfig
            from utils.enhanced_cloud_sync import EnhancedCloudSyncManager

            cloud_config = CloudConfig(self._get_project_path())
            sync_manager = EnhancedCloudSyncManager(cloud_config)
            auth_status = sync_manager.get_authentication_status()

            # Update Google Drive status
            drive_status = auth_status.get("google_drive", {})
            if drive_status.get("authenticated"):
                self._cloud_status_labels["google_drive"].config(
                    text=f"[OK] {drive_status.get('message', 'Conectado')}",
                    foreground="green"
                )
            else:
                self._cloud_status_labels["google_drive"].config(
                    text=f"X {drive_status.get('message', 'No conectado')}",
                    foreground="red"
                )

            # Update SharePoint status
            sharepoint_status = auth_status.get("sharepoint", {})
            if sharepoint_status.get("authenticated"):
                self._cloud_status_labels["sharepoint"].config(
                    text=f"[OK] {sharepoint_status.get('message', 'Conectado')}",
                    foreground="green"
                )
            else:
                self._cloud_status_labels["sharepoint"].config(
                    text=f"X {sharepoint_status.get('message', 'No conectado')}",
                    foreground="red"
                )

        except Exception as e:
            for label in getattr(self, '_cloud_status_labels', {}).values():
                label.config(text=f"[WARNING] Error: {e}", foreground="orange")

    def _get_project_path(self) -> Optional[Path]:
        """Get current project path as Path object."""
        return Path(self.current_project_path) if self.current_project_path else None

    # === PDF Corrector (Shared) ===

    @property
    def pdf_corrector(self):
        """Get the shared PDF corrector instance."""
        if self._pdf_corrector is None:
            from views.simple_pdf_corrector import SimplePDFCorrector
            self._pdf_corrector = SimplePDFCorrector(self.root)
        return self._pdf_corrector

    # === Export Dialog ===

    def show_export_dialog(self):
        """Show export dialog for multiple planos selection."""
        # Only allow export for planos
        if self.current_doc_type != "planos":
            messagebox.showinfo("Informacion", "La exportacion multiple solo esta disponible para Planos.")
            return

        # Get all planos documents
        if not self.document_controller:
            messagebox.showerror("Error", "Controlador de planos no inicializado.")
            return

        documents = self.document_controller.get_all_documents()
        if not documents:
            messagebox.showinfo("Informacion", "No hay planos disponibles para exportar.")
            return

        # Initialize export components if needed
        if not hasattr(self, '_export_dialog') or not self._export_dialog:
            from views.export_dialog import ExportDialog
            self._export_dialog = ExportDialog(self.root)
        if not hasattr(self, '_export_controller') or not self._export_controller:
            from controllers.export_controller import ExportController
            self._export_controller = ExportController(self.current_project_path, self.current_doc_type)

        # Define export callback
        def export_callback(selected_docs, export_dir):
            try:
                self._export_controller.export_documents(selected_docs, export_dir)
            except Exception as e:
                raise e

        # Show export dialog
        project_path = self.document_controller.get_project_path()
        self._export_dialog.show(documents, export_callback, project_path)

    # === XREF Progress Callback ===

    def _on_xref_progress(self, message: str):
        """Handle XREF processing progress updates."""
        _safe_print(f"[XREF] {message}")
        # Could update a status bar or progress indicator here

    # === Fast Document Loading ===

    def _get_documents_for_status_viewer(self):
        """
        Get documents for status viewer using fast summary loading when available.

        Performance optimization: Use lightweight summaries for initial display,
        avoiding the overhead of loading complete document history.
        Falls back to full document loading for backward compatibility.
        """
        try:
            # Try to use fast summary loading based on document type
            if self.current_doc_type == "planos" and self._current_handler:
                if hasattr(self._current_handler, 'get_document_summaries'):
                    print(f"DEBUG: Using fast PlanoSummary loading for status viewer")
                    return self._current_handler.get_document_summaries()
            elif self.current_doc_type == "licitaciones" and self._current_handler:
                if hasattr(self._current_handler, 'get_document_summaries'):
                    print(f"DEBUG: Using fast LicitacionSummary loading for status viewer")
                    return self._current_handler.get_document_summaries()

            # Fallback to handler's get_documents
            if self._current_handler:
                print(f"DEBUG: Using handler get_documents for status viewer")
                return self._current_handler.get_documents()

            # Final fallback
            _safe_print(f"WARNING: No handler available for {self.current_doc_type}")
            return []

        except Exception as e:
            _safe_print(f"Warning: Error in fast loading, falling back: {e}")
            if self._current_handler:
                return self._current_handler.get_documents()
            return []

    # === Planos File Management Helpers ===

    def _get_planos_document_files(self, document_name: str):
        """Get detailed file information for a planos document."""
        try:
            if not self.document_controller:
                return []

            result = self.document_controller.get_document_files_info(document_name)
            if result.get('success', False):
                return result.get('files', [])
            else:
                print(f"Error getting files for {document_name}: {result.get('message', 'Unknown error')}")
                return []
        except Exception as e:
            _safe_print(f"Error getting planos document files for {document_name}: {e}")
            return []

    def _get_planos_document_file_extensions(self, document_name: str) -> set:
        """Get file extensions for a planos document (filesystem as source of truth)."""
        try:
            if not self.document_controller:
                return set()
            return self.document_controller.file_service.get_file_extensions(document_name)
        except Exception as e:
            _safe_print(f"Error getting file extensions for {document_name}: {e}")
            return set()

    def _replace_planos_file(self, document_name: str, current_path: str, new_file_path: str):
        """Replace a file for a planos document."""
        try:
            if not self.document_controller:
                return False, "Controlador no inicializado"

            result = self.document_controller.replace_file_for_document(
                document_name,
                current_path,
                Path(new_file_path)
            )

            success = result.get('success', False)
            message = result.get('message', 'Error desconocido')

            return success, message

        except Exception as e:
            return False, f"Error al reemplazar archivo: {e}"

    def _add_planos_file(self, document_name: str, file_path: str, file_type: str):
        """Add a new file to a planos document."""
        try:
            if not self.document_controller:
                return False, "Controlador no inicializado"

            result = self.document_controller.add_file_to_document(
                document_name,
                Path(file_path),
                file_type
            )

            success = result.get('success', False)
            message = result.get('message', 'Error desconocido')

            return success, message

        except Exception as e:
            return False, f"Error al agregar archivo: {e}"

    def _populate_planos_files(self, document_name: str = None):
        """Populate file_paths for planos documents by scanning the file system."""
        try:
            if not self.document_controller:
                return False, "Controlador no inicializado"

            result = self.document_controller.populate_missing_file_paths(document_name)

            success = result.get('success', False)
            message = result.get('message', 'Error desconocido')

            return success, message

        except Exception as e:
            return False, f"Error al buscar archivos: {e}"

    # === Application Lifecycle ===

    def run(self):
        """Start the application."""
        self.show_project_selection()
        self.root.mainloop()


def main():
    """Main entry point."""
    app = AppController()
    app.run()


if __name__ == "__main__":
    main()
