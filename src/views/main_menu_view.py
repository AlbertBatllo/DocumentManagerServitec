import tkinter as tk
from tkinter import ttk
from typing import Callable
from .base_view import BaseView


class MainMenuView(BaseView):
    def __init__(self, root: tk.Tk, doc_type: str):
        super().__init__(root)
        self.doc_type = doc_type
        self.doc_type_display = "Planos" if doc_type == "planos" else "Certificaciones"

    def show(self, callbacks: dict) -> None:
        """Show the main menu."""
        self.clear_window()
        self.center_window(750, 650)
        
        # Header
        self.create_header(self.root, f"Gestión de {self.doc_type_display}")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Centered document type title - more prominent
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, pady=(0, 30), sticky="ew")
        
        title_label = ttk.Label(
            title_frame,
            text=self.doc_type_display.upper(),
            font=("Arial", 28, "bold"),
            foreground="#2E5984"  # Professional blue color
        )
        title_label.pack()
        
        # Subtitle with dynamic project info
        project_name = self._get_current_project_name()
        subtitle_label = ttk.Label(
            title_frame,
            text=f"{self.doc_type_display} - {project_name}",
            font=("Arial", 14),
            foreground="#666666"
        )
        subtitle_label.pack(pady=(5, 0))
        
        # Menu buttons
        if self.doc_type_display == "Certificaciones":
            new_doc_text = "Registrar Nueva Certificación"
            new_doc_tooltip = "Registrar una nueva certificación en estado S0, S1, S2 o S3"
        elif self.doc_type_display.endswith('s'):
            new_doc_text = f"Registrar Nuevo {self.doc_type_display.rstrip('s')}"
            new_doc_tooltip = f"Registrar un nuevo {self.doc_type_display.rstrip('s').lower()} en estado S0, S1, S2 o S3"
        else:
            new_doc_text = f"Registrar Nueva {self.doc_type_display}"
            new_doc_tooltip = f"Registrar una nueva {self.doc_type_display.lower()} en estado S0, S1, S2 o S3"
        
        button_configs = [
            ("Ver Estado de Archivos", callbacks['view_status'], "Ver el estado actual de todos los archivos"),
            # ("📋 Notificaciones y Tareas", callbacks.get('view_notifications', lambda: None), "Ver tareas asignadas y notificaciones"),  # Removed
            ("Corregir Información", callbacks['correct_info'], "Modificar información de un archivo"),
            ("Proceso de Corrección", callbacks['annotate_pdf'], "Anotar y corregir documentos PDF (Estados S1, S2, S3, A, B)"),
            ("Eliminar Archivos", callbacks['delete_files'], "Eliminar archivos existentes del sistema"),
            ("Configuración", callbacks['config'], "Configurar nombre de usuario"),
            ("Volver", callbacks['back'], "Volver al menú de selección de tipo")
        ]
        
        for i, (text, command, tooltip) in enumerate(button_configs):
            btn = ttk.Button(
                main_frame,
                text=text,
                command=command,
                width=30
            )
            btn.grid(row=i+1, column=0, pady=10, padx=50, sticky="ew")
        
        # Configure grid
        main_frame.columnconfigure(0, weight=1)
        
        # Footer with instructions
        footer_frame = ttk.Frame(self.root, padding="10")
        footer_frame.pack(side="bottom", fill="x")
        
        ttk.Label(
            footer_frame,
            text="Seleccione una opción para continuar",
            font=("Arial", 10, "italic")
        ).pack()

    def _get_current_project_name(self) -> str:
        """Extract project name from current directory or return default."""
        try:
            from pathlib import Path
            current_path = Path.cwd()
            
            # Check if we're in a project directory structure
            for part in current_path.parts:
                if part.startswith('PRJ-') or part.startswith('PROJ-'):
                    return part
            
            # If no specific project pattern found, use the current directory name
            if current_path.name and current_path.name not in ['src', 'views', 'document_manager']:
                return current_path.name
                
            # Fallback to parent directory name
            if current_path.parent.name and current_path.parent.name not in ['document_manager', 'project_integration']:
                return current_path.parent.name
                
            return "Proyecto Actual"
        except Exception:
            return "Proyecto Actual"

