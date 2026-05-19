import tkinter as tk
from tkinter import ttk
from typing import Callable
from .base_view import BaseView
# from .notification_widget import NotificationWidget  # Removed


class CentralizedMainMenuView(BaseView):
    def __init__(self, root: tk.Tk, doc_type: str):
        super().__init__(root)
        self.doc_type = doc_type
        if doc_type == "planos":
            self.doc_type_display = "Planos"
        elif doc_type == "licitaciones":
            self.doc_type_display = "Presupuestos"
        else:
            self.doc_type_display = "Certificaciones"
        self.project_name = None
        self.notification_widget = None

    def set_project_context(self, project_name: str):
        """Set the project context for the main menu."""
        self.project_name = project_name

    def show(self, callbacks: dict) -> None:
        """Show the main menu."""
        self.clear_window()
        self.center_window(750, 650)
        
        # Header with project and document type context
        header_title = f"{self.doc_type_display.upper()}"
        if self.project_name:
            header_title += f" - {self.project_name}"
        
        self.create_header(self.root, header_title)
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Project context info
        if self.project_name:
            context_frame = ttk.Frame(main_frame)
            context_frame.pack(fill="x", pady=(0, 20))
            
            ttk.Label(
                context_frame,
                text=f"{self.project_name}",
                font=("Arial", 11, "bold")
            ).pack(side="left")
            
            ttk.Label(
                context_frame,
                text=f"{self.doc_type_display}",
                font=("Arial", 11),
                foreground="gray"
            ).pack(side="right")
        
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
        
        # Build button configs based on document type
        button_configs = [
            ("Ver Estado de Archivos", callbacks['view_status'], "Ver el estado actual de todos los archivos"),
            ("Proceso de Corrección", callbacks['annotate_pdf'], "Anotar y corregir documentos PDF (Estados S1, S2, S3, A, B)"),
            # ("📋 Notificaciones y Tareas", callbacks['view_notifications'], "Ver notificaciones y asignaciones pendientes"),  # Removed
        ]
        
        # Only add delete files option for planos and presupuestos (not certificaciones)
        # Certificaciones have a different structure with monthly entries, not version/state entries
        if self.doc_type != "certificaciones":
            button_configs.append(("Eliminar Archivos", callbacks['delete_files'], "Eliminar archivos existentes del sistema"))
        
        # Add config button at the end
        button_configs.append(("Configuración", callbacks['config'], "Configurar nombre de usuario"))
        
        for text, command, tooltip in button_configs:
            btn = ttk.Button(
                main_frame,
                text=text,
                command=command,
                width=40
            )
            btn.pack(pady=8, padx=50, fill="x")
        
        # Create notification widget if callbacks are available
        try:
            if 'get_notification_data' in callbacks and 'get_current_user' in callbacks:
                print("DEBUG: Setting up notification widget with callbacks")
                self._setup_notification_widget(callbacks)
            else:
                print("DEBUG: Missing required callbacks for notification widget:")
                print(f"  - get_notification_data: {'✓' if 'get_notification_data' in callbacks else '✗'}")
                print(f"  - get_current_user: {'✓' if 'get_current_user' in callbacks else '✗'}")
        except Exception as e:
            print(f"ERROR: Failed to setup notification widget: {e}")
            import traceback
            traceback.print_exc()
        
        # Bottom section with navigation and footer
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(side="bottom", fill="x")
        
        # Navigation frame (Volver button)
        nav_frame = ttk.Frame(bottom_frame)
        nav_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Button(
            nav_frame,
            text="Volver",
            command=callbacks['back'],
            width=15
        ).pack(side="left")
        
        # Footer with navigation help
        footer_text = "💡 Navega: Volver → Cambiar Tipo Documento → Cambiar Proyecto"
        ttk.Label(
            bottom_frame,
            text=footer_text,
            font=("Arial", 9, "italic"),
            foreground="gray"
        ).pack()
    
    def _setup_notification_widget(self, callbacks: dict):
        """Setup the notification widget in the top-left corner."""
        print("DEBUG: _setup_notification_widget called")
        
        if self.notification_widget:
            print("DEBUG: Removing existing notification widget")
            # Remove existing widget safely
            try:
                self.notification_widget.hide_widget()
            except:
                pass  # Widget might already be destroyed
        
        # Create new notification widget - DISABLED
        print("DEBUG: Creating NotificationWidget - DISABLED")
        # self.notification_widget = NotificationWidget(self.root)  # Removed
        self.notification_widget = None
        
        # Set up callbacks for the widget
        def get_notifications_for_widget():
            try:
                if 'get_notification_data' in callbacks and 'get_current_user' in callbacks:
                    current_user = callbacks['get_current_user']()
                    print(f"DEBUG: Widget getting notifications for user: {current_user}")
                    if current_user:
                        notifications = callbacks['get_notification_data'](current_user)
                        print(f"DEBUG: Widget got {len(notifications)} notifications")
                        return notifications
                print("DEBUG: Widget callback - no user or missing callbacks")
                return []
            except Exception as e:
                print(f"ERROR: Widget notification callback failed: {e}")
                return []
        
        def mark_read_callback(assignment_id):
            if 'mark_notification_as_read' in callbacks:
                return callbacks['mark_notification_as_read'](assignment_id)
            return False
        
        def navigate_callback(document_id):
            if 'navigate_to_document' in callbacks:
                callbacks['navigate_to_document'](document_id)
        
        # Configure the widget - DISABLED
        # self.notification_widget.set_callbacks(
        #     get_notifications=get_notifications_for_widget,
        #     mark_read=mark_read_callback,
        #     on_click=navigate_callback
        # )  # Removed
        
        # Set current user - DISABLED
        print("DEBUG: Setting current user - DISABLED")
        # if 'get_current_user' in callbacks:
        #     current_user = callbacks['get_current_user']()
        #     print(f"DEBUG: Current user: {current_user}")
        #     if current_user:
        #         self.notification_widget.set_current_user(current_user)  # Removed
        
        # Initial refresh - DISABLED
        print("DEBUG: Notification widget disabled")
        # self.notification_widget.refresh_count()  # Removed
        # self.notification_widget.show_widget()  # Removed
        print("DEBUG: Notification widget setup completed (disabled)")