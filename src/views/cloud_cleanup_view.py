"""
Cloud Cleanup View
UI for managing cloud storage cleanup and version management.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, Any
from .base_view import BaseView


class CloudCleanupView(BaseView):
    def __init__(self, root: tk.Tk, enhanced_cloud_sync):
        super().__init__(root)
        self.enhanced_cloud_sync = enhanced_cloud_sync
        self.cleanup_preview = None
    
    def show(self, callbacks: Dict[str, Callable]) -> None:
        """Show the cloud cleanup management screen."""
        self.clear_window()
        self.center_window(900, 800)
        
        # Header
        self.create_header(self.root, "Gestión de Versiones en la Nube")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Info section
        info_frame = ttk.LabelFrame(main_frame, text="Política de Retención", padding="15")
        info_frame.pack(fill="x", pady=(0, 20))
        
        info_text = (
            "📋 Política Actual: Mantener las últimas 2 versiones de cada documento\n"
            "🗑️ Se eliminarán automáticamente las versiones más antiguas\n"
            "☁️ Aplica tanto a SharePoint como a Google Drive\n"
            "🔍 Usa la nomenclatura del archivo para identificar versiones"
        )
        
        ttk.Label(
            info_frame,
            text=info_text,
            font=("Arial", 10),
            foreground="darkblue",
            justify="left"
        ).pack(anchor="w")
        
        # Preview section
        preview_frame = ttk.LabelFrame(main_frame, text="Vista Previa de Limpieza", padding="15")
        preview_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        # Preview controls
        preview_controls = ttk.Frame(preview_frame)
        preview_controls.pack(fill="x", pady=(0, 10))
        
        ttk.Button(
            preview_controls,
            text="🔍 Analizar Archivos en la Nube",
            command=self.analyze_cloud_files
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            preview_controls,
            text="🔄 Actualizar Vista",
            command=self.refresh_preview
        ).pack(side="left")
        
        # Results display
        self.results_text = tk.Text(
            preview_frame,
            height=15,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#f8f9fa",
            fg="#2c3e50"
        )
        self.results_text.pack(fill="both", expand=True, pady=(10, 0))
        
        # Scrollbar for results
        scrollbar = ttk.Scrollbar(preview_frame, orient="vertical", command=self.results_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.results_text.configure(yscrollcommand=scrollbar.set)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill="x", pady=(0, 20))
        
        # Cleanup buttons
        ttk.Button(
            action_frame,
            text="🧹 Limpiar SharePoint",
            command=self.cleanup_sharepoint,
            style="Accent.TButton"
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            action_frame,
            text="🧹 Limpiar Google Drive",
            command=self.cleanup_drive,
            style="Accent.TButton"
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            action_frame,
            text="🧹 Limpiar Todo",
            command=self.cleanup_all,
            style="Accent.TButton"
        ).pack(side="left", padx=(0, 10))
        
        # Separator
        ttk.Separator(action_frame, orient="vertical").pack(side="left", fill="y", padx=20)
        
        # Settings button
        ttk.Button(
            action_frame,
            text="⚙️ Configuración",
            command=self.show_settings
        ).pack(side="left")
        
        # Navigation
        nav_frame = ttk.Frame(main_frame)
        nav_frame.pack(fill="x")
        
        ttk.Button(
            nav_frame,
            text="🔙 Volver",
            command=callbacks.get('back', lambda: None)
        ).pack(side="right")
        
        # Auto-load preview
        self.root.after(500, self.analyze_cloud_files)
    
    def analyze_cloud_files(self):
        """Analyze cloud files and show cleanup preview"""
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, "🔍 Analizando archivos en la nube...\n\n")
        self.root.update()
        
        try:
            # Get cleanup preview
            self.cleanup_preview = self.enhanced_cloud_sync.get_cleanup_preview()
            
            if not self.cleanup_preview:
                self.results_text.delete(1.0, tk.END)
                self.results_text.insert(tk.END, "❌ No se pudo conectar a los servicios de nube")
                return
            
            self._display_cleanup_preview(self.cleanup_preview)
            
        except Exception as e:
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(tk.END, f"❌ Error al analizar archivos: {str(e)}")
    
    def _display_cleanup_preview(self, preview: Dict[str, Any]):
        """Display the cleanup preview in the text widget"""
        self.results_text.delete(1.0, tk.END)
        
        # Header
        self.results_text.insert(tk.END, "📊 ANÁLISIS DE LIMPIEZA DE VERSIONES\n")
        self.results_text.insert(tk.END, "=" * 50 + "\n\n")
        
        # SharePoint section
        if 'sharepoint' in preview:
            sp_data = preview['sharepoint']
            self.results_text.insert(tk.END, "☁️ SHAREPOINT:\n")
            
            if sp_data.get('error'):
                self.results_text.insert(tk.END, f"   ❌ Error: {sp_data['error']}\n\n")
            elif sp_data.get('files_to_delete', 0) == 0:
                self.results_text.insert(tk.END, "   ✅ No hay archivos para eliminar\n\n")
            else:
                files_to_delete = sp_data.get('files_to_delete', 0)
                documents = sp_data.get('documents_analyzed', 0)
                self.results_text.insert(tk.END, f"   📄 Documentos analizados: {documents}\n")
                self.results_text.insert(tk.END, f"   🗑️ Archivos a eliminar: {files_to_delete}\n\n")
                
                # Show detailed cleanup plan
                if 'cleanup_plan' in sp_data:
                    self.results_text.insert(tk.END, "   📋 Plan de limpieza detallado:\n")
                    for doc_id, files in sp_data['cleanup_plan'].items():
                        self.results_text.insert(tk.END, f"      📄 {doc_id}:\n")
                        for file in files:
                            self.results_text.insert(tk.END, f"         ❌ {file}\n")
                    self.results_text.insert(tk.END, "\n")
        
        # Google Drive section
        if 'google_drive' in preview:
            gd_data = preview['google_drive']
            self.results_text.insert(tk.END, "🔍 GOOGLE DRIVE:\n")
            
            if gd_data.get('error'):
                self.results_text.insert(tk.END, f"   ❌ Error: {gd_data['error']}\n\n")
            elif gd_data.get('files_to_delete', 0) == 0:
                self.results_text.insert(tk.END, "   ✅ No hay archivos para eliminar\n\n")
            else:
                files_to_delete = gd_data.get('files_to_delete', 0)
                documents = gd_data.get('documents_analyzed', 0)
                self.results_text.insert(tk.END, f"   📄 Documentos analizados: {documents}\n")
                self.results_text.insert(tk.END, f"   🗑️ Archivos a eliminar: {files_to_delete}\n\n")
                
                # Show detailed cleanup plan
                if 'cleanup_plan' in gd_data:
                    self.results_text.insert(tk.END, "   📋 Plan de limpieza detallado:\n")
                    for doc_id, files in gd_data['cleanup_plan'].items():
                        self.results_text.insert(tk.END, f"      📄 {doc_id}:\n")
                        for file in files:
                            self.results_text.insert(tk.END, f"         ❌ {file}\n")
                    self.results_text.insert(tk.END, "\n")
        
        # Summary
        if 'summary' in preview and preview['summary'].get('dry_run'):
            total_files = preview['summary'].get('total_files_to_delete', 0)
            self.results_text.insert(tk.END, f"📊 RESUMEN: {total_files} archivos serán eliminados en total\n\n")
        
        # Instructions
        self.results_text.insert(tk.END, "💡 INSTRUCCIONES:\n")
        self.results_text.insert(tk.END, "   • Usa los botones de limpieza para ejecutar la eliminación\n")
        self.results_text.insert(tk.END, "   • Se mantendrán las últimas 2 versiones de cada documento\n")
        self.results_text.insert(tk.END, "   • La operación es irreversible\n")
    
    def refresh_preview(self):
        """Refresh the cleanup preview"""
        self.analyze_cloud_files()
    
    def cleanup_sharepoint(self):
        """Execute SharePoint cleanup after confirmation"""
        if not self.cleanup_preview:
            messagebox.showwarning("Aviso", "Primero ejecuta el análisis de archivos")
            return
        
        sp_data = self.cleanup_preview.get('sharepoint', {})
        files_to_delete = sp_data.get('files_to_delete', 0)
        
        if files_to_delete == 0:
            messagebox.showinfo("Info", "No hay archivos para eliminar en SharePoint")
            return
        
        # Confirmation dialog
        if not messagebox.askyesno(
            "Confirmar Limpieza", 
            f"¿Eliminar {files_to_delete} archivos antiguos de SharePoint?\n\n"
            "Esta operación no se puede deshacer."
        ):
            return
        
        try:
            result = self.enhanced_cloud_sync.manual_cleanup_document(None, dry_run=False)
            sp_result = result.get('sharepoint', {})
            
            if sp_result.get('success'):
                deleted = sp_result.get('deleted', 0)
                messagebox.showinfo("Éxito", f"✅ Se eliminaron {deleted} archivos de SharePoint")
            else:
                error = sp_result.get('error', 'Error desconocido')
                messagebox.showerror("Error", f"❌ Error en SharePoint: {error}")
            
            # Refresh preview
            self.analyze_cloud_files()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error durante la limpieza: {str(e)}")
    
    def cleanup_drive(self):
        """Execute Google Drive cleanup after confirmation"""
        if not self.cleanup_preview:
            messagebox.showwarning("Aviso", "Primero ejecuta el análisis de archivos")
            return
        
        gd_data = self.cleanup_preview.get('google_drive', {})
        files_to_delete = gd_data.get('files_to_delete', 0)
        
        if files_to_delete == 0:
            messagebox.showinfo("Info", "No hay archivos para eliminar en Google Drive")
            return
        
        # Confirmation dialog
        if not messagebox.askyesno(
            "Confirmar Limpieza", 
            f"¿Eliminar {files_to_delete} archivos antiguos de Google Drive?\n\n"
            "Esta operación no se puede deshacer."
        ):
            return
        
        try:
            result = self.enhanced_cloud_sync.manual_cleanup_document(None, dry_run=False)
            gd_result = result.get('google_drive', {})
            
            if gd_result.get('success'):
                deleted = gd_result.get('deleted', 0)
                messagebox.showinfo("Éxito", f"✅ Se eliminaron {deleted} archivos de Google Drive")
            else:
                error = gd_result.get('error', 'Error desconocido')
                messagebox.showerror("Error", f"❌ Error en Google Drive: {error}")
            
            # Refresh preview
            self.analyze_cloud_files()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error durante la limpieza: {str(e)}")
    
    def cleanup_all(self):
        """Execute cleanup for both services after confirmation"""
        if not self.cleanup_preview:
            messagebox.showwarning("Aviso", "Primero ejecuta el análisis de archivos")
            return
        
        # Calculate total files to delete
        sp_files = self.cleanup_preview.get('sharepoint', {}).get('files_to_delete', 0)
        gd_files = self.cleanup_preview.get('google_drive', {}).get('files_to_delete', 0)
        total_files = sp_files + gd_files
        
        if total_files == 0:
            messagebox.showinfo("Info", "No hay archivos para eliminar")
            return
        
        # Confirmation dialog
        if not messagebox.askyesno(
            "Confirmar Limpieza Completa", 
            f"¿Eliminar {total_files} archivos antiguos de ambos servicios?\n\n"
            f"SharePoint: {sp_files} archivos\n"
            f"Google Drive: {gd_files} archivos\n\n"
            "Esta operación no se puede deshacer."
        ):
            return
        
        try:
            result = self.enhanced_cloud_sync.manual_cleanup_all(dry_run=False)
            
            # Show results
            messages = []
            if result.get('sharepoint', {}).get('success'):
                sp_deleted = result['sharepoint'].get('deleted', 0)
                messages.append(f"SharePoint: {sp_deleted} archivos eliminados")
            
            if result.get('google_drive', {}).get('success'):
                gd_deleted = result['google_drive'].get('deleted', 0)
                messages.append(f"Google Drive: {gd_deleted} archivos eliminados")
            
            total_deleted = result.get('summary', {}).get('total_deleted', 0)
            
            messagebox.showinfo(
                "Limpieza Completada", 
                f"✅ Limpieza completada\n\n" + "\n".join(messages) + f"\n\nTotal: {total_deleted} archivos eliminados"
            )
            
            # Refresh preview
            self.analyze_cloud_files()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error durante la limpieza: {str(e)}")
    
    def show_settings(self):
        """Show cleanup settings dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Configuración de Limpieza")
        settings_window.geometry("400x300")
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # Main frame
        main_frame = ttk.Frame(settings_window, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(
            main_frame,
            text="Configuración de Retención de Versiones",
            font=("Arial", 12, "bold")
        ).pack(pady=(0, 20))
        
        # Version retention setting
        ttk.Label(main_frame, text="Número de versiones a mantener:").pack(anchor="w", pady=(0, 5))
        
        version_count = tk.StringVar(value="2")
        version_spinbox = ttk.Spinbox(main_frame, from_=1, to=10, textvariable=version_count, width=5)
        version_spinbox.pack(anchor="w", pady=(0, 20))
        
        # Auto-cleanup setting
        auto_cleanup = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            main_frame,
            text="Limpiar automáticamente al subir nuevas versiones",
            variable=auto_cleanup
        ).pack(anchor="w", pady=(0, 20))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(20, 0))
        
        ttk.Button(button_frame, text="Guardar", command=settings_window.destroy).pack(side="right", padx=(10, 0))
        ttk.Button(button_frame, text="Cancelar", command=settings_window.destroy).pack(side="right")