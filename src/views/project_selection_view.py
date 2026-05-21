import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional
from pathlib import Path
from .base_view import BaseView
from utils.folder_resolver import FolderResolver
from utils.app_paths import get_projects_root


class ProjectSelectionView(BaseView):
    def __init__(self, root: tk.Tk):
        super().__init__(root)

    def show(self, callback: Callable[[str, str], None], user_name: str = "",
             notification_callbacks: dict = None,
             on_create_project: Optional[Callable[[], None]] = None) -> None:
        """Show the project selection screen."""
        self.clear_window()
        self.center_window(750, 650)
        
        # Add notification widget if user and callbacks available
        if user_name and notification_callbacks and 'get_notification_data' in notification_callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: notification_callbacks.get('get_notification_data')(user_name),
                mark_read_callback=notification_callbacks.get('mark_notification_as_read'),
                navigate_callback=notification_callbacks.get('navigate_to_document'),
                current_user=user_name,
                delete_callback=notification_callbacks.get('delete_notification')
            )
        
        # Header
        self.create_header(self.root, "Seleccionar Proyecto")

        # Barra superior con CTA de creacion a la derecha
        topbar = ttk.Frame(self.root, padding=(20, 0, 20, 0))
        topbar.pack(fill="x")
        if on_create_project is not None:
            self.create_visible_button(
                topbar,
                text="+ Crear proyecto nuevo",
                command=on_create_project,
            ).pack(side="right")

        # Main frame
        main_frame = ttk.Frame(self.root, padding="40")
        main_frame.pack(fill="both", expand=True)

        # Instructions
        ttk.Label(
            main_frame,
            text="Selecciona un proyecto para gestionar sus documentos:",
            font=("Arial", 12)
        ).pack(pady=(0, 20))
        
        # Get available projects
        projects = self.get_available_projects()
        
        if not projects:
            # No projects found - show creation instructions
            ttk.Label(
                main_frame,
                text="No se encontraron proyectos.",
                font=("Arial", 14, "bold"),
                foreground="red"
            ).pack(pady=20)
            
            # Get the correct app directory for instructions
            app_dir = get_projects_root()

            instructions = (
                "Para usar el gestor de documentos:\n\n"
                "1. Crea carpetas con formato 'PRJ-XXX' en:\n"
                f"   {app_dir}\n\n"
                "2. Dentro de cada carpeta PRJ-XXX, crea carpetas de:\n"
                "   • Planos/           (ej: 02_Planos, 06_Planos, 06.-PLANOS)\n"
                "   • Presupuestos/     (ej: 03_Presupuestos)\n"
                "   • Certificaciones/  (ej: 04_Certificaciones)\n\n"
                "3. Reinicia la aplicación\n\n"
                "Ejemplo:\n"
                "   PRJ-001/\n"
                "   ├── 06_Planos/\n"
                "   ├── 03_Presupuestos/\n"
                "   └── 04_Certificaciones/"
            )
            
            instructions_label = ttk.Label(
                main_frame,
                text=instructions,
                font=("Courier", 10),
                foreground="darkblue",
                justify="left"
            )
            instructions_label.pack(pady=20)
            
            # Refresh button
            self.create_visible_button(
                main_frame,
                text="Buscar Proyectos",
                command=lambda: self.show(callback, user_name,
                                          notification_callbacks,
                                          on_create_project)
            ).pack(pady=20)
            
        else:
            # Show project list
            projects_frame = ttk.Frame(main_frame)
            projects_frame.pack(fill="both", expand=True, pady=10)
            
            # Project buttons
            for i, (project_name, project_path) in enumerate(projects):
                # Project info frame
                project_frame = ttk.Frame(projects_frame)
                project_frame.pack(fill="x", pady=5)
                
                # Project button
                btn = self.create_visible_button(
                    project_frame,
                    text=f"{project_name}",
                    command=lambda pn=project_name, pp=project_path: callback(pn, pp),
                    width=40
                )
                btn.pack(side="left", padx=10)
                
                # Project path info
                path_label = ttk.Label(
                    project_frame,
                    text=f"Path: {project_path}",
                    font=("Arial", 9),
                    foreground="gray"
                )
                path_label.pack(side="left", padx=(20, 0))
        
        # Footer
        footer_frame = ttk.Frame(self.root, padding="10")
        footer_frame.pack(side="bottom", fill="x")
        
        ttk.Label(
            footer_frame,
            text="Selecciona un proyecto para acceder a sus planos y certificaciones",
            font=("Arial", 10, "italic")
        ).pack()
        
        # Ensure notification widget is visible on top of all other elements
        self.ensure_notification_widget_visible()
    
    def get_available_projects(self) -> List[tuple]:
        """Get available projects by scanning for PRJ-* folders."""
        projects = []

        current_dir = get_projects_root()

        # Look for PRJ-* folders in app directory
        for item in current_dir.iterdir():
            if item.is_dir() and item.name.startswith("PRJ"):
                # Marker canonico post-Fase 1: la carpeta `.project_manager/`
                # contiene la BD del proyecto. Si existe, es un proyecto valido
                # aunque no tenga las subcarpetas legacy.
                if (item / ".project_manager").is_dir():
                    projects.append((item.name, str(item)))
                    continue

                # Compatibilidad con proyectos legacy: aceptar si existe alguna
                # de las subcarpetas conocidas (planos/presupuestos/certificaciones)
                # o si la carpeta esta totalmente vacia (lista para configurar).
                planos_dir = FolderResolver.resolve_planos(item)
                licitaciones_dir = FolderResolver.resolve_presupuestos(item)
                certificaciones_dir = FolderResolver.resolve_certificaciones(item)

                if (planos_dir.exists() or licitaciones_dir.exists() or certificaciones_dir.exists() or
                    (len(list(item.iterdir())) == 0)):
                    projects.append((item.name, str(item)))
        
        # Sort projects by name
        projects.sort(key=lambda x: x[0])
        
        return projects