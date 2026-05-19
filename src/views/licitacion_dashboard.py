import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List, Dict, Optional
from .responsive_base_view import ResponsiveBaseView
from models.licitacion_document import (
    LicitacionDocument, LOTES_ESTANDAR, STAGE_DISPLAY_NAMES,
    PRESUPUESTO_TYPES, TYPE_DISPLAY_NAMES, PRESUPUESTO_STATUSES, STATUS_DISPLAY_NAMES
)
from utils.smart_refresh_manager import SmartRefreshManager
from views.components.refresh_indicator import RefreshIndicator
from pathlib import Path


class LicitacionDashboard(ResponsiveBaseView):
    """Dashboard for viewing licitacion documents and lot status"""
    
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.documents = []
        self.filtered_documents = []
        self.selected_document: Optional[LicitacionDocument] = None
        
        # Smart refresh components
        self.refresh_manager: Optional[SmartRefreshManager] = None
        self.refresh_indicator: Optional[RefreshIndicator] = None
        self.callbacks: dict = {}
        self.last_document_hash: Optional[str] = None
        
    def show(self, documents: List[LicitacionDocument], callbacks: dict, user_name: str = "") -> None:
        """Show the presupuesto dashboard with responsive design"""
        self.clear_window()
        
        # Use responsive window sizing instead of fixed 950x550
        self.center_window_responsive(
            preferred_width=1100, 
            preferred_height=700,
            min_width=900,
            min_height=600
        )
        
        self.documents = documents
        self.filtered_documents = documents.copy()
        self.callbacks = callbacks  # Store callbacks for use in other methods
        
        # Window controls toolbar removed - no maximize buttons needed
        
        # Header
        self.create_header(self.root, "Gestión de Presupuestos")
        
        # Create main container structure
        # Content container - expandable
        main_content = ttk.Frame(self.root, padding="6")
        main_content.pack(fill="both", expand=True)
        
        # Use responsive bottom button frame
        bottom_frame = self.create_bottom_button_frame(self.root)
        
        # Centered Presupuestos title - more prominent
        title_frame = ttk.Frame(main_content)
        title_frame.pack(fill="x", pady=(0, 15))
        
        title_label = ttk.Label(
            title_frame,
            text="PRESUPUESTOS",
            font=("Arial", 28, "bold"),
            foreground="#2E5984"  # Professional blue color
        )
        title_label.pack()
        
        # Subtitle with dynamic project info
        project_name = self._get_project_name_from_controller()
        subtitle_label = ttk.Label(
            title_frame,
            text=f"Presupuestos - {project_name}",
            font=("Arial", 14),
            foreground="#666666"
        )
        subtitle_label.pack(pady=(5, 0))
        
        # Create dashboard sections
        self._create_filters_and_legend(main_content)
        self._create_lot_status_overview(main_content)
        self._create_document_list(main_content, callbacks)
        # Place action buttons in the bottom container for always-visible buttons
        self._create_action_buttons(bottom_frame, callbacks)
        
        # Set up notification widget if available
        if user_name and 'get_notification_data' in callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: callbacks.get('get_notification_data')(user_name),
                mark_read_callback=callbacks.get('mark_notification_as_read'),
                navigate_callback=callbacks.get('navigate_to_document'),
                current_user=user_name,
                delete_callback=callbacks.get('delete_notification')
            )
        
        # Add refresh indicator
        refresh_frame = ttk.Frame(main_content)
        refresh_frame.pack(fill="x", pady=(0, 5))
        self.refresh_indicator = RefreshIndicator(refresh_frame)
        self.refresh_indicator.set_manual_refresh_callback(self._manual_refresh)
        
        # Store callbacks for smart refresh
        self.callbacks = callbacks
        
        # Initial data load
        self._refresh_lot_status()
        self._refresh_document_list()
        
        # Initialize smart refresh
        self._setup_smart_refresh(callbacks)
    
    def _get_project_name_from_controller(self) -> str:
        """Extract project name from the current working directory or project context"""
        try:
            # Try to get from current working directory name
            from pathlib import Path
            current_path = Path.cwd()
            project_name = current_path.name
            
            # If current dir name looks like a project name, use it
            if project_name and project_name != ".":
                return project_name
            
            # Fallback: try to extract from any available project info
            # Check if we have documents and extract from their paths
            if hasattr(self, 'documents') and self.documents:
                for doc in self.documents[:1]:  # Check first document
                    if hasattr(doc, 'file_paths') and doc.file_paths:
                        # Extract project name from file path
                        doc_path = Path(doc.file_paths[0]) if doc.file_paths[0] else None
                        if doc_path and len(doc_path.parts) > 1:
                            # Look for project-like folder names (containing PRJ or uppercase)
                            for part in reversed(doc_path.parts):
                                if 'PRJ' in part or part.isupper() or '_' in part:
                                    return part
            
            return "Proyecto Actual"
        except Exception:
            return "Proyecto Actual"

    def _create_filters_and_legend(self, parent: tk.Widget) -> None:
        """Create filter controls and state legend"""
        # Top frame for filters and legend (using grid layout)
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill="x", pady=(0, 8))
        top_frame.columnconfigure(0, weight=1)  # Filter frame expands
        top_frame.columnconfigure(1, weight=0)  # Legend frame stays fixed
        
        # Filter frame (left side)
        filter_frame = ttk.LabelFrame(top_frame, text="Filtros", padding="8")
        filter_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        # Filter by lote
        ttk.Label(filter_frame, text="Lote:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.filter_lote_var = tk.StringVar(value="Todos")
        lote_values = ["Todos"] + LOTES_ESTANDAR
        self.filter_lote_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_lote_var,
            values=lote_values,
            width=35,  # Slightly smaller to fit legend
            state="readonly"
        )
        self.filter_lote_combo.grid(row=0, column=1, padx=(0, 15))
        self.filter_lote_combo.bind('<<ComboboxSelected>>', self._apply_filters)
        
        # Filter by status (new etapa filter)
        ttk.Label(filter_frame, text="Estado:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.filter_status_var = tk.StringVar(value="Todos")
        status_values = ["Todos"] + list(STATUS_DISPLAY_NAMES.values())
        self.filter_status_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_status_var,
            values=status_values,
            width=20,
            state="readonly"
        )
        self.filter_status_combo.grid(row=0, column=3, padx=(0, 15))
        self.filter_status_combo.bind('<<ComboboxSelected>>', self._apply_filters)
        
        # Filter by tipo (new filter)
        ttk.Label(filter_frame, text="Tipo:").grid(row=0, column=4, sticky="w", padx=(0, 10))
        self.filter_tipo_var = tk.StringVar(value="Todos")
        tipo_values = ["Todos"] + list(TYPE_DISPLAY_NAMES.values())
        self.filter_tipo_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_tipo_var,
            values=tipo_values,
            width=15,
            state="readonly"
        )
        self.filter_tipo_combo.grid(row=0, column=5, padx=(0, 15))
        self.filter_tipo_combo.bind('<<ComboboxSelected>>', self._apply_filters)
        
        # Filter by company (second row)
        ttk.Label(filter_frame, text="Empresa:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.filter_company_var = tk.StringVar()
        self.filter_company_entry = ttk.Entry(filter_frame, textvariable=self.filter_company_var, width=20)
        self.filter_company_entry.grid(row=1, column=1, padx=(0, 15), pady=(5, 0))
        self.filter_company_entry.bind('<KeyRelease>', self._apply_filters)
        
        # Clear filters button
        ttk.Button(
            filter_frame,
            text="Limpiar Filtros",
            command=self._clear_filters
        ).grid(row=1, column=2, columnspan=2, padx=(0, 15), pady=(5, 0))
        
        # Legend frame (right side)
        legend_container = ttk.Frame(top_frame)
        legend_container.grid(row=0, column=1, sticky="ne")
        
        # Legend toggle button
        self.legend_visible = False
        self.legend_button = ttk.Button(
            legend_container, 
            text="▼ Leyenda de Estados", 
            command=self._toggle_legend
        )
        self.legend_button.pack(anchor="e")
        
        # Legend frame (initially hidden)
        self.legend_frame = ttk.Frame(legend_container)
        # Don't pack initially - will be shown when toggled
        
        # Create legend content (but don't show initially)
        self._create_legend_content()

    def _create_lot_status_overview(self, parent: tk.Widget) -> None:
        """Create lot status overview section"""
        status_frame = ttk.LabelFrame(parent, text="Resumen de Lotes", padding="8")
        status_frame.pack(fill="x", pady=(0, 8))
        
        # Create scrollable frame for lot status
        canvas = tk.Canvas(status_frame, height=100)
        scrollbar = ttk.Scrollbar(status_frame, orient="horizontal", command=canvas.xview)
        self.status_scrollable_frame = ttk.Frame(canvas)
        
        self.status_scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.status_scrollable_frame, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set)
        
        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="bottom", fill="x")

    def _create_document_list(self, parent: tk.Widget, callbacks: dict) -> None:
        """Create document list table"""
        list_frame = ttk.LabelFrame(parent, text="Documentos", padding="8")
        list_frame.pack(fill="both", expand=True, pady=(0, 8))
        
        # Create treeview with scrollbars
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill="both", expand=True)
        
        # Columns (updated with Type, Status, and added Rev. Técnico/Rev. Gerencia columns)
        columns = ("Nombre", "Lote", "Empresa", "Tipo", "Estado", "Versión", "Autor", "Rev. Técnico", "Rev. Gerencia", "Notas")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)
        
        # Configure columns
        self.tree.heading("Nombre", text="Nombre")
        self.tree.heading("Lote", text="Lote")
        self.tree.heading("Empresa", text="Empresa")
        self.tree.heading("Tipo", text="Tipo")
        self.tree.heading("Estado", text="Estado")
        self.tree.heading("Versión", text="Versión")
        self.tree.heading("Autor", text="Autor")
        self.tree.heading("Rev. Técnico", text="Rev. Técnico")
        self.tree.heading("Rev. Gerencia", text="Rev. Gerencia")
        self.tree.heading("Notas", text="Notas")
        
        # Configure column widths
        self.tree.column("Nombre", width=250, minwidth=200)
        self.tree.column("Lote", width=180, minwidth=150)
        self.tree.column("Empresa", width=120, minwidth=100)
        self.tree.column("Tipo", width=120, minwidth=100)
        self.tree.column("Estado", width=100, minwidth=80)
        self.tree.column("Versión", width=80, minwidth=60)
        self.tree.column("Autor", width=140, minwidth=100)
        self.tree.column("Rev. Técnico", width=120, minwidth=100)
        self.tree.column("Rev. Gerencia", width=120, minwidth=100)
        self.tree.column("Notas", width=260, minwidth=180)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack tree and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Bind double-click event
        self.tree.bind("<Double-1>", lambda e: self._on_document_double_click(callbacks))
        
        # Bind selection event to update push button state
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_document_select())
        
        # Configure color tags for different stages
        self._configure_state_colors()

    def _configure_state_colors(self) -> None:
        """Configure color tags for different presupuesto statuses"""
        # Configure Treeview style to ensure custom colors show through selection
        style = ttk.Style()
        
        # Color coding based on status - standardized across all dashboards
        self.tree.tag_configure("S0", foreground="#FFFFFF", background="#333333")  # Pure White with dark background - Borrador (maximum visibility)
        self.tree.tag_configure("S1", foreground="#FFFF00", background="#2B2B2B")  # Yellow - Revisado por Delineación with dark background
        self.tree.tag_configure("S2", foreground="#00AAE4", background="#1A1A1A")  # Blue - Revisado por Técnico Especialista with dark background
        self.tree.tag_configure("S3", foreground="#B19CD9", background="#1A1A1A")  # Purple - Revisado por Director Proyecto with dark background
        self.tree.tag_configure("S3A", foreground="#008F39", background="#1A1A1A") # Green - Aprobado por propiedad/promotor with dark background
        self.tree.tag_configure("D", foreground="#FF0000", background="#1A1A1A")   # Red - Denegado with dark background
        self.tree.tag_configure("default", foreground="black")  # Default/Unknown
        
        # Configure Treeview to reduce selection highlighting interference
        try:
            # Completely disable selection highlighting so our custom colors always show
            style.configure("Treeview", selectbackground="", selectforeground="")
            # Also configure focus highlighting
            style.configure("Treeview", focuscolor="none")
            # Map state-specific styling to override selection
            style.map("Treeview", 
                     selectbackground=[("", "")],
                     selectforeground=[("", "")])
        except Exception:
            # Fallback if style configuration fails
            pass
        
        # Type-based color coding (for type column)
        self.tree.tag_configure("type_licitacion", foreground="#4169E1")    # Royal Blue
        self.tree.tag_configure("type_presupuesto", foreground="#32CD32")   # Lime Green  
        self.tree.tag_configure("type_adicionales", foreground="#FF4500")   # Orange Red

    def _create_action_buttons(self, parent: tk.Widget, callbacks: dict) -> None:
        """Create action buttons"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x")
        
        # Left side buttons (document actions)
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side="left")
        
        ttk.Button(
            left_buttons,
            text="Nuevo Documento",
            command=callbacks.get('new_document', lambda: None)
        ).pack(side="left", padx=(0, 10))
        
        self.btn_new_version = ttk.Button(
            left_buttons,
            text="Nueva Versión",
            command=lambda: self._show_new_version_with_selection(callbacks),
            state="disabled"
        )
        self.btn_new_version.pack(side="left", padx=(0, 10))
        
        self.btn_update_stage = ttk.Button(
            left_buttons,
            text="Cambiar Etapa",
            command=lambda: self._show_update_stage_with_selection(callbacks),
            state="disabled"
        )
        self.btn_update_stage.pack(side="left", padx=(0, 10))
        
        ttk.Button(
            left_buttons,
            text="Resumen por Lote",
            command=self._show_lot_summary
        ).pack(side="left", padx=(0, 10))
        
        # Ver Historial button
        self.btn_view_history = ttk.Button(
            left_buttons,
            text="Ver Historial",
            command=self._show_history,
            state="disabled"
        )
        self.btn_view_history.pack(side="left", padx=(0, 10))
        
        # Editar información button
        self.btn_edit_info = ttk.Button(
            left_buttons,
            text="Editar información",
            command=lambda: self._show_edit_info_with_selection(callbacks),
            state="disabled"
        )
        self.btn_edit_info.pack(side="left", padx=(0, 10))
        
        # Right side buttons (navigation)
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side="right")
        
        ttk.Button(
            right_buttons,
            text="Volver",
            command=callbacks.get('back', lambda: None)
        ).pack(side="right")
        
        # Ensure all buttons are visible and accessible
        self.ensure_buttons_visible(button_frame)

    def _apply_filters(self, event=None) -> None:
        """Apply filters to document list"""
        lote_filter = self.filter_lote_var.get()
        status_filter = self.filter_status_var.get()
        tipo_filter = self.filter_tipo_var.get()
        company_filter = self.filter_company_var.get().lower()
        
        self.filtered_documents = []
        
        for doc in self.documents:
            # Apply lote filter
            if lote_filter != "Todos" and doc.lote != lote_filter:
                continue
                
            # Apply status filter
            if status_filter != "Todos" and doc.get_status_display_name() != status_filter:
                continue
                
            # Apply tipo filter
            if tipo_filter != "Todos" and doc.get_type_display_name() != tipo_filter:
                continue
                
            # Apply company filter
            if company_filter and company_filter not in doc.company.lower():
                continue
                
            self.filtered_documents.append(doc)
        
        self._refresh_document_list()

    def _clear_filters(self) -> None:
        """Clear all filters"""
        self.filter_lote_var.set("Todos")
        self.filter_status_var.set("Todos")
        self.filter_tipo_var.set("Todos")
        self.filter_company_var.set("")
        self.filtered_documents = self.documents.copy()
        self._refresh_document_list()

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
        legend_content = ttk.LabelFrame(self.legend_frame, text="Estados de Licitación", padding=10)
        legend_content.pack(fill="both", expand=True)
        
        # Licitacion state colors - standardized across all dashboards
        self.licitacion_state_colors = {
            "S0": "#FFFFFF",  # White - Borrador
            "S1": "#FFFF00",  # Yellow - Revisado por Delineación
            "S2": "#00AAE4",  # Blue - Revisado por Técnico Especialista
            "S3": "#B19CD9",  # Purple - Revisado por Director Proyecto
            "S3A": "#008F39"  # Green - Aprobado por propiedad/promotor
        }
        
        # Estado display names for licitaciones (standardized)
        licitacion_status_names = {
            "S0": "Borrador",
            "S1": "Revisado por Delineación",
            "S2": "Revisado por Técnico Especialista", 
            "S3": "Revisado por Director Proyecto",
            "S3A": "Aprobado por propiedad/promotor"
        }
        
        for i, (status, color) in enumerate(self.licitacion_state_colors.items()):
            color_label = tk.Label(legend_content, text="  ", bg=color, relief="solid", borderwidth=1)
            color_label.grid(row=i, column=0, pady=2, sticky="w")
            text_label = ttk.Label(legend_content, text=f" {licitacion_status_names.get(status, status)}")
            text_label.grid(row=i, column=1, pady=2, sticky="w")
        
        # Info button
        info_button = ttk.Button(legend_content, text="?", command=self._show_status_info, width=2)
        info_button.grid(row=0, column=2, rowspan=len(self.licitacion_state_colors), sticky="ns", padx=(5,0))

    def _show_status_info(self) -> None:
        """Show status information popup for licitaciones"""
        info_win = tk.Toplevel(self.root)
        info_win.title("Información de Estados - Licitaciones")
        info_win.geometry("750x300")
        info_win.transient(self.root)
        info_win.grab_set()
        
        # Main frame
        main_frame = ttk.Frame(info_win, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="Estados de Documentos de Licitación", 
            font=("Arial", 14, "bold")
        )
        title_label.pack(pady=(0, 15))
        
        # Create text widget with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill="both", expand=True)
        
        text_widget = tk.Text(text_frame, wrap="word", font=("Arial", 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Information content
        info_text = """ESTADOS DE DOCUMENTOS DE LICITACIÓN

S0 - Borrador
    Trabajo en proceso. NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO

S1 - Revisado por Delineación  
    NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO

S2 - Revisado por Técnico Especialista
    Revisado por técnico especialista.

S3 - Revisado por Director Proyecto
    SE PUEDE ENVIAR A PROPIEDAD EN ESTE ESTADO

S3A - Aprobado por propiedad/promotor
    Aprobado por propiedad/promotor.

NOTAS:
• Los estados S0 y S1 NUNCA SE ENVIAN A PROPIEDAD
• Solo desde S3 en adelante se puede enviar documentación a propiedad
• Los colores en la interfaz corresponden a estos estados para facilitar la identificación visual
• Los documentos siguen el flujo: S0 → S1 → S2 → S3 → S3A
• Los filtros permiten visualizar documentos en estados específicos"""
        
        text_widget.insert("1.0", info_text)
        text_widget.config(state="disabled")
        
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Close button
        close_button = ttk.Button(main_frame, text="Cerrar", command=info_win.destroy)
        close_button.pack(pady=(15, 0))

    def _refresh_lot_status(self) -> None:
        """Refresh the lot status overview"""
        # Clear existing widgets
        for widget in self.status_scrollable_frame.winfo_children():
            widget.destroy()
        
        # Calculate counts per lote by document type (licitacion, presupuesto, adicional)
        lote_status = {}
        for lote in LOTES_ESTANDAR:
            lote_status[lote] = {
                'licitacion': 0,
                'presupuesto': 0,
                'adicional': 0
            }
        
        for doc in self.documents:
            lote_key = getattr(doc, 'lote', None)
            if lote_key not in lote_status:
                continue
            # Support both JSON and SQLite-backed objects/summaries
            doc_type = (
                getattr(doc, 'licitacion_document_type', None) or
                getattr(doc, 'document_type', None)
            )
            if doc_type in lote_status[lote_key]:
                lote_status[lote_key][doc_type] += 1
        
        # Create status widgets
        col = 0
        for lote in LOTES_ESTANDAR:
            # Only show lotes that have documents
            total_docs = sum(lote_status[lote].values())
            if total_docs == 0:
                continue
                
            # Truncate lote name more intelligently
            lote_display = lote[:25] + "..." if len(lote) > 25 else lote
            lote_frame = ttk.LabelFrame(self.status_scrollable_frame, text=lote_display, padding="6")
            lote_frame.grid(row=0, column=col, padx=4, sticky="ew")
            
            # Show only 3 key metrics: Licitaciones, Presupuestos, Adicionales (by type)
            licitaciones_count = lote_status[lote].get('licitacion', 0)
            presupuestos_count = lote_status[lote].get('presupuesto', 0)
            adicionales_count = lote_status[lote].get('adicional', 0)
            
            # Display simplified metrics - all white text, no color coding
            simplified_metrics = [
                ("Licitaciones", licitaciones_count),
                ("Presupuestos", presupuestos_count),
                ("Adicionales", adicionales_count)
            ]
            
            for i, (label, count) in enumerate(simplified_metrics):
                status_label = ttk.Label(
                    lote_frame,
                    text=f"{label}: {count}",
                    font=("Arial", 9),
                    foreground="white"
                )
                status_label.grid(row=i, column=0, sticky="w", pady=1, padx=2)
            
            col += 1

    def _refresh_document_list(self) -> None:
        """Refresh the document list table"""
        # Clear all items at once (much faster)
        self.tree.delete(*self.tree.get_children())
        
        # Sort documents by type: licitacion -> presupuesto -> adicionales
        type_order = {"licitacion": 1, "presupuesto": 2, "adicionales": 3}
        sorted_documents = sorted(
            self.filtered_documents,
            key=lambda doc: type_order.get(doc.document_type, 999)
        )
        
        # Add filtered documents with color coding
        for doc in sorted_documents:
            # Determine color tag based on current status
            status_tag = doc.current_status if hasattr(doc, 'current_status') and doc.current_status in [
                "S0", "S1", "S2", "S3", "P", "A", "B"
            ] else "default"
            
            # Get type and status display names
            type_display = doc.get_type_display_name() if hasattr(doc, 'get_type_display_name') else doc.document_type if hasattr(doc, 'document_type') else "N/A"
            status_display = doc.get_status_display_name() if hasattr(doc, 'get_status_display_name') else doc.current_status if hasattr(doc, 'current_status') else "N/A"
            
            # Safely get document autor (original uploader) with error handling
            try:
                autor_display = getattr(doc, 'autor', '') or ''
                if not isinstance(autor_display, str):
                    autor_display = str(autor_display) if autor_display else ''
            except Exception as e:
                print(f"Warning: Failed to get autor for document {doc.name}: {e}")
                autor_display = ''
            
            # Safely get notes from latest entry
            try:
                current_entry = getattr(doc, 'current_entry', None)
                notes_text = getattr(current_entry, 'notes', '') if current_entry else ''
                notes_display = notes_text[:120] + "..." if len(notes_text) > 120 else notes_text
            except Exception as e:
                print(f"Warning: Failed to get notes for document {doc.name}: {e}")
                notes_display = ''

            # Safely get rev_tecnica and rev_gerencia from document
            try:
                rev_tecnica_display = getattr(doc, 'rev_tecnica', '') or ''
                rev_gerencia_display = getattr(doc, 'rev_gerencia', '') or ''
                if not isinstance(rev_tecnica_display, str):
                    rev_tecnica_display = str(rev_tecnica_display) if rev_tecnica_display else ''
                if not isinstance(rev_gerencia_display, str):
                    rev_gerencia_display = str(rev_gerencia_display) if rev_gerencia_display else ''
            except Exception as e:
                print(f"Warning: Failed to get reviewer info for document {doc.name}: {e}")
                rev_tecnica_display = ''
                rev_gerencia_display = ''
            
            # Use full document name as the Treeview item id (iid) to avoid relying on
            # potentially truncated display values when handling double-click actions.
            self.tree.insert("", "end", iid=doc.name, values=(
                doc.name[:30] + "..." if len(doc.name) > 30 else doc.name,
                doc.lote[:25] + "..." if len(doc.lote) > 25 else doc.lote,
                doc.company,
                type_display,
                status_display,
                doc.current_version,
                autor_display,
                rev_tecnica_display,
                rev_gerencia_display,
                notes_display
            ), tags=(status_tag,))

    def _on_document_double_click(self, callbacks: dict) -> None:
        """Handle double-click on document"""
        selection = self.tree.selection()
        if not selection:
            return
        
        # Use the Treeview item's iid as the document identifier to ensure we
        # pass the full, untruncated name to the controller.
        doc_id = selection[0]
        
        # Open document location
        if 'open_document_location' in callbacks:
            try:
                callbacks['open_document_location'](doc_id)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo abrir la ubicación del documento: {e}")

    def _show_lot_summary(self) -> None:
        """Show detailed lot summary window"""
        # Create summary window
        summary_window = tk.Toplevel(self.root)
        summary_window.title("Resumen por Lote")
        summary_window.geometry("800x600")
        
        # Summary text
        text_frame = ttk.Frame(summary_window, padding="10")
        text_frame.pack(fill="both", expand=True)
        
        text_widget = tk.Text(text_frame, wrap="word", font=("Courier", 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Generate summary
        summary_text = "RESUMEN DE DOCUMENTOS POR LOTE\n"
        summary_text += "=" * 50 + "\n\n"
        
        for lote in LOTES_ESTANDAR:
            lote_docs = [doc for doc in self.documents if doc.lote == lote]
            if not lote_docs:
                continue
                
            summary_text += f"[L] {lote}\n"
            summary_text += "-" * 60 + "\n"
            
            # Count documents by type
            licitacion_count = len([doc for doc in lote_docs if doc.document_type == "licitacion"])
            presupuesto_count = len([doc for doc in lote_docs if doc.document_type == "presupuesto"])
            adicionales_count = len([doc for doc in lote_docs if doc.document_type == "adicionales"])
            
            summary_text += f"  • Licitaciones: {licitacion_count}\n"
            summary_text += f"  • Presupuestos: {presupuesto_count}\n"
            summary_text += f"  • Adicionales: {adicionales_count}\n\n"
        
        text_widget.insert("1.0", summary_text)
        text_widget.config(state="disabled")
        
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Close button
        ttk.Button(
            summary_window,
            text="Cerrar",
            command=summary_window.destroy
        ).pack(pady=10)

    def get_selected_document_id(self) -> str:
        """Get the name of the currently selected document (kept method name for compatibility)"""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            # First column is now name, but we need to extract the full name (removing "..." if truncated)
            name_display = item['values'][0]
            # Find the full name from the filtered documents
            for doc in self.filtered_documents:
                if doc.name.startswith(name_display.replace("...", "")):
                    return doc.name
            return name_display  # Fallback to display name
        return ""
    
    def get_selected_document_name(self) -> str:
        """Get the name of the currently selected document."""
        return self.get_selected_document_id()  # Alias for clarity
    
    def _setup_smart_refresh(self, callbacks: dict) -> None:
        """Initialize smart refresh system for presupuestos dashboard."""
        try:
            # Get the manifest path for presupuestos
            if 'get_project_path' in callbacks:
                project_path = Path(callbacks['get_project_path']())
                from utils.path_helper import PathHelper
                pm_path = PathHelper.get_project_manager_path(project_path)
                manifest_path = pm_path / "presupuestos" / "manifest.json"
                
                # Create refresh manager
                self.refresh_manager = SmartRefreshManager(
                    json_path=str(manifest_path),
                    refresh_callback=self._smart_refresh_data,
                    refresh_interval=3000  # 3 seconds
                )
                
                # Start the refresh cycle
                self.refresh_manager.start_refresh_cycle(self.root)
                
                # Calculate initial document hash
                self.last_document_hash = self._calculate_document_hash()
                
                print(f"SmartRefresh: Initialized for presupuestos dashboard")
                
        except Exception as e:
            print(f"ERROR: Failed to setup smart refresh for presupuestos: {e}")
    
    def _calculate_document_hash(self) -> str:
        """Calculate a hash of current presupuesto document data for change detection."""
        import hashlib
        
        # Create a string representation of all document data
        doc_data = []
        for doc in sorted(self.documents, key=lambda x: x.id):
            doc_info = f"{doc.id}|{doc.name}|{doc.lote}|{doc.company}|{doc.current_stage}|{doc.current_version}"
            # Include latest modification time if available
            if hasattr(doc, 'last_modified'):
                doc_info += f"|{doc.last_modified}"
            doc_data.append(doc_info)
        
        # Create hash
        data_string = "||".join(doc_data)
        return hashlib.md5(data_string.encode()).hexdigest()
    
    def _smart_refresh_data(self) -> bool:
        """Smart refresh callback - only updates if data actually changed."""
        try:
            if self.refresh_indicator:
                self.refresh_indicator.show_checking()
            
            # Get fresh presupuesto document data
            if 'refresh_licitaciones' in self.callbacks:
                fresh_documents = self.callbacks['refresh_licitaciones']()
                
                # Calculate hash of fresh data
                old_documents = self.documents
                self.documents = fresh_documents  # Temporarily assign for hash calculation
                fresh_hash = self._calculate_document_hash()
                
                # Check if anything actually changed
                if fresh_hash == self.last_document_hash:
                    # No changes
                    self.documents = old_documents  # Restore original
                    if self.refresh_indicator:
                        self.refresh_indicator.show_success(0)  # 0 changes
                    return False
                
                # Data changed! Update UI intelligently
                self.last_document_hash = fresh_hash
                self.filtered_documents = fresh_documents.copy()
                
                # Update both the document list and lot status
                changes_count = self._update_dashboard_intelligently(old_documents, fresh_documents)
                
                # Show success with change count
                if self.refresh_indicator:
                    self.refresh_indicator.show_success(changes_count)
                
                return True
                
        except Exception as e:
            print(f"SmartRefresh: Error during presupuestos refresh: {e}")
            if self.refresh_indicator:
                self.refresh_indicator.show_error("Error de actualización")
            return False
    
    def _update_dashboard_intelligently(self, old_documents: List[LicitacionDocument], new_documents: List[LicitacionDocument]) -> int:
        """Update dashboard intelligently, preserving user state."""
        changes_count = 0
        
        try:
            # Remember user state for document list
            selected_items = self.tree.selection()
            selected_doc_ids = []
            for item in selected_items:
                try:
                    doc_id = self.tree.item(item)['values'][0]
                    selected_doc_ids.append(doc_id)
                except (IndexError, tk.TclError):
                    pass
            
            # Remember scroll position
            scroll_position = 0
            try:
                if self.tree.yview():
                    scroll_position = self.tree.yview()[0]
            except:
                pass
            
            # Remember filter states
            current_lote_filter = self.filter_lote_var.get()
            current_status_filter = self.filter_status_var.get()
            current_tipo_filter = self.filter_tipo_var.get()
            current_company_filter = self.filter_company_var.get()
            
            # Update lot status overview
            lot_changes = self._update_lot_status_intelligently(old_documents, new_documents)
            changes_count += lot_changes
            
            # Update document list
            doc_list_changes = self._update_document_list_intelligently(old_documents, new_documents)
            changes_count += doc_list_changes
            
            # Restore user state
            if selected_doc_ids:
                new_selected_items = []
                for item in self.tree.get_children():
                    try:
                        doc_id = self.tree.item(item)['values'][0]
                        if doc_id in selected_doc_ids:
                            new_selected_items.append(item)
                    except (IndexError, tk.TclError):
                        continue
                
                if new_selected_items:
                    self.tree.selection_set(new_selected_items)
            
            # Restore scroll position
            try:
                self.tree.yview_moveto(scroll_position)
            except:
                pass
                
            # Restore filters
            self.filter_lote_var.set(current_lote_filter)
            self.filter_status_var.set(current_status_filter)
            self.filter_tipo_var.set(current_tipo_filter)
            self.filter_company_var.set(current_company_filter)
            
            # Re-apply filters
            self.root.after(200, self._apply_filters)
            
        except Exception as e:
            print(f"SmartRefresh: Error in intelligent presupuestos update: {e}")
            # Fallback to full refresh
            self._refresh_lot_status()
            self._refresh_document_list()
            changes_count = len(new_documents)
        
        return changes_count
    
    def _update_lot_status_intelligently(self, old_documents: List[LicitacionDocument], new_documents: List[LicitacionDocument]) -> int:
        """Update lot status overview with change detection."""
        changes_detected = 0
        
        try:
            # Calculate old and new lot statistics
            old_stats = self._calculate_lot_statistics(old_documents)
            new_stats = self._calculate_lot_statistics(new_documents)
            
            # Check if lot statistics changed
            if old_stats != new_stats:
                # Refresh lot status display
                self._refresh_lot_status()
                changes_detected = 1
                
                # Highlight changed lot status frames briefly
                self.root.after(100, self._highlight_lot_status_changes)
            
        except Exception as e:
            print(f"Error updating lot status: {e}")
        
        return changes_detected
    
    def _calculate_lot_statistics(self, documents: List[LicitacionDocument]) -> dict:
        """Calculate statistics for lot status comparison."""
        stats = {}
        for lote in LOTES_ESTANDAR:
            stats[lote] = {stage: 0 for stage in STAGE_DISPLAY_NAMES.keys()}
        
        for doc in documents:
            if doc.lote in stats:
                stats[doc.lote][doc.current_stage] += 1
        
        return stats
    
    def _highlight_lot_status_changes(self) -> None:
        """Briefly highlight lot status frames that changed."""
        try:
            # This is a visual effect - we could implement specific highlighting
            # For now, just refresh the lot status which is already efficient
            pass
        except Exception as e:
            print(f"Error highlighting lot status changes: {e}")
    
    def _update_document_list_intelligently(self, old_documents: List[LicitacionDocument], new_documents: List[LicitacionDocument]) -> int:
        """Update document list with minimal UI disruption."""
        changes_count = 0
        
        try:
            # Create lookup maps
            old_docs_map = {doc.id: doc for doc in old_documents}
            new_docs_map = {doc.id: doc for doc in new_documents}
            
            # Get current tree items
            tree_items = {}
            for item in self.tree.get_children():
                try:
                    doc_id = self.tree.item(item)['values'][0]
                    tree_items[doc_id] = item
                except (IndexError, tk.TclError):
                    continue
            
            # Update existing items, add new ones
            for doc in new_documents:
                if doc.id in tree_items:
                    # Document exists in tree - check if it needs updating
                    item = tree_items[doc.id]
                    
                    # Compare with old version
                    old_doc = old_docs_map.get(doc.id)
                    if old_doc and self._licitacion_documents_are_different(old_doc, doc):
                        # Document changed - update the tree item
                        new_values = self._get_tree_values_for_licitacion(doc)
                        self.tree.item(item, values=new_values)
                        changes_count += 1
                        
                        # Brief highlight effect
                        self.root.after(100, lambda i=item: self._highlight_changed_row(i))
                        
                elif doc.id not in old_docs_map:
                    # New document - add to tree
                    new_values = self._get_tree_values_for_licitacion(doc)
                    new_item = self.tree.insert('', 'end', values=new_values)
                    changes_count += 1
                    
                    # Highlight new row
                    self.root.after(100, lambda i=new_item: self._highlight_changed_row(i))
            
            # Remove deleted documents
            for doc_id, item in tree_items.items():
                if doc_id not in new_docs_map:
                    self.tree.delete(item)
                    changes_count += 1
            
        except Exception as e:
            print(f"Error updating document list: {e}")
            # Fallback
            self._refresh_document_list()
            changes_count = len(new_documents)
        
        return changes_count
    
    def _licitacion_documents_are_different(self, doc1: LicitacionDocument, doc2: LicitacionDocument) -> bool:
        """Check if two presupuesto documents have different data."""
        return (doc1.name != doc2.name or 
                doc1.lote != doc2.lote or
                doc1.company != doc2.company or
                doc1.current_stage != doc2.current_stage or
                doc1.current_version != doc2.current_version)
    
    def _get_tree_values_for_licitacion(self, doc: LicitacionDocument) -> tuple:
        """Get tree values tuple for a licitacion document including Autor, Rev. Técnico, Rev. Gerencia and Notas."""
        # Get type and status display names
        type_display = doc.get_type_display_name() if hasattr(doc, 'get_type_display_name') else getattr(doc, 'document_type', 'N/A')
        status_display = doc.get_status_display_name() if hasattr(doc, 'get_status_display_name') else getattr(doc, 'current_status', 'N/A')
        # Safely get document autor (original uploader) with error handling
        try:
            autor_display = getattr(doc, 'autor', '') or ''
            if not isinstance(autor_display, str):
                autor_display = str(autor_display) if autor_display else ''
        except Exception as e:
            print(f"Warning: Failed to get autor for document {doc.name}: {e}")
            autor_display = ''
        
        # Safely get notes from latest entry
        try:
            current_entry = getattr(doc, 'current_entry', None)
            notes_text = getattr(current_entry, 'notes', '') if current_entry else ''
            notes_display = notes_text[:120] + "..." if len(notes_text) > 120 else notes_text
        except Exception as e:
            print(f"Warning: Failed to get notes for document {doc.name}: {e}")
            notes_display = ''
        
        # Safely get rev_tecnica and rev_gerencia from document
        try:
            rev_tecnica_display = getattr(doc, 'rev_tecnica', '') or ''
            rev_gerencia_display = getattr(doc, 'rev_gerencia', '') or ''
            if not isinstance(rev_tecnica_display, str):
                rev_tecnica_display = str(rev_tecnica_display) if rev_tecnica_display else ''
            if not isinstance(rev_gerencia_display, str):
                rev_gerencia_display = str(rev_gerencia_display) if rev_gerencia_display else ''
        except Exception as e:
            print(f"Warning: Failed to get reviewer info for document {doc.name}: {e}")
            rev_tecnica_display = ''
            rev_gerencia_display = ''
        
        return (
            doc.name[:30] + "..." if len(doc.name) > 30 else doc.name,
            doc.lote[:25] + "..." if len(doc.lote) > 25 else doc.lote,
            doc.company,
            type_display,
            status_display,
            doc.current_version,
            autor_display,
            rev_tecnica_display,
            rev_gerencia_display,
            notes_display
        )
    
    def _highlight_changed_row(self, item) -> None:
        """Briefly highlight a changed row in the document tree."""
        try:
            # Configure highlight tag
            self.tree.tag_configure('changed', background='#ffffcc')
            
            # Apply highlight
            self.tree.item(item, tags=('changed',))
            
            # Remove highlight after 1 second
            self.root.after(1000, lambda: self._remove_highlight(item))
        except tk.TclError:
            pass  # Item might have been deleted
    
    def _remove_highlight(self, item) -> None:
        """Remove highlight from a tree item."""
        try:
            self.tree.item(item, tags=())
        except tk.TclError:
            pass  # Item might have been deleted
    
    def _manual_refresh(self) -> None:
        """Handle manual refresh request for licitaciones."""
        try:
            if self.refresh_manager:
                self.refresh_manager.force_refresh()
            else:
                # Fallback - refresh manually
                if 'refresh_licitaciones' in self.callbacks:
                    fresh_documents = self.callbacks['refresh_licitaciones']()
                    self.documents = fresh_documents
                    self.filtered_documents = fresh_documents.copy()
                    self._refresh_lot_status()
                    self._refresh_document_list()
                    if self.refresh_indicator:
                        self.refresh_indicator.show_success(len(fresh_documents))
        except Exception as e:
            print(f"Manual refresh error in licitaciones: {e}")
            if self.refresh_indicator:
                self.refresh_indicator.show_error("Error en actualización manual")
    
    def _on_document_select(self) -> None:
        """Handle document selection to update button states"""
        try:
            selected_doc = self._get_selected_document()
            self.selected_document = selected_doc
            
            # Enable/disable buttons based on selection
            if hasattr(self, 'btn_view_history'):
                if selected_doc:
                    self.btn_view_history.config(state="normal")
                else:
                    self.btn_view_history.config(state="disabled")
            
            if hasattr(self, 'btn_new_version'):
                if selected_doc:
                    self.btn_new_version.config(state="normal")
                else:
                    self.btn_new_version.config(state="disabled")
            
            if hasattr(self, 'btn_update_stage'):
                if selected_doc:
                    self.btn_update_stage.config(state="normal")
                else:
                    self.btn_update_stage.config(state="disabled")
            
            if hasattr(self, 'btn_edit_info'):
                if selected_doc:
                    self.btn_edit_info.config(state="normal")
                else:
                    self.btn_edit_info.config(state="disabled")
        except Exception as e:
            print(f"Error in document selection: {e}")
    
    def _get_selected_document(self) -> Optional[LicitacionDocument]:
        """Get the currently selected document"""
        selection = self.tree.selection()
        if not selection:
            return None
        
        try:
            item = self.tree.item(selection[0])
            name_display = item['values'][0]
            
            # Find the full document by name
            for doc in self.filtered_documents:
                if doc.name.startswith(name_display.replace("...", "")):
                    return doc
        except (IndexError, KeyError):
            pass
        
        return None
    
    def _push_to_certificacion(self, callbacks: dict) -> None:
        """Push approved adicional to certificaciones"""
        try:
            selected_doc = self._get_selected_document()
            if not selected_doc:
                messagebox.showwarning("Selección requerida", "Por favor, seleccione un documento")
                return
            
            if not (hasattr(selected_doc, 'can_push_to_certificacion') and selected_doc.can_push_to_certificacion()):
                messagebox.showwarning(
                    "No se puede transferir", 
                    "Solo se pueden transferir adicionales aprobados (estado A) que no hayan sido transferidos previamente"
                )
                return
            
            # Confirm the push action
            result = messagebox.askyesno(
                "Confirmar transferencia",
                f"¿Transferir el adicional '{selected_doc.name}' a Certificaciones?\\n\\n"
                f"Lote: {selected_doc.lote}\\n"
                f"Empresa: {selected_doc.company}\\n"
                f"Importe: {selected_doc.importe_adicional:,.2f} € (si está definido)\\n\\n"
                f"Esta acción creará una nueva entrada en el módulo de certificaciones."
            )
            
            if result:
                # Call the push callback
                if 'push_adicional_to_certificacion' in callbacks:
                    message = callbacks['push_adicional_to_certificacion'](selected_doc.name)
                    messagebox.showinfo("Éxito", message)
                    
                    # Refresh the dashboard to show updated status
                    if 'refresh_licitaciones' in callbacks:
                        fresh_documents = callbacks['refresh_licitaciones']()
                        if fresh_documents:
                            self.documents = fresh_documents
                            self.filtered_documents = fresh_documents.copy()
                            self._refresh_document_list()
                            self._on_document_select()  # Update button state
                else:
                    messagebox.showerror("Error", "Funcionalidad de transferencia no disponible")
                    
        except Exception as e:
            messagebox.showerror("Error", f"Error al transferir a certificaciones: {str(e)}")
    
    def _show_new_version_with_selection(self, callbacks: dict) -> None:
        """Show new version dialog for selected licitacion using NewVersionForm"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona una licitación de la tabla.")
            return
        
        # Prepare pre-selected document data
        pre_selected_document = {
            'id': self.selected_document.name,
            'name': self.selected_document.name,
            'state': getattr(self.selected_document, 'current_status', 'S0'),
            'version': self.selected_document.current_version
        }
        
        # Call the new version callback with pre-selected document
        if 'new_version' in callbacks:
            callbacks['new_version'](pre_selected_document)
    
    def _show_update_stage_with_selection(self, callbacks: dict) -> None:
        """Show update stage dialog for selected licitacion using UpdateStateForm"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona una licitación de la tabla.")
            return
        
        # Prepare pre-selected document data
        pre_selected_document = {
            'id': self.selected_document.name,
            'name': self.selected_document.name,
            'state': getattr(self.selected_document, 'current_status', 'S0'),
            'version': self.selected_document.current_version
        }
        
        # Call the update stage callback with pre-selected document
        if 'update_stage' in callbacks:
            callbacks['update_stage'](pre_selected_document)
    
    def _show_edit_info_with_selection(self, callbacks: dict) -> None:
        """Show edit info dialog for selected licitacion using CorrectionForm"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona una licitación de la tabla.")
            return
        
        # Call the edit document info callback with selected document name
        if 'edit_document_info' in callbacks:
            callbacks['edit_document_info'](self.selected_document.name)
    
    def _show_history(self) -> None:
        """Show history for selected licitacion/presupuesto document"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un documento de la tabla.")
            return
        
        # CRITICAL: Load the full SQLiteLicitacionDocument instead of using the summary
        # The self.selected_document is a LicitacionSummary which doesn't have entries
        full_document = None
        if 'get_document' in self.callbacks:
            full_document = self.callbacks['get_document'](self.selected_document.name)
            print(f"DEBUG: Loaded full document type: {type(full_document)}")
            if full_document and hasattr(full_document, 'entries'):
                print(f"DEBUG: Full document has {len(full_document.entries)} entries")
        
        if not full_document:
            messagebox.showerror("Error", "No se pudo cargar el documento completo para mostrar el historial.")
            return
        
        # Use full_document instead of self.selected_document for the history
        document_for_history = full_document
        
        # Create history window
        history_window = tk.Toplevel(self.root)
        history_window.title(f"Historial - {document_for_history.name}")
        history_window.geometry("900x500")
        history_window.transient(self.root)
        history_window.grab_set()
        
        # Header
        header_frame = ttk.Frame(history_window, padding="10")
        header_frame.pack(fill="x")
        
        ttk.Label(
            header_frame,
            text=f"Documento: {document_for_history.name}",
            font=("Arial", 12, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text=f"Lote: {document_for_history.lote}",
            font=("Arial", 10)
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text=f"Empresa: {document_for_history.company}",
            font=("Arial", 10)
        ).pack(anchor="w")
        
        
        # History table
        tree_frame = ttk.Frame(history_window, padding="10")
        tree_frame.pack(fill="both", expand=True)
        
        columns = (
            "Versión", "Fecha", "Etapa", "Estado", "Tipo", "Notas"
        )
        
        history_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=15
        )
        
        # Configure columns
        history_tree.heading("Versión", text="Versión")
        history_tree.heading("Fecha", text="Fecha")
        history_tree.heading("Etapa", text="Etapa")
        history_tree.heading("Estado", text="Estado")
        history_tree.heading("Tipo", text="Tipo")
        history_tree.heading("Notas", text="Notas")
        
        # Configure column widths
        history_tree.column("Versión", width=80)
        history_tree.column("Fecha", width=100)
        history_tree.column("Etapa", width=120)
        history_tree.column("Estado", width=100)
        history_tree.column("Tipo", width=100)
        history_tree.column("Notas", width=250)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=history_tree.yview)
        history_tree.configure(yscrollcommand=scrollbar.set)
        
        # Add entries (from document entries/history) - USE FULL DOCUMENT
        entries_added = 0
        try:
            if hasattr(document_for_history, 'entries') and document_for_history.entries:
                # Sort entries by timestamp (newest first)
                sorted_entries = sorted(document_for_history.entries, key=lambda x: getattr(x, 'timestamp', ''), reverse=True)
                
                # Debug info
                print(f"DEBUG: Found {len(sorted_entries)} entries for licitacion document '{document_for_history.name}'")
                
                for entry in sorted_entries:
                    try:
                        # Format timestamp to readable date
                        timestamp_display = getattr(entry, 'timestamp', 'N/A')
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(timestamp_display.replace('Z', '+00:00'))
                            timestamp_display = dt.strftime("%d/%m/%Y %H:%M")
                        except Exception as e:
                            print(f"DEBUG: Timestamp parsing error for {timestamp_display}: {e}")
                            # If parsing fails, try to show at least the date part
                            if len(timestamp_display) >= 10:
                                timestamp_display = timestamp_display[:10]
                        
                        notes_text = getattr(entry, 'notes', 'N/A')
                        notes_display = notes_text[:150] + "..." if len(notes_text) > 150 else notes_text
                        
                        print(f"DEBUG: Inserting entry - Version: {getattr(entry, 'version', 'N/A')}, Status: {getattr(entry, 'status', 'N/A')}")
                        
                        history_tree.insert(
                            "",
                            "end",
                            values=(
                                getattr(entry, 'version', 'N/A'),
                                timestamp_display,
                                getattr(entry, 'stage', 'N/A'),
                                getattr(entry, 'status', 'N/A'),
                                getattr(entry, 'document_type', 'N/A'),
                                notes_display
                            )
                        )
                        entries_added += 1
                        print(f"DEBUG: Successfully inserted entry {entries_added}")
                        
                    except Exception as e:
                        print(f"DEBUG: Error inserting entry: {e}")
                        import traceback
                        traceback.print_exc()
                    
            # If still no entries found, check for document-level history or version info
            if entries_added == 0:
                print(f"DEBUG: No entries found for licitacion, checking document attributes...")
                print(f"DEBUG: Document type: {type(self.selected_document)}")
                print(f"DEBUG: Document dir: {dir(self.selected_document)}")
                
                # Try to get history from different possible sources
                history_entries = []
                
                # Check if document has versions attribute (some document types might store history differently)
                if hasattr(self.selected_document, 'versions') and self.selected_document.versions:
                    print(f"DEBUG: Found versions attribute with {len(self.selected_document.versions)} items")
                    for version_data in self.selected_document.versions:
                        history_entries.append({
                            'version': getattr(version_data, 'version', 'N/A'),
                            'timestamp': getattr(version_data, 'timestamp', 'N/A'),
                            'stage': getattr(version_data, 'stage', 'N/A'),
                            'status': getattr(version_data, 'status', 'N/A'),
                            'document_type': getattr(version_data, 'document_type', 'N/A'),
                            'notes': getattr(version_data, 'notes', '')
                        })
                
                # Check if document has history attribute
                elif hasattr(self.selected_document, 'history') and self.selected_document.history:
                    print(f"DEBUG: Found history attribute with {len(self.selected_document.history)} items")
                    for hist_entry in self.selected_document.history:
                        history_entries.append({
                            'version': getattr(hist_entry, 'version', 'N/A'),
                            'timestamp': getattr(hist_entry, 'timestamp', 'N/A'),
                            'stage': getattr(hist_entry, 'stage', 'N/A'),
                            'status': getattr(hist_entry, 'status', 'N/A'),
                            'document_type': getattr(hist_entry, 'document_type', 'N/A'),
                            'notes': getattr(hist_entry, 'notes', '')
                        })
                
                # If we found alternative history sources, display them
                if history_entries:
                    # Sort by timestamp (newest first)
                    try:
                        history_entries.sort(key=lambda x: x['timestamp'], reverse=True)
                    except:
                        pass  # Keep original order if sorting fails
                    
                    for entry in history_entries:
                        # Format timestamp
                        timestamp_display = entry['timestamp']
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(timestamp_display.replace('Z', '+00:00'))
                            timestamp_display = dt.strftime("%d/%m/%Y %H:%M")
                        except:
                            if len(timestamp_display) >= 10:
                                timestamp_display = timestamp_display[:10]
                        
                        notes_display = entry['notes'][:150] + "..." if len(entry['notes']) > 150 else entry['notes']
                        
                        history_tree.insert(
                            "",
                            "end",
                            values=(
                                entry['version'],
                                timestamp_display,
                                entry['stage'],
                                entry['status'],
                                entry['document_type'],
                                notes_display
                            )
                        )
                        entries_added += 1
                
                # Last resort: show current state only if no history found anywhere
                if entries_added == 0:
                    print(f"DEBUG: No history found anywhere for licitacion, showing current state only")
                    
                    # Add warning message in header
                    warning_frame = ttk.Frame(header_frame)
                    warning_frame.pack(fill="x", pady=(5, 0))
                    ttk.Label(
                        warning_frame,
                        text="⚠️ Este documento no tiene historial de cambios registrado. Mostrando estado actual únicamente.",
                        font=("Arial", 9),
                        foreground="#FF8C00"
                    ).pack(anchor="w")
                    
        except Exception as e:
            print(f"Error loading licitacion history entries: {e}")
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
        
        # If no entries were added, show current state as fallback
        if entries_added == 0:
            creation_date = getattr(self.selected_document, 'creation_date', 'N/A')
            
            # Get display names safely
            stage_display = 'N/A'
            try:
                if hasattr(self.selected_document, 'get_stage_display_name'):
                    stage_display = self.selected_document.get_stage_display_name()
                else:
                    stage_display = getattr(self.selected_document, 'current_stage', 'N/A')
            except:
                pass
            
            status_display = 'N/A'
            try:
                if hasattr(self.selected_document, 'get_status_display_name'):
                    status_display = self.selected_document.get_status_display_name()
                else:
                    status_display = getattr(self.selected_document, 'current_status', 'N/A')
            except:
                pass
            
            type_display = 'N/A'
            try:
                if hasattr(self.selected_document, 'get_type_display_name'):
                    type_display = self.selected_document.get_type_display_name()
                else:
                    type_display = getattr(self.selected_document, 'document_type', 'N/A')
            except:
                pass
            
            notes_text = getattr(self.selected_document, 'notes', 'Sin historial disponible')
            notes_display = notes_text[:150] + "..." if len(notes_text) > 150 else notes_text
            
            history_tree.insert(
                "",
                "end",
                values=(
                    self.selected_document.current_version,
                    creation_date,
                    stage_display,
                    status_display,
                    type_display,
                    notes_display
                )
            )
        
        # Pack tree and scrollbar
        history_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Close button
        button_frame = ttk.Frame(history_window, padding="10")
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Cerrar",
            command=history_window.destroy
        ).pack(anchor="center")
    
    def __del__(self):
        """Cleanup when presupuesto dashboard is destroyed."""
        if self.refresh_manager:
            self.refresh_manager.stop_refresh_cycle()