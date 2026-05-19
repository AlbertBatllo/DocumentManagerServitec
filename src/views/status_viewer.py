import tkinter as tk
from tkinter import ttk
import tkinter.font as font
from typing import List, Callable, Optional
from models.document import Document
from config.settings import StatusConfig
from .base_view import BaseView
from utils.smart_refresh_manager import SmartRefreshManager
from views.components.refresh_indicator import RefreshIndicator
from pathlib import Path


class StatusViewer:
    def __init__(self, root: tk.Tk, status_config: StatusConfig, doc_type: str = "planos"):
        self.root = root
        self.status_config = status_config
        self.doc_type = doc_type
        self.tree = None
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.user_filter_var = tk.StringVar()
        self.documents: List[Document] = []
        self.notification_widget = None
        
        # Smart refresh components
        self.refresh_manager: Optional[SmartRefreshManager] = None
        self.refresh_indicator: Optional[RefreshIndicator] = None
        self.callbacks: dict = {}
        self.last_document_hash: Optional[str] = None
        
    def show(self, documents: List[Document], callbacks: dict, user_name: str = None) -> None:
        """Show the status viewer window."""
        self.documents = documents
        self.callbacks = callbacks
        self._initial_batch_size = 50  # Show first 50 docs immediately for faster response
        self._progressive_batch_size = 25  # Load 25 more docs at a time
        self._loading_in_progress = False
        
        # Ensure window is large enough for all buttons to be visible, preserving user size
        if BaseView._current_window_size is not None:
            current_width, current_height = BaseView._current_window_size
            if current_width >= 900 and current_height >= 700:
                self.root.geometry(f"{current_width}x{current_height}")
            else:
                self.root.geometry("900x700")
                BaseView._current_window_size = (900, 700)
        else:
            self.root.geometry("900x700")
            BaseView._current_window_size = (900, 700)
        
        # Set up size tracking
        def on_window_resize(event):
            if event.widget == self.root:
                new_geometry = self.root.geometry()
                size_part = new_geometry.split('+')[0]
                if 'x' in size_part:
                    width_str, height_str = size_part.split('x')
                    try:
                        new_width = int(width_str)
                        new_height = int(height_str)
                        BaseView._current_window_size = (new_width, new_height)
                    except ValueError:
                        pass
        
        self.root.bind('<Configure>', on_window_resize)
        
        # Clear window
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Defer notification widget setup to avoid blocking initial display
        if user_name and 'get_notification_data' in callbacks:
            self.root.after(200, lambda: self._setup_notification_widget(callbacks, user_name))
        
        # Main container using grid layout like the original
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Top frame for filters and legend (using grid layout)
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 10))
        top_frame.columnconfigure(0, weight=1)  # Filter frame expands
        top_frame.columnconfigure(1, weight=0)  # Legend frame stays fixed
        
        # Filter frame (left side) - stack vertically
        filter_frame = ttk.Frame(top_frame)
        filter_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        # Search by ID (row 0)
        ttk.Label(filter_frame, text="Buscar por ID:").grid(row=0, column=0, padx=5, sticky="w")
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.grid(row=0, column=1, padx=5, sticky="w")
        search_entry.bind('<KeyRelease>', lambda e: self._apply_filters())
        
        # Filter by status (row 1)
        ttk.Label(filter_frame, text="Filtrar por Estado:").grid(row=1, column=0, padx=5, sticky="w", pady=(5, 0))
        filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            values=["Todos"] + list(self.status_config.STATE_MAP.values()),
            state="readonly",
            width=20
        )
        filter_combo.set("Todos")
        filter_combo.grid(row=1, column=1, padx=5, sticky="w", pady=(5, 0))
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_filters())
        
        # Filter by user name (row 2)
        ttk.Label(filter_frame, text="Filtrar por Usuario:").grid(row=2, column=0, padx=5, sticky="w", pady=(5, 0))
        user_filter_entry = ttk.Entry(filter_frame, textvariable=self.user_filter_var, width=20)
        user_filter_entry.grid(row=2, column=1, padx=5, sticky="w", pady=(5, 0))
        user_filter_entry.bind('<KeyRelease>', lambda e: self._apply_filters())
        
        # Clear filters button (row 3)
        ttk.Button(
            filter_frame,
            text="Limpiar Filtros",
            command=self._clear_filters
        ).grid(row=3, column=0, columnspan=2, padx=5, sticky="w", pady=(5, 0))
        
        # Legend panel (right side) - exactly like original
        legend_frame = ttk.LabelFrame(top_frame, text="Leyenda de Estados", padding=10)
        legend_frame.grid(row=0, column=1, sticky="e", padx=10)
        
        # Info button
        info_button = ttk.Button(legend_frame, text="?", command=self._show_status_info, width=2)
        info_button.grid(row=0, column=2, rowspan=len(self.status_config.STATUS_COLORS), sticky="ns", padx=(5,0))
        
        # Color legend entries - exactly like original
        for i, (status, color) in enumerate(self.status_config.STATUS_COLORS.items()):
            color_label = tk.Label(legend_frame, text="  ", bg=color)
            color_label.grid(row=i, column=0, pady=2, sticky="w")
            text_label = ttk.Label(legend_frame, text=f" {self.status_config.STATE_MAP.get(status, status)}")
            text_label.grid(row=i, column=1, pady=2, sticky="w")
        
        # Create treeview
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview - different columns for certificates vs planos (removed ID column)
        if self.doc_type == "certificaciones":
            columns = ("Nombre", "Mes", "Año", "Estado", "Autor", "Rev. Téc.", "Rev. Ger.", "Notas")
        else:
            columns = ("Nombre", "Versión", "Estado", "Fecha", "Autor", "Rev. Téc.", "Rev. Ger.", "Notas")
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="tree headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Configure columns
        self.tree.column("#0", width=0, stretch=False)
        self.tree.column("Nombre", width=250)  # Expanded from 150 to 250 (since ID column is removed)
        
        if self.doc_type == "certificaciones":
            self.tree.column("Mes", width=50, anchor="center")
            self.tree.column("Año", width=60, anchor="center")
        else:
            self.tree.column("Versión", width=60, anchor="center")
        
        self.tree.column("Estado", width=60, anchor="center")
        
        if self.doc_type == "planos":
            self.tree.column("Fecha", width=80, anchor="center")
        
        self.tree.column("Autor", width=100, anchor="center")
        self.tree.column("Rev. Téc.", width=100, anchor="center")
        self.tree.column("Rev. Ger.", width=100, anchor="center")
        self.tree.column("Notas", width=200)
        
        # Headers
        self.tree.heading("Nombre", text="Nombre")
        
        if self.doc_type == "certificaciones":
            self.tree.heading("Mes", text="Mes")
            self.tree.heading("Año", text="Año")
        else:
            self.tree.heading("Versión", text="Versión")
        
        self.tree.heading("Estado", text="Estado")
        
        if self.doc_type == "planos":
            self.tree.heading("Fecha", text="Fecha")
        
        self.tree.heading("Autor", text="Autor")
        self.tree.heading("Rev. Téc.", text="Rev. Téc.")
        self.tree.heading("Rev. Ger.", text="Rev. Ger.")
        self.tree.heading("Notas", text="Notas")
        
        # Configure tags for colors
        for state_code, color in self.status_config.STATUS_COLORS.items():
            self.tree.tag_configure(state_code, foreground=color)
        
        # Pack treeview and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        # Bind events
        self.tree.bind('<Double-Button-1>', callbacks['on_double_click'])
        self.tree.bind('<<TreeviewSelect>>', callbacks['on_select'])
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(
            button_frame,
            text="Ver Historial",
            command=callbacks['view_history']
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame,
            text="Proceso Corrección",
            command=callbacks.get('annotate_document', lambda: None)
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame,
            text="✏️ Editar información",
            command=callbacks.get('edit_document_info', lambda: None)
        ).pack(side="left", padx=5)
        
        # Add export button only for planos
        if self.doc_type == "planos":
            ttk.Button(
                button_frame,
                text="Exportar Múltiples",
                command=callbacks.get('export_multiple', lambda: None)
            ).pack(side="left", padx=5)
        
        # Add action buttons for document management
        ttk.Button(
            button_frame,
            text="🆕 Nuevo Documento",
            command=callbacks.get('new_document', lambda: None)
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame,
            text="📄 Nueva Versión", 
            command=callbacks.get('new_version', lambda: None)
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame,
            text="🔄 Actualizar Estado",
            command=callbacks.get('update_state', lambda: None)
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame,
            text="Volver",
            command=callbacks['back']
        ).pack(side="right", padx=5)
        
        # Status bar
        self.status_label = ttk.Label(
            main_frame,
            text=f"Total: {len(documents)} documentos",
            relief="sunken"
        )
        self.status_label.pack(fill="x", pady=(5, 0))
        
        # Add refresh indicator
        self.refresh_indicator = RefreshIndicator(main_frame)
        self.refresh_indicator.set_manual_refresh_callback(self._manual_refresh)
        
        # Populate tree (after status_label is created)
        self._populate_tree()
        
        # Start progressive loading if we have more documents than initial batch
        if len(self.documents) > self._initial_batch_size:
            # Start loading the rest after a short delay to let UI appear first
            self.root.after(50, self._load_remaining_documents)
        
        # Defer smart refresh setup - only initialize after UI is shown
        # This avoids blocking the initial display
        self.root.after(500, lambda: self._setup_smart_refresh(callbacks))

    def refresh_documents(self, documents: List[Document]) -> None:
        """Refresh the displayed documents without recreating the view."""
        self.documents = documents
        self._populate_tree()
    
    def _populate_tree(self) -> None:
        """
        Populate the treeview with filtered documents.
        Optimized for performance with minimal operations.
        """
        # Clear existing items in one operation
        self.tree.delete(*self.tree.get_children())
        
        # Get filters once
        search_text = self.search_var.get().lower() if self.search_var.get() else ""
        filter_status = self.filter_var.get()
        user_filter_text = self.user_filter_var.get().lower() if self.user_filter_var.get() else ""
        
        # Build filtered list and tree data in single pass
        tree_items = []
        
        for doc in self.documents:
            # Skip early if search doesn't match
            if search_text:
                # Cache the lowered name
                if not hasattr(doc, '_lower_name_cache'):
                    doc._lower_name_cache = doc.name.lower()
                if search_text not in doc._lower_name_cache:
                    continue
            
            # Skip if status doesn't match
            if filter_status != "Todos":
                status_text = self.status_config.STATE_MAP.get(doc.current_state, doc.current_state)
                if status_text != filter_status:
                    continue
            
            # Skip if user filter doesn't match
            if user_filter_text:
                # Cache lowered user fields
                if not hasattr(doc, '_lower_users_cache'):
                    doc._lower_users_cache = (
                        doc.autor.lower(),
                        doc.rev_tecnica.lower(), 
                        doc.rev_gerencia.lower()
                    )
                
                if not any(user_filter_text in field for field in doc._lower_users_cache):
                    continue
            
            # Document passed filters - prepare tree data
            tree_items.append((doc.name, doc))
        
        # Sort once
        tree_items.sort(key=lambda x: x[0])
        
        # Limit initial batch for responsiveness
        initial_items = tree_items[:self._initial_batch_size] if hasattr(self, '_initial_batch_size') else tree_items
        
        # Batch insert items
        for _, doc in initial_items:
            # Use cached latest_notes property (major performance gain)
            last_notes = doc.latest_notes
            
            # Use status code directly instead of descriptive text
            status_code = doc.current_state
            
            # Handle different column structures for certificates vs planos
            if self.doc_type == "certificaciones":
                # Parse month/year from version (format: "MM/YYYY")
                month = ""
                year = ""
                if "/" in doc.version:
                    parts = doc.version.split("/")
                    if len(parts) == 2:
                        month = parts[0]
                        year = parts[1]
                
                values = (
                    doc.name,
                    month,
                    year,
                    status_code,
                    doc.autor,
                    doc.rev_tecnica,
                    doc.rev_gerencia,
                    last_notes
                )
            else:
                # Use cached creation_date property (major performance gain)
                document_date = doc.creation_date
                
                # Remove "v" prefix from version display
                display_version = doc.version
                if display_version.startswith('v'):
                    display_version = display_version[1:]
                
                values = (
                    doc.name,
                    display_version,
                    status_code,
                    document_date,
                    doc.autor,
                    doc.rev_tecnica,
                    doc.rev_gerencia,
                    last_notes
                )
            
            # Insert item
            self.tree.insert(
                "",
                "end",
                values=values,
                tags=(doc.current_state,)
            )
        
        # Update status bar
        shown = len(initial_items) if hasattr(self, '_initial_batch_size') else len(tree_items)
        total = len(tree_items)
        if shown < total:
            self.status_label.config(text=f"Mostrando: {shown} de {total} documentos (cargando...)")
        else:
            self.status_label.config(text=f"Mostrando: {total} de {len(self.documents)} documentos")

    def _apply_filters(self) -> None:
        """Apply search and filter criteria."""
        self._populate_tree()

    def _clear_filters(self) -> None:
        """Clear all filters."""
        self.search_var.set("")
        self.filter_var.set("Todos")
        self.user_filter_var.set("")
        self._populate_tree()

    def get_selected_document_id(self) -> Optional[str]:
        """Get the name of the currently selected document (kept method name for compatibility)."""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            return item['values'][0]  # Name is now the first column
        return None
    
    def get_selected_document_name(self) -> Optional[str]:
        """Get the name of the currently selected document."""
        return self.get_selected_document_id()  # Alias for clarity

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
            ("S3A", "Aprobado por propiedad/promotor", "Aprobado por propiedad/promotor.")
        ]
        
        for row in status_data:
            tree.insert("", "end", values=row)
        
        tree.pack(fill="both", expand=True, padx=10, pady=10)
    
    def _setup_notification_widget(self, callbacks: dict, user_name: str):
        """Setup the notification widget for StatusViewer."""
        try:
            # Import here to avoid circular imports - DISABLED
            # from .notification_widget import NotificationWidget  # Removed
            
            # Remove existing widget if any
            if self.notification_widget:
                try:
                    self.notification_widget.hide_widget()
                except (AttributeError, RuntimeError):
                    # Widget might already be destroyed or not exist
                    pass
            
            # Create new widget - DISABLED
            # self.notification_widget = NotificationWidget(self.root)  # Removed
            self.notification_widget = None
            
            # Set callbacks - DISABLED
            # self.notification_widget.set_callbacks(
            #     get_notifications=lambda: callbacks.get('get_notification_data')(user_name),
            #     mark_read=callbacks.get('mark_notification_as_read'),
            #     on_click=callbacks.get('navigate_to_document'),
            #     delete_notification=callbacks.get('delete_notification')
            # )  # Removed
            
            # Set current user - DISABLED
            # self.notification_widget.set_current_user(user_name)  # Removed
            
            # Refresh and show - DISABLED
            # self.notification_widget.refresh_count()  # Removed
            # self.notification_widget.show_widget()  # Removed
            
            print(f"DEBUG: Notification widget setup for StatusViewer")
            
        except Exception as e:
            print(f"ERROR: Failed to setup notification widget in StatusViewer: {e}")
            import traceback
            traceback.print_exc()
    
    def _setup_smart_refresh(self, callbacks: dict) -> None:
        """Initialize smart refresh system for status viewer."""
        try:
            # Get the manifest path for current document type
            if 'get_project_path' not in callbacks:
                return  # Smart refresh disabled
                
            project_path = Path(callbacks['get_project_path']())
            from utils.path_helper import PathHelper
            pm_path = PathHelper.get_project_manager_path(project_path)
            manifest_path = pm_path / self.doc_type / "manifest.json"
            
            if not manifest_path.exists():
                return  # No manifest file
            
            # Create refresh manager with fixed interval to avoid network detection
            # Network detection is expensive and blocks UI
            self.refresh_manager = SmartRefreshManager(
                json_path=str(manifest_path),
                refresh_callback=self._smart_refresh_data,
                refresh_interval=15000  # 15 seconds fixed - avoids expensive network detection
            )
            
            # Start the refresh cycle
            self.refresh_manager.start_refresh_cycle(self.root)
            
            # Calculate initial document hash
            self.last_document_hash = self._calculate_document_hash()
                
        except Exception as e:
            # Silently fail - smart refresh is optional
            pass
    
    def _calculate_document_hash(self) -> str:
        """Calculate a hash of current document data for change detection."""
        import hashlib
        
        # Quick hash based on document count and key properties
        # Much faster than hashing all document data
        hash_parts = [
            str(len(self.documents)),
            # Sample first and last few documents for changes
            *[f"{doc.name}|{doc.current_version}|{doc.current_state}" 
              for doc in self.documents[:5]],
            *[f"{doc.name}|{doc.current_version}|{doc.current_state}" 
              for doc in self.documents[-5:] if len(self.documents) > 5]
        ]
        
        # Create hash
        data_string = "|".join(hash_parts)
        return hashlib.md5(data_string.encode()).hexdigest()
    
    def _smart_refresh_data(self) -> bool:
        """Smart refresh callback - only updates if data actually changed."""
        try:
            print("DEBUG SmartRefresh: _smart_refresh_data callback triggered!")
            
            if self.refresh_indicator:
                self.refresh_indicator.show_checking()
            
            # Get fresh document data
            if 'refresh_documents' in self.callbacks:
                print("DEBUG SmartRefresh: Getting fresh documents...")
                fresh_documents = self.callbacks['refresh_documents']()
                print(f"DEBUG SmartRefresh: Got {len(fresh_documents)} fresh documents")
                
                # Calculate hash of fresh data
                old_documents = self.documents
                self.documents = fresh_documents  # Temporarily assign for hash calculation
                fresh_hash = self._calculate_document_hash()
                
                print(f"DEBUG SmartRefresh: Old hash: {self.last_document_hash}")
                print(f"DEBUG SmartRefresh: New hash: {fresh_hash}")
                
                # Check if anything actually changed
                if fresh_hash == self.last_document_hash:
                    # No changes
                    print("DEBUG SmartRefresh: No changes detected")
                    self.documents = old_documents  # Restore original
                    if self.refresh_indicator:
                        self.refresh_indicator.show_success(0)  # 0 changes
                    return False
                
                # Data changed! Update UI intelligently
                print("DEBUG SmartRefresh: Changes detected! Updating UI...")
                self.last_document_hash = fresh_hash
                changes_count = self._update_tree_intelligently(old_documents, fresh_documents)
                print(f"DEBUG SmartRefresh: Updated tree with {changes_count} changes")
                
                # Update status bar
                self.status_label.config(text=f"Total: {len(fresh_documents)} documentos")
                
                # Show success with change count
                if self.refresh_indicator:
                    self.refresh_indicator.show_success(changes_count)
                
                print("DEBUG SmartRefresh: Refresh completed successfully")
                return True
            else:
                print("DEBUG SmartRefresh: No 'refresh_documents' callback available")
                
        except Exception as e:
            print(f"SmartRefresh: Error during refresh: {e}")
            if self.refresh_indicator:
                self.refresh_indicator.show_error("Error de actualización")
            return False
    
    def _update_tree_intelligently(self, old_documents: List[Document], new_documents: List[Document]) -> int:
        """Update tree view intelligently, preserving user state and minimizing flicker."""
        changes_count = 0
        
        try:
            # Remember user state
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
            
            # Create lookup maps
            old_docs_map = {doc.name: doc for doc in old_documents}
            new_docs_map = {doc.name: doc for doc in new_documents}
            
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
                if doc.name in tree_items:
                    # Document exists in tree - check if it needs updating
                    item = tree_items[doc.name]
                    
                    # Compare with old version
                    old_doc = old_docs_map.get(doc.name)
                    if old_doc and self._documents_are_different(old_doc, doc):
                        # Document changed - update the tree item
                        new_values = self._get_tree_values_for_document(doc)
                        self.tree.item(item, values=new_values)
                        
                        # Highlight changed row briefly
                        self.tree.set_children(item)  # This might help with refresh
                        changes_count += 1
                        
                        # Brief highlight effect
                        self.root.after(100, lambda i=item: self._highlight_changed_row(i))
                        
                elif doc.name not in old_docs_map:
                    # New document - add to tree
                    new_values = self._get_tree_values_for_document(doc)
                    new_item = self.tree.insert('', 'end', values=new_values)
                    changes_count += 1
                    
                    # Highlight new row
                    self.root.after(100, lambda i=new_item: self._highlight_changed_row(i))
            
            # Remove deleted documents
            for doc_id, item in tree_items.items():
                if doc_id not in new_docs_map:
                    self.tree.delete(item)
                    changes_count += 1
            
            # Restore user selection
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
                
            # Re-apply filters to maintain consistency
            self.root.after(200, self._apply_filters)
            
        except Exception as e:
            print(f"SmartRefresh: Error in intelligent update: {e}")
            # Fallback to full repopulation
            self._populate_tree()
            changes_count = len(new_documents)
        
        return changes_count
    
    def _documents_are_different(self, doc1: Document, doc2: Document) -> bool:
        """
        Check if two documents have different data.
        Optimized to use cached properties instead of sorting.
        """
        if (doc1.name != doc2.name or 
            doc1.current_version != doc2.current_version or
            doc1.current_state != doc2.current_state or
            doc1.autor != doc2.autor or
            doc1.rev_tecnica != doc2.rev_tecnica or
            doc1.rev_gerencia != doc2.rev_gerencia):
            return True
            
        # Check if latest entry is different using cached properties
        if len(doc1.entries) != len(doc2.entries):
            return True
            
        if doc1.entries and doc2.entries:
            # Use cached latest_entry property instead of sorting
            latest1 = doc1.latest_entry
            latest2 = doc2.latest_entry
            if latest1 and latest2:
                if (latest1.timestamp != latest2.timestamp or 
                    latest1.notes != latest2.notes):
                    return True
        
        return False
    
    def _get_tree_values_for_document(self, doc: Document) -> tuple:
        """
        Get tree values tuple for a document.
        Optimized to use cached properties instead of repeated sorting.
        """
        # Use cached latest_notes property instead of sorting
        last_notes = doc.latest_notes
        status_code = doc.current_state
        
        if self.doc_type == "certificaciones":
            # Parse month/year from version (format: "MM/YYYY")
            month, year = "", ""
            if "/" in doc.version:
                parts = doc.version.split("/")
                if len(parts) == 2:
                    month, year = parts
            
            return (doc.name, doc.name, month, year, status_code, doc.autor, doc.rev_tecnica, doc.rev_gerencia, last_notes)
        else:
            # Use cached creation_date property instead of sorting
            fecha = doc.creation_date
            
            # Remove "v" prefix from version display
            display_version = doc.version
            if display_version.startswith('v'):
                display_version = display_version[1:]
            
            return (doc.name, doc.name, display_version, status_code, fecha, doc.autor, doc.rev_tecnica, doc.rev_gerencia, last_notes)
    
    def _highlight_changed_row(self, item) -> None:
        """Briefly highlight a changed row."""
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
        """Handle manual refresh request."""
        try:
            if self.refresh_manager:
                self.refresh_manager.force_refresh()
            else:
                # Fallback - just repopulate
                if 'refresh_documents' in self.callbacks:
                    self.documents = self.callbacks['refresh_documents']()
                    self._populate_tree()
                    if self.refresh_indicator:
                        self.refresh_indicator.show_success(len(self.documents))
        except Exception as e:
            print(f"Manual refresh error: {e}")
            if self.refresh_indicator:
                self.refresh_indicator.show_error("Error en actualización manual")
    
    def _load_remaining_documents(self) -> None:
        """
        Load remaining documents progressively for better responsiveness.
        Loads documents in chunks to avoid blocking the UI.
        """
        if self._loading_in_progress:
            return
            
        try:
            self._loading_in_progress = True
            
            # Calculate how many documents are currently shown
            currently_shown = self._initial_batch_size
            total_documents = len(self.documents)
            
            if currently_shown >= total_documents:
                self._loading_in_progress = False
                return
            
            # Calculate next batch
            next_batch_end = min(currently_shown + self._progressive_batch_size, total_documents)
            
            # Extend the batch size
            self._initial_batch_size = next_batch_end
            
            # Update the tree with new batch
            self._populate_tree()
            
            # Update status to show progress
            if hasattr(self, 'status_label'):
                self.status_label.config(
                    text=f"Cargando: {next_batch_end} de {total_documents} documentos..."
                )
            
            # Schedule next batch if there are more documents
            if next_batch_end < total_documents:
                # Use shorter delay for better perceived performance
                self.root.after(50, self._load_remaining_documents)
            else:
                # All loaded, update final status
                if hasattr(self, 'status_label'):
                    self.status_label.config(
                        text=f"Total: {total_documents} documentos"
                    )
                self._loading_in_progress = False
                
        except Exception as e:
            print(f"Error loading remaining documents: {e}")
            self._loading_in_progress = False
    
    def __del__(self):
        """Cleanup when status viewer is destroyed."""
        if self.refresh_manager:
            self.refresh_manager.stop_refresh_cycle()