import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable
from pathlib import Path
from .base_view import BaseView
from utils.folder_resolver import FolderResolver


class CentralizedTypeSelectionView(BaseView):
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.project_path = None
        self.project_name = None
        
    def set_project_context(self, project_name: str, project_path: str):
        """Set the project context for document type selection."""
        self.project_name = project_name
        self.project_path = Path(project_path)

    def show(self, on_select_callback: Callable[[str, str], None], back_callback: Callable = None, 
             user_name: str = "", notification_callbacks: dict = None) -> None:
        """Show the document type selection menu."""
        self.clear_window()
        self.center_window(900, 750)
        
        # Add notification widget if user and callbacks available
        if user_name and notification_callbacks and 'get_notification_data' in notification_callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: notification_callbacks.get('get_notification_data')(user_name),
                mark_read_callback=notification_callbacks.get('mark_notification_as_read'),
                navigate_callback=notification_callbacks.get('navigate_to_document'),
                current_user=user_name,
                delete_callback=notification_callbacks.get('delete_notification')
            )
        
        # Header with project context
        header_title = f"Selección de Tipo de Documento - {self.project_name}"
        self.create_header(self.root, header_title)
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="40")
        main_frame.pack(fill="both", expand=True)
        
        # Project info
        project_info_frame = ttk.LabelFrame(main_frame, text="Proyecto Seleccionado", padding="10")
        project_info_frame.pack(fill="x", pady=(0, 20))
        
        ttk.Label(
            project_info_frame,
            text=f"📁 {self.project_name}",
            font=("Arial", 12, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            project_info_frame,
            text=f"📍 {self.project_path}",
            font=("Arial", 9),
            foreground="gray"
        ).pack(anchor="w", pady=(5, 0))
        
        # Instructions
        ttk.Label(
            main_frame,
            text="Seleccione el tipo de documento a gestionar:",
            font=("Arial", 12)
        ).pack(pady=20)
        
        # Document type buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(expand=True)
        
        # Check what document types are available
        planos_path = FolderResolver.resolve_planos(self.project_path)
        licitacion_path = FolderResolver.resolve_presupuestos(self.project_path)
        cert_path = FolderResolver.resolve_certificaciones(self.project_path)

        # Marker post-Fase 1: la BD del proyecto (en .project_manager/)
        # es la fuente de verdad de las metadatas. Las subcarpetas fisicas
        # son opcionales y se crearan en la primera subida (Fase 6+).
        # Para proyectos legacy sin .project_manager/ se mantiene la
        # comprobacion historica de existencia de subcarpetas.
        post_fase1 = (self.project_path / ".project_manager").is_dir()

        planos_exists = post_fase1 or planos_path.exists()
        licitacion_exists = post_fase1 or licitacion_path.exists()
        cert_exists = post_fase1 or cert_path.exists()
        
        if not planos_exists and not licitacion_exists and not cert_exists:
            # No document folders found - show creation instructions
            ttk.Label(
                main_frame,
                text="⚠️ No se encontraron carpetas de documentos",
                font=("Arial", 14, "bold"),
                foreground="red"
            ).pack(pady=20)
            
            instructions = (
                f"En el proyecto {self.project_name}, crea las siguientes carpetas:\n\n"
                "• Planos/              (para planos técnicos)\n"
                "• Presupuestos/        (para documentos de presupuesto)\n"
                "• Certificaciones/     (para certificaciones)\n\n"
                "Ejemplo: 02_Planos, 06_Planos, 06.-PLANOS, etc.\n"
                "Luego regresa a esta pantalla."
            )
            
            instructions_label = ttk.Label(
                main_frame,
                text=instructions,
                font=("Arial", 10),
                foreground="darkblue",
                justify="left"
            )
            instructions_label.pack(pady=20)
            
        else:
            # Create document type selection buttons
            button_frame = ttk.Frame(buttons_frame)
            button_frame.pack(expand=True)
            
            button_frame.grid_columnconfigure(0, weight=1)
            button_frame.grid_columnconfigure(1, weight=1)
            button_frame.grid_columnconfigure(2, weight=1)
            
            # Planos (column 0)
            if planos_exists:
                # Type name - larger and bold
                ttk.Label(
                    button_frame,
                    text="PLANOS",
                    font=("Arial", 18, "bold"),
                    justify="center"
                ).grid(row=0, column=0, padx=10, pady=(10, 5))
                
                btn_planos = ttk.Button(
                    button_frame,
                    text="Acceder",
                    command=lambda: on_select_callback("planos", str(planos_path)),
                    width=18
                )
                btn_planos.grid(row=1, column=0, padx=10, pady=5)
                
                ttk.Label(
                    button_frame,
                    text="Gestionar planos técnicos\ny dibujos de ingeniería",
                    font=("Arial", 9),
                    justify="center",
                    foreground="green"
                ).grid(row=2, column=0, padx=10, pady=5)
            else:
                ttk.Label(
                    button_frame,
                    text="Planos\n(No disponible)",
                    font=("Arial", 10),
                    justify="center",
                    foreground="gray"
                ).grid(row=0, column=0, padx=10, pady=10)
                
                ttk.Label(
                    button_frame,
                    text="Carpeta de Planos\nno encontrada",
                    font=("Arial", 8),
                    justify="center",
                    foreground="red"
                ).grid(row=1, column=0, padx=10, pady=5)
            
            # Licitaciones (column 1) 
            if licitacion_exists:
                # Type name - larger and bold
                ttk.Label(
                    button_frame,
                    text="PRESUPUESTOS",
                    font=("Arial", 18, "bold"),
                    justify="center"
                ).grid(row=0, column=1, padx=10, pady=(10, 5))
                
                btn_licitacion = ttk.Button(
                    button_frame,
                    text="Acceder",
                    command=lambda: on_select_callback("licitaciones", str(licitacion_path)),
                    width=18
                )
                btn_licitacion.grid(row=1, column=1, padx=10, pady=5)
                
                ttk.Label(
                    button_frame,
                    text="Gestionar mediciones,\npresupuestos y adjudicaciones",
                    font=("Arial", 9),
                    justify="center",
                    foreground="green"
                ).grid(row=2, column=1, padx=10, pady=5)
            else:
                ttk.Label(
                    button_frame,
                    text="Presupuestos\n(No disponible)",
                    font=("Arial", 10),
                    justify="center",
                    foreground="gray"
                ).grid(row=0, column=1, padx=10, pady=10)
                
                ttk.Label(
                    button_frame,
                    text="Carpeta 03_Presupuestos/\nno encontrada",
                    font=("Arial", 8),
                    justify="center",
                    foreground="red"
                ).grid(row=1, column=1, padx=10, pady=5)
            
            # Certificaciones (column 2)
            if cert_exists:
                # Type name - larger and bold
                ttk.Label(
                    button_frame,
                    text="CERTIFICACIONES",
                    font=("Arial", 18, "bold"),
                    justify="center"
                ).grid(row=0, column=2, padx=10, pady=(10, 5))
                
                btn_cert = ttk.Button(
                    button_frame,
                    text="Acceder",
                    command=lambda: on_select_callback("certificaciones", str(cert_path)),
                    width=18
                )
                btn_cert.grid(row=1, column=2, padx=10, pady=5)
                
                ttk.Label(
                    button_frame,
                    text="Gestionar certificaciones\ny control financiero",
                    font=("Arial", 9),
                    justify="center",
                    foreground="green"
                ).grid(row=2, column=2, padx=10, pady=5)
            else:
                ttk.Label(
                    button_frame,
                    text="Certificaciones\n(No disponible)",
                    font=("Arial", 10),
                    justify="center",
                    foreground="gray"
                ).grid(row=0, column=2, padx=10, pady=10)
                
                ttk.Label(
                    button_frame,
                    text="Carpeta 04_Certificaciones/\nno encontrada",
                    font=("Arial", 8),
                    justify="center",
                    foreground="red"
                ).grid(row=1, column=2, padx=10, pady=5)
        
        # Navigation buttons - positioned before cloud sync for better visibility
        nav_frame = ttk.Frame(main_frame)
        nav_frame.pack(fill="x", pady=(20, 20))
        
        ttk.Button(
            nav_frame,
            text="Cambiar Proyecto",
            command=back_callback if back_callback else lambda: None
        ).pack(side="left")
        
        def _refresh():
            FolderResolver.clear_cache()
            self.show(on_select_callback, back_callback)

        ttk.Button(
            nav_frame,
            text="Actualizar",
            command=_refresh
        ).pack(side="right")
        
        
        # Ensure notification widget is visible on top of all other elements
        self.ensure_notification_widget_visible()
    
    def _go_back_to_projects(self):
        """Navigate back to project selection."""
        # This will be handled by the main app
        pass
    
