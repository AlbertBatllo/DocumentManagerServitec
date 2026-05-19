import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
from typing import List, Dict, Callable, Optional, Tuple, Set
from pathlib import Path
from models.document import Document
from utils.file_manager import FileManager
from utils.folder_resolver import FolderResolver


class ExportDialog:
    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.window = None
        self.documents: List[Document] = []
        self.selected_exports: Dict[str, Dict] = {}  # doc_id -> {version, state, selected, available_files}
        self.tree = None
        self.export_callback: Optional[Callable] = None
        self.project_path: Optional[Path] = None
        # Demo/mock controls for file type availability during export selection
        # When enabled, skips filesystem detection and uses preset availability
        self.mock_mode: bool = False
        self.mock_available_files: Optional[Dict[str, bool]] = None
        
    def show(self, documents: List[Document], export_callback: Callable, project_path: Optional[Path] = None) -> None:
        """Show the export dialog with document selection."""
        self.documents = documents
        self.export_callback = export_callback
        self.project_path = project_path or Path.cwd()
        self.selected_exports = {}
        
        # Enable mock mode via environment variable for easy demo/testing
        # DOCUMENT_MANAGER_EXPORT_MOCK=1 will enable PDF+DWG as available for all rows
        try:
            import os
            self.mock_mode = os.getenv("DOCUMENT_MANAGER_EXPORT_MOCK", "0") == "1"
            # Optional comma-separated list to customize types, e.g. "pdf,dwg"
            mock_types_env = os.getenv("DOCUMENT_MANAGER_EXPORT_MOCK_TYPES")
            if mock_types_env:
                types = [t.strip().lower() for t in mock_types_env.split(",") if t.strip()]
                self.mock_available_files = {ext: (ext in types) for ext in ["pdf", "dwg", "rvt", "dwt"]}
        except Exception:
            # Fallback to no-mock if env not accessible
            self.mock_mode = False
            self.mock_available_files = None
        
        # Create window
        self.window = tk.Toplevel(self.parent)
        self.window.title("Exportar Planos Seleccionados")
        self.window.geometry("1200x800")
        self.window.minsize(1100, 700)  # Ensure minimum size
        self.window.grab_set()  # Make it modal
        
        # Add proper window protocol handling for Windows close button
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        
        # Main frame with grid layout
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Configure grid weights - DON'T expand the content frame vertically
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)  # Only the tree area should expand
        
        # Instructions (row 0)
        instructions = ttk.Label(
            main_frame, 
            text="Selecciona los planos que deseas exportar y elige la versión/estado específico para cada uno:",
            font=("TkDefaultFont", 10, "bold")
        )
        instructions.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        # Additional instructions (row 1)
        sub_instructions = ttk.Label(
            main_frame,
            text="• Clic en la casilla ☐ para seleccionar/deseleccionar documentos\n• Clic en 'Versión a Exportar' para cambiar versión/estado específico\n• Clic en 'Archivos Disponibles' para seleccionar tipos de archivo (PDF, DWG, RVT, etc.)\n• También puedes usar doble clic en cualquier fila para seleccionar/deseleccionar",
            font=("TkDefaultFont", 9),
            foreground="gray"
        )
        sub_instructions.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        # Mock mode banner (if needed)
        current_row = 2
        if self.mock_mode:
            ttk.Label(
                main_frame,
                text="Modo demo activo: disponibles PDF y DWG por fila (configurable por env).",
                font=("TkDefaultFont", 8, "italic"),
                foreground="gray"
            ).grid(row=current_row, column=0, sticky="ew", pady=(0, 6))
            current_row = 3
            main_frame.grid_rowconfigure(3, weight=1)  # Adjust weight row if banner exists
        
        # Create content frame that can expand
        content_frame = ttk.Frame(main_frame)
        content_frame.grid(row=current_row, column=0, sticky="nsew", pady=(0, 10))
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)
        
        # Create treeview with checkboxes
        self._create_document_tree(content_frame)
        
        # Buttons frame - FIXED position at bottom, non-expanding
        button_frame = ttk.Frame(main_frame, relief="solid", borderwidth=1)  # Border for debugging
        button_frame.grid(row=current_row+1, column=0, sticky="ew", pady=(20, 10), ipady=10)
        button_frame.grid_columnconfigure(0, weight=1)
        
        # Select/Deselect all buttons
        ttk.Button(button_frame, text="Seleccionar Todo", command=self._select_all).pack(side="left", padx=(10, 5))
        ttk.Button(button_frame, text="Deseleccionar Todo", command=self._deselect_all).pack(side="left", padx=5)
        
        # Export and Cancel buttons
        ttk.Button(button_frame, text="Cancelar", command=self._close).pack(side="right", padx=(5, 10))
        self.export_btn = ttk.Button(button_frame, text="Exportar Seleccionados", command=self._export_selected)
        self.export_btn.pack(side="right", padx=(5, 0))
        
        # Update export button state
        self._update_export_button()
        
    def _create_document_tree(self, parent: ttk.Frame) -> None:
        """Create the treeview for document selection."""
        # Frame for tree and scrollbar using grid
        tree_frame = ttk.Frame(parent)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        
        # Create treeview with checkbox column (fixed height to leave space for buttons)
        columns = ("id", "name", "current_version", "current_state", "available_files", "version_select")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", height=12)
        
        # Configure columns
        self.tree.heading("#0", text="✓ Seleccionar")
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Nombre")
        self.tree.heading("current_version", text="Versión Actual")
        self.tree.heading("current_state", text="Estado Actual")
        self.tree.heading("available_files", text="Archivos Disponibles (Click para editar)")
        self.tree.heading("version_select", text="Versión a Exportar (Click para cambiar)")
        
        self.tree.column("#0", width=100, minwidth=100, anchor="center")
        self.tree.column("id", width=120)
        self.tree.column("name", width=280)
        self.tree.column("current_version", width=100)
        self.tree.column("current_state", width=120)
        self.tree.column("available_files", width=200)
        self.tree.column("version_select", width=220)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Grid tree and scrollbar
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Populate tree
        self._populate_tree()
        
        # Bind events - single click for column actions, double click for selection toggle
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_double_click)
        
    def _populate_tree(self) -> None:
        """Populate the tree with documents."""
        for doc in self.documents:
            try:
                # Get all available versions for this document
                try:
                    versions = doc.get_all_versions() if hasattr(doc, 'get_all_versions') else []
                except (AttributeError, Exception):
                    versions = []
                    
                if not versions:
                    versions = [getattr(doc, 'current_version', '1.0')]
                    
                # Default selection is current version and state
                default_version = doc.current_version
                default_state = doc.current_state
                
                # Detect available file types for current version/state
                try:
                    available_files = self._detect_available_files(doc, default_version, default_state)
                    doc_id = getattr(doc, 'id', None) or getattr(doc, 'name', 'UNKNOWN')
                    print(f"[EXPORT] Detected for {doc_id} v{default_version} {default_state}: {available_files}")
                except Exception as e:
                    # If file detection fails, create default structure
                    doc_id = getattr(doc, 'id', None) or getattr(doc, 'name', 'UNKNOWN')
                    print(f"[EXPORT] ERROR detecting files for {doc_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    available_files = {"pdf": True, "dwg": False, "rvt": False, "dwt": False}
                
                # Build file types display string
                file_types = []
                for ext, available in available_files.items():
                    if available:
                        file_types.append(f"{ext.upper()} ✓")
                    else:
                        file_types.append(f"{ext.upper()} ✗")
                files_display = " ".join(file_types)
                
                # Build version display string
                version_display = f"{default_version} ({default_state})"
                
                # Get document identifier - use name as ID for compatibility
                doc_id = getattr(doc, 'id', None) or getattr(doc, 'name', 'UNKNOWN')
                
                # Insert item with checkbox in first column
                item_id = self.tree.insert("", "end", text="☐", values=(
                    doc_id,
                    doc.name,
                    doc.current_version,
                    doc.current_state,
                    files_display,
                    version_display
                ))
                
                # Store selection data
                self.selected_exports[doc_id] = {
                    "selected": False,
                    "version": default_version,
                    "state": default_state,
                    "available_files": available_files.copy(),  # All files selected by default
                    "available_versions": versions,
                    "document": doc,
                    "tree_item": item_id
                }
            except Exception as e:
                # If there's any error with this document, create a minimal entry
                item_id = self.tree.insert("", "end", text="☐", values=(
                    getattr(doc, 'id', 'UNKNOWN'),
                    getattr(doc, 'name', 'UNKNOWN'),
                    getattr(doc, 'current_version', '1.0'),
                    getattr(doc, 'current_state', 'S0'),
                    "PDF ✓ DWG ✗ RVT ✗ DWT ✗",
                    f"{getattr(doc, 'current_version', '1.0')} ({getattr(doc, 'current_state', 'S0')})"
                ))
    
    def _on_tree_click(self, event) -> None:
        """Handle tree click events."""
        item = self.tree.identify("item", event.x, event.y)
        column = self.tree.identify("column", event.x, event.y)
        
        print(f"DEBUG: Tree click - item: {item}, column: {column}")
        
        if item and column:
            # Handle checkbox column click (column #0)
            if column == "#0":
                print(f"DEBUG: Checkbox column clicked for item {item}")
                # Toggle selection for checkbox click
                self._toggle_selection_by_item(item)
                return
            
            # Get column index to compare with our column layout
            try:
                col_index = int(column.replace('#', '')) - 1 if column.startswith('#') else -1
                column_names = ("id", "name", "current_version", "current_state", "available_files", "version_select")
                
                print(f"DEBUG: Column index: {col_index}, Column names: {column_names}")
                
                if col_index == 4:  # Available files column (index 4)
                    print(f"DEBUG: Showing file type selector for item {item}")
                    self._show_file_type_selector(item)
                    return
                elif col_index == 5:  # Version select column (index 5)
                    print(f"DEBUG: Showing version selector for item {item}")
                    self._show_version_selector(item)
                    return
            except (ValueError, IndexError) as e:
                print(f"DEBUG: Error parsing column: {e}")
        
        # For other columns, do nothing on single click
    
    def _on_double_click(self, event) -> None:
        """Handle double-click to toggle selection."""
        self._toggle_selection(event)
    
    def _toggle_selection(self, event) -> None:
        """Toggle document selection."""
        # Get the item that was clicked
        clicked_item = self.tree.identify("item", event.x, event.y)
        if not clicked_item:
            # Fallback to selected item if no item was clicked
            clicked_item = self.tree.selection()[0] if self.tree.selection() else None
            
        if not clicked_item:
            return
        
        print(f"DEBUG: Toggling selection for item: {clicked_item}")
            
        # Find document by tree item
        doc_id = None
        for d_id, data in self.selected_exports.items():
            if data["tree_item"] == clicked_item:
                doc_id = d_id
                break
                
        if doc_id:
            # Toggle selection
            old_state = self.selected_exports[doc_id]["selected"]
            self.selected_exports[doc_id]["selected"] = not old_state
            print(f"DEBUG: Toggled {doc_id} selection: {old_state} -> {self.selected_exports[doc_id]['selected']}")
            self._update_tree_display()
            self._update_export_button()
        else:
            print(f"DEBUG: Could not find doc_id for tree item {clicked_item}")
    
    def _toggle_selection_by_item(self, tree_item) -> None:
        """Toggle document selection by tree item."""
        # Find document by tree item
        doc_id = None
        for d_id, data in self.selected_exports.items():
            if data["tree_item"] == tree_item:
                doc_id = d_id
                break
                
        if doc_id:
            # Toggle selection
            old_state = self.selected_exports[doc_id]["selected"]
            self.selected_exports[doc_id]["selected"] = not old_state
            print(f"DEBUG: Toggled {doc_id} selection: {old_state} -> {self.selected_exports[doc_id]['selected']}")
            self._update_tree_display()
            self._update_export_button()
        else:
            print(f"DEBUG: Could not find doc_id for tree item {tree_item}")
    
    def _show_version_selector(self, item) -> None:
        """Show version selector for a document."""
        # Find document by tree item
        doc_id = None
        for d_id, data in self.selected_exports.items():
            if data["tree_item"] == item:
                doc_id = d_id
                break
                
        if not doc_id:
            return
            
        doc_data = self.selected_exports[doc_id]
        document = doc_data["document"]
        
        # Create version selection dialog
        version_window = tk.Toplevel(self.window)
        version_window.title(f"Seleccionar Versión - {doc_id}")
        version_window.geometry("400x300")
        version_window.grab_set()
        
        # Main frame
        frame = ttk.Frame(version_window, padding="10")
        frame.pack(fill="both", expand=True)
        
        ttk.Label(
            frame, 
            text=f"Selecciona la versión a exportar para {doc_id}:",
            font=("TkDefaultFont", 10, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        ttk.Label(
            frame,
            text="Elige la versión y estado específico que deseas exportar:",
            font=("TkDefaultFont", 9),
            foreground="gray"
        ).pack(anchor="w", pady=(0, 10))
        
        # Get version history - handle cases where method doesn't exist
        try:
            history = document.get_version_history()
        except (AttributeError, Exception) as e:
            print(f"DEBUG: Could not get version history for {doc_id}: {e}")
            # Fallback to current version only
            history = [{
                'version': document.current_version if hasattr(document, 'current_version') else '1.0',
                'state': document.current_state if hasattr(document, 'current_state') else 'S0',
                'date': getattr(document, 'creation_date', '2023-01-01T00:00:00')
            }]
        
        # Create listbox for version selection
        version_var = tk.StringVar()
        
        for entry in history:
            version_text = f"{entry['version']} - {entry['state']} ({entry['date'][:10]})"
            radio = ttk.Radiobutton(
                frame, 
                text=version_text,
                variable=version_var,
                value=f"{entry['version']}|{entry['state']}"
            )
            radio.pack(anchor="w", pady=2)
            
            # Set default selection
            if entry['version'] == doc_data['version'] and entry['state'] == doc_data['state']:
                radio.invoke()
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        def apply_selection():
            selection = version_var.get()
            if selection:
                version, state = selection.split("|")
                doc_data["version"] = version
                doc_data["state"] = state
                self._update_tree_display()
                version_window.destroy()
                
        def cancel_selection():
            version_window.destroy()
            
        ttk.Button(btn_frame, text="Aplicar", command=apply_selection).pack(side="right", padx=(5, 0))
        ttk.Button(btn_frame, text="Cancelar", command=cancel_selection).pack(side="right")
    
    def _show_file_type_selector(self, item) -> None:
        """Show file type selector for a document."""
        # Find document by tree item
        doc_id = None
        for d_id, data in self.selected_exports.items():
            if data["tree_item"] == item:
                doc_id = d_id
                break
                
        if not doc_id:
            return
            
        doc_data = self.selected_exports[doc_id]
        
        # Create file type selection dialog
        file_window = tk.Toplevel(self.window)
        file_window.title(f"Seleccionar Tipos de Archivo - {doc_id}")
        file_window.geometry("350x250")
        file_window.grab_set()
        
        # Main frame
        frame = ttk.Frame(file_window, padding="10")
        frame.pack(fill="both", expand=True)
        
        ttk.Label(
            frame, 
            text=f"Selecciona los tipos de archivo a exportar para {doc_id}:",
            font=("TkDefaultFont", 10, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        ttk.Label(
            frame,
            text="Marca los tipos de archivo que deseas incluir en la exportación:",
            font=("TkDefaultFont", 9),
            foreground="gray"
        ).pack(anchor="w", pady=(0, 10))
        
        # File type checkboxes
        file_vars = {}
        available_files = doc_data.get("available_files", {})
        
        for ext in ["pdf", "dwg", "rvt", "dwt"]:
            var = tk.BooleanVar()
            file_vars[ext] = var
            
            # Set initial state - checked if file exists and is currently selected
            is_available = available_files.get(ext, False)
            var.set(is_available)  # Default: select all available files
            
            # Create checkbox
            checkbox = ttk.Checkbutton(
                frame,
                text=f"{ext.upper()} {'(disponible)' if is_available else '(no disponible)'}",
                variable=var,
                state="normal" if is_available else "disabled"
            )
            checkbox.pack(anchor="w", pady=2)
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        def apply_file_selection():
            # Update available_files with selected state
            for ext, var in file_vars.items():
                doc_data["available_files"][ext] = var.get() and available_files.get(ext, False)
            self._update_tree_display()
            file_window.destroy()
                
        def cancel_file_selection():
            file_window.destroy()
            
        ttk.Button(btn_frame, text="Aplicar", command=apply_file_selection).pack(side="right", padx=(5, 0))
        ttk.Button(btn_frame, text="Cancelar", command=cancel_file_selection).pack(side="right")
    
    def _update_tree_display(self) -> None:
        """Update tree display with current selections."""
        for doc_id, data in self.selected_exports.items():
            item = data["tree_item"]
            
            # Build file types display string
            available_files = data.get("available_files", {})
            file_types = []
            for ext, selected in available_files.items():
                if selected:
                    file_types.append(f"{ext.upper()} ✓")
                else:
                    file_types.append(f"{ext.upper()} ✗")
            files_display = " ".join(file_types)
            
            version_display = f"{data['version']} ({data['state']})"
            
            # Update the tree item
            current_values = list(self.tree.item(item, "values"))
            current_values[4] = files_display  # Available files column
            current_values[5] = version_display  # Version select column
            self.tree.item(item, values=current_values)
            
            # Update checkbox and appearance based on selection
            if data["selected"]:
                self.tree.item(item, text="☑", tags=("selected",))
            else:
                self.tree.item(item, text="☐", tags=())
        
        # Configure tags
        self.tree.tag_configure("selected", background="lightblue")
    
    def _select_all(self) -> None:
        """Select all documents."""
        print(f"DEBUG: Selecting all documents ({len(self.selected_exports)} total)")
        for doc_id in self.selected_exports:
            self.selected_exports[doc_id]["selected"] = True
        self._update_tree_display()
        self._update_export_button()
    
    def _deselect_all(self) -> None:
        """Deselect all documents."""
        print(f"DEBUG: Deselecting all documents ({len(self.selected_exports)} total)")
        for doc_id in self.selected_exports:
            self.selected_exports[doc_id]["selected"] = False
        self._update_tree_display()
        self._update_export_button()
    
    def _update_export_button(self) -> None:
        """Update export button state based on selections."""
        try:
            has_selections = any(data.get("selected", False) for data in self.selected_exports.values())
            selected_count = sum(1 for data in self.selected_exports.values() if data.get("selected", False))
            
            # Update button text to show selection count
            button_text = f"Exportar Seleccionados ({selected_count})" if selected_count > 0 else "Exportar Seleccionados"
            
            if hasattr(self, 'export_btn') and self.export_btn:
                self.export_btn.config(
                    state="normal" if has_selections else "disabled",
                    text=button_text
                )
                print(f"DEBUG: Export button updated - {selected_count} selected, state: {'enabled' if has_selections else 'disabled'}")
        except Exception as e:
            print(f"DEBUG: Error updating export button: {e}")
    
    def _export_selected(self) -> None:
        """Export selected documents."""
        selected_docs = {
            doc_id: data for doc_id, data in self.selected_exports.items() 
            if data["selected"]
        }
        
        if not selected_docs:
            messagebox.showwarning("Advertencia", "No hay documentos seleccionados para exportar.")
            return
        
        # Ask user for export directory
        export_dir = filedialog.askdirectory(
            title="Selecciona la carpeta de destino para exportar los planos",
            parent=self.window
        )
        
        if not export_dir:
            return
            
        try:
            # Call export callback
            if self.export_callback:
                self.export_callback(selected_docs, export_dir)
            
            messagebox.showinfo(
                "Exportación Completada", 
                f"Se exportaron {len(selected_docs)} planos a:\n{export_dir}"
            )
            self._close()
            
        except Exception as e:
            messagebox.showerror("Error de Exportación", f"Error al exportar: {str(e)}")
    
    def _close(self) -> None:
        """Close the dialog."""
        if self.window:
            self.window.destroy()
    
    def _detect_available_files(self, document: Document, version: str, state: str) -> Dict[str, bool]:
        """Detect available file types for a specific document/version/state."""
        # Mock mode short-circuit for demo/use without filesystem dependencies
        if getattr(self, "mock_mode", False):
            if getattr(self, "mock_available_files", None):
                return dict(self.mock_available_files)  # copy
            return {"pdf": True, "dwg": True, "rvt": False, "dwt": False}

        available_files = {"pdf": False, "dwg": False, "rvt": False, "dwt": False}
        
        try:
            from pathlib import Path
            
            # Convert project_path to Path object if it's a string
            if not self.project_path:
                available_files["pdf"] = True
                return available_files
                
            project_path = Path(self.project_path) if isinstance(self.project_path, str) else self.project_path
            planos_folder = FolderResolver.resolve_planos(project_path)
            
            if not planos_folder.exists():
                available_files["pdf"] = True
                return available_files
            
            # Look for files matching: {doc_id}_{name}_{version}_{state}.{ext}
            # Example: PRJ-001-PL-001_Plano Estructural Torre A_v2.0_A.pdf
            doc_id = getattr(document, 'id', None) or getattr(document, 'name', 'UNKNOWN')
            for ext in ["pdf", "dwg", "rvt", "dwt"]:
                pattern = f"{doc_id}_*_{version}_{state}.{ext}"
                files = list(planos_folder.glob(pattern))
                available_files[ext] = len(files) > 0
                            
        except Exception as e:
            # If anything fails, default to PDF available only
            import traceback
            traceback.print_exc()
            available_files = {"pdf": True, "dwg": False, "rvt": False, "dwt": False}
        
        return available_files