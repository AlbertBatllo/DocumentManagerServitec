import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from typing import Callable, List, Dict, Optional, Tuple
from .responsive_base_view import ResponsiveBaseView
from models.plano_document import PlanoDocument, PLANO_STATES, STATE_DISPLAY_NAMES
from utils.smart_refresh_manager import SmartRefreshManager
from views.components.refresh_indicator import RefreshIndicator
from views.file_management_panel import FileManagementPanel
from pathlib import Path


class PlanosDashboard(ResponsiveBaseView):
    """Dashboard for viewing plano documents and status"""
    
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.documents = []
        self.filtered_documents = []
        self.selected_document: Optional[PlanoDocument] = None
        self.selected_documents: List[PlanoDocument] = []
        
        # File type filtering variables
        self.file_type_filters = {
            '.pdf': tk.BooleanVar(value=True),
            '.dwg': tk.BooleanVar(value=True),
            '.rvt': tk.BooleanVar(value=True)
        }
        
        # Smart refresh components
        self.refresh_manager: Optional[SmartRefreshManager] = None
        self.refresh_indicator: Optional[RefreshIndicator] = None
        self.callbacks: dict = {}
        self.last_document_hash: Optional[str] = None
        
    def show(self, documents: List[PlanoDocument], callbacks: dict, user_name: str = "", scroll_to_document: str = None) -> None:
        """Show the planos dashboard with responsive design

        Args:
            documents: List of plano documents to display
            callbacks: Dictionary of callback functions
            user_name: Current user name for notifications
            scroll_to_document: Optional document name to scroll to and select after loading
        """
        self.clear_window()
        self._scroll_to_document = scroll_to_document  # Store for use after rendering
        
        # Use responsive window sizing instead of fixed 950x550
        self.center_window_responsive(
            preferred_width=1100, 
            preferred_height=700,
            min_width=900,
            min_height=600
        )
        
        self.documents = documents
        self.filtered_documents = []  # Will be populated by _apply_filters
        self.callbacks = callbacks  # Store callbacks for XREF status checking
        self.user_name = user_name  # Stored for use during operations like bulk upload
        
        # Window controls toolbar removed - no maximize buttons needed

        # Header
        self.create_header(self.root, "Gestión de Planos")

        # Reserve bottom button frame BEFORE main content so it always gets space.
        # show_help=False: el texto "💡 Usa las barras..." se elimina (Fase 4);
        # ensure_buttons_visible() ya garantiza la responsividad sin recordatorio.
        bottom_actions_frame = self.create_bottom_button_frame(self.root, show_help=False)

        # Status bar (also at bottom, above buttons)
        self.status_label = ttk.Label(
            self.root,
            text=f"Total: {len(documents)} documentos",
            relief="sunken",
            padding=(6, 2)
        )
        self.status_label.pack(side="bottom", fill="x")

        # Main container (takes remaining space)
        main_frame = ttk.Frame(self.root, padding="6")
        main_frame.pack(fill="both", expand=True)

        # Layout Fase 4: barra superior (Filtratge + PLANOS + Editar/Leyenda),
        # panel de filtros colapsable, indicador de refresh, tabla central.
        self._create_top_bar(main_frame)
        self._create_filter_panel(main_frame)

        # Add refresh indicator (justo por encima de la tabla)
        refresh_frame = ttk.Frame(main_frame)
        refresh_frame.pack(fill="x", pady=(0, 2))
        self.refresh_indicator = RefreshIndicator(refresh_frame)
        self.refresh_indicator.set_manual_refresh_callback(self._manual_refresh)

        # Tabla central (debe ser el ultimo pack para que expand=True se la
        # quede todo el espacio vertical restante).
        self._create_document_list(main_frame, callbacks)

        # Place action buttons in the bottom-fixed container so they are always visible
        self._create_action_buttons(bottom_actions_frame, callbacks)

        # Set up notification widget if available
        if user_name and 'get_notification_data' in callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: callbacks.get('get_notification_data')(user_name),
                mark_read_callback=callbacks.get('mark_notification_as_read'),
                navigate_callback=callbacks.get('navigate_to_document'),
                current_user=user_name,
                delete_callback=callbacks.get('delete_notification')
            )
        
        # Store callbacks for smart refresh
        self.callbacks = callbacks
        
        # Initial data load with filters applied
        self._apply_filters()  # This will populate filtered_documents and refresh the list

        # Scroll to document if specified (after a short delay to ensure rendering is complete)
        if self._scroll_to_document:
            self.root.after(100, lambda: self._scroll_to_and_select_document(self._scroll_to_document))

        # Initialize smart refresh
        self._setup_smart_refresh(callbacks)

    # ==================================================================
    # Top bar / filter panel / legend modal (Fase 4)
    # ==================================================================

    # Colores de la leyenda. Centralizar aqui hasta que la Fase 5 los
    # importe desde domain/estados.py.
    plano_state_colors = {
        "S0": "#FFFFFF",  # Pure White - Borrador
        "S1": "#FFFF00",  # Yellow - Revisado por Delineación
        "S2": "#00AAE4",  # Blue - Revisado por Técnico Especialista
        "S3": "#B19CD9",  # Purple - Revisado por Director Proyecto
        "S3A": "#008F39", # Green - Aprobado por propiedad/promotor
        "D": "#FF0000",   # Red - Denegado
    }

    def _create_top_bar(self, parent: tk.Widget) -> None:
        """
        Crea la barra superior con 3 zonas:
          - izquierda: boton [▼ Filtratge] (despliega el panel de filtros)
          - centro:    titulo "PLANOS" en grande
          - derecha:   [✎ Editar] + [▼ Leyenda de Estados] (modal)
        """
        top_bar = ttk.Frame(parent)
        top_bar.pack(fill="x", pady=(0, 4))
        top_bar.columnconfigure(0, weight=0)
        top_bar.columnconfigure(1, weight=1)
        top_bar.columnconfigure(2, weight=0)

        # Izquierda: filter toggle
        self.filter_panel_visible = False
        self.filter_toggle_button = ttk.Button(
            top_bar,
            text="▼ Filtratge",
            command=self._toggle_filter_panel,
        )
        self.filter_toggle_button.grid(row=0, column=0, sticky="w", padx=(0, 8))

        # Centro: titulo PLANOS
        ttk.Label(
            top_bar,
            text="PLANOS",
            font=("Arial", 24, "bold"),
            foreground="#2E5984",
        ).grid(row=0, column=1, sticky="ew")

        # Derecha: acciones (Editar + Leyenda)
        actions_frame = ttk.Frame(top_bar)
        actions_frame.grid(row=0, column=2, sticky="e")

        edit_callback = (self.callbacks or {}).get('edit_project')
        if edit_callback:
            self.edit_button = ttk.Button(
                actions_frame,
                text="✎ Editar",
                command=edit_callback,
            )
            self.edit_button.pack(side="left", padx=(0, 6))

        self.legend_button = ttk.Button(
            actions_frame,
            text="▼ Leyenda de Estados",
            command=self._show_legend_modal,
        )
        self.legend_button.pack(side="left")

    def _create_filter_panel(self, parent: tk.Widget) -> None:
        """
        Crea el panel de filtros (colapsado por defecto). El layout interno
        replica el que existia en la version anterior: 6 filas con todos
        los filtros actuales. Las StringVar/BooleanVar mantienen el mismo
        nombre para no romper _apply_filters ni _clear_filters.
        """
        # Recordamos el parent para poder hacer pack/pack_forget desde el
        # toggle sin pasarselo cada vez.
        self._filter_panel_parent = parent

        self.filter_panel = ttk.LabelFrame(parent, text="Filtros", padding=8)
        # No se hace pack inicial: el panel arranca oculto.

        filter_frame = ttk.Frame(self.filter_panel)
        filter_frame.pack(fill="x")

        # Buscar por nombre (row 0)
        ttk.Label(filter_frame, text="Buscar por nombre:").grid(row=0, column=0, padx=5, sticky="w")
        self.filter_id_var = tk.StringVar()
        self.filter_id_entry = ttk.Entry(filter_frame, textvariable=self.filter_id_var, width=20)
        self.filter_id_entry.grid(row=0, column=1, padx=5, sticky="w")
        self.filter_id_entry.bind('<KeyRelease>', lambda e: self._apply_filters())

        # Filtrar por Estado (row 1)
        ttk.Label(filter_frame, text="Filtrar por Estado:").grid(row=1, column=0, padx=5, sticky="w", pady=(5, 0))
        self.filter_state_var = tk.StringVar(value="Todos")
        state_values = ["Todos"] + list(STATE_DISPLAY_NAMES.values())
        self.filter_state_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_state_var,
            values=state_values,
            state="readonly",
            width=20
        )
        self.filter_state_combo.grid(row=1, column=1, padx=5, sticky="w", pady=(5, 0))
        self.filter_state_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_filters())

        # Filtrar por Fase (row 2)
        ttk.Label(filter_frame, text="Filtrar por Fase:").grid(row=2, column=0, padx=5, sticky="w", pady=(5, 0))
        self.filter_phase_var = tk.StringVar(value="Todas")
        phase_values = ["Todas", "Implantación", "Proyecto Básico", "Proyecto Ejecutivo", "Dirección Obra"]
        self.filter_phase_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_phase_var,
            values=phase_values,
            state="readonly",
            width=20
        )
        self.filter_phase_combo.grid(row=2, column=1, padx=5, sticky="w", pady=(5, 0))
        self.filter_phase_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_filters())

        # Filtrar por Usuario (row 3)
        ttk.Label(filter_frame, text="Filtrar por Usuario:").grid(row=3, column=0, padx=5, sticky="w", pady=(5, 0))
        self.filter_user_var = tk.StringVar()
        self.filter_user_entry = ttk.Entry(filter_frame, textvariable=self.filter_user_var, width=20)
        self.filter_user_entry.grid(row=3, column=1, padx=5, sticky="w", pady=(5, 0))
        self.filter_user_entry.bind('<KeyRelease>', lambda e: self._apply_filters())

        # Tipos de Archivo (row 4)
        ttk.Label(filter_frame, text="Tipos de Archivo:").grid(row=4, column=0, padx=5, sticky="w", pady=(5, 0))
        file_type_frame = ttk.Frame(filter_frame)
        file_type_frame.grid(row=4, column=1, padx=5, sticky="w", pady=(5, 0))
        for i, (ext, var) in enumerate(self.file_type_filters.items()):
            cb = ttk.Checkbutton(
                file_type_frame,
                text=ext.upper(),
                variable=var,
                command=self._apply_filters,
            )
            cb.grid(row=0, column=i, padx=(0, 8), sticky="w")

        # Limpiar Filtros (row 5)
        ttk.Button(
            filter_frame,
            text="Limpiar Filtros",
            command=self._clear_filters,
        ).grid(row=5, column=0, columnspan=2, padx=5, sticky="w", pady=(5, 0))

    def _toggle_filter_panel(self) -> None:
        """Despliega o colapsa el panel de filtros."""
        if self.filter_panel_visible:
            self.filter_panel.pack_forget()
            self.filter_toggle_button.config(text="▼ Filtratge")
            self.filter_panel_visible = False
        else:
            # winfo_children() devuelve TODOS los hijos (esten packed o no),
            # asi que self.filter_panel aparece en la lista aunque no este
            # mostrado. Hay que excluirlo para no hacer pack(before=self).
            children = [
                c for c in self._filter_panel_parent.winfo_children()
                if c is not self.filter_panel
            ]
            # Tras filtrar: children[0] = top_bar, children[1] = refresh_frame.
            # Queremos que el panel aparezca entre ambos.
            anchor = children[1] if len(children) > 1 else None
            if anchor is not None:
                self.filter_panel.pack(fill="x", pady=(0, 6), before=anchor)
            else:
                self.filter_panel.pack(fill="x", pady=(0, 6))
            self.filter_toggle_button.config(text="▲ Filtratge")
            self.filter_panel_visible = True

    def _show_legend_modal(self) -> None:
        """
        Abre la leyenda como modal (Toplevel). Decision Fase 4: 'modal
        porque no roba espacio permanente' (REFACTOR_PLAN seccion 7).
        La Fase 5 reutilizara este modal centralizando ESTADO_A_COLOR.
        """
        win = tk.Toplevel(self.root)
        win.title("Leyenda de Estados")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        container = ttk.Frame(win, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Leyenda de estados",
            font=("Arial", 12, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        # Tabla: muestra de color + nombre. Igual que el panel anterior.
        table = ttk.Frame(container)
        table.pack(fill="x")
        for i, (status, color) in enumerate(self.plano_state_colors.items()):
            color_sample = tk.Label(table, text="  ", bg=color, relief="solid", borderwidth=1, width=4)
            color_sample.grid(row=i, column=0, padx=(0, 8), pady=3, sticky="w")
            ttk.Label(
                table,
                text=STATE_DISPLAY_NAMES.get(status, status),
            ).grid(row=i, column=1, sticky="w", pady=3)

        # Info adicional + boton Cerrar.
        ttk.Button(
            container,
            text="Mas detalles…",
            command=self._show_status_info,
        ).pack(anchor="w", pady=(12, 0))

        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_frame, text="Cerrar", command=win.destroy).pack(side="right")

        # Centrar relativo al padre.
        win.update_idletasks()
        try:
            px = self.root.winfo_rootx()
            py = self.root.winfo_rooty()
            pw = self.root.winfo_width()
            ph = self.root.winfo_height()
            ww = win.winfo_width()
            wh = win.winfo_height()
            x = px + (pw - ww) // 2
            y = py + (ph - wh) // 2
            win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass

        win.protocol("WM_DELETE_WINDOW", win.destroy)

    def _show_status_info(self) -> None:
        """Show status information popup - exactly like original."""
        info_win = tk.Toplevel(self.root)
        info_win.title("Información de Estados")
        info_win.geometry("750x250")
        info_win.transient(self.root)
        info_win.grab_set()
        
        cols = ('code', 'meaning', 'usage')
        tree = ttk.Treeview(info_win, columns=cols, show='headings')
        
        tree.heading('code', text='Código')
        tree.heading('meaning', text='Significado')
        tree.heading('usage', text='Uso Común')
        tree.column('code', width=60, anchor='center')
        tree.column('meaning', width=150)
        tree.column('usage', width=500)
        
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


    def _create_document_list(self, parent: tk.Widget, callbacks: dict) -> None:
        """
        Tabla central con las 10 columnas exactas del REFACTOR_PLAN seccion 6.

        Cambios Fase 4:
          - Sin LabelFrame envolvente (la tabla ocupa todo el espacio).
          - Orden y nombres de columnas alineados con la nueva especificacion.
          - Columnas 'Codigo' y 'Tipo archivo' se leen del documento si el
            modelo las expone, si no quedan vacias (placeholder hasta que
            futuras fases las pueblen).
        """
        # Create treeview with scrollbars directly in parent (no LabelFrame).
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, pady=(0, 4))

        # Columnas en el orden exacto del REFACTOR_PLAN seccion 6.
        columns = (
            "Código", "Nombre", "Tipo archivo", "Estado", "Versión",
            "Fase requerida", "Fecha", "Autor",
            "Revisión Técnica", "Revisión Gerencia",
        )
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            height=12, selectmode="extended",
        )

        # Headings (texto visible = nombre de columna).
        for col in columns:
            self.tree.heading(col, text=col)

        # Anchuras razonables. stretch=False para que la suma horizontal
        # active el h_scrollbar y las columnas no se compriman.
        self.tree.column("Código",             width=100, minwidth=70,  stretch=False)
        self.tree.column("Nombre",             width=200, minwidth=140, stretch=False)
        self.tree.column("Tipo archivo",       width=90,  minwidth=70,  stretch=False)
        self.tree.column("Estado",             width=70,  minwidth=50,  stretch=False, anchor="center")
        self.tree.column("Versión",            width=70,  minwidth=50,  stretch=False, anchor="center")
        self.tree.column("Fase requerida",     width=130, minwidth=90,  stretch=False)
        self.tree.column("Fecha",              width=110, minwidth=80,  stretch=False, anchor="center")
        self.tree.column("Autor",              width=80,  minwidth=60,  stretch=False, anchor="center")
        self.tree.column("Revisión Técnica",   width=120, minwidth=90,  stretch=False, anchor="center")
        self.tree.column("Revisión Gerencia",  width=130, minwidth=100, stretch=False, anchor="center")
        
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

        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self._on_select_document)

        # Bind hover for notes tooltip
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._hide_tooltip)
        self._tooltip = None
        self._tooltip_id = None

        # Configure color tags for different states
        self._configure_state_colors()

        # Enable drag-and-drop on the treeview
        self.enable_drag_and_drop_for_treeview(
            self.tree,
            lambda fps, rid: self._on_files_dropped_on_dashboard(fps, rid, callbacks)
        )

    def _configure_state_colors(self) -> None:
        """Configure color tags for different plano states"""
        # Configure Treeview style to ensure custom colors show through selection
        style = ttk.Style()
        
        # Color coding using standardized colors
        self.tree.tag_configure("S0", foreground="#FFFFFF", background="#333333")  # Pure White with dark background - Borrador (maximum visibility)
        self.tree.tag_configure("S1", foreground="#FFFF00", background="#2B2B2B")  # Yellow - Revisado por Delineación with dark background
        self.tree.tag_configure("S2", foreground="#00AAE4", background="#1A1A1A")  # Blue - Revisado por Técnico Especialista with dark background
        self.tree.tag_configure("S3", foreground="#B19CD9", background="#1A1A1A")  # Purple - Revisado por Director Proyecto with dark background
        self.tree.tag_configure("S3A", foreground="#008F39", background="#1A1A1A") # Green - Aprobado por propiedad/promotor with dark background
        self.tree.tag_configure("D", foreground="#FF0000", background="#1A1A1A")   # Red - Denegado with dark background
        self.tree.tag_configure("default", foreground="#808080")  # Gray (no black)
        
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

    def _on_tree_motion(self, event) -> None:
        """Show tooltip with full notes when hovering over a row."""
        # Get the row under cursor
        item = self.tree.identify_row(event.y)
        if not item:
            self._hide_tooltip()
            return

        # Get the column under cursor
        column = self.tree.identify_column(event.x)

        # Only show tooltip for Notas column (#10)
        if column != "#10":
            self._hide_tooltip()
            return

        # Get the notes value
        values = self.tree.item(item, "values")
        if not values or len(values) < 10:
            self._hide_tooltip()
            return

        notes = values[9]  # Notas is the 10th column (index 9)
        if not notes or notes == "":
            self._hide_tooltip()
            return

        # Show tooltip after a short delay
        if self._tooltip_id:
            self.tree.after_cancel(self._tooltip_id)

        self._tooltip_id = self.tree.after(500, lambda: self._show_tooltip(event, notes))

    def _show_tooltip(self, event, text: str) -> None:
        """Display tooltip window with text."""
        self._hide_tooltip()

        if not text:
            return

        # Create tooltip window
        self._tooltip = tk.Toplevel(self.tree)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.wm_attributes("-topmost", True)

        # Position near cursor
        x = self.tree.winfo_rootx() + event.x + 20
        y = self.tree.winfo_rooty() + event.y + 10
        self._tooltip.wm_geometry(f"+{x}+{y}")

        # Create label with notes text
        label = tk.Label(
            self._tooltip,
            text=text,
            justify="left",
            background="#FFFFE0",
            foreground="#000000",
            relief="solid",
            borderwidth=1,
            wraplength=400,
            padx=8,
            pady=4
        )
        label.pack()

    def _hide_tooltip(self, event=None) -> None:
        """Hide the tooltip window."""
        if self._tooltip_id:
            self.tree.after_cancel(self._tooltip_id)
            self._tooltip_id = None

        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    def _create_action_buttons(self, parent: tk.Widget, callbacks: dict) -> None:
        """Create action buttons in two rows for better space management"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x")
        
        # First row - Document management actions
        first_row = ttk.Frame(button_frame)
        first_row.pack(fill="x", pady=(0, 5))

        first_row_left = ttk.Frame(first_row)
        first_row_left.pack(side="left")

        self.btn_new_version = self.create_visible_button(
            first_row_left,
            text="Registrar Nueva Versión",
            command=lambda: self._show_new_version_with_selection(callbacks),
            state="disabled"
        )
        self.btn_new_version.pack(side="left", padx=(0, 8))

        self.btn_edit_info = self.create_visible_button(
            first_row_left,
            text="Editar información",
            command=lambda: self._show_edit_info_with_selection(callbacks),
            state="disabled"
        )
        self.btn_edit_info.pack(side="left", padx=(0, 8))

        # Right side of first row - Navigation
        first_row_right = ttk.Frame(first_row)
        first_row_right.pack(side="right")

        self.create_visible_button(
            first_row_right,
            text="Volver",
            command=callbacks.get('back', lambda: None)
        ).pack(side="right")

        # Second row - File actions
        second_row = ttk.Frame(button_frame)
        second_row.pack(fill="x")

        second_row_left = ttk.Frame(second_row)
        second_row_left.pack(side="left")

        self.btn_manage_files = self.create_visible_button(
            second_row_left,
            text="Gestionar Archivos",
            command=lambda: self._show_file_management_with_selection(callbacks),
            state="disabled"
        )
        self.btn_manage_files.pack(side="left", padx=(0, 8))

        self.btn_view_history = self.create_visible_button(
            second_row_left,
            text="Ver Historial",
            command=lambda: self._show_history_with_selection(callbacks),
            state="disabled"
        )
        self.btn_view_history.pack(side="left", padx=(0, 8))

        self.create_visible_button(
            second_row_left,
            text="Subida Masiva",
            command=lambda: self._batch_upload(callbacks)
        ).pack(side="left", padx=(0, 8))

        self.create_visible_button(
            second_row_left,
            text="Eliminar Archivos",
            command=callbacks.get('delete_files', lambda: None)
        ).pack(side="left", padx=(0, 8))

        # Ensure all buttons are visible and accessible
        self.ensure_buttons_visible(button_frame)
    
    def _get_referencias_status(self, doc) -> str:
        """Get XREF references status for a plano document."""
        try:
            # Check if document has associated DWG or DWG files (only DWG files have XREF references)
            associated_dwg = getattr(doc, 'associated_dwg', '')
            has_dwg = bool(associated_dwg)

            if not has_dwg:
                # Check file_paths as fallback
                doc_files = getattr(doc, 'file_paths', [])
                if isinstance(doc_files, str):
                    try:
                        import json
                        doc_files = json.loads(doc_files) if doc_files else []
                    except (json.JSONDecodeError, TypeError):
                        doc_files = []

                for file_path in doc_files:
                    if file_path and file_path.lower().endswith('.dwg'):
                        has_dwg = True
                        break

            if not has_dwg:
                # Non-DWG files don't have XREF references, so they're always "complete"
                return "✓"

            # For DWG files, check XREF status via controller
            if hasattr(self, 'callbacks') and 'get_plano_xref_status' in self.callbacks:
                xref_status = self.callbacks['get_plano_xref_status'](doc.name)
                
                if 'error' in xref_status:
                    return "?"  # Unknown status
                
                processing_status = xref_status.get('processing_status', 'unknown')
                
                if processing_status == 'completed':
                    # Check if all references are resolved
                    references_count = xref_status.get('references_count', 0)
                    
                    if references_count == 0:
                        return "✓"  # No references needed, complete
                    else:
                        # Check missing references via controller
                        if 'get_missing_references' in self.callbacks:
                            missing_refs = self.callbacks['get_missing_references'](doc.name)
                            # missing_refs is a list of missing reference files for this plano
                            return "✗" if missing_refs else "✓"
                        else:
                            return "✓"  # Assume complete if can't check missing
                            
                elif processing_status in ['processing', 'queued']:
                    return "⏳"  # Processing in progress
                elif processing_status and processing_status.startswith('failed'):
                    return "❌"  # Processing failed
                else:
                    return "?"  # Unknown status
            else:
                # No controller callback available
                return "?"
                
        except Exception as e:
            print(f"Error getting XREF status for {doc.name}: {e}")
            return "?"

    def _apply_filters(self, event=None) -> None:
        """Apply filters to document list"""
        id_filter = self.filter_id_var.get().lower()
        state_filter = self.filter_state_var.get()
        phase_filter = self.filter_phase_var.get()
        user_filter = self.filter_user_var.get().lower()

        # Get file type filter states
        show_pdf = self.file_type_filters['.pdf'].get()
        show_dwg = self.file_type_filters['.dwg'].get()
        show_rvt = self.file_type_filters['.rvt'].get()

        # Reset filtered documents list
        self.filtered_documents = []

        for doc in self.documents:
            # Apply basic text filters first
            if id_filter and id_filter not in doc.id.lower():
                continue

            if state_filter != "Todos" and doc.get_state_display_name() != state_filter:
                continue

            doc_phase = getattr(doc, 'project_phase', 'Implantación')
            if phase_filter != "Todas" and doc_phase != phase_filter:
                continue

            if user_filter and not any(user_filter in field.lower() for field in [
                doc.autor, doc.rev_tecnica, doc.rev_gerencia
            ]):
                continue

            # File-type filter: based on the extension of the file actually
            # shown in the "Nombre" column. Unchecking PDF hides rows whose
            # displayed filename ends in .pdf, etc.
            if not (show_pdf or show_dwg or show_rvt):
                continue

            try:
                from pathlib import Path
                displayed = self._get_display_filename(doc)
                ext = Path(displayed).suffix.lower()
                if ext == '.pdf' and not show_pdf:
                    continue
                if ext == '.dwg' and not show_dwg:
                    continue
                if ext == '.rvt' and not show_rvt:
                    continue
                # Unknown / no extension: only show when no type is being narrowed.
                if ext not in ('.pdf', '.dwg', '.rvt') and not (show_pdf and show_dwg and show_rvt):
                    continue
            except Exception:
                pass

            self.filtered_documents.append(doc)

        self._refresh_document_list()
        self._update_status_label()

    def _clear_filters(self) -> None:
        """Clear all filters including file type filters"""
        self.filter_id_var.set("")
        self.filter_state_var.set("Todos")
        self.filter_phase_var.set("Todas")
        self.filter_user_var.set("")
        
        # Clear file type filters (set all to True)
        for var in self.file_type_filters.values():
            var.set(True)
            
        self._apply_filters()  # Reapply filters which will refresh the list and status

    def _update_status_label(self) -> None:
        """Update status label with current filter counts"""
        if hasattr(self, 'status_label'):
            filtered_count = len(self.filtered_documents)
            total_count = len(self.documents)
            
            if filtered_count == total_count:
                self.status_label.config(text=f"Total: {total_count} documentos")
            else:
                self.status_label.config(text=f"Mostrando: {filtered_count} de {total_count} documentos")

    def refresh_document_list(self) -> None:
        """
        Public method to refresh document list from database.
        Call this after adding/removing files to update the dashboard.
        """
        try:
            # Reload documents from database
            if 'refresh_planos' in self.callbacks:
                fresh_documents = self.callbacks['refresh_planos']()
                self.documents = fresh_documents
                # Re-apply filters to update filtered_documents with new file_paths
                self._apply_filters()
        except Exception as e:
            print(f"Error refreshing document list: {e}")
            # Fallback: just refresh display with current data
            self._refresh_document_list()

    def _refresh_document_list(self) -> None:
        """Refresh the document list table"""
        # Clear all items at once (much faster)
        self.tree.delete(*self.tree.get_children())

        # Add filtered documents with color coding. Delegamos la construccion
        # del tuple a _get_tree_values_for_plano para evitar duplicacion y
        # mantener un unico sitio donde mapear PlanoDocument -> columnas.
        for doc in self.filtered_documents:
            # Determine color tag based on current state
            state_tag = doc.current_state if doc.current_state in PLANO_STATES else "default"

            # Use the document name as the Treeview item id (iid) to ensure we
            # can properly identify the document when handling double-click actions.
            self.tree.insert(
                "", "end",
                iid=doc.name,
                values=self._get_tree_values_for_plano(doc),
                tags=(state_tag,),
            )

        # Update status bar
        if hasattr(self, 'status_label'):
            self.status_label.config(text=f"Mostrando: {len(self.filtered_documents)} de {len(self.documents)} documentos")

    def _scroll_to_and_select_document(self, doc_name: str) -> None:
        """Scroll to and select a specific document in the treeview.

        Args:
            doc_name: The document name (iid) to scroll to and select
        """
        try:
            # Check if the document exists in the tree
            if doc_name in self.tree.get_children():
                # Select the document
                self.tree.selection_set(doc_name)
                # Make sure it's visible by scrolling to it
                self.tree.see(doc_name)
                # Set focus to the tree
                self.tree.focus(doc_name)
        except tk.TclError:
            # Document not found or tree not ready
            pass

    def _on_document_double_click(self, callbacks: dict) -> None:
        """
        Handle double-click on document with smart file type selection.

        Simple logic based on filter state:
        - If only DWG is selected → open the .dwg file location
        - If only PDF is selected → open the .pdf file location
        - If multiple/all filters → default to PDF
        """
        selection = self.tree.selection()
        if not selection:
            return

        doc_id = selection[0]

        # Determine preferred extension based on active filters
        active_filters = [ext for ext, var in self.file_type_filters.items() if var.get()]

        if len(active_filters) == 1:
            # Only one filter active - use that extension
            preferred_extension = active_filters[0]
        else:
            # Multiple or all filters - default to PDF
            preferred_extension = '.pdf'

        # Use the simplified open_specific_file callback
        if 'open_specific_file' in callbacks:
            try:
                callbacks['open_specific_file'](doc_id, preferred_extension)
                return
            except Exception as e:
                print(f"Error opening specific file: {e}")

        # Fallback: open document location
        if 'open_document_location' in callbacks:
            try:
                callbacks['open_document_location'](doc_id)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo abrir la ubicación del documento: {e}")

    def _on_select_document(self, event=None) -> None:
        """Handle document selection (supports multi-selection)"""
        selection = self.tree.selection()
        if selection:
            # Tree items are inserted with iid=doc.name, so the iid IS the doc id.
            # Don't use values[0] — that's now the displayed filename, not the doc name.
            primary_id = selection[0]
            self.selected_document = next(
                (doc for doc in self.filtered_documents if doc.name == primary_id),
                None
            )

            # Build list of all selected documents (for batch operations)
            self.selected_documents = []
            for sel_item in selection:
                doc = next((d for d in self.filtered_documents if d.name == sel_item), None)
                if doc:
                    self.selected_documents.append(doc)

            # Enable/disable buttons
            if self.selected_document:
                for btn_name in ('btn_view_history', 'btn_new_version',
                                 'btn_edit_info', 'btn_manage_files'):
                    if hasattr(self, btn_name):
                        getattr(self, btn_name).config(state="normal")
            else:
                for btn_name in ('btn_view_history', 'btn_new_version',
                                 'btn_edit_info', 'btn_manage_files'):
                    if hasattr(self, btn_name):
                        getattr(self, btn_name).config(state="disabled")
        else:
            self.selected_document = None
            self.selected_documents = []
            for btn_name in ('btn_view_history', 'btn_new_version',
                             'btn_edit_info', 'btn_manage_files'):
                if hasattr(self, btn_name):
                    getattr(self, btn_name).config(state="disabled")

    def _show_history(self) -> None:
        """Show history for selected plano document"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un plano de la tabla.")
            return
        
        # Create history window
        history_window = tk.Toplevel(self.root)
        history_window.title(f"Historial - {self.selected_document.name}")
        history_window.geometry("900x500")
        history_window.transient(self.root)
        history_window.grab_set()
        
        # Header
        header_frame = ttk.Frame(history_window, padding="10")
        header_frame.pack(fill="x")
        
        ttk.Label(
            header_frame,
            text=f"Plano: {self.selected_document.name}",
            font=("Arial", 12, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text=f"Estado: {self.selected_document.current_state} | Versión: {self.selected_document.current_version}",
            font=("Arial", 10)
        ).pack(anchor="w")
        
        # History table
        tree_frame = ttk.Frame(history_window, padding="10")
        tree_frame.pack(fill="both", expand=True)
        
        columns = (
            "Versión", "Fecha", "Estado", "Autor", "Rev. Téc.", "Rev. Ger.", "Notas"
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
        history_tree.heading("Estado", text="Estado")
        history_tree.heading("Autor", text="Autor")
        history_tree.heading("Rev. Téc.", text="Rev. Téc.")
        history_tree.heading("Rev. Ger.", text="Rev. Ger.")
        history_tree.heading("Notas", text="Notas")
        
        # Configure column widths (allow stretch to fill available space)
        history_tree.column("Versión", width=80, stretch=True)
        history_tree.column("Fecha", width=140, stretch=True)
        history_tree.column("Estado", width=100, stretch=True)
        history_tree.column("Autor", width=160, stretch=True)
        history_tree.column("Rev. Téc.", width=160, stretch=True)
        history_tree.column("Rev. Ger.", width=160, stretch=True)
        history_tree.column("Notas", width=300, stretch=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=history_tree.yview)
        history_tree.configure(yscrollcommand=scrollbar.set)
        
        # Add entries (from document entries/history)
        entries_added = 0
        try:
            if hasattr(self.selected_document, 'entries') and self.selected_document.entries:
                # Sort entries by timestamp (newest first)
                sorted_entries = sorted(self.selected_document.entries, key=lambda x: x.timestamp, reverse=True)
                
                for entry in sorted_entries:
                    # Format timestamp to readable date using the same format as main list
                    timestamp_display = self._format_date(entry.timestamp)
                    
                    notes_display = entry.notes if entry.notes else ""
                    if len(notes_display) > 100:
                        notes_display = notes_display[:100] + "..."
                    
                    # Note: rev_tecnica and rev_gerencia are document-level fields, not entry-level
                    # For planos, these represent the users who did technical/management review
                    history_tree.insert(
                        "",
                        "end",
                        values=(
                            entry.version or 'N/A',
                            timestamp_display,
                            entry.state or 'N/A',
                            entry.author or 'N/A',
                            self.selected_document.rev_tecnica or '',  # Document-level field
                            self.selected_document.rev_gerencia or '', # Document-level field
                            notes_display
                        )
                    )
                    entries_added += 1
                    
            # If still no entries found, check for document-level history or version info
            if entries_added == 0:
                # Try to get history from different possible sources
                history_entries = []

                # Check if document has versions attribute (some document types might store history differently)
                if hasattr(self.selected_document, 'versions') and self.selected_document.versions:
                    for version_data in self.selected_document.versions:
                        history_entries.append({
                            'version': getattr(version_data, 'version', 'N/A'),
                            'timestamp': getattr(version_data, 'timestamp', 'N/A'),
                            'state': getattr(version_data, 'state', 'N/A'),
                            'author': getattr(version_data, 'author', 'N/A'),
                            'notes': getattr(version_data, 'notes', '')
                        })
                
                # Check if document has history attribute
                elif hasattr(self.selected_document, 'history') and self.selected_document.history:
                    for hist_entry in self.selected_document.history:
                        history_entries.append({
                            'version': getattr(hist_entry, 'version', 'N/A'),
                            'timestamp': getattr(hist_entry, 'timestamp', 'N/A'),
                            'state': getattr(hist_entry, 'state', 'N/A'),
                            'author': getattr(hist_entry, 'author', 'N/A'),
                            'notes': getattr(hist_entry, 'notes', '')
                        })
                
                # If we found alternative history sources, display them
                if history_entries:
                    # Sort by timestamp (newest first)
                    try:
                        history_entries.sort(key=lambda x: x['timestamp'], reverse=True)
                    except (KeyError, TypeError, ValueError):
                        # Keep original order if sorting fails due to missing timestamps or invalid data
                        pass
                    
                    for entry in history_entries:
                        timestamp_display = self._format_date(entry['timestamp'])
                        notes_display = entry['notes']
                        if len(notes_display) > 100:
                            notes_display = notes_display[:100] + "..."
                        
                        history_tree.insert(
                            "",
                            "end",
                            values=(
                                entry['version'],
                                timestamp_display,
                                entry['state'],
                                entry['author'],
                                self.selected_document.rev_tecnica or '',
                                self.selected_document.rev_gerencia or '',
                                notes_display
                            )
                        )
                        entries_added += 1
                
                # Last resort: show current state only if no history found anywhere
                if entries_added == 0:
                    # Add warning message in header
                    warning_frame = ttk.Frame(header_frame)
                    warning_frame.pack(fill="x", pady=(5, 0))
                    ttk.Label(
                        warning_frame,
                        text="⚠️ Este documento no tiene historial de cambios registrado. Mostrando estado actual únicamente.",
                        font=("Arial", 9),
                        foreground="#FF8C00"
                    ).pack(anchor="w")
                    
                    # Show current state as single entry
                    creation_date = 'N/A'
                    if hasattr(self.selected_document, 'creation_date'):
                        try:
                            creation_date = self._format_date(self.selected_document.creation_date)
                        except (ValueError, TypeError, AttributeError):
                            # Date formatting may fail with invalid or missing dates
                            pass
                    
                    notes_display = self.selected_document.latest_notes or ''
                    if len(notes_display) > 100:
                        notes_display = notes_display[:100] + "..."
                    
                    history_tree.insert(
                        "",
                        "end",
                        values=(
                            self.selected_document.current_version or '1.0',
                            creation_date,
                            self.selected_document.current_state or 'S0',
                            self.selected_document.autor or '',
                            self.selected_document.rev_tecnica or '',
                            self.selected_document.rev_gerencia or '',
                            notes_display
                        )
                    )
                    entries_added += 1
                
        except Exception as e:
            print(f"Error loading history entries: {e}")
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

    def get_selected_document_id(self) -> str:
        """Get the name of the currently selected document (kept method name for compatibility)"""
        selection = self.tree.selection()
        if selection:
            # Las filas se insertan con iid=doc.name (ver _refresh_document_list
            # y _on_select_document); el iid es la fuente de verdad del id,
            # independientemente del orden de las columnas visibles.
            primary_id = selection[0]
            for doc in self.filtered_documents:
                if doc.name == primary_id:
                    return doc.name
            return primary_id
        return ""
    
    def get_selected_document_name(self) -> str:
        """Get the name of the currently selected document."""
        return self.get_selected_document_id()  # Alias for clarity
    
    def _setup_smart_refresh(self, callbacks: dict) -> None:
        """Initialize smart refresh system for planos dashboard."""
        try:
            # Get the manifest path for planos
            if 'get_project_path' in callbacks:
                project_path = Path(callbacks['get_project_path']())
                from utils.path_helper import PathHelper
                pm_path = PathHelper.get_project_manager_path(project_path)
                manifest_path = pm_path / "planos" / "manifest.json"
                
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
                
                print(f"SmartRefresh: Initialized for planos dashboard")
                
        except Exception as e:
            print(f"ERROR: Failed to setup smart refresh for planos: {e}")
    
    def _calculate_document_hash(self) -> str:
        """Calculate a hash of current plano document data for change detection."""
        import hashlib

        # Create a string representation of all document data
        # NOTE: file_paths not included - filesystem is now source of truth
        # File changes are detected at filter-time by querying the filesystem
        doc_data = []
        for doc in sorted(self.documents, key=lambda x: x.name):
            doc_info = f"{doc.name}|{doc.current_state}|{doc.current_version}|{doc.autor}|{doc.rev_tecnica}|{doc.rev_gerencia}"
            # Include latest modification time if available
            if doc.entries:
                latest_entry = sorted(doc.entries, key=lambda x: x.timestamp, reverse=True)[0]
                doc_info += f"|{latest_entry.timestamp}|{latest_entry.notes}"
            doc_data.append(doc_info)

        # Create hash
        data_string = "||".join(doc_data)
        return hashlib.md5(data_string.encode()).hexdigest()
    
    def _smart_refresh_data(self) -> bool:
        """Smart refresh callback - only updates if data actually changed."""
        try:
            if self.refresh_indicator:
                self.refresh_indicator.show_checking()
            
            # Get fresh plano document data
            if 'refresh_planos' in self.callbacks:
                fresh_documents = self.callbacks['refresh_planos']()
                
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
                
                # Update both the document list and state status
                changes_count = self._update_dashboard_intelligently(old_documents, fresh_documents)
                
                # Show success with change count
                if self.refresh_indicator:
                    self.refresh_indicator.show_success(changes_count)
                
                return True
                
        except Exception as e:
            print(f"SmartRefresh: Error during planos refresh: {e}")
            if self.refresh_indicator:
                self.refresh_indicator.show_error("Error de actualización")
            return False
    
    def _update_dashboard_intelligently(self, old_documents: List[PlanoDocument], new_documents: List[PlanoDocument]) -> int:
        """Update dashboard intelligently, preserving user state."""
        changes_count = 0
        
        try:
            # Remember user state for document list. Items are inserted with
            # iid=doc.name, so the iid IS the doc id — don't go through values[0].
            selected_items = self.tree.selection()
            selected_doc_ids = list(selected_items)
            
            # Remember scroll position
            scroll_position = 0
            try:
                if self.tree.yview():
                    scroll_position = self.tree.yview()[0]
            except (AttributeError, IndexError, RuntimeError):
                # Tree widget may not be initialized or yview() may fail
                pass
            
            # Remember filter states
            current_id_filter = self.filter_id_var.get()
            current_state_filter = self.filter_state_var.get()
            current_phase_filter = self.filter_phase_var.get()
            current_user_filter = self.filter_user_var.get()
            
            # Update document list
            doc_list_changes = self._update_document_list_intelligently(old_documents, new_documents)
            changes_count += doc_list_changes
            
            # Restore user state — iids ARE doc.names, match directly.
            if selected_doc_ids:
                new_selected_items = [
                    item for item in self.tree.get_children() if item in selected_doc_ids
                ]
                if new_selected_items:
                    self.tree.selection_set(new_selected_items)
            
            # Restore scroll position
            try:
                self.tree.yview_moveto(scroll_position)
            except (AttributeError, RuntimeError, ValueError):
                # Tree widget may not be initialized or scroll operation may fail
                pass
                
            # Restore filters
            self.filter_id_var.set(current_id_filter)
            self.filter_state_var.set(current_state_filter)
            self.filter_phase_var.set(current_phase_filter)
            self.filter_user_var.set(current_user_filter)
            
            # Re-apply filters
            self.root.after(200, self._apply_filters)
            
        except Exception as e:
            print(f"SmartRefresh: Error in intelligent planos update: {e}")
            # Fallback to full refresh
            self._refresh_document_list()
            changes_count = len(new_documents)
        
        return changes_count
    
    def _update_document_list_intelligently(self, old_documents: List[PlanoDocument], new_documents: List[PlanoDocument]) -> int:
        """Update document list with minimal UI disruption."""
        changes_count = 0
        
        try:
            # Create lookup maps (using names instead of IDs)
            old_docs_map = {doc.name: doc for doc in old_documents}
            new_docs_map = {doc.name: doc for doc in new_documents}
            
            # Get current tree items. Items are inserted with iid=doc.name, so
            # the iid is the doc identity — read it directly instead of digging
            # into values[0] (which is now the displayed filename, not the doc name).
            tree_items = {item: item for item in self.tree.get_children()}
            
            # Update existing items, add new ones
            for doc in new_documents:
                if doc.name in tree_items:
                    # Document exists in tree - check if it needs updating
                    item = tree_items[doc.name]
                    
                    # Compare with old version
                    old_doc = old_docs_map.get(doc.name)
                    if old_doc and self._plano_documents_are_different(old_doc, doc):
                        # Document changed - update the tree item
                        new_values = self._get_tree_values_for_plano(doc)
                        self.tree.item(item, values=new_values)
                        changes_count += 1
                        
                        # Brief highlight effect
                        self.root.after(100, lambda i=item: self._highlight_changed_row(i))
                        
                elif doc.name not in old_docs_map:
                    # New document - add to tree (use doc.name as iid for consistency
                    # with _refresh_document_list so selection lookups work).
                    new_values = self._get_tree_values_for_plano(doc)
                    new_item = self.tree.insert('', 'end', iid=doc.name, values=new_values)
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
    
    def _plano_documents_are_different(self, doc1: PlanoDocument, doc2: PlanoDocument) -> bool:
        """Check if two plano documents have different data."""
        return (doc1.name != doc2.name or 
                doc1.current_state != doc2.current_state or
                doc1.current_version != doc2.current_version or
                doc1.autor != doc2.autor or
                doc1.rev_tecnica != doc2.rev_tecnica or
                doc1.rev_gerencia != doc2.rev_gerencia or
                doc1.latest_notes != doc2.latest_notes)
    
    def _format_date(self, date_string: str) -> str:
        """
        Format date string to day-month-year hour:minute format (DD-MM-YYYY HH:MM).
        Handles various input formats including ISO timestamps.
        """
        if not date_string:
            return ""
        
        try:
            from datetime import datetime
            # Try to parse ISO format timestamp
            if 'T' in date_string or 'Z' in date_string:
                dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
                return dt.strftime("%d-%m-%Y %H:%M")
            # Try to parse if it's already in a date format
            elif '-' in date_string or '/' in date_string:
                # Try common date formats
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", 
                           "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M", "%d-%m-%Y"]:
                    try:
                        dt = datetime.strptime(date_string, fmt)
                        return dt.strftime("%d-%m-%Y %H:%M")
                    except ValueError:
                        continue
            # If all parsing fails, return as-is
            return date_string
        except Exception as e:
            # If any error occurs, return the original string
            return date_string
    
    def _get_display_filename(self, doc) -> str:
        """Return the most representative attached filename for the dashboard.

        Picks the working file matching the currently active type filter when
        only one type is selected (so filtering by .DWG shows the .dwg name,
        not the .pdf the plano also has). Otherwise falls back to: working PDF
        → working DWG → any tracked file → plano's logical name.

        Only the basename is returned so the column shows e.g.
        "04 PLANTAS-ESTADO REFORMADO.dwg" instead of the project-level plano id.
        """
        from pathlib import Path
        file_paths_raw = getattr(doc, 'file_paths', []) or []
        if isinstance(file_paths_raw, str):
            import json
            try:
                file_paths = json.loads(file_paths_raw) or []
            except (json.JSONDecodeError, TypeError):
                file_paths = []
        else:
            file_paths = list(file_paths_raw)

        if not file_paths:
            return doc.name

        working = [p for p in file_paths if 'working' in p.lower()]
        pool = working or file_paths

        pdfs = [p for p in pool if p.lower().endswith('.pdf')]
        dwgs = [p for p in pool if p.lower().endswith('.dwg')]
        rvts = [p for p in pool if p.lower().endswith('.rvt')]

        # Honor the active type filter: when the user has narrowed to a single
        # type, show the filename of that type so the column matches the filter.
        try:
            show_pdf = self.file_type_filters['.pdf'].get()
            show_dwg = self.file_type_filters['.dwg'].get()
            show_rvt = self.file_type_filters['.rvt'].get()
        except (AttributeError, KeyError, tk.TclError):
            show_pdf = show_dwg = show_rvt = True

        active_count = sum(1 for v in (show_pdf, show_dwg, show_rvt) if v)
        if active_count == 1:
            if show_dwg and dwgs:
                return Path(dwgs[0]).name
            if show_pdf and pdfs:
                return Path(pdfs[0]).name
            if show_rvt and rvts:
                return Path(rvts[0]).name

        chosen = (pdfs or dwgs or rvts or pool)[0]
        return Path(chosen).name

    def _get_tree_values_for_plano(self, doc: PlanoDocument) -> tuple:
        """
        Tupla de 10 valores en el orden del REFACTOR_PLAN seccion 6.

        Columnas que aun no expone el modelo PlanoDocument (Codigo,
        Tipo archivo) se intentan leer via getattr y caen a '' si no
        existen. Asi se rellenaran solas cuando una fase futura amplie
        el modelo / controller a leer la tabla `planos` nueva.
        """
        # Remove 'v' prefix from version display
        version_display = (
            doc.current_version.lstrip('v')
            if doc.current_version.startswith('v')
            else doc.current_version
        )

        fecha_display = self._format_date(doc.creation_date)
        project_phase = getattr(doc, 'project_phase', 'Implantación')

        # Codigo y tipo_archivo no estan aun en PlanoDocument; getattr
        # con default '' evita AttributeError y deja la celda vacia.
        codigo = getattr(doc, 'codigo', '') or ''
        tipo_archivo = getattr(doc, 'tipo_archivo', '') or ''

        return (
            codigo,
            self._get_display_filename(doc),
            tipo_archivo,
            doc.current_state,
            version_display,
            project_phase,
            fecha_display,
            doc.autor,
            doc.rev_tecnica,
            doc.rev_gerencia,
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
        """Handle manual refresh request for planos."""
        try:
            if self.refresh_manager:
                self.refresh_manager.force_refresh()
            else:
                # Fallback - refresh manually
                if 'refresh_planos' in self.callbacks:
                    fresh_documents = self.callbacks['refresh_planos']()
                    self.documents = fresh_documents
                    self.filtered_documents = fresh_documents.copy()
                    self._refresh_document_list()
                    if self.refresh_indicator:
                        self.refresh_indicator.show_success(len(fresh_documents))
        except Exception as e:
            print(f"Manual refresh error in planos: {e}")
            if self.refresh_indicator:
                self.refresh_indicator.show_error("Error en actualización manual")
    
    def _show_new_version_with_selection(self, callbacks: dict) -> None:
        """Show new version dialog for selected plano using NewVersionForm"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un plano de la tabla.")
            return
        
        # Prepare pre-selected document data
        pre_selected_document = {
            'id': self.selected_document.name,
            'name': self.selected_document.name,
            'state': self.selected_document.current_state,
            'version': self.selected_document.current_version
        }
        
        # Call the new version callback with pre-selected document
        if 'new_version' in callbacks:
            callbacks['new_version'](pre_selected_document)
    
    def _show_update_state_with_selection(self, callbacks: dict) -> None:
        """Show update state dialog for selected plano using UpdateStateForm"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un plano de la tabla.")
            return
        
        # Prepare pre-selected document data
        pre_selected_document = {
            'id': self.selected_document.name,
            'name': self.selected_document.name,
            'state': self.selected_document.current_state,
            'version': self.selected_document.current_version
        }
        
        # Call the update state callback with pre-selected document
        if 'update_state' in callbacks:
            callbacks['update_state'](pre_selected_document)
    
    def _show_edit_info_with_selection(self, callbacks: dict) -> None:
        """Show edit info dialog for selected plano(s). Supports batch editing."""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un plano de la tabla.")
            return

        selected_docs = getattr(self, 'selected_documents', [self.selected_document])

        # Single document: use full CorrectionForm
        if len(selected_docs) <= 1:
            if 'edit_document_info' in callbacks:
                callbacks['edit_document_info'](self.selected_document.name)
            return

        # Multiple documents: show batch edit dialog for all fields
        self._show_batch_edit_dialog(selected_docs, callbacks)

    def _show_batch_edit_dialog(self, documents: list, callbacks: dict) -> None:
        """Show a dialog to edit multiple fields for multiple selected documents at once."""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edición en Lote ({len(documents)} planos)")
        dialog.geometry("650x520")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.geometry("+{}+{}".format(
            int(dialog.winfo_screenwidth() / 2 - 325),
            int(dialog.winfo_screenheight() / 2 - 260)
        ))

        # Header
        header = ttk.Frame(dialog, padding="15 15 15 5")
        header.pack(fill="x")

        ttk.Label(
            header,
            text=f"Edición en Lote ({len(documents)} planos)",
            font=("Arial", 14, "bold"),
            foreground="#2E5984"
        ).pack(anchor="w")

        # List of selected documents
        doc_names = ", ".join(d.name for d in documents[:5])
        if len(documents) > 5:
            doc_names += f" ... (+{len(documents) - 5} más)"
        ttk.Label(
            header,
            text=f"Documentos: {doc_names}",
            font=("Arial", 9),
            foreground="#666666",
            wraplength=600
        ).pack(anchor="w", pady=(5, 0))

        ttk.Label(
            header,
            text="Activa la casilla de cada campo que desees modificar:",
            font=("Arial", 9, "italic"),
            foreground="#888888"
        ).pack(anchor="w", pady=(5, 0))

        # Content frame with fields
        content = ttk.Frame(dialog, padding="15 5 15 5")
        content.pack(fill="both", expand=True)

        # Phase values
        phase_values = ["Implantación", "Proyecto Básico", "Proyecto Ejecutivo", "Dirección Obra"]

        # Track checkbuttons and widgets for each field
        field_vars = {}   # field_name -> BooleanVar (checkbox)
        field_widgets = {}  # field_name -> widget to get value from

        def toggle_field(field_name):
            """Enable/disable a field widget based on its checkbox."""
            enabled = field_vars[field_name].get()
            widget = field_widgets[field_name]
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly" if enabled else "disabled")
            elif isinstance(widget, tk.Text):
                widget.configure(state="normal" if enabled else "disabled")
            else:
                widget.configure(state="normal" if enabled else "disabled")

        row = 0

        # --- Estado ---
        field_vars['estado'] = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(content, text="Modificar Estado:", variable=field_vars['estado'],
                             command=lambda: toggle_field('estado'))
        cb.grid(row=row, column=0, sticky="w", pady=4)
        estado_combo = ttk.Combobox(content, values=PLANO_STATES, state="disabled", width=15)
        estado_combo.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=4)
        estado_combo.set("S0")
        field_widgets['estado'] = estado_combo
        row += 1

        # --- Fase ---
        field_vars['fase'] = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(content, text="Modificar Fase:", variable=field_vars['fase'],
                             command=lambda: toggle_field('fase'))
        cb.grid(row=row, column=0, sticky="w", pady=4)
        fase_combo = ttk.Combobox(content, values=phase_values, state="disabled", width=25)
        fase_combo.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=4)
        fase_combo.set("Implantación")
        field_widgets['fase'] = fase_combo
        row += 1

        # --- Autor ---
        field_vars['autor'] = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(content, text="Modificar Autor:", variable=field_vars['autor'],
                             command=lambda: toggle_field('autor'))
        cb.grid(row=row, column=0, sticky="w", pady=4)
        autor_entry = ttk.Entry(content, state="disabled", width=30)
        autor_entry.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=4)
        field_widgets['autor'] = autor_entry
        row += 1

        # --- Rev. Técnica ---
        field_vars['rev_tecnica'] = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(content, text="Modificar Rev. Técnica:", variable=field_vars['rev_tecnica'],
                             command=lambda: toggle_field('rev_tecnica'))
        cb.grid(row=row, column=0, sticky="w", pady=4)
        rev_tec_entry = ttk.Entry(content, state="disabled", width=30)
        rev_tec_entry.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=4)
        field_widgets['rev_tecnica'] = rev_tec_entry
        row += 1

        # --- Rev. Gerencia ---
        field_vars['rev_gerencia'] = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(content, text="Modificar Rev. Gerencia:", variable=field_vars['rev_gerencia'],
                             command=lambda: toggle_field('rev_gerencia'))
        cb.grid(row=row, column=0, sticky="w", pady=4)
        rev_ger_entry = ttk.Entry(content, state="disabled", width=30)
        rev_ger_entry.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=4)
        field_widgets['rev_gerencia'] = rev_ger_entry
        row += 1

        # --- Notas ---
        field_vars['notas'] = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(content, text="Modificar Notas:", variable=field_vars['notas'],
                             command=lambda: toggle_field('notas'))
        cb.grid(row=row, column=0, sticky="nw", pady=4)
        notas_text = tk.Text(content, height=3, wrap="word", state="disabled", width=40)
        notas_text.grid(row=row, column=1, sticky="we", padx=(10, 0), pady=4)
        field_widgets['notas'] = notas_text
        row += 1

        content.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ttk.Frame(dialog, padding="15")
        btn_frame.pack(fill="x")

        def apply_changes():
            # Check at least one field is selected
            any_selected = any(v.get() for v in field_vars.values())
            if not any_selected:
                messagebox.showwarning("Sin cambios",
                                       "Activa al menos una casilla para modificar un campo.",
                                       parent=dialog)
                return

            update_cb = callbacks.get('update_document_info')
            phase_cb = callbacks.get('update_plano_phase')

            if not update_cb:
                messagebox.showerror("Error", "Función de actualización no disponible.", parent=dialog)
                return

            # Read values from enabled fields
            new_estado = estado_combo.get() if field_vars['estado'].get() else None
            new_fase = fase_combo.get() if field_vars['fase'].get() else None
            new_autor = autor_entry.get() if field_vars['autor'].get() else None
            new_rev_tecnica = rev_tec_entry.get() if field_vars['rev_tecnica'].get() else None
            new_rev_gerencia = rev_ger_entry.get() if field_vars['rev_gerencia'].get() else None
            new_notas = notas_text.get("1.0", tk.END).strip() if field_vars['notas'].get() else None

            success_count = 0
            errors = []

            for doc in documents:
                try:
                    # For each field: use new value if checkbox active, else keep original
                    estado = new_estado if new_estado is not None else doc.current_state
                    autor = new_autor if new_autor is not None else getattr(doc, 'autor', '')
                    rev_tecnica = new_rev_tecnica if new_rev_tecnica is not None else getattr(doc, 'rev_tecnica', '')
                    rev_gerencia = new_rev_gerencia if new_rev_gerencia is not None else getattr(doc, 'rev_gerencia', '')
                    notas = new_notas if new_notas is not None else getattr(doc, 'notes', '')

                    update_cb(
                        doc.name, doc.name, doc.name,
                        doc.current_version, estado,
                        getattr(doc, 'author', ''), notas,
                        autor, rev_tecnica, rev_gerencia
                    )

                    # Update phase separately if requested
                    if new_fase is not None and phase_cb:
                        try:
                            phase_cb(doc.name, new_fase)
                        except Exception as pe:
                            errors.append(f"{doc.name} (fase): {pe}")

                    success_count += 1
                except Exception as e:
                    errors.append(f"{doc.name}: {e}")

            dialog.destroy()

            # Build summary of what was changed
            changed_fields = []
            if new_estado is not None:
                changed_fields.append(f"Estado={new_estado}")
            if new_fase is not None:
                changed_fields.append(f"Fase={new_fase}")
            if new_autor is not None:
                changed_fields.append(f"Autor={new_autor}")
            if new_rev_tecnica is not None:
                changed_fields.append(f"Rev.Téc.={new_rev_tecnica}")
            if new_rev_gerencia is not None:
                changed_fields.append(f"Rev.Ger.={new_rev_gerencia}")
            if new_notas is not None:
                changed_fields.append("Notas")
            fields_str = ", ".join(changed_fields)

            if errors:
                messagebox.showwarning(
                    "Resultado Parcial",
                    f"Actualizados: {success_count}/{len(documents)}\n"
                    f"Campos: {fields_str}\n\nErrores:\n" + "\n".join(errors)
                )
            else:
                messagebox.showinfo(
                    "Éxito",
                    f"Campos actualizados en {success_count} documentos:\n{fields_str}"
                )

            # Refresh the list
            try:
                if 'refresh_planos' in self.callbacks:
                    fresh_documents = self.callbacks['refresh_planos']()
                    self.documents = fresh_documents
                    self._apply_filters()
            except Exception as e:
                print(f"Error refreshing after batch edit: {e}")
                self._refresh_document_list()

        ttk.Button(btn_frame, text="Aplicar Cambios", command=apply_changes).pack(side="left", padx=(0, 10))
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side="right")

    def _show_history_with_selection(self, callbacks: dict) -> None:
        """Show file history window for selected plano with filters and double-click support"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un plano de la tabla.")
            return

        # Use the handler's view_history callback which has filters and double-click
        if 'view_history' in callbacks:
            callbacks['view_history'](self.selected_document.name)
        else:
            # Fallback to internal history view
            self._show_history()

    def _show_file_management_with_selection(self, callbacks: dict) -> None:
        """Show file management panel for selected plano"""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un plano de la tabla.")
            return
        
        try:
            # Create file management panel callbacks
            file_mgmt_callbacks = {
                'get_current_files': lambda doc_name: callbacks.get('get_current_files', self._default_get_current_files)(doc_name),
                'replace_file': lambda doc_name, current_path, new_path: callbacks.get('replace_file', self._default_replace_file)(doc_name, current_path, new_path),
                'add_file': lambda doc_name, file_path, file_type, dwg_name=None: callbacks.get('add_file', self._default_add_file)(doc_name, file_path, file_type, dwg_name),
                'get_project_path': lambda: callbacks.get('get_project_path', lambda: Path.cwd())(),
                'get_available_dwgs': lambda: callbacks.get('get_available_dwgs', lambda: [])(),
                'set_associated_dwg': lambda doc_name, dwg_path: callbacks.get('set_associated_dwg', lambda n, p: (False, "Not implemented"))(doc_name, dwg_path)
            }
            
            # Create and show file management panel (refresh dashboard on close)
            panel = FileManagementPanel(
                self.root, self.selected_document, file_mgmt_callbacks,
                on_close=self.refresh_document_list
            )
            panel.show()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al abrir gestión de archivos: {e}")
            print(f"Error opening file management panel: {e}")
    
    def _default_get_current_files(self, document_name: str) -> List[Dict]:
        """Default implementation to get current files for a document"""
        # Find the document in our current list
        doc = next((d for d in self.filtered_documents if d.name == document_name), None)
        if not doc:
            return []
        
        files = []
        try:
            # Parse file paths from document
            file_paths_raw = getattr(doc, 'file_paths', [])
            if isinstance(file_paths_raw, str):
                import json
                try:
                    file_paths = json.loads(file_paths_raw)
                except json.JSONDecodeError:
                    file_paths = []
            else:
                file_paths = file_paths_raw
            
            # Convert to file info format
            for file_path_str in file_paths:
                if file_path_str:
                    files.append({
                        'path': file_path_str,
                        'type': Path(file_path_str).suffix.lower(),
                        'relative_path': file_path_str
                    })
        except Exception as e:
            print(f"Error parsing file paths for {document_name}: {e}")
        
        return files
    
    def _default_replace_file(self, document_name: str, current_path: str, new_path: str) -> Tuple[bool, str]:
        """Default implementation for file replacement"""
        return False, "Funcionalidad de reemplazo no implementada en el controlador."

    def _default_add_file(self, document_name: str, file_path: str, file_type: str, dwg_name: str = None) -> Tuple[bool, str]:
        """Default implementation for file addition"""
        return False, "Funcionalidad de adición no implementada en el controlador."

    # ── Quick upload from dashboard ──────────────────────────────────────

    def _quick_upload_file(self, callbacks: dict, extension: str) -> None:
        """Upload a single file of the given type to the selected plano."""
        if not self.selected_document:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un plano de la tabla.")
            return

        # Build file dialog filter
        ext_upper = extension.lstrip('.').upper()
        filetypes = [(f"Archivos {ext_upper}", f"*{extension}"), ("Todos los archivos", "*.*")]

        file_path = filedialog.askopenfilename(
            title=f"Seleccionar {ext_upper} para '{self.selected_document.name}'",
            filetypes=filetypes
        )
        if not file_path:
            return

        # For DWG: ask for custom name
        dwg_name = None
        if extension == ".dwg":
            dwg_name = simpledialog.askstring(
                "Nombre del DWG",
                "Nombre con el que se guardará el DWG (sin extensión):",
                initialvalue=self.selected_document.name,
                parent=self.root
            )
            if dwg_name is None:  # cancelled
                return

        add_file_cb = callbacks.get('add_file')
        if not add_file_cb:
            messagebox.showerror("Error", "Funcionalidad de subida no disponible.")
            return

        result = add_file_cb(self.selected_document.name, file_path, extension, dwg_name)
        success = result.get('success', False) if isinstance(result, dict) else result[0]
        message = result.get('message', '') if isinstance(result, dict) else result[1]

        if success:
            messagebox.showinfo("Éxito", message)
            self.refresh_document_list()
        else:
            messagebox.showerror("Error", message)

    # ── Batch upload ─────────────────────────────────────────────────────

    def _batch_upload(self, callbacks: dict) -> None:
        """Upload multiple files and auto-match them to planos."""
        file_paths = filedialog.askopenfilenames(
            title="Seleccionar archivos para subida masiva",
            filetypes=[
                ("PDF y DWG", "*.pdf *.dwg"),
                ("Archivos PDF", "*.pdf"),
                ("Archivos DWG", "*.dwg"),
                ("Todos los archivos", "*.*")
            ]
        )
        if not file_paths:
            return

        paths = [Path(p) for p in file_paths]
        assignments = self._match_files_to_planos(paths)
        confirmed = self._show_batch_preview(assignments)
        if confirmed:
            self._process_batch_uploads(confirmed, callbacks)

    def _match_files_to_planos(self, file_paths: List[Path]) -> List[Dict]:
        """Match uploaded files to existing planos.

        Primary strategy: sheet-code matching. Names starting with a code like
        "DGA.33", a range "DGA.33-35", or a lettered variant "DGA.49a" are parsed
        and mapped to planos whose code falls within that range. A file without a
        letter (e.g. "DGA.49") matches all letter variants of that number
        (DGA.49, DGA.49a, DGA.49b, ...). A ranged file (e.g. "DGA.42-48") matches
        every plano whose base number is inside the range, including letter variants.

        Fallback: fuzzy name similarity (threshold 0.75) for files without a
        recognizable sheet code.

        Returns one entry per (file, plano) pair. Files without a match produce
        one entry with matched_plano=None.
        """
        import re
        from utils.fuzzy_matcher import FuzzyMatcher

        SHEET_CODE_RE = re.compile(r'^\s*([A-Za-z]+)\.(\d+)(?:([a-zA-Z])|-(\d+))?')
        # Strip known document extensions only. Path(name).stem over-strips when the
        # name contains dots in the middle (e.g. "DGA.33 PLANO" -> "DGA").
        EXT_RE = re.compile(r'\.(dwg|pdf|rvt)$', re.IGNORECASE)
        # Leading sheet/section code, used to drop the prefix before fuzzy comparison
        # so matching focuses on descriptive content. Handles both letter-prefixed
        # codes (DGA.21, DGA.21a, DGA.42-48) and numeric-only ones (03.2, 03.2a).
        CODE_PREFIX_RE = re.compile(
            r'^\s*(?:[A-Za-z]+\.)?\d+(?:\.\d+)?(?:[a-zA-Z]|-\d+)?[\s_\-.]+'
        )

        def sheet_signature(name: str):
            """Extract (prefix, start_num, end_num, letter) or None."""
            stripped = EXT_RE.sub('', name)
            m = SHEET_CODE_RE.match(stripped)
            if not m:
                return None
            prefix, start, letter, end = m.groups()
            start_n = int(start)
            end_n = int(end) if end else start_n
            return (prefix.upper(), start_n, end_n, letter.lower() if letter else None)

        def normalize_for_match(name: str) -> str:
            name = EXT_RE.sub('', name)
            name = CODE_PREFIX_RE.sub('', name)
            name = re.sub(r'_v\d+\.\d+_[A-Z]\d*', '', name)
            name = re.sub(r'[()\[\]{}]', '', name)
            name = name.replace('-', '_').replace(' ', '_')
            while '__' in name:
                name = name.replace('__', '_')
            return name.strip('_').lower()

        def token_set_similarity(s1: str, s2: str) -> float:
            """Order-independent Jaccard on word tokens."""
            tokens1 = {t for t in re.split(r'[\s_\-./]+', s1) if t}
            tokens2 = {t for t in re.split(r'[\s_\-./]+', s2) if t}
            if not tokens1 or not tokens2:
                return 0.0
            return len(tokens1 & tokens2) / len(tokens1 | tokens2)

        def doc_candidate_names(doc):
            """All names a doc can be matched against: its logical name plus any
            tracked file basenames. Lets users upload `04 PLANTAS-REFORMADO_v2.pdf`
            and have it match a plano whose attached file is
            `04 PLANTAS-REFORMADO.dwg`, even if the plano's logical name is
            something abstract like `DGA.10`."""
            from pathlib import Path
            names = [doc.name]
            raw = getattr(doc, 'file_paths', []) or []
            if isinstance(raw, str):
                import json
                try:
                    raw = json.loads(raw) or []
                except (json.JSONDecodeError, TypeError):
                    raw = []
            seen = {doc.name}
            for p in raw:
                bn = Path(p).name
                if bn and bn not in seen:
                    names.append(bn)
                    seen.add(bn)
            return names

        # Pre-compute candidate names and signatures for each plano
        # (one plano can have several candidates: its logical name + each tracked file).
        plano_candidates = [(doc.name, doc_candidate_names(doc)) for doc in self.documents]
        plano_sigs = []
        for doc_name, cands in plano_candidates:
            for cand in cands:
                sig = sheet_signature(cand)
                if sig:
                    plano_sigs.append((doc_name, sig))

        matcher = FuzzyMatcher(similarity_threshold=0.75)
        assignments = []

        for fp in file_paths:
            file_sig = sheet_signature(fp.name)
            code_matches = []

            if file_sig:
                f_prefix, f_start, f_end, f_letter = file_sig
                is_range = f_start != f_end
                seen_for_file = set()
                for doc_name, p_sig in plano_sigs:
                    if doc_name in seen_for_file:
                        continue
                    p_prefix, p_start, _p_end, p_letter = p_sig
                    if p_prefix != f_prefix:
                        continue
                    if not (f_start <= p_start <= f_end):
                        continue
                    # Letter rules:
                    #  - file has letter -> plano must have the same letter
                    #  - single file without letter -> plano must have no letter (exact sheet)
                    #  - ranged file without letter -> accept any letter variant
                    if f_letter is not None:
                        if p_letter != f_letter:
                            continue
                    elif not is_range and p_letter is not None:
                        continue
                    code_matches.append(doc_name)
                    seen_for_file.add(doc_name)

            if code_matches:
                for doc_name in code_matches:
                    assignments.append({
                        'file_path': fp,
                        'matched_plano': doc_name,
                        'confidence': 1.0
                    })
                continue

            # Fallback: fuzzy name similarity. Combine sequence ratio (good for
            # typos / partial differences) with token-set Jaccard (order-independent,
            # catches "OBRA NUEVA PLANTAS" vs "PLANTAS OBRA NUEVA"). Take the max.
            # Compare against every candidate name per plano (logical + tracked files).
            normalized_file = normalize_for_match(fp.name)
            best_match = None
            best_confidence = 0.0
            exact_hit = False
            for doc_name, cands in plano_candidates:
                if exact_hit:
                    break
                for cand in cands:
                    normalized_doc = normalize_for_match(cand)
                    if normalized_file == normalized_doc:
                        best_match = doc_name
                        best_confidence = 1.0
                        exact_hit = True
                        break
                    seq_ratio = matcher.calculate_similarity(normalized_file, normalized_doc)
                    jaccard = token_set_similarity(normalized_file, normalized_doc)
                    similarity = max(seq_ratio, jaccard)
                    if similarity > best_confidence:
                        best_confidence = similarity
                        if similarity >= 0.75:
                            best_match = doc_name

            assignments.append({
                'file_path': fp,
                'matched_plano': best_match,
                'confidence': best_confidence
            })

        return assignments

    def _show_batch_preview(self, assignments: List[Dict]) -> Optional[List[Dict]]:
        """Show a preview dialog of the batch assignments. Returns confirmed list or None."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Vista previa de subida masiva")
        dialog.geometry("800x500")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("+{}+{}".format(
            int(dialog.winfo_screenwidth() / 2 - 400),
            int(dialog.winfo_screenheight() / 2 - 250)
        ))

        ttk.Label(dialog, text="Asignación de archivos a planos",
                  font=("Arial", 13, "bold")).pack(pady=(12, 6))

        # Treeview
        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=4)

        cols = ("Archivo", "Tipo", "Plano Asignado", "Confianza")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14)
        tree.heading("Archivo", text="Archivo")
        tree.heading("Tipo", text="Tipo")
        tree.heading("Plano Asignado", text="Plano Asignado")
        tree.heading("Confianza", text="Confianza")
        tree.column("Archivo", width=280)
        tree.column("Tipo", width=60, stretch=False)
        tree.column("Plano Asignado", width=280)
        tree.column("Confianza", width=90, stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Track unique files so the counter reflects source files, not upload operations
        # (one file can map to several planos when the file covers a range like DGA.33-35).
        files_seen = {}
        for a in assignments:
            fp: Path = a['file_path']
            ext = fp.suffix.upper().lstrip('.')
            if a['matched_plano']:
                plano = a['matched_plano']
                conf = f"{a['confidence']:.0%}"
            else:
                # No match → will be created as a brand new plano with the filename as name
                plano = f"Crear nuevo: {fp.stem}"
                conf = "Nuevo"
            tree.insert("", "end", values=(fp.name, ext, plano, conf))
            key = str(fp)
            if key not in files_seen:
                files_seen[key] = False
            if a['matched_plano']:
                files_seen[key] = True

        unique_files_total = len(files_seen)
        unique_files_matched = sum(1 for matched in files_seen.values() if matched)
        unique_files_new = unique_files_total - unique_files_matched
        # Each assignment is one operation: matched ones add a file to an existing plano,
        # unmatched ones create a brand new plano.
        operations_count = len(assignments)

        info_parts = []
        if unique_files_matched:
            info_parts.append(f"{unique_files_matched} emparejados")
        if unique_files_new:
            info_parts.append(f"{unique_files_new} nuevos")
        info_text = f"{unique_files_total} archivos: " + ", ".join(info_parts) if info_parts else f"{unique_files_total} archivos"
        if operations_count > unique_files_total:
            info_text += f" — se realizarán {operations_count} operaciones"

        ttk.Label(dialog,
                  text=info_text + ".",
                  font=("Arial", 10), foreground="#666666").pack(pady=4)

        result = {'confirmed': None}

        def on_confirm():
            result['confirmed'] = list(assignments)
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        btn_unit = "operaciones" if operations_count != 1 else "operación"
        ttk.Button(btn_frame, text=f"Confirmar Subida ({operations_count} {btn_unit})",
                   command=on_confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancelar",
                   command=dialog.destroy).pack(side="left", padx=6)

        dialog.wait_window()
        return result['confirmed']

    def _process_batch_uploads(self, assignments: List[Dict], callbacks: dict) -> None:
        """Process confirmed batch uploads.

        Matched assignments are uploaded as a new version of the existing plano
        (keeping the plano's current version/state). This routes through the
        same path as the "Nueva versión" form: previous PDFs are archived to
        Old/ and the new file lands with the canonical name (no `-N` suffix).
        Unmatched assignments create a brand new plano named after the file.

        For both paths, the source file's mtime is preserved as the entry
        timestamp so the dashboard "Fecha" column shows when the file was
        produced, not when it was uploaded.
        """
        from datetime import datetime

        submit_new_version_cb = callbacks.get('submit_new_version')
        submit_new_doc_cb = callbacks.get('submit_new_document')
        add_file_cb = callbacks.get('add_file')  # legacy fallback only
        if not submit_new_version_cb and not add_file_cb:
            messagebox.showerror("Error", "Funcionalidad de subida no disponible.")
            return

        # Build a quick lookup so we can read the matched plano's current
        # version/state without another DB hit.
        docs_by_name = {d.name: d for d in self.documents}

        successes = []
        errors = []
        warnings = []

        def file_mtime_iso(path: Path) -> str:
            try:
                return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
            except OSError:
                return datetime.now().isoformat()

        for a in assignments:
            fp: Path = a['file_path']
            doc_name = a['matched_plano']
            ext = fp.suffix.lower()
            mtime_iso = file_mtime_iso(fp)

            try:
                if doc_name:
                    doc = docs_by_name.get(doc_name)
                    if not doc:
                        errors.append(f"{fp.name}: plano '{doc_name}' no encontrado")
                        continue
                    version = doc.current_version or "1.0"
                    state = doc.current_state or "S0"
                    author = getattr(self, 'user_name', '') or doc.autor or ''
                    dwg_name = doc_name if ext == '.dwg' else ""

                    if submit_new_version_cb:
                        # The handler returns a list of per-file messages from
                        # the controller; lines starting with "Error" mean a
                        # routing failure for that file. Treat those as errors
                        # rather than blindly counting success.
                        result_msgs = submit_new_version_cb(
                            doc_name, doc_name, version, state,
                            [fp], author, "Subida masiva", dwg_name,
                            mtime_iso
                        ) or []
                        if isinstance(result_msgs, str):
                            result_msgs = [result_msgs]
                        bad = [m for m in result_msgs if isinstance(m, str) and m.lower().startswith('error')]
                        warns = [m for m in result_msgs if isinstance(m, str) and m.startswith('⚠')]
                        if bad:
                            success = False
                            message = "; ".join(bad)
                        else:
                            success = True
                            message = f"Nueva versión añadida a {doc_name}"
                            warnings.extend(warns)
                    else:
                        # Fallback: legacy add_file. Won't archive old PDFs and
                        # may produce -N suffixes, but preserves prior behavior.
                        result = add_file_cb(doc_name, str(fp), ext,
                                             doc_name if ext == '.dwg' else None)
                        success = result.get('success', False) if isinstance(result, dict) else result[0]
                        message = result.get('message', '') if isinstance(result, dict) else result[1]
                else:
                    if not submit_new_doc_cb:
                        success = False
                        message = "Creación de plano nuevo no disponible."
                    else:
                        new_name = fp.stem
                        author = getattr(self, 'user_name', '') or ''
                        result_msgs = submit_new_doc_cb(
                            new_name, new_name, "1.0", "S0",
                            [fp], author, "Subida masiva", "",
                            mtime_iso
                        ) or []
                        if isinstance(result_msgs, str):
                            result_msgs = [result_msgs]
                        bad = [m for m in result_msgs if isinstance(m, str) and m.lower().startswith('error')]
                        warns = [m for m in result_msgs if isinstance(m, str) and m.startswith('⚠')]
                        if bad:
                            success = False
                            message = "; ".join(bad)
                        else:
                            success = True
                            message = f"Plano nuevo creado: {new_name}"
                            warnings.extend(warns)

                if success:
                    successes.append(fp.name)
                else:
                    errors.append(f"{fp.name}: {message}")
            except Exception as e:
                errors.append(f"{fp.name}: {e}")

        # Summary
        summary = f"Subidos: {len(successes)} de {len(assignments)}"
        if errors:
            summary += f"\n\nErrores:\n" + "\n".join(errors)
        if warnings:
            summary += f"\n\nAvisos:\n" + "\n".join(warnings)

        if errors or warnings:
            messagebox.showwarning("Subida Masiva", summary)
        else:
            messagebox.showinfo("Subida Masiva", summary)

        self.refresh_document_list()

    # ── Drag & drop handler ──────────────────────────────────────────────

    def _on_files_dropped_on_dashboard(self, file_paths: List[Path], row_id: Optional[str],
                                       callbacks: dict) -> None:
        """Handle files dropped on the dashboard treeview."""
        if row_id:
            # Files dropped on a specific row → upload directly to that plano
            doc = next((d for d in self.filtered_documents if d.name == row_id), None)
            if not doc:
                messagebox.showwarning("Error", f"No se encontró el plano '{row_id}'.")
                return

            add_file_cb = callbacks.get('add_file')
            if not add_file_cb:
                messagebox.showerror("Error", "Funcionalidad de subida no disponible.")
                return

            successes = []
            errors = []
            for fp in file_paths:
                ext = fp.suffix.lower()
                if ext not in ('.pdf', '.dwg', '.rvt'):
                    errors.append(f"{fp.name}: tipo no soportado")
                    continue
                dwg_name = doc.name if ext == '.dwg' else None
                try:
                    result = add_file_cb(doc.name, str(fp), ext, dwg_name)
                    success = result.get('success', False) if isinstance(result, dict) else result[0]
                    message = result.get('message', '') if isinstance(result, dict) else result[1]
                    if success:
                        successes.append(fp.name)
                    else:
                        errors.append(f"{fp.name}: {message}")
                except Exception as e:
                    errors.append(f"{fp.name}: {e}")

            if successes:
                msg = f"Subidos a '{doc.name}': {len(successes)} archivo(s)"
                if errors:
                    msg += f"\nErrores: {len(errors)}"
                messagebox.showinfo("Subida", msg)
            elif errors:
                messagebox.showerror("Error", "\n".join(errors))

            self.refresh_document_list()
        else:
            # Files dropped on empty area → batch matching flow
            assignments = self._match_files_to_planos(file_paths)
            confirmed = self._show_batch_preview(assignments)
            if confirmed:
                self._process_batch_uploads(confirmed, callbacks)


    def __del__(self):
        """Cleanup when planos dashboard is destroyed."""
        if self.refresh_manager:
            self.refresh_manager.stop_refresh_cycle()