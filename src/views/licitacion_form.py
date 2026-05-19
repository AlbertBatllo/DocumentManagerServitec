import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
from pathlib import Path
from typing import Callable, List
from .base_view import BaseView
from .update_state_form import UpdateStateForm
from models.licitacion_document import (
    LOTES_ESTANDAR, LICITACION_STAGES, STAGE_DISPLAY_NAMES,
    PRESUPUESTO_TYPES, TYPE_DISPLAY_NAMES, PRESUPUESTO_STATUSES, 
    STATUS_DISPLAY_NAMES, STATUS_HELP_TEXT
)
import difflib


class LicitacionForm(BaseView):
    """Form for creating and managing presupuesto documents"""
    
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.selected_files = []
        self.companies_list = []
        self.existing_doc_ids = []
        self.selected_parent_id = None
        self.files_listbox = None
        self.file_count_label = None
        
    def show_new_document_form(self, callbacks: dict, user_name: str = "") -> None:
        """Show form for creating a new presupuesto document"""
        # Store callbacks for later use
        self.current_callbacks = callbacks
        print(f"DEBUG: Stored callbacks: {list(callbacks.keys())}")
        
        # Reset file selection for new upload session
        self.selected_files = []
        
        self.clear_window()
        self.center_window(750, 850)  # Increased height for better button visibility
        self.root.minsize(750, 800)  # Increased minimum size
        
        # Header
        self.create_header(self.root, "Nuevo Presupuesto")
        
        # IMPORTANT: Create bottom frame FIRST - ensure it's always visible
        bottom_frame = ttk.Frame(self.root, padding="15")
        bottom_frame.pack(side="bottom", fill="x", expand=False)
        
        # Create buttons immediately to ensure they're always visible
        self._create_buttons(bottom_frame, callbacks, is_new_document=True)
        
        # Create main container with better separation from bottom frame
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Create scrollable main content within the container
        canvas = tk.Canvas(main_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Main frame inside canvas
        main_frame = ttk.Frame(canvas, padding="12")
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor="nw")
        
        # Configure canvas scrolling
        def configure_scroll(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Update scroll region after a delay to ensure all widgets are properly sized
            canvas.after_idle(lambda: canvas.configure(scrollregion=canvas.bbox("all")))
        
        def update_canvas_width(event):
            canvas_width = event.width
            canvas.itemconfig(canvas_window, width=canvas_width)
        
        main_frame.bind('<Configure>', configure_scroll)
        canvas.bind('<Configure>', update_canvas_width)
        
        # Form fields
        self._create_form_fields(main_frame, user_name, is_new_document=True)
        
        # Set focus after widget creation is complete
        self.root.after_idle(lambda: self.doc_id_entry.focus() if hasattr(self, 'doc_id_entry') else None)
        
        # Update scroll region after all widgets are created
        self.root.after(100, configure_scroll)

    def _create_form_fields(self, parent: tk.Widget, user_name: str, is_new_document: bool) -> None:
        """Create the form input fields"""
        try:
            if is_new_document:
                # Full form for new documents
                self._create_full_form_fields(parent, user_name)
            else:
                # Simplified form for new versions - only essential fields
                self._create_simplified_version_form(parent, user_name)
        except Exception as e:
            print(f"ERROR in _create_form_fields: {e}")
            import traceback
            traceback.print_exc()
            
            # Create minimal fallback form
            ttk.Label(parent, text="Error al cargar el formulario completo").pack(pady=10)
            ttk.Label(parent, text="Nombre del Documento:").pack(anchor="w")
            self.doc_id_entry = ttk.Entry(parent, width=30)
            self.doc_id_entry.pack(anchor="w", pady=5)
            
            # Create basic file selection 
            ttk.Label(parent, text="Archivos:").pack(anchor="w", pady=(10, 0))
            self.selected_files = []
            ttk.Button(parent, text="Seleccionar Archivos", command=self._add_file).pack(pady=5)

    def _create_simplified_version_form(self, parent: tk.Widget, user_name: str) -> None:
        """Create simplified form fields for new version (minimal necessary info)"""
        # Document Name (read-only - already completed, cannot be changed)
        ttk.Label(parent, text="Nombre del Documento:").pack(anchor="w", pady=(0, 3))
        self.doc_id_entry = ttk.Entry(parent, width=50, font=("Arial", 12), state="readonly")
        self.doc_id_entry.pack(anchor="w", pady=(0, 3))
        
        # Info label for status feedback
        info_text = "Documento seleccionado - no se puede cambiar"
        self.info_label = ttk.Label(parent, text=info_text, foreground="blue")
        self.info_label.pack(anchor="w", pady=(0, 15))
        
        # Status and Valor row (lado a lado) - simplified version
        ttk.Label(parent, text="Estado:").pack(anchor="w", pady=(0, 5))
        status_valor_frame = ttk.Frame(parent)
        status_valor_frame.pack(fill="x", pady=(0, 15))
        
        # Status section (left side)
        status_left_frame = ttk.Frame(status_valor_frame)
        status_left_frame.pack(side="left", fill="x", expand=True)
        
        self.status_var = tk.StringVar(value="S0")
        status_display_list = [f"{status} - {STATUS_DISPLAY_NAMES[status]}" for status in PRESUPUESTO_STATUSES]
        self.status_combo = ttk.Combobox(
            status_left_frame,
            textvariable=self.status_var,
            values=status_display_list,
            width=35,
            font=("Arial", 11),
            state="readonly"
        )
        self.status_combo.pack(side="left")
        
        # Valor section (right side) - conditional visibility
        valor_right_frame = ttk.Frame(status_valor_frame)
        valor_right_frame.pack(side="right", padx=(20, 0))
        
        self.valor_label = ttk.Label(valor_right_frame, text="Valor/Importe (€):")
        self.valor_entry = ttk.Entry(valor_right_frame, width=25, font=("Arial", 11))
        # Initially hidden - will be shown/hidden based on document type
        
        # Version
        ttk.Label(parent, text="Nueva Versión:").pack(anchor="w", pady=(0, 5))
        self.version_entry = ttk.Entry(parent, width=30, font=("Arial", 12))
        self.version_entry.pack(anchor="w", pady=(0, 15))
        
        # File selection (essential)
        self._create_file_selection_section(parent)
        
        # Notes (optional, simplified)
        ttk.Label(parent, text="Notas (opcional):").pack(anchor="w", pady=(10, 5))
        self.notes_text = tk.Text(parent, height=2, width=60, font=("Arial", 10))
        self.notes_text.pack(anchor="w", pady=(0, 10))

    def _create_full_form_fields(self, parent: tk.Widget, user_name: str) -> None:
        """Create full form fields for new documents"""
        # Document Name
        ttk.Label(parent, text="Nombre del Documento:").pack(anchor="w", pady=(0, 3))
        self.doc_id_entry = ttk.Entry(parent, width=30, font=("Arial", 12))
        self.doc_id_entry.pack(anchor="w", pady=(0, 3))
        
        # Info label for fuzzy matching feedback
        info_text = "Introduce un nombre de presupuesto."
        self.info_label = ttk.Label(parent, text=info_text, foreground="orange")
        self.info_label.pack(anchor="w", pady=(0, 10))
        
        # Document Description (optional)
        ttk.Label(parent, text="Descripción (opcional):").pack(anchor="w", pady=(0, 5))
        self.name_entry = ttk.Entry(parent, width=50, font=("Arial", 12))
        self.name_entry.pack(anchor="w", pady=(0, 15))
        
        # Lote selection
        ttk.Label(parent, text="Lote:").pack(anchor="w", pady=(0, 5))
        self.lote_var = tk.StringVar()
        self.lote_combo = ttk.Combobox(
            parent, 
            textvariable=self.lote_var, 
            values=LOTES_ESTANDAR,
            width=60,
            font=("Arial", 11),
            state="readonly"
        )
        self.lote_combo.pack(anchor="w", pady=(0, 15))
        
        # Bind lote change to refresh parent presupuestos
        self.lote_combo.bind('<<ComboboxSelected>>', self._on_lote_change)
        
        # Document Type selection
        ttk.Label(parent, text="Tipo de Documento:").pack(anchor="w", pady=(0, 5))
        type_frame = ttk.Frame(parent)
        type_frame.pack(fill="x", pady=(0, 10))
        
        # Set default to display name, not internal value
        default_display_name = TYPE_DISPLAY_NAMES.get("licitacion", "Licitación")
        self.type_var = tk.StringVar(value=default_display_name)
        type_display_list = [TYPE_DISPLAY_NAMES[doc_type] for doc_type in PRESUPUESTO_TYPES]
        self.type_combo = ttk.Combobox(
            type_frame,
            textvariable=self.type_var,
            values=type_display_list,
            width=25,
            font=("Arial", 11),
            state="readonly"
        )
        self.type_combo.pack(side="left", padx=(0, 10))
        
        # Help button for document types
        self.type_help_btn = ttk.Button(
            type_frame,
            text="?",
            width=3,
            command=self._show_type_help
        )
        self.type_help_btn.pack(side="left")
        
        # Status and Valor row (lado a lado)
        ttk.Label(parent, text="Estado:").pack(anchor="w", pady=(10, 5))
        status_valor_frame = ttk.Frame(parent)
        status_valor_frame.pack(fill="x", pady=(0, 15))
        
        # Status section (left side)
        status_left_frame = ttk.Frame(status_valor_frame)
        status_left_frame.pack(side="left", fill="x", expand=True)
        
        self.status_var = tk.StringVar(value="S0")
        status_display_list = [f"{status} - {STATUS_DISPLAY_NAMES[status]}" for status in PRESUPUESTO_STATUSES]
        self.status_combo = ttk.Combobox(
            status_left_frame,
            textvariable=self.status_var,
            values=status_display_list,
            width=35,
            font=("Arial", 11),
            state="readonly"
        )
        self.status_combo.pack(side="left", padx=(0, 10))
        
        # Help button for status
        self.status_help_btn = ttk.Button(
            status_left_frame,
            text="?",
            width=3,
            command=self._show_status_help
        )
        self.status_help_btn.pack(side="left")
        
        # Valor section (right side) - conditional visibility
        valor_right_frame = ttk.Frame(status_valor_frame)
        valor_right_frame.pack(side="right", padx=(20, 0))
        
        self.valor_label = ttk.Label(valor_right_frame, text="Valor/Importe (€):")
        self.valor_entry = ttk.Entry(valor_right_frame, width=25, font=("Arial", 11))
        # Initially hidden - will be shown/hidden based on document type
        
        # Bind type and status changes
        self.type_combo.bind('<<ComboboxSelected>>', self._on_type_change)
        self.status_combo.bind('<<ComboboxSelected>>', self._on_status_change)
        
        # Company field (for presupuesto and licitacion) / Parent Presupuesto (for adicionales)
        self.company_label = ttk.Label(parent, text="Empresa:")
        self.company_label.pack(anchor="w", pady=(10, 5))
        
        self.company_var = tk.StringVar()
        self.company_entry = ttk.Entry(parent, textvariable=self.company_var, width=50, font=("Arial", 12))
        self.company_entry.pack(anchor="w", pady=(0, 15))
        
        # Parent Presupuesto selection (replaces empresa field for adicionales)
        self.parent_label = ttk.Label(parent, text="Presupuesto Padre (Aceptado):")
        self.parent_var = tk.StringVar()
        self.parent_combo = ttk.Combobox(
            parent,
            textvariable=self.parent_var,
            width=50,
            font=("Arial", 11),
            state="readonly"
        )
        # Initially hidden - will be shown only for adicionales
        
        # Trigger initial type change to set up field visibility
        self.root.after_idle(self._on_type_change)
        
        # Version
        ttk.Label(parent, text="Versión:").pack(anchor="w", pady=(0, 5))
        self.version_entry = ttk.Entry(parent, width=30, font=("Arial", 12))
        self.version_entry.insert(0, "1.0")  # Default version
        self.version_entry.pack(anchor="w", pady=(0, 15))
        
        # File selection section
        self._create_file_selection_section(parent)
        
        # Notes (optional, collapsible)
        notes_frame = ttk.LabelFrame(parent, text="Notas (Opcional)", padding="6")
        notes_frame.pack(fill="x", pady=(6, 0))
        
        self.notes_text = tk.Text(notes_frame, height=2, width=60, font=("Arial", 10))
        self.notes_text.pack(fill="x")
        
        # Bind events for intelligent fuzzy matching
        self.doc_id_entry.bind('<FocusOut>', self._check_document_id)
        self.doc_id_entry.bind('<KeyRelease>', self._on_id_change)

    def _create_file_selection_section(self, parent: tk.Widget) -> None:
        """Create file selection section (used by both forms)"""
        # File selection with improved UI
        file_frame = ttk.LabelFrame(parent, text="Archivos del Documento", padding="10")
        file_frame.pack(fill="both", expand=True, pady=(10, 15))
        
        # File selection buttons
        file_button_frame = ttk.Frame(file_frame)
        file_button_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(
            file_button_frame,
            text="➕ Añadir Archivo",
            command=self._add_file
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            file_button_frame,
            text="➖ Quitar Archivo",
            command=self._remove_file
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            file_button_frame,
            text="🗑️ Limpiar Todo",
            command=self._clear_files
        ).pack(side="left")
        
        # File list display
        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill="both", expand=True)
        
        # Create listbox with scrollbar
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.files_listbox = tk.Listbox(
            list_frame,
            height=4,
            selectmode="single",
            yscrollcommand=scrollbar.set
        )
        self.files_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.files_listbox.yview)
        
        # Enable drag-and-drop for the files listbox
        self.enable_drag_and_drop_for_listbox(
            self.files_listbox,
            self._on_files_dropped
        )
        
        # File count label
        self.file_count_label = ttk.Label(
            file_frame,
            text="No hay archivos seleccionados",
            foreground="gray"
        )
        self.file_count_label.pack(anchor="w", pady=(5, 0))

    def _create_buttons(self, parent: tk.Widget, callbacks: dict, is_new_document: bool) -> None:
        """Create form action buttons"""
        try:
            # Add separator for visual clarity
            separator = ttk.Separator(parent, orient='horizontal')
            separator.pack(fill="x", pady=(5, 10))
            
            button_frame = ttk.Frame(parent)
            button_frame.pack(fill="x", pady=(10, 10))
            
            # Submit button
            submit_text = "✓ Crear Documento" if is_new_document else "✓ Añadir Versión"
            submit_command = self._submit_new_document if is_new_document else self._submit_new_version
            
            submit_btn = ttk.Button(
                button_frame,
                text=submit_text,
                command=lambda: submit_command(callbacks),
                width=20
            )
            submit_btn.pack(side="left", padx=(0, 15))
            
            # Cancel/Back button
            cancel_btn = ttk.Button(
                button_frame,
                text="✗ Cancelar",
                command=callbacks.get('back', lambda: None),
                width=15
            )
            cancel_btn.pack(side="left")
            
            print(f"Created buttons for {'new document' if is_new_document else 'new version'} form")
            
        except Exception as e:
            print(f"Error creating buttons: {e}")
            # Fallback minimal buttons
            simple_frame = ttk.Frame(parent)
            simple_frame.pack(fill="x", pady=10)
            ttk.Button(simple_frame, text="Enviar", 
                      command=lambda: self._submit_new_document(callbacks) if is_new_document else self._submit_new_version(callbacks)).pack(side="left", padx=5)
            ttk.Button(simple_frame, text="Volver", 
                      command=callbacks.get('back', lambda: None)).pack(side="left", padx=5)

    def _add_file(self) -> None:
        """Add a file to the document"""
        try:
            import os
            import sys
            
            # Basic root window check
            if not hasattr(self, 'root') or not self.root:
                messagebox.showerror("Error", "La aplicación no está lista. Intenta de nuevo.")
                return
            
            # Set initial directory with fallback
            initial_dir = None
            try:
                initial_dir = os.path.expanduser("~/Desktop")
                if not os.path.exists(initial_dir):
                    initial_dir = os.path.expanduser("~")
            except (OSError, AttributeError) as e:
                print(f"Warning: Could not determine initial directory: {e}")
                initial_dir = os.getcwd()
            
            # Force focus to root window first
            self.root.focus_force()
            self.root.lift()
            
            # Use a more robust file dialog approach
            file_paths = None
            try:
                # On macOS, sometimes the parent needs to be None to avoid crashes
                parent_window = None if sys.platform == 'darwin' else self.root
                
                file_paths = filedialog.askopenfilenames(
                    parent=parent_window,
                    title="Seleccionar archivos de licitación",
                    initialdir=initial_dir,
                    filetypes=[
                        ("Archivos PDF", "*.pdf"),
                        ("Archivos Excel", "*.xlsx *.xls"),
                        ("Archivos Word", "*.docx *.doc"),
                        ("Todos los archivos", "*.*")
                    ]
                )
            except Exception as dialog_error:
                print(f"File dialog error: {dialog_error}")
                # Fallback: try without parent
                file_paths = filedialog.askopenfilenames(
                    title="Seleccionar archivos de licitación",
                    initialdir=initial_dir,
                    filetypes=[
                        ("Archivos PDF", "*.pdf"),
                        ("Todos los archivos", "*.*")
                    ]
                )
            
            if file_paths:
                # Initialize selected_files if it doesn't exist
                if not hasattr(self, 'selected_files'):
                    self.selected_files = []
                
                added_count = 0
                for file_path in file_paths:
                    try:
                        path = Path(file_path)
                        if path.exists() and path not in self.selected_files:
                            self.selected_files.append(path)
                            # Only update listbox if it exists
                            if hasattr(self, 'files_listbox'):
                                self.files_listbox.insert(tk.END, path.name)
                            added_count += 1
                    except Exception as path_error:
                        print(f"Error processing file path {file_path}: {path_error}")
                        continue
                
                if added_count > 0:
                    self._update_file_count()
                    print(f"Added {added_count} files. Total files: {len(self.selected_files)}")
                    messagebox.showinfo("Éxito", f"Se agregaron {added_count} archivos correctamente.")
                else:
                    messagebox.showwarning("Aviso", "No se pudieron agregar archivos o ya estaban en la lista.")
            else:
                print("No files selected or dialog cancelled")
                
        except Exception as e:
            import traceback
            error_msg = f"Error al abrir el selector de archivos: {str(e)}"
            print(f"{error_msg}\n{traceback.format_exc()}")
            messagebox.showerror("Error", f"No se pudo abrir el selector de archivos.\n\nDetalles técnicos: {str(e)}")
    
    def _remove_file(self) -> None:
        """Remove selected file from the list"""
        try:
            if not hasattr(self, 'files_listbox') or not hasattr(self, 'selected_files'):
                messagebox.showinfo("Error", "Lista de archivos no disponible")
                return
                
            selection = self.files_listbox.curselection()
            if selection:
                index = selection[0]
                self.files_listbox.delete(index)
                if index < len(self.selected_files):
                    del self.selected_files[index]
                self._update_file_count()
                print(f"Removed file at index {index}. Remaining files: {len(self.selected_files)}")
            else:
                messagebox.showinfo("Información", "Por favor, seleccione un archivo para quitar")
        except Exception as e:
            print(f"Error removing file: {e}")
            messagebox.showerror("Error", "No se pudo quitar el archivo")
    
    def _clear_files(self) -> None:
        """Clear all selected files"""
        try:
            if not hasattr(self, 'selected_files'):
                self.selected_files = []
                return
                
            if self.selected_files:
                if messagebox.askyesno("Confirmar", "¿Desea quitar todos los archivos seleccionados?"):
                    self.selected_files.clear()
                    if hasattr(self, 'files_listbox'):
                        self.files_listbox.delete(0, tk.END)
                    self._update_file_count()
                    print("All files cleared")
        except Exception as e:
            print(f"Error clearing files: {e}")
    
    def _update_file_count(self) -> None:
        """Update the file count label"""
        try:
            if not hasattr(self, 'selected_files'):
                self.selected_files = []
            
            count = len(self.selected_files)
            
            if hasattr(self, 'file_count_label') and self.file_count_label:
                if count == 0:
                    self.file_count_label.config(
                        text="No hay archivos seleccionados",
                        foreground="gray"
                    )
                elif count == 1:
                    self.file_count_label.config(
                        text="1 archivo seleccionado",
                        foreground="green"
                    )
                else:
                    self.file_count_label.config(
                        text=f"{count} archivos seleccionados",
                        foreground="green"
                    )
        except Exception as e:
            print(f"Error updating file count: {e}")
    
    def _on_files_dropped(self, path_objects: List[Path]) -> None:
        """Handle files dropped onto the listbox.
        
        Args:
            path_objects: List of Path objects for the dropped files
        """
        try:
            # Initialize selected_files if it doesn't exist
            if not hasattr(self, 'selected_files'):
                self.selected_files = []
            
            added_count = 0
            for path_obj in path_objects:
                if path_obj not in self.selected_files:
                    self.selected_files.append(path_obj)
                    # Update listbox if it exists
                    if hasattr(self, 'files_listbox'):
                        self.files_listbox.insert(tk.END, path_obj.name)
                    added_count += 1
            
            if added_count > 0:
                self._update_file_count()
                print(f"Added {added_count} files via drag and drop. Total files: {len(self.selected_files)}")
                messagebox.showinfo("Éxito", f"Se agregaron {added_count} archivos mediante arrastrar y soltar.")
        except Exception as e:
            print(f"Error handling dropped files: {e}")

    def _submit_new_document(self, callbacks: dict) -> None:
        """Submit new document form with complete data"""
        try:
            # Validate required fields
            doc_id = self.doc_id_entry.get().strip() if hasattr(self, 'doc_id_entry') else ""
            lote = self.lote_var.get().strip() if hasattr(self, 'lote_var') else ""
            doc_type_display = self.type_var.get().strip() if hasattr(self, 'type_var') else ""
            # Convert display name to internal value
            doc_type = ""
            print(f"DEBUG TYPE CONVERSION: doc_type_display='{doc_type_display}'")
            print(f"DEBUG TYPE CONVERSION: TYPE_DISPLAY_NAMES={TYPE_DISPLAY_NAMES}")
            for key, value in TYPE_DISPLAY_NAMES.items():
                if value == doc_type_display:
                    doc_type = key
                    print(f"DEBUG TYPE CONVERSION: Found match - internal='{doc_type}'")
                    break
            if not doc_type:
                print(f"DEBUG TYPE CONVERSION: No match found! Using display name as fallback.")
                doc_type = doc_type_display.lower()  # Fallback
            status = self.status_var.get().strip() if hasattr(self, 'status_var') else ""
            company = self.company_var.get().strip() if hasattr(self, 'company_var') else ""
            version = self.version_entry.get().strip() if hasattr(self, 'version_entry') else ""
            
            # Check required fields
            errors = []
            if not doc_id:
                errors.append("- Nombre del documento")
            if not lote:
                errors.append("- Lote")
            if not doc_type:
                errors.append("- Tipo de documento")
            if not status:
                errors.append("- Estado")
            # For adicionales, check parent presupuesto instead of empresa
            if doc_type == "adicional":
                parent_selection = self.parent_var.get().strip() if hasattr(self, 'parent_var') else ""
                if not parent_selection or parent_selection.startswith("Seleccione") or parent_selection.startswith("No hay") or parent_selection.startswith("Error"):
                    errors.append("- Presupuesto Padre (requerido para adicionales)")
            else:
                # For presupuesto and licitacion, check empresa
                if not company:
                    errors.append("- Empresa")
            
            if not version:
                errors.append("- Versión")
            if not hasattr(self, 'selected_files') or not self.selected_files:
                errors.append("- Al menos un archivo")
            
            # Validate valor field for presupuesto and adicional types
            if doc_type in ["presupuesto", "adicional"]:
                # Ensure valor field is visible before validation
                if hasattr(self, '_on_type_change'):
                    self._on_type_change()  # Make sure valor field is visible
                
                valor_str = ""
                if hasattr(self, 'valor_entry') and self.valor_entry:
                    valor_str = self.valor_entry.get().strip()
                
                print(f"DEBUG: doc_type={doc_type}, has_valor_entry={hasattr(self, 'valor_entry')}, valor_str='{valor_str}'")
                
                if not valor_str:
                    errors.append("- Valor/Importe (requerido para presupuestos y adicionales)")
                else:
                    try:
                        # Handle both comma and dot as decimal separators
                        valor_str_normalized = valor_str.replace(',', '.')
                        # Check if it's a valid number (integer or float)
                        if '.' in valor_str_normalized:
                            valor = float(valor_str_normalized)
                        else:
                            valor = int(valor_str_normalized)
                            valor = float(valor)  # Convert to float for consistency
                        
                        print(f"DEBUG: Parsed valor={valor}")
                        
                        if valor <= 0:
                            errors.append("- Valor/Importe debe ser mayor que cero")
                    except (ValueError, TypeError) as e:
                        print(f"DEBUG: Valor parsing error: {e}")
                        errors.append("- Valor/Importe debe ser un número válido (entero o decimal con '.' o ',')")
            
            if errors:
                messagebox.showwarning(
                    "Campos Requeridos",
                    "Por favor, complete los siguientes campos:\n\n" + "\n".join(errors)
                )
                return
            
            # Extract status code if it's in display format "S1 - Description"
            if " - " in status:
                status = status.split(" - ")[0]
            
            # Call the add_new_document callback
            if 'add_new_document' in callbacks:
                # Get current user
                current_user = callbacks.get('get_current_user', lambda: 'Usuario')()
                
                # Get notes if any
                notes = self.notes_text.get("1.0", tk.END).strip() if hasattr(self, 'notes_text') else ""
                
                # Get all selected file paths
                file_paths = self.selected_files if self.selected_files else []
                if not file_paths:
                    messagebox.showerror("Error", "Debe seleccionar al menos un archivo")
                    return
                
                # Get valor if applicable
                valor = None
                print(f"DEBUG SUBMIT: doc_type={doc_type}, has_valor_entry={hasattr(self, 'valor_entry')}")
                if doc_type in ["presupuesto", "adicional"]:
                    # Ensure valor field is visible and accessible
                    if hasattr(self, '_on_type_change'):
                        self._on_type_change()  # Make sure valor field is visible
                    
                    if hasattr(self, 'valor_entry'):
                        valor_str = self.valor_entry.get().strip()
                        print(f"DEBUG SUBMIT: valor_str='{valor_str}'")
                        if valor_str:
                            # Handle both comma and dot as decimal separators
                            valor_str_normalized = valor_str.replace(',', '.')
                            if '.' in valor_str_normalized:
                                valor = float(valor_str_normalized)
                            else:
                                valor = float(int(valor_str_normalized))
                            print(f"DEBUG SUBMIT: parsed valor={valor}")
                        else:
                            print("DEBUG SUBMIT: valor_str is empty!")
                    else:
                        print("DEBUG SUBMIT: No valor_entry attribute found!")
                else:
                    print(f"DEBUG SUBMIT: Skipping valor extraction - doc_type not in [presupuesto, adicional]")
                
                # Get parent presupuesto ID for adicionales
                parent_presupuesto_id = None
                if doc_type == "adicional":
                    parent_selection = self.parent_var.get().strip() if hasattr(self, 'parent_var') else ""
                    if parent_selection and not parent_selection.startswith(("Seleccione", "No hay", "Error")):
                        # Extract the presupuesto ID (before the first " - ")
                        parent_presupuesto_id = parent_selection.split(" - ")[0]
                        print(f"DEBUG SUBMIT: parent_presupuesto_id='{parent_presupuesto_id}'")
                
                # Call add_new_document with individual parameters including valor and parent_presupuesto_id
                result = callbacks['add_new_document'](
                    doc_id, lote, company, doc_type, status, version, 
                    file_paths, current_user, notes, valor, 
                    None, parent_presupuesto_id  # parent_licitacion_name=None, parent_presupuesto_id
                )
                if result:
                    messagebox.showinfo("Éxito", "Documento creado exitosamente")
                    callbacks.get('back', lambda: None)()
                else:
                    messagebox.showerror("Error", "No se pudo crear el documento")
            else:
                messagebox.showerror("Error", "Funcionalidad no disponible")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al crear documento: {str(e)}")

    def _submit_new_version(self, callbacks: dict) -> None:
        """Submit new version form with complete data"""
        try:
            # Validate required fields
            doc_id = self.doc_id_entry.get().strip() if hasattr(self, 'doc_id_entry') else ""
            version = self.version_entry.get().strip() if hasattr(self, 'version_entry') else ""
            
            # Check required fields
            errors = []
            if not doc_id:
                errors.append("- Nombre del documento")
            if not version:
                errors.append("- Versión")
            if not hasattr(self, 'selected_files') or not self.selected_files:
                errors.append("- Al menos un archivo")
            
            # Check if document exists and get its type for valor validation
            existing_doc = None
            if 'get_document' in callbacks:
                existing_doc = callbacks['get_document'](doc_id)
                if not existing_doc:
                    messagebox.showerror("Documento no encontrado", 
                                       f"No existe un documento con el nombre '{doc_id}'. "
                                       f"Verifique el nombre o cree un nuevo documento primero.")
                    return
                
                # Validate valor field for presupuesto and adicional types
                if hasattr(existing_doc, 'document_type') and existing_doc.document_type in ["presupuesto", "adicional"]:
                    valor_str = self.valor_entry.get().strip() if hasattr(self, 'valor_entry') else ""
                    if not valor_str:
                        errors.append("- Valor/Importe (requerido para presupuestos y adicionales)")
                    else:
                        try:
                            # Handle both comma and dot as decimal separators
                            valor_str_normalized = valor_str.replace(',', '.')
                            # Check if it's a valid number (integer or float)
                            if '.' in valor_str_normalized:
                                valor = float(valor_str_normalized)
                            else:
                                valor = int(valor_str_normalized)
                                valor = float(valor)  # Convert to float for consistency
                            
                            if valor <= 0:
                                errors.append("- Valor/Importe debe ser mayor que cero")
                        except (ValueError, TypeError):
                            errors.append("- Valor/Importe debe ser un número válido (entero o decimal con '.' o ',')")
            
            if errors:
                messagebox.showwarning(
                    "Campos Requeridos",
                    "Por favor, complete los siguientes campos:\n\n" + "\n".join(errors)
                )
                return
            
            # Call the add_new_version callback
            if 'add_new_version' in callbacks:
                # Get current user
                current_user = callbacks.get('get_current_user', lambda: 'Usuario')()
                
                # Get notes if any
                notes = self.notes_text.get("1.0", tk.END).strip() if hasattr(self, 'notes_text') else ""
                
                # Get status if changed
                status = self.status_var.get().strip() if hasattr(self, 'status_var') else None
                if status and " - " in status:
                    status = status.split(" - ")[0]
                
                # Convert selected files to Path objects
                file_paths = [Path(fp) for fp in self.selected_files] if self.selected_files else []
                if not file_paths:
                    messagebox.showerror("Error", "Debe seleccionar al menos un archivo")
                    return
                
                # Get valor if applicable for presupuesto/adicional types
                valor = None
                if existing_doc and hasattr(existing_doc, 'document_type') and existing_doc.document_type in ["presupuesto", "adicional"]:
                    if hasattr(self, 'valor_entry'):
                        valor_str = self.valor_entry.get().strip()
                        if valor_str:
                            # Handle both comma and dot as decimal separators
                            valor_str_normalized = valor_str.replace(',', '.')
                            if '.' in valor_str_normalized:
                                valor = float(valor_str_normalized)
                            else:
                                valor = float(int(valor_str_normalized))
                
                # Call add_new_version with individual parameters including valor
                # Note: status is state in the controller method signature
                result = callbacks['add_new_version'](
                    doc_id, version, status, file_paths, current_user, notes, valor
                )
                if result:
                    messagebox.showinfo("Éxito", "Nueva versión añadida exitosamente")
                    callbacks.get('back', lambda: None)()
                else:
                    messagebox.showerror("Error", "No se pudo añadir la nueva versión")
            else:
                messagebox.showerror("Error", "Funcionalidad no disponible")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al añadir versión: {str(e)}")

    # Add methods for other required forms
    def show_new_version_form(self, callbacks: dict, user_name: str = "", pre_selected_document: dict = None):
        """Show new version form"""
        # Store callbacks and pre-selected document for later use
        self.current_callbacks = callbacks
        self.pre_selected_document = pre_selected_document
        
        # Reset file selection for new upload session
        self.selected_files = []
        
        self.clear_window()
        self.center_window(750, 850)  # Increased height for better button visibility
        self.root.minsize(750, 800)  # Increased minimum size
        
        # Header
        self.create_header(self.root, "Nueva Versión - Licitación")
        
        # IMPORTANT: Create bottom frame FIRST - ensure it's always visible
        bottom_frame = ttk.Frame(self.root, padding="15")
        bottom_frame.pack(side="bottom", fill="x", expand=False)
        
        # Create buttons immediately to ensure they're always visible
        self._create_buttons(bottom_frame, callbacks, is_new_document=False)
        
        # Create main container with better separation from bottom frame
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Create scrollable main content within the container
        canvas = tk.Canvas(main_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Main frame inside canvas
        main_frame = ttk.Frame(canvas, padding="12")
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor="nw")
        
        # Configure canvas scrolling
        def configure_scroll(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Update scroll region after a delay to ensure all widgets are properly sized
            canvas.after_idle(lambda: canvas.configure(scrollregion=canvas.bbox("all")))
        
        def update_canvas_width(event):
            canvas_width = event.width
            canvas.itemconfig(canvas_window, width=canvas_width)
        
        main_frame.bind('<Configure>', configure_scroll)
        canvas.bind('<Configure>', update_canvas_width)
        
        # Form fields
        self._create_form_fields(main_frame, user_name, is_new_document=False)
        
        # Auto-populate fields if document is pre-selected from dashboard
        if self.pre_selected_document:
            self._populate_preselected_document_for_new_version()
        
        # Set focus after widget creation is complete
        self.root.after_idle(lambda: self.doc_id_entry.focus() if hasattr(self, 'doc_id_entry') else None)
        
        # Update scroll region after all widgets are created
        self.root.after(100, configure_scroll)
        
    def _populate_preselected_document_for_new_version(self):
        """Auto-populate form fields for new version with pre-selected document information."""
        if not self.pre_selected_document:
            return
        
        doc_id = self.pre_selected_document.get('id', '')
        doc_name = self.pre_selected_document.get('name', '')
        latest_version = self.pre_selected_document.get('version', '')
        current_status = self.pre_selected_document.get('status', 'S0')
        
        if doc_id:
            # Populate the document ID field (temporarily enable it to set the value)
            if hasattr(self, 'doc_id_entry'):
                self.doc_id_entry.config(state="normal")
                self.doc_id_entry.delete(0, tk.END)
                self.doc_id_entry.insert(0, doc_id)
                self.doc_id_entry.config(state="readonly")
            
            # Update info label to show it's pre-selected
            info_text = f"NUEVA VERSIÓN para: '{doc_name or doc_id}'"
            if latest_version:
                info_text += f". Versión actual: {latest_version}"
            info_text += " (seleccionado desde la tabla)"
            
            if hasattr(self, 'info_label') and self.info_label:
                self.info_label.config(
                    text=info_text,
                    foreground="blue"
                )
            
            # Set status based on current document status if available
            if hasattr(self, 'status_combo') and current_status:
                # Find matching status in the combo values
                for value in self.status_combo['values']:
                    if value.startswith(current_status):
                        self.status_combo.set(value)
                        break
        
    def show_update_stage_form(self, callbacks: dict, user_name: str = "", pre_selected_document: dict = None):
        """Show update stage form using UpdateStateForm - ultra-simplified version"""
        # Create state mapping for presupuestos
        state_map = {}
        for status in PRESUPUESTO_STATUSES:
            state_map[f"{status} - {STATUS_DISPLAY_NAMES[status]}"] = status
        
        # Create and show the UpdateStateForm
        update_form = UpdateStateForm(
            self.root,
            doc_type="licitaciones", 
            state_map=state_map
        )
        update_form.show(callbacks, user_name, pre_selected_document)
        
    def set_context_data(self, companies: List[str] = None, existing_doc_ids: List[str] = None):
        """Set context data for autocomplete and validation"""
        self.companies_list = companies or []
        self.existing_doc_ids = existing_doc_ids or []
        
    def store_callbacks(self, callbacks: dict):
        """Store callbacks for later use"""
        self.current_callbacks = callbacks

    # Add missing helper methods
    def _check_document_id(self, event=None):
        """Check if document ID exists"""
        pass
        
    def _on_id_change(self, event=None):
        """Handle document ID changes"""
        pass
        
    def _show_type_help(self):
        """Show help for document types"""
        from tkinter import messagebox
        help_text = """Tipos de documento:
        
• Licitación: Documento principal de presupuesto
• Adicionales: Trabajos adicionales a licitaciones aprobadas
• Mediciones: Mediciones y certificaciones de obra"""
        messagebox.showinfo("Ayuda - Tipos de Documento", help_text)
        
    def _show_status_help(self):
        """Show help for status"""
        from tkinter import messagebox
        help_text = """Estados del documento:
        
• S0 - Borrador: Trabajo en proceso. NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO
• S1 - Revisado por Delineación: NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO
• S2 - Revisado por Técnico Especialista: Revisado por técnico especialista
• S3 - Revisado por Director Proyecto: SE PUEDE ENVIAR A PROPIEDAD EN ESTE ESTADO
• S3A - Aprobado por propiedad/promotor: Aprobado por propiedad/promotor"""
        messagebox.showinfo("Ayuda - Estados", help_text)
        
    def _on_type_change(self, event=None):
        """Handle document type changes - show/hide valor and parent fields based on type"""
        if not hasattr(self, 'type_var') or not hasattr(self, 'valor_label'):
            print("DEBUG: Missing type_var or valor_label attributes")
            return
            
        # Get selected type display name and convert to internal type
        selected_type_display = self.type_var.get()
        
        # Convert display name back to internal type
        type_map = {v: k for k, v in TYPE_DISPLAY_NAMES.items()}
        selected_type = type_map.get(selected_type_display, selected_type_display)
        
        print(f"DEBUG: Type change - display='{selected_type_display}', internal='{selected_type}'")
        
        # Show valor field for presupuesto and adicional types
        if selected_type in ["presupuesto", "adicional"]:
            print("DEBUG: Showing valor field")
            self.valor_label.pack(anchor="w", pady=(0, 5))
            self.valor_entry.pack(anchor="w", pady=(5, 0))
        else:
            print("DEBUG: Hiding valor field")
            # Hide valor field for licitacion type
            self.valor_label.pack_forget()
            self.valor_entry.pack_forget()
            # Clear the field when hidden
            if hasattr(self, 'valor_entry') and self.valor_entry:
                self.valor_entry.delete(0, tk.END)
        
        # Show/hide company vs parent presupuesto field based on type
        if selected_type == "adicional":
            print("DEBUG: Showing parent presupuesto field for adicional")
            # Hide empresa field
            if hasattr(self, 'company_label'):
                self.company_label.pack_forget()
            if hasattr(self, 'company_entry'):
                self.company_entry.pack_forget()
                self.company_var.set("")
            
            # Show parent presupuesto field
            if hasattr(self, 'parent_label'):
                self.parent_label.pack(anchor="w", pady=(10, 5))
            if hasattr(self, 'parent_combo'):
                self.parent_combo.pack(anchor="w", pady=(0, 15))
                self._populate_parent_presupuestos()
        else:
            print("DEBUG: Showing empresa field for presupuesto/licitacion")
            # Hide parent presupuesto field
            if hasattr(self, 'parent_label'):
                self.parent_label.pack_forget()
            if hasattr(self, 'parent_combo'):
                self.parent_combo.pack_forget()
                self.parent_var.set("")
            
            # Show empresa field
            if hasattr(self, 'company_label'):
                self.company_label.pack(anchor="w", pady=(10, 5))
            if hasattr(self, 'company_entry'):
                self.company_entry.pack(anchor="w", pady=(0, 15))
        
    def _on_status_change(self, event=None):
        """Handle status changes"""
        pass
        
    def _on_lote_change(self, event=None):
        """Handle lote changes - refresh parent presupuestos for adicionales"""
        print(f"DEBUG: Lote changed to: {self.lote_var.get()}")
        # If we're in adicional mode, refresh the parent presupuestos
        if hasattr(self, 'type_var'):
            selected_type_display = self.type_var.get()
            type_map = {v: k for k, v in TYPE_DISPLAY_NAMES.items()}
            selected_type = type_map.get(selected_type_display, selected_type_display)
            
            if selected_type == "adicional" and hasattr(self, 'parent_combo'):
                self._populate_parent_presupuestos()
        
    def _populate_parent_presupuestos(self):
        """Populate parent presupuesto dropdown with accepted presupuestos from same lote"""
        if not hasattr(self, 'parent_combo') or not hasattr(self, 'current_callbacks'):
            return
            
        try:
            # Get current lote selection
            current_lote = self.lote_var.get().strip() if hasattr(self, 'lote_var') else ""
            if not current_lote:
                self.parent_combo['values'] = ["Seleccione primero un lote"]
                return
            
            # Get accepted presupuestos from same lote via callback
            if 'get_accepted_presupuestos_by_lote' in self.current_callbacks:
                accepted_presupuestos = self.current_callbacks['get_accepted_presupuestos_by_lote'](current_lote)
                
                if accepted_presupuestos:
                    # Format as "ID - Empresa (Valor)"
                    options = []
                    for presupuesto in accepted_presupuestos:
                        empresa = getattr(presupuesto, 'company', 'Sin empresa')
                        valor = getattr(presupuesto, 'valor', 0)
                        display_text = f"{presupuesto.name} - {empresa}"
                        if valor:
                            display_text += f" ({valor}€)"
                        options.append(display_text)
                    
                    self.parent_combo['values'] = options
                    print(f"DEBUG: Populated {len(options)} parent presupuestos for lote {current_lote}")
                else:
                    self.parent_combo['values'] = ["No hay presupuestos aceptados en este lote"]
                    print(f"DEBUG: No accepted presupuestos found for lote {current_lote}")
            else:
                self.parent_combo['values'] = ["Error: No se pudo cargar presupuestos"]
                print("DEBUG: get_accepted_presupuestos_by_lote callback not available")
                
        except Exception as e:
            print(f"ERROR populating parent presupuestos: {e}")
            self.parent_combo['values'] = ["Error al cargar presupuestos"]
        
    def _setup_valor_field_for_existing_document(self, doc_id: str, callbacks: dict):
        """Setup valor field visibility for new version form based on existing document type"""
        if not hasattr(self, 'valor_label') or not callbacks.get('get_document'):
            return
            
        try:
            existing_doc = callbacks['get_document'](doc_id)
            if existing_doc and hasattr(existing_doc, 'document_type'):
                if existing_doc.document_type in ["presupuesto", "adicional"]:
                    # Show valor field for presupuesto and adicional types
                    self.valor_label.pack(anchor="w", pady=(0, 5))
                    self.valor_entry.pack(anchor="w", pady=(5, 0))
                    
                    # Pre-populate with existing valor if available
                    if hasattr(existing_doc, 'valor') and existing_doc.valor:
                        self.valor_entry.delete(0, tk.END)
                        self.valor_entry.insert(0, str(existing_doc.valor))
                else:
                    # Hide valor field for licitacion type
                    self.valor_label.pack_forget()
                    self.valor_entry.pack_forget()
        except Exception as e:
            print(f"Error setting up valor field: {e}")