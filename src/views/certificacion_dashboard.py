import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
from typing import List, Optional, Callable, Dict, Any
from pathlib import Path
from datetime import datetime
import subprocess
import platform
from .responsive_base_view import ResponsiveBaseView
from models.certificacion_document import CertificacionDocument, CERTIFICACION_STATES, CERTIFICACION_STATE_DISPLAY_NAMES, CERTIFICACION_STATE_DESCRIPTIONS
from controllers.certificacion_controller import CertificacionController


class CertificacionDashboard(ResponsiveBaseView):
    """Dashboard for viewing and managing certificaciones"""
    
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.certificaciones: List[CertificacionDocument] = []
        self.controller: Optional[CertificacionController] = None
        self.selected_certificacion: Optional[CertificacionDocument] = None
        
    def show(self, controller: CertificacionController, callbacks: dict, user_name: str = "") -> None:
        """Show the certificacion dashboard with responsive design"""
        self.clear_window()
        
        # Use responsive window sizing instead of fixed 1100x700
        self.center_window_responsive(
            preferred_width=1200, 
            preferred_height=800,
            min_width=900,
            min_height=600
        )
        
        self.controller = controller
        self.callbacks = callbacks
        
        # Use fast summary loading for improved performance
        self.certificaciones = self._get_certificaciones_for_display(controller)
        
        # Window controls toolbar removed - no maximize buttons needed
        
        # Header
        self.create_header(self.root, "CERTIFICACIONES - Panel de Control")
        
        # Create main container structure
        # Content container - expandable
        main_content = ttk.Frame(self.root, padding="10")
        main_content.pack(fill="both", expand=True)
        
        # Bottom container using responsive design
        bottom_frame = self.create_bottom_button_frame(self.root)
        
        # Centered Certificaciones title - more prominent
        title_frame = ttk.Frame(main_content)
        title_frame.pack(fill="x", pady=(0, 15))
        
        title_label = ttk.Label(
            title_frame,
            text="CERTIFICACIONES",
            font=("Arial", 28, "bold"),
            foreground="#2E5984"  # Professional blue color
        )
        title_label.pack()
        
        # Subtitle with dynamic project info
        project_name = self._get_project_name_from_controller(controller)
        subtitle_label = ttk.Label(
            title_frame,
            text=f"Certificaciones - {project_name}",
            font=("Arial", 14),
            foreground="#666666"
        )
        subtitle_label.pack(pady=(5, 0))
        
        # Top section - Financial summary
        self._create_financial_summary(main_content)
        
        # State legend section
        self._create_state_legend(main_content)
        
        # Middle section - Certificaciones list
        self._create_certificaciones_list(main_content)
        
        # Add helpful hint for double-click functionality
        hint_frame = ttk.Frame(main_content)
        hint_frame.pack(fill="x", pady=(5, 0))
        
        hint_label = ttk.Label(
            hint_frame,
            text="💡 Consejo: Haz doble clic en una certificación para abrir su carpeta de archivos",
            font=("Arial", 9),
            foreground="#666666"
        )
        hint_label.pack(anchor="w")
        
        # Bottom section - Actions (moved to bottom frame for always-visible buttons)
        self._create_action_buttons(bottom_frame, callbacks)
        
        # Setup notification widget if available
        if user_name and 'get_notification_data' in callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: callbacks.get('get_notification_data')(user_name),
                mark_read_callback=callbacks.get('mark_notification_as_read'),
                navigate_callback=callbacks.get('navigate_to_document'),
                current_user=user_name
            )
        
        # Refresh data
        self._refresh_list()
        self._refresh_summary()
    
    def _get_project_name_from_controller(self, controller) -> str:
        """Extract project name from controller's project path"""
        try:
            if hasattr(controller, 'project_path') and controller.project_path:
                # Get the project folder name (last part of the path)
                project_name = controller.project_path.name
                # If it's just "." or empty, try to get from storage path
                if project_name == "." or not project_name:
                    if hasattr(controller, 'storage_path'):
                        # Get parent directory name from storage path
                        project_name = controller.storage_path.parent.name
                return project_name if project_name else "Proyecto Actual"
            return "Proyecto Actual"
        except Exception:
            return "Proyecto Actual"
    
    def _get_certificaciones_for_display(self, controller: CertificacionController):
        """
        Get certificaciones for dashboard display using fast summary loading when available.
        
        Performance optimization: Use lightweight summaries for initial display,
        avoiding the overhead of loading complete monthly history.
        Falls back to full document loading for backward compatibility.
        """
        try:
            # Try to use fast summary loading if available
            if hasattr(controller, 'get_certificacion_summaries'):
                print(f"DEBUG: Using fast CertificacionSummary loading for dashboard")
                return controller.get_certificacion_summaries()
            
            # Fallback to traditional full document loading
            print(f"DEBUG: Using traditional full certificacion document loading")
            return controller.get_all_certificaciones()
            
        except Exception as e:
            print(f"Warning: Error in fast certificacion loading, falling back: {e}")
            # Always have a fallback to ensure app doesn't crash
            return controller.get_all_certificaciones()

    def _create_financial_summary(self, parent: tk.Widget) -> None:
        """Create financial summary section"""
        summary_frame = ttk.LabelFrame(parent, text="Resumen Financiero Global", padding="10")
        summary_frame.pack(fill="x", pady=(0, 10))
        
        # Create summary labels with placeholders
        summary_grid = ttk.Frame(summary_frame)
        summary_grid.pack(fill="x")
        
        # Configure columns
        for i in range(4):
            summary_grid.columnconfigure(i, weight=1)
        
        # Summary labels
        self.lbl_total_presupuesto = self._create_summary_item(
            summary_grid, "PRESUPUESTO TOTAL", "0.00 €", 0, 0, "#2E7D32"
        )
        
        self.lbl_total_certificado = self._create_summary_item(
            summary_grid, "TOTAL CERTIFICADO", "0.00 €", 0, 1, "#1565C0"
        )
        
        self.lbl_total_adicionales = self._create_summary_item(
            summary_grid, "TOTAL ADICIONALES", "0.00 €", 0, 2, "#7B1FA2"
        )
        
        self.lbl_porcentaje_global = self._create_summary_item(
            summary_grid, "% COMPLETADO GLOBAL", "0.00%", 0, 3, "#E65100"
        )

    def _create_summary_item(self, parent: tk.Widget, title: str, value: str, 
                            row: int, col: int, color: str) -> ttk.Label:
        """Create a summary display item"""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, padx=10, pady=5, sticky="ew")
        
        ttk.Label(
            frame,
            text=title,
            font=("Arial", 9, "bold")
        ).pack(anchor="w")
        
        value_label = ttk.Label(
            frame,
            text=value,
            font=("Arial", 14, "bold"),
            foreground=color
        )
        value_label.pack(anchor="w")
        
        return value_label

    def _create_state_legend(self, parent: tk.Widget) -> None:
        """Create collapsible state legend like in Planos"""
        # Container for the legend
        legend_container = ttk.Frame(parent)
        legend_container.pack(fill="x", pady=(0, 10))
        
        # Right-align the legend
        legend_controls = ttk.Frame(legend_container)
        legend_controls.pack(side="right")
        
        # Legend toggle button
        self.legend_visible = False
        self.legend_button = ttk.Button(
            legend_controls,
            text="▼ Leyenda de Estados",
            command=self._toggle_legend
        )
        self.legend_button.pack(anchor="e")
        
        # Legend frame (initially hidden)
        self.legend_frame = ttk.Frame(legend_controls)
        # Don't pack initially - will be shown when toggled
        
        # Color legend for certificacion states (standardized)
        self.certificacion_state_colors = {
            "S0": "#FFFFFF",  # White - Borrador
            "S1": "#FFFF00",  # Yellow - Revisado por Delineación
            "S2": "#00AAE4",  # Blue - Revisado por Técnico Especialista
            "S3": "#B19CD9",  # Purple - Revisado por Director Proyecto
            "S3A": "#008F39" # Green - Aprobado por propiedad/promotor
        }
        
        # Create legend content (but don't show initially)
        self._create_legend_content()

    def _toggle_legend(self) -> None:
        """Toggle the visibility of the legend panel"""
        if self.legend_visible:
            # Hide legend
            self.legend_frame.pack_forget()
            self.legend_button.config(text="▼ Leyenda de Estados")
            self.legend_visible = False
        else:
            # Show legend
            self.legend_frame.pack(pady=(5, 0), anchor="e")
            self.legend_button.config(text="▲ Leyenda de Estados")
            self.legend_visible = True

    def _create_legend_content(self) -> None:
        """Create the legend content inside the legend frame"""
        # Clear existing content
        for widget in self.legend_frame.winfo_children():
            widget.destroy()
        
        # Create a labeled frame for the legend
        legend_content = ttk.LabelFrame(self.legend_frame, text="Estados en Certificaciones", padding=10)
        legend_content.pack(fill="both", expand=True)
        
        for i, (status, color) in enumerate(self.certificacion_state_colors.items()):
            color_label = tk.Label(legend_content, text="  ", bg=color)
            color_label.grid(row=i, column=0, pady=2, sticky="w")
            text_label = ttk.Label(legend_content, text=f" {CERTIFICACION_STATE_DISPLAY_NAMES.get(status, status)}")
            text_label.grid(row=i, column=1, pady=2, sticky="w")
        
        # Info button
        info_button = ttk.Button(legend_content, text="?", command=self._show_status_info, width=2)
        info_button.grid(row=0, column=2, rowspan=len(self.certificacion_state_colors), sticky="ns", padx=(5,0))

    def _show_status_info(self) -> None:
        """Show status information popup for certificaciones"""
        info_win = tk.Toplevel(self.root)
        info_win.title("Información de Estados - Certificaciones")
        info_win.geometry("800x300")
        info_win.transient(self.root)
        info_win.grab_set()
        
        cols = ('code', 'meaning', 'description')
        tree = ttk.Treeview(info_win, columns=cols, show='headings')
        
        tree.heading('code', text='Código')
        tree.heading('meaning', text='Estado en certificaciones')
        tree.heading('description', text='Significado')
        tree.column('code', width=60, anchor='center')
        tree.column('meaning', width=180)
        tree.column('description', width=520)
        
        status_data = [
            ("S0", "Borrador", "Trabajo en proceso. NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO"),
            ("S1", "Revisado por Delineación", "NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO"),
            ("S2", "Revisado por Técnico Especialista", "Revisado por técnico especialista."),
            ("S3", "Revisado por Director Proyecto", "SE PUEDE ENVIAR A PROPIEDAD EN ESTE ESTADO"),
            ("S3A", "Aprobado por propiedad/promotor", "Aprobado por propiedad/promotor."),
            ("D", "Denegado", "Documento rechazado. ESTADO FINAL - Sin sincronización en la nube.")
        ]
        
        for row in status_data:
            tree.insert("", "end", values=row)
        
        tree.pack(fill="both", expand=True, padx=10, pady=10)

    def _create_certificaciones_list(self, parent: tk.Widget) -> None:
        """Create the certificaciones list table"""
        list_frame = ttk.LabelFrame(parent, text="Certificaciones Activas", padding="10")
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Create treeview with scrollbars
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill="both", expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        columns = (
            "Lote", "Empresa", "Estado", "Presupuesto", "Certificado", 
            "% Completado", "Adicionales", "Total", "Última Actualización"
        )
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="tree headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            height=12
        )
        
        # Configure scrollbars
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Configure columns
        self.tree.column("#0", width=60, minwidth=60)  # ID column
        self.tree.column("Lote", width=200, minwidth=150)
        self.tree.column("Empresa", width=150, minwidth=100)
        self.tree.column("Estado", width=80, minwidth=60, anchor="center")
        self.tree.column("Presupuesto", width=120, minwidth=100, anchor="e")
        self.tree.column("Certificado", width=120, minwidth=100, anchor="e")
        self.tree.column("% Completado", width=100, minwidth=80, anchor="center")
        self.tree.column("Adicionales", width=100, minwidth=80, anchor="e")
        self.tree.column("Total", width=120, minwidth=100, anchor="e")
        self.tree.column("Última Actualización", width=130, minwidth=100, anchor="center")
        
        # Configure headings
        self.tree.heading("#0", text="Nombre")
        for col in columns:
            self.tree.heading(col, text=col)
        
        # Pack components
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self._on_select_certificacion)
        
        # Bind double-click event to open company folder
        self.tree.bind("<Double-1>", self._on_double_click_certificacion)
        
        # Configure treeview styling without changing global theme
        self.style = ttk.Style()
        
        # Configure tag colors for certificacion states (text coloring like planos/presupuestos)
        # Using foreground colors matching the legend - same pattern as planos and presupuestos
        self.tree.tag_configure("S0", foreground="#FFFFFF", background="#333333")  # Pure White with dark background - Borrador (maximum visibility)
        self.tree.tag_configure("S1", foreground="#FFFF00", background="#2B2B2B")  # Yellow - Revisado por Delineación with dark background
        self.tree.tag_configure("S2", foreground="#00AAE4", background="#1A1A1A")  # Blue - Revisado por Técnico Especialista with dark background
        self.tree.tag_configure("S3", foreground="#B19CD9", background="#1A1A1A")  # Purple - Revisado por Director Proyecto with dark background
        self.tree.tag_configure("S3A", foreground="#008F39", background="#1A1A1A") # Green - Aprobado por propiedad/promotor with dark background
        self.tree.tag_configure("D", foreground="#FF0000", background="#1A1A1A")   # Red - Denegado with dark background
        
        # Configure Treeview to reduce selection highlighting interference
        try:
            # Completely disable selection highlighting so our custom colors always show
            self.style.configure("Treeview", selectbackground="", selectforeground="")
            # Also configure focus highlighting
            self.style.configure("Treeview", focuscolor="none")
            # Map state-specific styling to override selection
            self.style.map("Treeview", 
                          selectbackground=[("", "")],
                          selectforeground=[("", "")])
        except Exception:
            # Fallback if style configuration fails
            pass
        self.tree.tag_configure("default_state", foreground="#808080")  # Gray (default)

    def _create_action_buttons(self, parent: tk.Widget, callbacks: dict) -> None:
        """Create action buttons"""
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x")
        
        # Left side - Certificacion actions
        left_frame = ttk.Frame(action_frame)
        left_frame.pack(side="left", fill="x", expand=True)
        
        ttk.Button(
            left_frame,
            text="Nueva Certificación Mensual",
            command=self._show_monthly_certification_form,
            state="disabled"
        ).pack(side="left", padx=5)
        
        self.btn_monthly = left_frame.winfo_children()[-1]
        
        
        ttk.Button(
            left_frame,
            text="Ver Historial",
            command=self._show_history,
            state="disabled"
        ).pack(side="left", padx=5)
        
        self.btn_history = left_frame.winfo_children()[-1]
        
        ttk.Button(
            left_frame,
            text="Ver Adicionales",
            command=self._show_adicionales,
            state="disabled"
        ).pack(side="left", padx=5)
        
        self.btn_adicionales = left_frame.winfo_children()[-1]
        
        # State management buttons
        ttk.Button(
            left_frame,
            text="Cambiar Estado",
            command=lambda: self._show_state_change_dialog(callbacks),
            state="disabled"
        ).pack(side="left", padx=5)
        
        self.btn_change_state = left_frame.winfo_children()[-1]
        
        # Add annotation/correction button
        ttk.Button(
            left_frame,
            text="Editar Información",
            command=lambda: self._show_edit_info_with_selection(callbacks),
            state="disabled"
        ).pack(side="left", padx=5)
        
        self.btn_edit_info = left_frame.winfo_children()[-1]
        
        # Right side - Export and navigation
        right_frame = ttk.Frame(action_frame)
        right_frame.pack(side="right")
        
        ttk.Button(
            right_frame,
            text="Exportar a Excel",
            command=self._export_to_excel,
            width=20
        ).pack(side="left", padx=5)
        
        ttk.Button(
            right_frame,
            text="Actualizar",
            command=self._refresh_all
        ).pack(side="left", padx=5)
        
        ttk.Button(
            right_frame,
            text="Volver",
            command=callbacks.get('back', lambda: None)
        ).pack(side="left", padx=5)
        
        # Ensure all buttons are visible and accessible
        self.ensure_buttons_visible(action_frame)

    def _on_select_certificacion(self, event=None) -> None:
        """Handle certificacion selection"""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            cert_nombre = item['text']
            
            # Find selected certificacion by nombre
            self.selected_certificacion = next(
                (c for c in self.certificaciones if c.nombre == cert_nombre), 
                None
            )
            
            # Enable/disable buttons
            if self.selected_certificacion:
                self.btn_monthly.config(state="normal")
                self.btn_history.config(state="normal")
                self.btn_adicionales.config(state="normal")
                self.btn_change_state.config(state="normal")
                self.btn_edit_info.config(state="normal")
            else:
                self.btn_monthly.config(state="disabled")
                self.btn_history.config(state="disabled")
                self.btn_adicionales.config(state="disabled")
                self.btn_change_state.config(state="disabled")
                self.btn_edit_info.config(state="disabled")

    def _on_double_click_certificacion(self, event=None) -> None:
        """Handle double-click on certificacion to open file location"""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = self.tree.item(selection[0])
        cert_nombre = item['text']
        
        # Use the open_document_location callback if available
        if 'open_document_location' in self.callbacks:
            try:
                self.callbacks['open_document_location'](cert_nombre)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo abrir la ubicación del documento: {e}")
        else:
            # Fallback to the old folder opening behavior
            self._fallback_open_folder(cert_nombre)
    
    def _fallback_open_folder(self, cert_nombre: str) -> None:
        """Fallback method to open company folder (old behavior)"""
        # Find selected certificacion by nombre
        certificacion = next(
            (c for c in self.certificaciones if c.nombre == cert_nombre), 
            None
        )
        
        if not certificacion or not self.controller:
            return
        
        try:
            # Get the company folder path using the file manager
            if hasattr(self.controller, 'file_manager'):
                company_folder = self.controller.file_manager.get_company_folder_path(certificacion)
                
                # Create the folder if it doesn't exist
                if not company_folder.exists():
                    self.controller.file_manager.create_company_folder(certificacion)
                
                # Open the folder in the system file manager
                self._open_folder_in_explorer(company_folder)
            else:
                messagebox.showwarning(
                    "Funcionalidad no disponible",
                    "El sistema de archivos no está configurado para esta certificación."
                )
                
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"No se pudo abrir la carpeta de la certificación: {str(e)}"
            )

    def _open_folder_in_explorer(self, folder_path: Path) -> None:
        """Open folder in system file explorer"""
        try:
            system = platform.system()
            folder_str = str(folder_path)
            
            if system == "Windows":
                subprocess.Popen(["explorer", folder_str])
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", folder_str])
            else:
                messagebox.showwarning(
                    "Sistema no soportado",
                    f"No se puede abrir carpetas automáticamente en {system}"
                )
        except Exception as e:
            messagebox.showerror(
                "Error del sistema",
                f"No se pudo abrir la carpeta: {str(e)}"
            )
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Error inesperado al abrir la carpeta: {str(e)}"
            )

    def _refresh_list(self) -> None:
        """Refresh the certificaciones list"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Sort certificaciones by lote
        self.certificaciones.sort(key=lambda x: x.lote_number)
        
        # Add certificaciones to tree
        for cert in self.certificaciones:
            # Format values
            presupuesto = f"{cert.presupuesto_contratado:,.2f} €"
            certificado = f"{cert.cumulative_certificado:,.2f} €"
            porcentaje = cert.porcentaje_completado_actual
            adicionales = f"{cert.cumulative_adicionales:,.2f} €"
            total = f"{cert.total_certificado_global:,.2f} €"
            
            # Get last update date
            if cert.latest_entry:
                last_update = cert.latest_entry.fecha
            else:
                last_update = "-"
            
            # Determine tag based on state (prioritizing state over percentage)
            state_tag = cert.current_state if cert.current_state in CERTIFICACION_STATES else "default_state"
            
            # Insert item
            self.tree.insert(
                "",
                "end",
                text=cert.nombre,  # Use nombre instead of id
                values=(
                    cert.lote,
                    cert.empresa,
                    cert.current_state,  # Add state column
                    presupuesto,
                    certificado,
                    f"{porcentaje:.1f}%",
                    adicionales,
                    total,
                    last_update
                ),
                tags=(state_tag,)
            )

    def _refresh_summary(self) -> None:
        """Refresh financial summary"""
        if self.controller:
            summary = self.controller.get_financial_summary()
            
            self.lbl_total_presupuesto.config(
                text=f"{summary['total_presupuesto_contratado']:,.2f} €"
            )
            self.lbl_total_certificado.config(
                text=f"{summary['total_certificado']:,.2f} €"
            )
            self.lbl_total_adicionales.config(
                text=f"{summary['total_adicionales']:,.2f} €"
            )
            self.lbl_porcentaje_global.config(
                text=f"{summary['porcentaje_global']:.1f}%"
            )

    def _refresh_all(self) -> None:
        """Refresh all data"""
        if self.controller:
            # Use fast summary loading for refresh operations too
            self.certificaciones = self._get_certificaciones_for_display(self.controller)
            self._refresh_list()
            self._refresh_summary()

    def _show_history(self) -> None:
        """Show history for selected certificacion"""
        if not self.selected_certificacion:
            return
        
        # Get full document if we have a summary
        full_document = None
        if self.controller:
            # Load the full certificacion document (not just summary)
            full_document = self.controller.get_certificacion(self.selected_certificacion.nombre)
        
        if not full_document:
            messagebox.showwarning("Error", "No se pudo cargar el historial de la certificación")
            return
        
        # Create history window
        history_window = tk.Toplevel(self.root)
        history_window.title(f"Historial - {full_document.nombre}")
        history_window.geometry("900x500")
        history_window.transient(self.root)
        history_window.grab_set()
        
        # Header
        header_frame = ttk.Frame(history_window, padding="10")
        header_frame.pack(fill="x")
        
        ttk.Label(
            header_frame,
            text=f"Certificación: {full_document.nombre}",
            font=("Arial", 12, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text=f"Lote: {full_document.lote}",
            font=("Arial", 10)
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text=f"Empresa: {full_document.empresa}",
            font=("Arial", 10)
        ).pack(anchor="w")
        
        # History table
        tree_frame = ttk.Frame(history_window, padding="10")
        tree_frame.pack(fill="both", expand=True)
        
        columns = (
            "Nº", "Fecha", "Importe", "Retención", "Prorrata",
            "Adicionales", "Total", "% Acumulado", "Autor"
        )
        
        history_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=15
        )
        
        for col in columns:
            history_tree.heading(col, text=col)
            history_tree.column(col, width=100)
        
        # Add entries
        try:
            history_entries = full_document.get_history()
            print(f"DEBUG: Found {len(history_entries)} history entries for certificacion '{self.selected_certificacion.nombre}'")
            
            if not history_entries:
                # Add warning message in header
                warning_frame = ttk.Frame(header_frame)
                warning_frame.pack(fill="x", pady=(5, 0))
                ttk.Label(
                    warning_frame,
                    text="⚠️ Esta certificación no tiene historial de certificaciones registrado.",
                    font=("Arial", 9),
                    foreground="#FF8C00"
                ).pack(anchor="w")
            else:
                for entry in history_entries:
                    history_tree.insert(
                        "",
                        "end",
                        values=(
                            entry.numero_certificacion,
                            entry.fecha,
                            f"{entry.importe_certificado:,.2f}",
                            f"{entry.retencion:,.2f}",
                            f"{entry.cuenta_prorrata:,.2f}",
                            f"{entry.total_adicionales:,.2f}",
                            f"{entry.total_certificado:,.2f}",
                            f"{entry.porcentaje_completado:.1f}%",
                            entry.author
                        )
                    )
        except Exception as e:
            print(f"Error loading certificacion history entries: {e}")
            import traceback
            traceback.print_exc()
            
            # Show error message
            error_frame = ttk.Frame(header_frame)
            error_frame.pack(fill="x", pady=(5, 0))
            ttk.Label(
                error_frame,
                text=f"❌ Error al cargar el historial: {str(e)}",
                font=("Arial", 9),
                foreground="#FF0000"
            ).pack(anchor="w")
        
        history_tree.pack(fill="both", expand=True)
        
        # Close button
        ttk.Button(
            history_window,
            text="Cerrar",
            command=history_window.destroy
        ).pack(pady=10)

    def _show_adicionales(self) -> None:
        """Show adicionales associated with this certificacion in a simple table"""
        if not self.selected_certificacion:
            return
        
        # Get full document if we have a summary
        full_document = None
        if self.controller:
            # Load the full certificacion document (not just summary)
            full_document = self.controller.get_certificacion(self.selected_certificacion.nombre)
        
        if not full_document:
            messagebox.showwarning("Error", "No se pudo cargar los adicionales de la certificación")
            return
        
        # Create adicionales window
        adicionales_window = tk.Toplevel(self.root)
        adicionales_window.title(f"Adicionales - {full_document.nombre}")
        adicionales_window.geometry("950x550")
        adicionales_window.transient(self.root)
        
        # Header
        header_frame = ttk.Frame(adicionales_window, padding="10")
        header_frame.pack(fill="x")
        
        ttk.Label(
            header_frame,
            text=f"Adicionales Asociados - {full_document.nombre}",
            font=("Arial", 14, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text=f"Lote: {full_document.lote}",
            font=("Arial", 10)
        ).pack(anchor="w")
        
        # Collect all adicionales used in this certificacion
        # Map adicional_id -> (fecha, cert_num, importe)
        adicionales_data = {}
        
        for entry in full_document.entries:
            for adicional_id in entry.adicionales_ids:
                if adicional_id not in adicionales_data:
                    adicionales_data[adicional_id] = {
                        'fecha': entry.fecha,
                        'cert_num': entry.numero_certificacion,
                        'id': adicional_id
                    }
        
        # Get full adicional details from licitacion repository or SQLite controller
        adicionales_list = []
        if self.controller:
            for adicional_id, data in adicionales_data.items():
                adicional_doc = None
                
                # Try SQLite controller first
                if hasattr(self.controller, 'licitacion_controller') and self.controller.licitacion_controller:
                    adicional_doc = self.controller.licitacion_controller.get_document(adicional_id)
                # Fallback to JSON repository
                elif hasattr(self.controller, 'licitacion_repo') and self.controller.licitacion_repo:
                    adicional_doc = self.controller.licitacion_repo.get_document(adicional_id)
                if adicional_doc:
                    # Get the earliest timestamp (when it was uploaded to the system)
                    fecha_subida = "-"
                    if adicional_doc.entries:
                        earliest_entry = min(adicional_doc.entries, key=lambda x: x.timestamp)
                        # Format timestamp to date only
                        try:
                            fecha_subida = earliest_entry.timestamp.split('T')[0]
                        except:
                            fecha_subida = earliest_entry.timestamp
                    
                    # Get importe from valor first, fallback to importe_adicional
                    importe = 0.0
                    if hasattr(adicional_doc, 'valor') and adicional_doc.valor:
                        importe = adicional_doc.valor
                    elif hasattr(adicional_doc, 'importe_adicional') and adicional_doc.importe_adicional:
                        importe = adicional_doc.importe_adicional
                    
                    adicionales_list.append({
                        'id': adicional_id,
                        'name': adicional_doc.name,
                        'company': adicional_doc.company,
                        'importe': importe,
                        'fecha_subida': fecha_subida,
                        'fecha': data['fecha'],
                        'cert_num': data['cert_num']
                    })
        
        # Summary section
        summary_frame = ttk.LabelFrame(adicionales_window, text="Resumen", padding="10")
        summary_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        total_importe = sum(ad['importe'] for ad in adicionales_list)
        
        summary_grid = ttk.Frame(summary_frame)
        summary_grid.pack(fill="x")
        
        ttk.Label(
            summary_grid,
            text="Total Adicionales:",
            font=("Arial", 10, "bold")
        ).grid(row=0, column=0, padx=10, sticky="w")
        
        ttk.Label(
            summary_grid,
            text=f"{total_importe:,.2f} €",
            font=("Arial", 14, "bold"),
            foreground="#2E7D32"
        ).grid(row=0, column=1, padx=10, sticky="w")
        
        ttk.Label(
            summary_grid,
            text="Cantidad:",
            font=("Arial", 10, "bold")
        ).grid(row=0, column=2, padx=10, sticky="w")
        
        ttk.Label(
            summary_grid,
            text=f"{len(adicionales_list)}",
            font=("Arial", 14, "bold"),
            foreground="#1565C0"
        ).grid(row=0, column=3, padx=10, sticky="w")
        
        # Adicionales table
        table_frame = ttk.LabelFrame(adicionales_window, text="Detalle de Adicionales", padding="10")
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        if not adicionales_list:
            # Show message if no adicionales
            ttk.Label(
                table_frame,
                text="No hay adicionales asociados a esta certificación.",
                font=("Arial", 11),
                foreground="#666666"
            ).pack(pady=20)
        else:
            # Create treeview with scrollbars
            tree_container = ttk.Frame(table_frame)
            tree_container.pack(fill="both", expand=True)
            
            vsb = ttk.Scrollbar(tree_container, orient="vertical")
            hsb = ttk.Scrollbar(tree_container, orient="horizontal")
            
            columns = ("Nombre", "Empresa", "Importe", "Fecha Subida", "Cert. Nº")
            
            adicionales_tree = ttk.Treeview(
                tree_container,
                columns=columns,
                show="headings",
                yscrollcommand=vsb.set,
                xscrollcommand=hsb.set,
                height=15
            )
            
            vsb.config(command=adicionales_tree.yview)
            hsb.config(command=adicionales_tree.xview)
            
            # Configure columns
            adicionales_tree.column("Nombre", width=350, anchor="w")
            adicionales_tree.column("Empresa", width=180, anchor="w")
            adicionales_tree.column("Importe", width=130, anchor="e")
            adicionales_tree.column("Fecha Subida", width=130, anchor="center")
            adicionales_tree.column("Cert. Nº", width=100, anchor="center")
            
            # Configure headings
            for col in columns:
                adicionales_tree.heading(col, text=col)
            
            # Pack components
            adicionales_tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            
            tree_container.grid_rowconfigure(0, weight=1)
            tree_container.grid_columnconfigure(0, weight=1)
            
            # Populate table - sort by certification date
            sorted_adicionales = sorted(adicionales_list, key=lambda x: (x['cert_num'], x['fecha_subida']))
            
            for adicional in sorted_adicionales:
                adicionales_tree.insert(
                    "",
                    "end",
                    values=(
                        adicional['name'],
                        adicional['company'],
                        f"{adicional['importe']:,.2f} €",
                        adicional['fecha_subida'],
                        adicional['cert_num']
                    )
                )
        
        # Close button
        ttk.Button(
            adicionales_window,
            text="Cerrar",
            command=adicionales_window.destroy,
            width=15
        ).pack(pady=10)

    def _show_state_change_dialog(self, callbacks: dict) -> None:
        """Show state change dialog for selected certificacion using UpdateStateForm"""
        if not self.selected_certificacion:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona una certificación de la tabla.")
            return
        
        # Prepare pre-selected document data
        pre_selected_document = {
            'id': self.selected_certificacion.nombre,
            'name': self.selected_certificacion.nombre,
            'state': self.selected_certificacion.current_state,
            'version': getattr(self.selected_certificacion, 'latest_version', 'N/A')
        }
        
        # Call the update state callback with pre-selected document
        if 'update_state' in callbacks:
            callbacks['update_state'](pre_selected_document)
    

    def _show_edit_info_with_selection(self, callbacks: dict) -> None:
        """Show edit info dialog for selected certificacion using CorrectionForm"""
        if not self.selected_certificacion:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona una certificación de la tabla.")
            return
        
        # Call the edit document info callback with selected document name
        if 'edit_document_info' in callbacks:
            callbacks['edit_document_info'](self.selected_certificacion.nombre)

    def _export_to_excel(self) -> None:
        """Export certificaciones to Excel"""
        if not self.controller:
            messagebox.showerror("Error", "Controlador no disponible")
            return
        
        # Ask for save location
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialfile=f"certificaciones_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )
        
        if file_path:
            try:
                exported_path = self.controller.export_to_excel(file_path)
                messagebox.showinfo(
                    "Exportación Exitosa",
                    f"Certificaciones exportadas a:\n{exported_path}"
                )
            except Exception as e:
                messagebox.showerror("Error", f"Error al exportar: {str(e)}")

    def _show_monthly_certification_form(self) -> None:
        """Show the monthly certification form for selected certificacion"""
        if not self.selected_certificacion:
            messagebox.showwarning("Selección", "Selecciona una certificación primero.")
            return
        
        try:
            from views.monthly_certificacion_form import MonthlyCertificacionForm
            
            # Prepare callbacks for the monthly form
            monthly_callbacks = {
                'back': lambda: self.show(self.controller, self.callbacks),
                'get_available_adicionales': self.controller.get_available_adicionales,
                'create_monthly_certificacion': self.controller.create_monthly_certificacion_with_files
            }
            
            # Show the monthly form
            monthly_form = MonthlyCertificacionForm(self.root)
            monthly_form.show(self.selected_certificacion, monthly_callbacks)
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al mostrar formulario mensual: {str(e)}")

