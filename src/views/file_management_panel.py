"""
File Management Panel for Planos
Allows viewing, replacing, and adding individual files for a plano entry without changing version/state.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Dict, Callable, Optional, Tuple
import json
from utils.folder_resolver import FolderResolver
import shutil
from datetime import datetime


class FileManagementPanel:
    """
    Panel for managing files associated with a specific plano entry.
    Allows individual file replacement and addition without version/state changes.
    """

    def __init__(self, parent: tk.Widget, plano_document, callbacks: Dict[str, Callable],
                 on_close: Callable = None):
        """
        Initialize the file management panel.

        Args:
            parent: Parent tkinter widget
            plano_document: The PlanoDocument object being managed
            callbacks: Dictionary of callback functions:
                - get_current_files: Function to get current file list
                - replace_file: Function to replace a specific file
                - add_file: Function to add a new file
                - get_project_path: Function to get project base path
                - get_available_dwgs: Function to get list of DWGs in CAD/Working
                - set_associated_dwg: Function to set the associated DWG for document
            on_close: Optional callback invoked when the panel is closed
        """
        self.parent = parent
        self.plano_document = plano_document
        self.callbacks = callbacks
        self.on_close = on_close
        self.window = None
        self.current_files = []
        self.file_tree = None
        self.associated_dwg_label = None
        
    def _has_any_dwg(self) -> bool:
        """Check if the entry has any DWG file (either associated or in file_paths)."""
        # Check associated_dwg
        associated_dwg = getattr(self.plano_document, 'associated_dwg', '') or ''
        if associated_dwg:
            return True

        # Check file_paths for DWG files
        file_paths = getattr(self.plano_document, 'file_paths', []) or []
        if isinstance(file_paths, str):
            try:
                import json
                file_paths = json.loads(file_paths)
            except:
                file_paths = []

        for fp in file_paths:
            if fp and fp.lower().endswith('.dwg'):
                return True

        return False

    def show(self):
        """Show the file management panel in a new window."""
        # Create modal window
        self.window = tk.Toplevel(self.parent)
        self.window.title(f"Gestión de Archivos - {self.plano_document.name}")
        self.window.geometry("900x600")
        self.window.transient(self.parent)
        self.window.grab_set()
        
        # Center window
        self.window.geometry("+{}+{}".format(
            int(self.window.winfo_screenwidth()/2 - 450),
            int(self.window.winfo_screenheight()/2 - 300)
        ))
        
        # Handle window close via X button and Escape key
        self.window.protocol("WM_DELETE_WINDOW", self._close_window)
        self.window.bind("<Escape>", lambda e: self._close_window())

        # Create UI components
        self._create_header()
        self._create_dwg_association_section()
        self._create_file_list_section()
        self._create_action_buttons()
        self._create_bottom_buttons()

        # Load current files
        self._refresh_file_list()
    
    def _create_header(self):
        """Create header section with document info."""
        header_frame = ttk.Frame(self.window, padding="15")
        header_frame.pack(fill="x")
        
        # Title
        title_label = ttk.Label(
            header_frame,
            text=f"📁 Gestión de Archivos",
            font=("Arial", 16, "bold"),
            foreground="#2E5984"
        )
        title_label.pack(anchor="w")
        
        # Document info
        info_frame = ttk.Frame(header_frame)
        info_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(
            info_frame,
            text=f"Documento: {self.plano_document.name}",
            font=("Arial", 12, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            info_frame,
            text=f"Versión: {self.plano_document.current_version} | Estado: {self.plano_document.current_state}",
            font=("Arial", 10),
            foreground="#666666"
        ).pack(anchor="w")
        
        # Warning message
        warning_frame = ttk.Frame(header_frame)
        warning_frame.pack(fill="x", pady=(10, 0))
        
        warning_label = ttk.Label(
            warning_frame,
            text="Los cambios afectarán únicamente el contenido de los archivos. La versión y estado permanecerán sin cambios.",
            font=("Arial", 9),
            foreground="#FF8C00",
            wraplength=800
        )
        warning_label.pack(anchor="w")

    def _create_dwg_association_section(self):
        """Create section for DWG file association."""
        dwg_frame = ttk.LabelFrame(self.window, text="Archivo DWG Asociado", padding="10")
        dwg_frame.pack(fill="x", padx=15, pady=(0, 10))

        # Current association display
        info_frame = ttk.Frame(dwg_frame)
        info_frame.pack(fill="x")

        # Get current associated DWG and check for any existing DWG
        associated_dwg = getattr(self.plano_document, 'associated_dwg', '') or ''
        has_any_dwg = self._has_any_dwg()

        # Display current association
        ttk.Label(info_frame, text="DWG:", font=("Arial", 10, "bold")).pack(side="left")

        if associated_dwg:
            dwg_name = Path(associated_dwg).name if associated_dwg else "Sin asociar"
            self.associated_dwg_label = ttk.Label(
                info_frame,
                text=f" {dwg_name}",
                font=("Arial", 10),
                foreground="#2E5984"
            )
        else:
            self.associated_dwg_label = ttk.Label(
                info_frame,
                text=" Sin asociar - Haga clic en 'Asociar DWG' para vincular un archivo",
                font=("Arial", 10, "italic"),
                foreground="#888888"
            )
        self.associated_dwg_label.pack(side="left", padx=(5, 0))

        # Buttons frame
        btn_frame = ttk.Frame(dwg_frame)
        btn_frame.pack(fill="x", pady=(10, 0))

        # Disable "Asociar DWG" if entry already has ANY DWG (associated or in file_paths)
        self.btn_associate_dwg = ttk.Button(
            btn_frame,
            text="Asociar DWG",
            command=self._associate_dwg,
            state="disabled" if has_any_dwg else "normal"
        )
        self.btn_associate_dwg.pack(side="left", padx=(0, 10))

        self.btn_clear_dwg = ttk.Button(
            btn_frame,
            text="Quitar Asociación",
            command=self._clear_dwg_association,
            state="normal" if associated_dwg else "disabled"
        )
        self.btn_clear_dwg.pack(side="left", padx=(0, 10))

        if associated_dwg:
            self.btn_open_dwg = ttk.Button(
                btn_frame,
                text="Abrir DWG",
                command=self._open_associated_dwg
            )
            self.btn_open_dwg.pack(side="left")

        # Help text
        help_label = ttk.Label(
            dwg_frame,
            text="Un mismo archivo DWG puede contener múltiples layouts. Asocie el DWG que contiene el layout de este plano.",
            font=("Arial", 8),
            foreground="#666666",
            wraplength=850
        )
        help_label.pack(anchor="w", pady=(5, 0))

    def _associate_dwg(self):
        """Show dialog to associate a DWG file."""
        # Get available DWGs from CAD/Working folder
        if 'get_available_dwgs' in self.callbacks:
            available_dwgs = self.callbacks['get_available_dwgs']()
        else:
            messagebox.showerror("Error", "Funcionalidad no disponible.", parent=self.window)
            return

        if not available_dwgs:
            messagebox.showinfo(
                "Sin archivos DWG",
                "No se encontraron archivos DWG en la carpeta CAD/Working.\n\n"
                "Asegúrese de que los archivos DWG estén en la ubicación correcta.",
                parent=self.window
            )
            return

        # Create selection dialog
        dialog = tk.Toplevel(self.window)
        dialog.title("Seleccionar DWG")
        dialog.geometry("500x400")
        dialog.transient(self.window)
        dialog.grab_set()

        # Center dialog
        dialog.geometry("+{}+{}".format(
            int(dialog.winfo_screenwidth()/2 - 250),
            int(dialog.winfo_screenheight()/2 - 200)
        ))

        ttk.Label(
            dialog,
            text="Seleccione el archivo DWG a asociar:",
            font=("Arial", 11)
        ).pack(pady=(15, 10))

        # Listbox with scrollbar
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Arial", 10))
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        # Populate listbox with DWG names
        for dwg_path in available_dwgs:
            listbox.insert(tk.END, Path(dwg_path).name)

        # Store paths for selection
        dwg_paths = available_dwgs

        def on_select():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("Selección requerida", "Por favor, seleccione un archivo DWG.", parent=dialog)
                return

            selected_path = dwg_paths[selection[0]]

            # Set the association
            if 'set_associated_dwg' in self.callbacks:
                success, message = self.callbacks['set_associated_dwg'](
                    self.plano_document.name,
                    selected_path
                )

                if success:
                    # Update the label
                    self.associated_dwg_label.config(
                        text=f" {Path(selected_path).name}",
                        font=("Arial", 10),
                        foreground="#2E5984"
                    )
                    # Update button states: disable associate and add DWG, enable clear
                    self.btn_associate_dwg.config(state="disabled")
                    self.btn_add_dwg.config(state="disabled")  # One DWG per entry
                    self.btn_clear_dwg.config(state="normal")
                    # Update the document object
                    self.plano_document.associated_dwg = selected_path
                    dialog.destroy()
                    messagebox.showinfo("Éxito", message, parent=self.window)
                else:
                    messagebox.showerror("Error", message, parent=dialog)
            else:
                messagebox.showerror("Error", "Funcionalidad no disponible.", parent=dialog)

        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="Asociar", command=on_select).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side="left", padx=5)

        # Double-click to select
        listbox.bind("<Double-1>", lambda e: on_select())

    def _clear_dwg_association(self):
        """Clear the DWG association."""
        if messagebox.askyesno(
            "Confirmar",
            f"¿Está seguro de quitar la asociación del DWG para '{self.plano_document.name}'?",
            parent=self.window
        ):
            if 'set_associated_dwg' in self.callbacks:
                success, message = self.callbacks['set_associated_dwg'](
                    self.plano_document.name,
                    ''  # Empty string to clear
                )

                if success:
                    self.associated_dwg_label.config(
                        text=" Sin asociar - Haga clic en 'Asociar DWG' para vincular un archivo",
                        font=("Arial", 10, "italic"),
                        foreground="#888888"
                    )
                    # Update the document object first
                    self.plano_document.associated_dwg = ''
                    # Check if there's still a DWG in file_paths
                    still_has_dwg = self._has_any_dwg()
                    # Update button states based on whether there's still a DWG
                    self.btn_associate_dwg.config(state="disabled" if still_has_dwg else "normal")
                    self.btn_add_dwg.config(state="disabled" if still_has_dwg else "normal")
                    self.btn_clear_dwg.config(state="disabled")
                    messagebox.showinfo("Éxito", "Asociación eliminada.", parent=self.window)
                    # Refresh file list so the removed DWG disappears from the table
                    self._refresh_file_list()
                else:
                    messagebox.showerror("Error", message, parent=self.window)

    def _open_associated_dwg(self):
        """Open the associated DWG file."""
        associated_dwg = getattr(self.plano_document, 'associated_dwg', '')
        if not associated_dwg:
            messagebox.showwarning("Sin asociación", "Este documento no tiene un DWG asociado.", parent=self.window)
            return

        dwg_path = Path(associated_dwg)
        if not dwg_path.exists():
            # Try to find it relative to project path
            if 'get_project_path' in self.callbacks:
                project_path = self.callbacks['get_project_path']()
                dwg_path = project_path / associated_dwg
                if not dwg_path.exists():
                    dwg_path = FolderResolver.resolve_planos(project_path) / "CAD" / "Working" / Path(associated_dwg).name

        if dwg_path.exists():
            from utils.file.file_manager import FileManager
            FileManager.open_file_location(dwg_path)
        else:
            messagebox.showwarning(
                "Archivo no encontrado",
                f"No se pudo encontrar el archivo DWG:\n{associated_dwg}",
                parent=self.window
            )

    def _create_file_list_section(self):
        """Create section showing current files."""
        # Main content frame
        content_frame = ttk.LabelFrame(self.window, text="Archivos Actuales", padding="10")
        content_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        
        # Create treeview for file list
        tree_frame = ttk.Frame(content_frame)
        tree_frame.pack(fill="both", expand=True)
        
        # Define columns
        columns = ("Tipo", "Nombre", "Ubicación", "Tamaño", "Modificado")
        self.file_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=12)
        
        # Configure columns
        self.file_tree.heading("Tipo", text="Tipo")
        self.file_tree.heading("Nombre", text="Nombre del Archivo")
        self.file_tree.heading("Ubicación", text="Ubicación")
        self.file_tree.heading("Tamaño", text="Tamaño")
        self.file_tree.heading("Modificado", text="Última Modificación")
        
        # Configure column widths
        self.file_tree.column("Tipo", width=60, minwidth=50, stretch=False)
        self.file_tree.column("Nombre", width=200, minwidth=150, stretch=True)
        self.file_tree.column("Ubicación", width=250, minwidth=200, stretch=True)
        self.file_tree.column("Tamaño", width=80, minwidth=70, stretch=False)
        self.file_tree.column("Modificado", width=120, minwidth=100, stretch=False)
        
        # Add scrollbars
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.file_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.file_tree.xview)
        self.file_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack tree and scrollbars
        self.file_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Bind double-click to open file location
        self.file_tree.bind("<Double-1>", self._on_file_double_click)
        
        # Configure tags for different file types (white text for dark background)
        self.file_tree.tag_configure("PDF", foreground="white")
        self.file_tree.tag_configure("DWG", foreground="white")
        self.file_tree.tag_configure("RVT", foreground="white")
        self.file_tree.tag_configure("default", foreground="white")
        self.file_tree.tag_configure("missing", foreground="#AAAAAA")  # Light gray for missing files
    
    def _create_action_buttons(self):
        """Create action buttons for file operations."""
        action_frame = ttk.Frame(self.window, padding="15")
        action_frame.pack(fill="x")
        
        # Left side - file operations
        left_frame = ttk.Frame(action_frame)
        left_frame.pack(side="left")
        
        self.btn_replace = ttk.Button(
            left_frame,
            text="🔄 Reemplazar Archivo Seleccionado",
            command=self._replace_selected_file,
            state="disabled"
        )
        self.btn_replace.pack(side="left", padx=(0, 10))

        self.btn_promote = ttk.Button(
            left_frame,
            text="⬆ Promover a Last",
            command=self._promote_selected_file,
            state="disabled"
        )
        self.btn_promote.pack(side="left", padx=(0, 10))

        self.btn_add_pdf = ttk.Button(
            left_frame,
            text="➕ Agregar PDF",
            command=lambda: self._add_new_file(".pdf")
        )
        self.btn_add_pdf.pack(side="left", padx=(0, 10))

        # Disable "Agregar DWG" if entry already has ANY DWG (one DWG per entry)
        self.btn_add_dwg = ttk.Button(
            left_frame,
            text="➕ Agregar DWG",
            command=lambda: self._add_new_file(".dwg"),
            state="disabled" if self._has_any_dwg() else "normal"
        )
        self.btn_add_dwg.pack(side="left", padx=(0, 10))
        
        self.btn_add_rvt = ttk.Button(
            left_frame,
            text="➕ Agregar RVT",
            command=lambda: self._add_new_file(".rvt")
        )
        self.btn_add_rvt.pack(side="left", padx=(0, 10))
        
        # Right side - file actions
        right_frame = ttk.Frame(action_frame)
        right_frame.pack(side="right")
        
        self.btn_open_location = ttk.Button(
            right_frame,
            text="📂 Abrir Ubicación",
            command=self._open_file_location,
            state="disabled"
        )
        self.btn_open_location.pack(side="right", padx=(10, 0))
        
        self.btn_refresh = ttk.Button(
            right_frame,
            text="🔄 Actualizar Lista",
            command=self._refresh_file_list
        )
        self.btn_refresh.pack(side="right", padx=(10, 0))
        
        # Bind selection event to enable/disable buttons
        self.file_tree.bind("<<TreeviewSelect>>", self._on_file_selection_change)
    
    def _close_window(self):
        """Close the file management window and notify the parent."""
        if self.window:
            self.window.destroy()
            self.window = None
        if self.on_close:
            try:
                self.on_close()
            except Exception as e:
                print(f"Error in on_close callback: {e}")

    def _create_bottom_buttons(self):
        """Create bottom control buttons."""
        bottom_frame = ttk.Frame(self.window, padding="15")
        bottom_frame.pack(fill="x")

        # Prominent "Back to Dashboard" button
        import sys
        if sys.platform.startswith('win'):
            back_btn = tk.Button(
                bottom_frame,
                text="<< Volver al Dashboard",
                command=self._close_window,
                bg='#404040',
                fg='#FFFFFF',
                activebackground='#5A5A5A',
                activeforeground='#FFFFFF',
                relief='raised',
                borderwidth=2,
                font=('Arial', 10, 'bold'),
                cursor='hand2'
            )
        else:
            back_btn = ttk.Button(
                bottom_frame,
                text="<< Volver al Dashboard",
                command=self._close_window
            )
        back_btn.pack(side="right")

        # Status label
        self.status_label = ttk.Label(
            bottom_frame,
            text="",
            foreground="#666666"
        )
        self.status_label.pack(side="left")
    
    def _refresh_file_list(self):
        """Refresh the file list from the database."""
        try:
            # Clear current tree
            for item in self.file_tree.get_children():
                self.file_tree.delete(item)

            # Get current files from callback (now returns absolute paths)
            if 'get_current_files' in self.callbacks:
                self.current_files = self.callbacks['get_current_files'](self.plano_document.name)
                print(f"DEBUG: Got {len(self.current_files) if self.current_files else 0} files from callback for {self.plano_document.name}")
                print(f"DEBUG: Files: {self.current_files}")
            else:
                # Fallback: parse from document object
                self.current_files = self._parse_file_paths_from_document()
                print(f"DEBUG: Used fallback, got {len(self.current_files) if self.current_files else 0} files")

            # Populate tree
            existing_count = 0
            for i, file_info in enumerate(self.current_files):
                raw_path = file_info.get('path', '')
                # Controller now returns absolute paths
                file_path = Path(raw_path) if raw_path else None
                file_exists = file_path.exists() if file_path else False
                if file_exists:
                    existing_count += 1
                
                # Determine file type for tag
                file_ext = file_path.suffix.upper().lstrip('.') if file_path else 'UNKNOWN'
                tag = file_ext if file_ext in ['PDF', 'DWG', 'RVT'] else 'default'
                
                # Add missing tag if file doesn't exist
                if not file_exists:
                    tag = 'missing'
                
                # Format file size
                size_str = "—"
                if file_exists:
                    try:
                        size_bytes = file_path.stat().st_size
                        if size_bytes < 1024:
                            size_str = f"{size_bytes} B"
                        elif size_bytes < 1024**2:
                            size_str = f"{size_bytes/1024:.1f} KB"
                        else:
                            size_str = f"{size_bytes/(1024**2):.1f} MB"
                    except Exception:
                        size_str = "Error"
                
                # Format modification time
                mod_time_str = "—"
                if file_exists:
                    try:
                        mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                        mod_time_str = mod_time.strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        mod_time_str = "Error"
                
                # Insert into tree
                self.file_tree.insert("", "end", values=(
                    file_ext,
                    file_path.name if file_path else "Sin archivo",
                    str(file_path.parent) if file_path else "—",
                    size_str,
                    mod_time_str
                ), tags=(tag,))
            
            # Update status
            file_count = len(self.current_files)
            self.status_label.config(text=f"Total: {file_count} archivos | Existentes: {existing_count}")

            # Update DWG button states based on current files
            self._update_dwg_button_states()

        except Exception as e:
            messagebox.showerror("Error", f"Error al actualizar lista de archivos: {e}")
            print(f"Error refreshing file list: {e}")

    def _update_dwg_button_states(self):
        """Update DWG-related button states based on current file status."""
        has_any_dwg = self._has_any_dwg()
        associated_dwg = getattr(self.plano_document, 'associated_dwg', '') or ''

        # One DWG per entry: disable both add and associate if any DWG exists
        self.btn_add_dwg.config(state="disabled" if has_any_dwg else "normal")
        self.btn_associate_dwg.config(state="disabled" if has_any_dwg else "normal")
        # Clear association button only enabled if there's an associated_dwg
        self.btn_clear_dwg.config(state="normal" if associated_dwg else "disabled")
    
    def _parse_file_paths_from_document(self) -> List[Dict]:
        """Parse file paths from document object as fallback."""
        files = []
        try:
            # Get file paths from document
            file_paths_raw = getattr(self.plano_document, 'file_paths', [])
            if isinstance(file_paths_raw, str):
                try:
                    file_paths = json.loads(file_paths_raw)
                except json.JSONDecodeError:
                    file_paths = []
            else:
                file_paths = file_paths_raw
            
            # Convert to standard format
            project_path = self.callbacks.get('get_project_path', lambda: Path.cwd())()
            for file_path_str in file_paths:
                if file_path_str:
                    # Handle both absolute and relative paths
                    file_path = Path(file_path_str)
                    if not file_path.is_absolute():
                        file_path = project_path / file_path_str
                    
                    files.append({
                        'path': str(file_path),
                        'type': file_path.suffix.lower(),
                        'relative_path': file_path_str
                    })
        except Exception as e:
            print(f"Error parsing file paths: {e}")
        
        return files
    
    def _on_file_selection_change(self, event=None):
        """Handle file selection change to enable/disable buttons."""
        selection = self.file_tree.selection()
        has_selection = bool(selection)

        self.btn_replace.config(state="normal" if has_selection else "disabled")
        self.btn_open_location.config(state="normal" if has_selection else "disabled")

        # Promote only enabled when the selected file lives under Working/
        promote_state = "disabled"
        if has_selection:
            try:
                values = self.file_tree.item(selection[0])['values']
                folder_str = str(values[2]) if len(values) > 2 else ''
                if 'Working' in Path(folder_str).parts:
                    promote_state = "normal"
            except Exception:
                pass
        self.btn_promote.config(state=promote_state)
    
    def _on_file_double_click(self, event=None):
        """Handle double-click on file to open location."""
        self._open_file_location()
    
    def _replace_selected_file(self):
        """Replace the currently selected file."""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un archivo de la lista.")
            return
        
        try:
            # Get selected file info
            selected_item = selection[0]
            item_values = self.file_tree.item(selected_item)['values']
            current_file_name = item_values[1]
            current_file_path = Path(item_values[2]) / current_file_name
            
            # Determine file type from current file
            file_ext = current_file_path.suffix.lower()
            file_type_filter = []
            if file_ext == '.pdf':
                file_type_filter = [("PDF files", "*.pdf")]
            elif file_ext == '.dwg':
                file_type_filter = [("DWG files", "*.dwg")]
            elif file_ext == '.rvt':
                file_type_filter = [("RVT files", "*.rvt")]
            else:
                file_type_filter = [("All files", "*.*")]
            
            # Open file dialog
            new_file_path = filedialog.askopenfilename(
                title=f"Seleccionar nuevo archivo para reemplazar {current_file_name}",
                filetypes=file_type_filter + [("All files", "*.*")],
                parent=self.window
            )
            
            if new_file_path:
                # Confirm replacement
                if messagebox.askyesno(
                    "Confirmar Reemplazo",
                    f"¿Está seguro de reemplazar:\n\n{current_file_name}\n\ncon:\n\n{Path(new_file_path).name}?\n\nEsta acción no se puede deshacer.",
                    parent=self.window
                ):
                    # Call replacement callback
                    if 'replace_file' in self.callbacks:
                        success, message = self.callbacks['replace_file'](
                            self.plano_document.name,
                            str(current_file_path),
                            new_file_path
                        )
                        
                        if success:
                            messagebox.showinfo("Éxito", message, parent=self.window)
                            self._refresh_file_list()
                        else:
                            messagebox.showerror("Error", message, parent=self.window)
                    else:
                        messagebox.showerror("Error", "Funcionalidad de reemplazo no disponible.", parent=self.window)
        
        except Exception as e:
            messagebox.showerror("Error", f"Error al reemplazar archivo: {e}", parent=self.window)

    def _promote_selected_file(self):
        """Promote the selected Working/ file to Last/ (previous Last → Old)."""
        selection = self.file_tree.selection()
        if not selection:
            return
        try:
            values = self.file_tree.item(selection[0])['values']
            file_name = values[1]
            folder = Path(str(values[2]))
            file_path = folder / file_name

            if 'Working' not in folder.parts:
                messagebox.showwarning(
                    "Promoción no aplicable",
                    "Sólo se pueden promover archivos que están en Working/.",
                    parent=self.window,
                )
                return

            confirm = messagebox.askyesno(
                "Confirmar promoción",
                f"¿Promover '{file_name}' a Last?\n\n"
                f"La versión anterior en Last (si existe) se moverá a Old.",
                parent=self.window,
            )
            if not confirm:
                return

            cb = self.callbacks.get('promote_file')
            if not cb:
                messagebox.showerror(
                    "Error",
                    "Funcionalidad de promoción no disponible.",
                    parent=self.window,
                )
                return
            success, message = cb(self.plano_document.name, str(file_path))
            if success:
                messagebox.showinfo("Éxito", message, parent=self.window)
                self._refresh_file_list()
            else:
                messagebox.showerror("Error", message, parent=self.window)
        except Exception as e:
            messagebox.showerror("Error", f"Error al promover archivo: {e}", parent=self.window)

    def _add_new_file(self, file_extension: str):
        """Add a new file of the specified type."""
        try:
            # Determine file type filter
            if file_extension == '.pdf':
                file_filter = [("PDF files", "*.pdf")]
                file_type_name = "PDF"
            elif file_extension == '.dwg':
                file_filter = [("DWG files", "*.dwg")]
                file_type_name = "DWG"
            elif file_extension == '.rvt':
                file_filter = [("RVT files", "*.rvt")]
                file_type_name = "RVT"
            else:
                file_filter = [("All files", "*.*")]
                file_type_name = "archivo"

            # Open file dialog
            new_file_path = filedialog.askopenfilename(
                title=f"Seleccionar {file_type_name} para agregar",
                filetypes=file_filter + [("All files", "*.*")],
                parent=self.window
            )

            if new_file_path:
                # For DWG files, show rename dialog
                dwg_name = None
                if file_extension == '.dwg':
                    dwg_name = self._show_dwg_name_dialog(self.plano_document.name)
                    if dwg_name is None:  # User cancelled
                        return

                # Confirm addition
                final_name = f"{dwg_name}.dwg" if dwg_name else Path(new_file_path).name
                if messagebox.askyesno(
                    "Confirmar Adición",
                    f"¿Está seguro de agregar:\n\n{Path(new_file_path).name}\n\nal documento {self.plano_document.name}?\n\nSe guardará como: {final_name}",
                    parent=self.window
                ):
                    # Call add file callback
                    if 'add_file' in self.callbacks:
                        success, message = self.callbacks['add_file'](
                            self.plano_document.name,
                            new_file_path,
                            file_extension,
                            dwg_name
                        )

                        if success:
                            messagebox.showinfo("Éxito", message, parent=self.window)
                            self._refresh_file_list()
                            # If a DWG was added, disable DWG buttons (one DWG per entry)
                            if file_extension == '.dwg':
                                self.btn_add_dwg.config(state="disabled")
                                self.btn_associate_dwg.config(state="disabled")
                        else:
                            messagebox.showerror("Error", message, parent=self.window)
                    else:
                        messagebox.showerror("Error", "Funcionalidad de adición no disponible.", parent=self.window)

        except Exception as e:
            messagebox.showerror("Error", f"Error al agregar archivo: {e}", parent=self.window)

    def _show_dwg_name_dialog(self, default_name: str) -> Optional[str]:
        """
        Show dialog to enter custom DWG filename.

        Args:
            default_name: Default name to show (entry name)

        Returns:
            The entered name (without extension), or None if cancelled
        """
        dialog = tk.Toplevel(self.window)
        dialog.title("Nombre del DWG")
        dialog.geometry("400x150")
        dialog.transient(self.window)
        dialog.grab_set()

        # Center dialog
        dialog.geometry("+{}+{}".format(
            int(dialog.winfo_screenwidth()/2 - 200),
            int(dialog.winfo_screenheight()/2 - 75)
        ))

        result = {'name': None}

        ttk.Label(
            dialog,
            text="Nombre con el que se guardará el DWG:",
            font=("Arial", 10)
        ).pack(pady=(15, 5), padx=15, anchor="w")

        name_entry = ttk.Entry(dialog, font=("Arial", 11), width=40)
        name_entry.pack(pady=5, padx=15, fill="x")
        name_entry.insert(0, default_name)
        name_entry.select_range(0, tk.END)
        name_entry.focus_set()

        ttk.Label(
            dialog,
            text="El archivo se guardará como: nombre.dwg (sin versión ni estado)",
            font=("Arial", 8),
            foreground="#666666"
        ).pack(pady=(0, 10), padx=15, anchor="w")

        def on_ok():
            name = name_entry.get().strip()
            if name:
                result['name'] = name
                dialog.destroy()
            else:
                messagebox.showwarning("Nombre requerido", "Por favor, ingrese un nombre para el DWG.", parent=dialog)

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Aceptar", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=on_cancel).pack(side="left", padx=5)

        # Enter key to accept
        name_entry.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        dialog.wait_window()
        return result['name']
    
    def _open_file_location(self):
        """Open the location of the selected file and preselect it in Finder/Explorer."""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona un archivo de la lista.")
            return

        try:
            # Get selected file info
            selected_item = selection[0]
            item_values = self.file_tree.item(selected_item)['values']
            file_name = item_values[1]  # Filename column
            file_folder = item_values[2]  # Location (folder) column

            if file_folder and file_folder != "—" and file_name and file_name != "Sin archivo":
                from utils.file.file_manager import FileManager

                # Construct full file path from folder + filename
                full_file_path = Path(file_folder) / file_name

                if full_file_path.exists():
                    # Use FileManager which properly preselects the file
                    FileManager.open_file_location(full_file_path)
                else:
                    # Try to open the parent folder if file doesn't exist
                    parent_folder = Path(file_folder)
                    if parent_folder.exists():
                        import subprocess
                        import sys
                        if sys.platform == "darwin":
                            subprocess.run(["open", str(parent_folder)])
                        elif sys.platform == "win32":
                            subprocess.run(["explorer", str(parent_folder)])
                        else:
                            subprocess.run(["xdg-open", str(parent_folder)])
                    else:
                        messagebox.showwarning("Ubicación no encontrada", f"La ubicación no existe: {full_file_path}", parent=self.window)
            else:
                messagebox.showwarning("Sin ubicación", "El archivo seleccionado no tiene una ubicación válida.", parent=self.window)

        except Exception as e:
            messagebox.showerror("Error", f"Error al abrir ubicación: {e}", parent=self.window)
    
