import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Callable, Optional
from models.document import Document
from config.settings import StatusConfig
from .base_view import BaseView


class DeleteFilesView(BaseView):
    def __init__(self, root: tk.Tk, status_config: StatusConfig, doc_type: str):
        super().__init__(root)
        self.status_config = status_config
        self.doc_type = doc_type
        self.doc_type_display = "Planos" if doc_type == "planos" else "Certificaciones"
        self.doc_type_singular = "plano" if doc_type == "planos" else "certificación"
        self.tree = None
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.documents: List[Document] = []
        self.version_entries = []  # All version/state entries across all documents
        self.selected_entries = set()  # Track selected entries for deletion (doc_id:version:state)
        
    def show(self, documents: List[Document], callbacks: dict, user_name: str = "") -> None:
        """Show the delete files window."""
        self.documents = documents
        self.callbacks = callbacks
        
        # Clear window and set size
        self.clear_window()
        self.set_window_size(800, 650)
        
        # Add notification widget if user and callbacks available
        if user_name and 'get_notification_data' in callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: callbacks.get('get_notification_data')(user_name),
                mark_read_callback=callbacks.get('mark_notification_as_read'),
                navigate_callback=callbacks.get('navigate_to_document'),
                current_user=user_name,
                delete_callback=callbacks.get('delete_notification')
            )
        
        # Header
        self.create_header(self.root, f"Eliminar Versiones/Estados - {self.doc_type_display}")
        
        # Create main container structure
        # Content container - expandable
        main_content = ttk.Frame(self.root, padding="8")
        main_content.pack(fill="both", expand=True)
        
        # Bottom container - fixed at bottom for buttons
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(side="bottom", fill="x")
        
        # Info frame at the top
        info_frame = ttk.Frame(main_content)
        info_frame.pack(fill="x", pady=(0, 10))
        
        info_label = ttk.Label(
            info_frame,
            text="📋 Esta vista muestra TODAS las versiones y estados de cada documento. Seleccione las versiones/estados específicos que desea eliminar.",
            font=("Arial", 10),
            foreground="blue"
        )
        info_label.pack()
        
        # Warning frame
        warning_frame = ttk.Frame(main_content)
        warning_frame.pack(fill="x", pady=(5, 10))
        
        warning_label = ttk.Label(
            warning_frame,
            text="ℹ️ Los archivos eliminados se moverán a la carpeta _PAPELERA del proyecto y se podrán recuperar manualmente",
            font=("Arial", 11),
            foreground="#0a5"
        )
        warning_label.pack()
        
        # Top frame for filters
        top_frame = ttk.Frame(main_content)
        top_frame.pack(fill="x", pady=(0, 10))
        top_frame.columnconfigure(0, weight=1)
        
        # Filter frame
        filter_frame = ttk.LabelFrame(top_frame, text="Filtros", padding=8)
        filter_frame.pack(fill="x")
        
        # Search by Name
        ttk.Label(filter_frame, text="Buscar por Nombre:").grid(row=0, column=0, padx=5, sticky="w")
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.grid(row=0, column=1, padx=5, sticky="w")
        search_entry.bind('<KeyRelease>', lambda e: self._apply_filters())
        
        # Filter by status
        ttk.Label(filter_frame, text="Filtrar por Estado:").grid(row=0, column=2, padx=(20, 5), sticky="w")
        filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            values=["Todos"] + list(self.status_config.STATE_MAP.values()),
            state="readonly",
            width=20
        )
        filter_combo.set("Todos")
        filter_combo.grid(row=0, column=3, padx=5, sticky="w")
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_filters())
        
        # Clear filters button
        ttk.Button(
            filter_frame,
            text="Limpiar Filtros",
            command=self._clear_filters
        ).grid(row=0, column=4, padx=(20, 5))
        
        # Selection controls
        selection_frame = ttk.Frame(main_content)
        selection_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(
            selection_frame,
            text="Seleccionar Todo",
            command=self._select_all
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            selection_frame,
            text="Deseleccionar Todo",
            command=self._deselect_all
        ).pack(side="left", padx=(0, 10))
        
        # Selected count label
        self.selection_label = ttk.Label(
            selection_frame,
            text="Documentos seleccionados: 0",
            font=("Arial", 10, "bold")
        )
        self.selection_label.pack(side="right")
        
        # Create treeview for file list
        tree_frame = ttk.Frame(main_content)
        tree_frame.pack(fill="both", expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview with checkboxes - updated to show individual version/state entries
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("Seleccionar", "Nombre", "Versión", "Estado", "Fecha", "Autor", "Archivo"),
            show="tree headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )

        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        # Configure columns (removed ID column)
        self.tree.column("#0", width=0, stretch=False)
        self.tree.column("Seleccionar", width=80, anchor="center")
        self.tree.column("Nombre", width=220)
        self.tree.column("Versión", width=70, anchor="center")
        self.tree.column("Estado", width=70, anchor="center")
        self.tree.column("Fecha", width=120, anchor="center")
        self.tree.column("Autor", width=100, anchor="center")
        self.tree.column("Archivo", width=200)

        # Headers
        self.tree.heading("Seleccionar", text="☐")
        self.tree.heading("Nombre", text="Nombre")
        self.tree.heading("Versión", text="Versión")
        self.tree.heading("Estado", text="Estado")
        self.tree.heading("Fecha", text="Fecha")
        self.tree.heading("Autor", text="Autor")
        self.tree.heading("Archivo", text="Archivo")
        
        # Configure tags for colors
        for state_code, color in self.status_config.STATUS_COLORS.items():
            self.tree.tag_configure(state_code, foreground=color)
        
        # Pack treeview and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        # Bind click events
        self.tree.bind('<Button-1>', self._on_tree_click)
        self.tree.bind('<Double-Button-1>', self._on_double_click)
        
        # Button frame - moved to bottom container for always-visible buttons
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(fill="x")
        
        # Delete button
        self.delete_button = ttk.Button(
            button_frame,
            text="🗑️ Eliminar Seleccionados",
            command=self._delete_selected_files,
            state="disabled"
        )
        self.delete_button.pack(side="left", padx=5)
        
        # Back button
        ttk.Button(
            button_frame,
            text="Volver",
            command=callbacks['back']
        ).pack(side="right", padx=5)
        
        # Status bar
        self.status_label = ttk.Label(
            main_content,
            text=f"Total: {len(documents)} documentos",
            relief="sunken"
        )
        self.status_label.pack(fill="x", pady=(5, 0))
        
        # Populate tree
        self._populate_tree()

    def _populate_tree(self) -> None:
        """Populate the treeview with filtered version/state entries."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Clear selection tracking
        self.selected_entries.clear()
        
        # Build list of all version/state entries
        self.version_entries = []
        for doc in self.documents:
            for entry in doc.entries:
                # Generate filename for this specific version/state using correct FileManager pattern
                from utils.file_manager import FileManager
                # Use FileManager.generate_filename for consistency with file creation
                # Default to PDF extension, but we'll improve this later with proper extension detection
                filename = FileManager.generate_filename(doc.id, doc.name, entry.version, ".pdf")
                
                # Create entry dict with all needed info (use name as key, not id)
                version_entry = {
                    "doc_id": doc.id,
                    "doc_name": doc.name,
                    "version": entry.version,
                    "state": entry.state,
                    "date": entry.timestamp,
                    "author": entry.author,
                    "filename": filename,
                    "notes": entry.notes,
                    "entry_key": f"{doc.name}:{entry.version}:{entry.state}"  # Unique identifier using name
                }
                self.version_entries.append(version_entry)
        
        # Get filters
        search_text = self.search_var.get().lower()
        filter_status = self.filter_var.get()

        # Filter entries
        filtered_entries = []
        for entry in self.version_entries:
            # Apply name filter (search in doc_name)
            if search_text and search_text not in entry["doc_name"].lower():
                continue
            
            # Apply status filter
            if filter_status != "Todos":
                status_text = self.status_config.STATE_MAP.get(entry["state"], entry["state"])
                if status_text != filter_status:
                    continue
            
            filtered_entries.append(entry)
        
        # Sort by ID, then by timestamp (newest first)
        filtered_entries.sort(key=lambda x: (x["doc_id"], x["date"]), reverse=True)
        
        # Add to tree
        for entry in filtered_entries:
            # Format date for display
            try:
                from datetime import datetime
                date_obj = datetime.fromisoformat(entry["date"].replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError, KeyError, IndexError):
                # Date parsing may fail with invalid formats or missing data
                formatted_date = entry["date"][:16]  # Fallback to first 16 chars
            
            # Insert item (removed ID column)
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    "☐",  # Checkbox placeholder
                    entry["doc_name"],
                    entry["version"],
                    entry["state"],
                    formatted_date,
                    entry["author"],
                    entry["filename"]
                ),
                tags=(entry["state"],)
            )
        
        # Update status bar and selection
        total_entries = len(self.version_entries)
        self.status_label.config(text=f"Mostrando: {len(filtered_entries)} de {total_entries} versiones/estados")
        self._update_selection_display()

    def _on_tree_click(self, event):
        """Handle tree click for checkbox selection."""
        item = self.tree.identify('item', event.x, event.y)
        column = self.tree.identify('column', event.x, event.y)
        
        # Check if clicked on checkbox column
        if item and column == '#1':  # Checkbox column
            self._toggle_selection(item)

    def _on_double_click(self, event):
        """Handle double-click to open file location."""
        item = self.tree.selection()
        if item:
            values = self.tree.item(item[0])['values']
            filename = values[6]  # Filename column (after removing ID)
            if 'open_file_location' in self.callbacks:
                try:
                    self.callbacks['open_file_location'](filename)
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo abrir la ubicación del archivo: {e}")

    def _toggle_selection(self, item):
        """Toggle selection of an item."""
        values = self.tree.item(item)['values']
        doc_name = values[1]  # Nombre column
        version = values[2]   # Version column
        state = values[3]     # State column
        entry_key = f"{doc_name}:{version}:{state}"
        
        if entry_key in self.selected_entries:
            # Deselect
            self.selected_entries.remove(entry_key)
            self.tree.set(item, "Seleccionar", "☐")
        else:
            # Select
            self.selected_entries.add(entry_key)
            self.tree.set(item, "Seleccionar", "☑")
        
        self._update_selection_display()

    def _select_all(self):
        """Select all visible entries."""
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            doc_name = values[1]
            version = values[2]
            state = values[3]
            entry_key = f"{doc_name}:{version}:{state}"
            self.selected_entries.add(entry_key)
            self.tree.set(item, "Seleccionar", "☑")
        self._update_selection_display()

    def _deselect_all(self):
        """Deselect all entries."""
        for item in self.tree.get_children():
            self.tree.set(item, "Seleccionar", "☐")
        self.selected_entries.clear()
        self._update_selection_display()

    def _update_selection_display(self):
        """Update the selection count and delete button state."""
        count = len(self.selected_entries)
        self.selection_label.config(text=f"Versiones/Estados seleccionados: {count}")
        
        # Enable/disable delete button
        if count > 0:
            self.delete_button.config(state="normal")
        else:
            self.delete_button.config(state="disabled")

    def _delete_selected_files(self):
        """Delete the selected files after confirmation."""
        if not self.selected_entries:
            messagebox.showwarning("Advertencia", "No hay versiones/estados seleccionados para eliminar.")
            return
        
        # Get selected entry details for confirmation
        selected_entry_details = []
        for entry_key in self.selected_entries:
            # Find the corresponding entry data
            for entry in self.version_entries:
                if entry["entry_key"] == entry_key:
                    selected_entry_details.append(entry)
                    break
        
        # Show confirmation dialog
        entry_list = "\n".join([
            f"• {entry['doc_id']} - {entry['doc_name']} (v{entry['version']} - {entry['state']}) - {entry['filename']}"
            for entry in selected_entry_details
        ])
        confirmation_text = (
            f"¿Está seguro de que desea eliminar {len(selected_entry_details)} versión(es)/estado(s)?\n\n"
            f"Los archivos se moverán a la carpeta _PAPELERA del proyecto.\n"
            f"Podrá recuperarlos moviéndolos manualmente de vuelta.\n\n"
            f"Versiones/Estados a eliminar:\n{entry_list}\n\n"
            f"Escriba 'ELIMINAR' para confirmar:"
        )
        
        # Custom confirmation dialog
        confirm_window = tk.Toplevel(self.root)
        confirm_window.title("Confirmar Eliminación")
        confirm_window.geometry("600x400")
        confirm_window.transient(self.root)
        confirm_window.grab_set()
        
        # Main frame
        main_content = ttk.Frame(confirm_window, padding="20")
        main_content.pack(fill="both", expand=True)
        
        # Info label
        warning_label = ttk.Label(
            main_content,
            text="🗑️ ELIMINAR (mover a _PAPELERA) 🗑️",
            font=("Arial", 14, "bold"),
            foreground="#0a5"
        )
        warning_label.pack(pady=(0, 10))
        
        # Confirmation text
        text_widget = tk.Text(main_content, height=15, width=70, wrap=tk.WORD)
        text_widget.insert("1.0", confirmation_text)
        text_widget.config(state="disabled")
        text_widget.pack(fill="both", expand=True, pady=(0, 10))
        
        # Confirmation entry
        ttk.Label(main_content, text="Escriba 'ELIMINAR' para confirmar:").pack(anchor="w")
        confirm_var = tk.StringVar()
        confirm_entry = ttk.Entry(main_content, textvariable=confirm_var, width=20)
        confirm_entry.pack(anchor="w", pady=(5, 10))
        confirm_entry.focus()
        
        # Buttons
        button_frame = ttk.Frame(main_content)
        button_frame.pack(fill="x")
        
        def confirm_deletion():
            if confirm_var.get().strip().upper() == "ELIMINAR":
                confirm_window.destroy()
                self._perform_deletion(selected_entry_details)
            else:
                messagebox.showerror("Error", "Debe escribir 'ELIMINAR' exactamente para confirmar.")
        
        ttk.Button(
            button_frame,
            text="Eliminar",
            command=confirm_deletion
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            button_frame,
            text="Cancelar",
            command=confirm_window.destroy
        ).pack(side="left")
        
        # Bind Enter key
        confirm_entry.bind("<Return>", lambda e: confirm_deletion())

    def _perform_deletion(self, entries_to_delete):
        """Perform the actual deletion of specific version/state entries."""
        if 'delete_entries' in self.callbacks:
            try:
                # Convert entries to the format expected by the controller (use doc_name as doc_id)
                entry_specs = []
                for entry in entries_to_delete:
                    entry_specs.append({
                        'doc_id': entry['doc_name'],  # Use name as identifier
                        'version': entry['version'],
                        'state': entry['state'],
                        'filename': entry['filename']
                    })
                
                result = self.callbacks['delete_entries'](entry_specs)
                messagebox.showinfo("Éxito", result)
                
                # Refresh the document list
                if 'refresh_documents' in self.callbacks:
                    self.documents = self.callbacks['refresh_documents']()
                    self._populate_tree()
                else:
                    # Fallback: refresh the tree
                    self._populate_tree()
                    
            except Exception as e:
                messagebox.showerror("Error", f"Error al eliminar versiones/estados: {str(e)}")

    def _apply_filters(self) -> None:
        """Apply search and filter criteria."""
        self._populate_tree()

    def _clear_filters(self) -> None:
        """Clear all filters."""
        self.search_var.set("")
        self.filter_var.set("Todos")
        self._populate_tree()