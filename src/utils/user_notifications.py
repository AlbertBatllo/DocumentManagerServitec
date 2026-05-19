"""
User notification system for critical errors.
Provides user-friendly error messages for critical system failures.
"""

import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable
import threading
from utils.error_logger import logger


class UserNotificationManager:
    """Manages user notifications for critical errors."""
    
    def __init__(self):
        self._root_window: Optional[tk.Tk] = None
        self._notification_enabled = True
    
    def set_root_window(self, root: tk.Tk) -> None:
        """Set the main application window for notifications."""
        self._root_window = root
    
    def disable_notifications(self) -> None:
        """Disable user notifications (for testing)."""
        self._notification_enabled = False
    
    def enable_notifications(self) -> None:
        """Enable user notifications."""
        self._notification_enabled = True
    
    def notify_database_error(self, operation: str, user_message: Optional[str] = None) -> None:
        """Notify user of database-related errors."""
        if not self._notification_enabled:
            return
        
        default_message = (
            f"Error de base de datos durante: {operation}\n\n"
            "Los datos pueden no haberse guardado correctamente. "
            "Por favor, verifica tu trabajo y contacta soporte si el problema persiste."
        )
        
        message = user_message or default_message
        self._show_error_dialog("Error de Base de Datos", message)
    
    def notify_file_operation_error(self, operation: str, file_path: str, user_message: Optional[str] = None) -> None:
        """Notify user of file operation errors."""
        if not self._notification_enabled:
            return
        
        default_message = (
            f"Error de archivo durante: {operation}\n"
            f"Archivo: {file_path}\n\n"
            "Verifica que el archivo existe y tienes permisos de acceso. "
            "Si el archivo está en una unidad de red, verifica la conexión."
        )
        
        message = user_message or default_message
        self._show_error_dialog("Error de Archivo", message)
    
    def notify_network_error(self, service: str, user_message: Optional[str] = None) -> None:
        """Notify user of network/authentication errors."""
        if not self._notification_enabled:
            return
        
        default_message = (
            f"Error de conexión con {service}\n\n"
            "Verifica tu conexión a internet y las credenciales de autenticación. "
            "Puedes continuar trabajando localmente."
        )
        
        message = user_message or default_message
        self._show_warning_dialog("Error de Conexión", message)
    
    def notify_configuration_error(self, config_type: str, user_message: Optional[str] = None) -> None:
        """Notify user of configuration loading errors."""
        if not self._notification_enabled:
            return
        
        default_message = (
            f"Error al cargar configuración: {config_type}\n\n"
            "Se usarán valores por defecto. "
            "Revisa los archivos de configuración o contacta soporte."
        )
        
        message = user_message or default_message
        self._show_warning_dialog("Error de Configuración", message)
    
    def notify_critical_system_error(self, operation: str, user_message: Optional[str] = None) -> None:
        """Notify user of critical system errors that may affect functionality."""
        if not self._notification_enabled:
            return
        
        default_message = (
            f"Error crítico del sistema durante: {operation}\n\n"
            "Esta operación puede haber fallado. "
            "Se recomienda guardar tu trabajo y reiniciar la aplicación."
        )
        
        message = user_message or default_message
        self._show_error_dialog("Error Crítico", message)
    
    def _show_error_dialog(self, title: str, message: str) -> None:
        """Show error dialog to user."""
        self._show_dialog(messagebox.showerror, title, message)
    
    def _show_warning_dialog(self, title: str, message: str) -> None:
        """Show warning dialog to user."""
        self._show_dialog(messagebox.showwarning, title, message)
    
    def _show_dialog(self, dialog_func: Callable, title: str, message: str) -> None:
        """Show dialog in thread-safe manner."""
        def show_dialog():
            try:
                if self._root_window and self._root_window.winfo_exists():
                    # Ensure dialog shows on top
                    self._root_window.lift()
                    self._root_window.focus_force()
                    dialog_func(title, message, parent=self._root_window)
                else:
                    # Fallback if no root window
                    dialog_func(title, message)
            except Exception as e:
                # Last resort - log the notification failure
                logger.error(f"Failed to show user notification dialog", e, {
                    "title": title, 
                    "message": message[:100] + "..." if len(message) > 100 else message
                })
        
        # Show dialog in main thread if possible
        if threading.current_thread() is threading.main_thread():
            show_dialog()
        else:
            # Schedule for main thread
            if self._root_window:
                try:
                    self._root_window.after(0, show_dialog)
                except Exception:
                    # Fallback - show immediately
                    show_dialog()
            else:
                show_dialog()


# Global notification manager instance
notification_manager = UserNotificationManager()


def notify_user_of_database_error(operation: str, user_message: Optional[str] = None) -> None:
    """Convenience function to notify user of database errors."""
    notification_manager.notify_database_error(operation, user_message)


def notify_user_of_file_error(operation: str, file_path: str, user_message: Optional[str] = None) -> None:
    """Convenience function to notify user of file errors."""
    notification_manager.notify_file_operation_error(operation, file_path, user_message)


def notify_user_of_network_error(service: str, user_message: Optional[str] = None) -> None:
    """Convenience function to notify user of network errors."""
    notification_manager.notify_network_error(service, user_message)


def notify_user_of_config_error(config_type: str, user_message: Optional[str] = None) -> None:
    """Convenience function to notify user of configuration errors."""
    notification_manager.notify_configuration_error(config_type, user_message)


def notify_user_of_critical_error(operation: str, user_message: Optional[str] = None) -> None:
    """Convenience function to notify user of critical errors."""
    notification_manager.notify_critical_system_error(operation, user_message)