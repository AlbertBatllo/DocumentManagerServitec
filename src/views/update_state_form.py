import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Callable, Optional, List, Tuple
from pathlib import Path
from .base_view import BaseView
from .assignment_dialog import AssignmentDialog
import difflib


class UpdateStateForm(BaseView):
    def __init__(self, root: tk.Tk, doc_type: str, state_map: dict):
        super().__init__(root)
        self.doc_type = doc_type
        
        # Set display names based on doc_type
        if doc_type == "planos":
            self.doc_type_display = "Planos"
            self.doc_type_singular = "plano"
            self.doc_type_gender = "male"
        elif doc_type == "certificaciones":
            self.doc_type_display = "Certificaciones"
            self.doc_type_singular = "certificación"
            self.doc_type_gender = "female"
        elif doc_type == "licitaciones":
            self.doc_type_display = "Presupuestos"
            self.doc_type_singular = "presupuesto"
            self.doc_type_gender = "male"
        else:
            # Default fallback
            self.doc_type_display = doc_type.title()
            self.doc_type_singular = doc_type[:-1] if doc_type.endswith('s') else doc_type
            self.doc_type_gender = "male"
        
        self.state_map = state_map
        self.callbacks = {}
        
        # Form fields
        self.blueprint_id_entry = None
        self.info_label = None
        self.new_state_combo = None
        self.notes_entry = None
        self.author_entry = None
        self.presupuesto_entry = None
        self.presupuesto_label = None
        
        # File upload fields
        self.files_to_upload: List[str] = []
        self.files_listbox = None
        self.file_upload_frame = None

    def show(self, callbacks: dict, user_name: str = "", pre_selected_document: dict = None) -> None:
        """Show the update state form."""
        self.callbacks = callbacks
        self.user_name = user_name  # Store user_name for later use
        self.pre_selected_document = pre_selected_document
        self.clear_window()
        self.set_window_size(750, 650)
        
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
        self.create_header(self.root)
        
        # Create main container structure
        # IMPORTANT: Bottom container FIRST - fixed at bottom for buttons
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(side="bottom", fill="x")
        
        # Content container - expandable
        main_content = ttk.Frame(self.root, padding="20")
        main_content.pack(fill="both", expand=True)
        
        # Name field - read-only (already completed, cannot be changed)
        id_text = f"Nombre de la {self.doc_type_singular}:" if self.doc_type_gender == 'female' else f"Nombre del {self.doc_type_singular}:"
        ttk.Label(main_content, text=id_text).grid(row=0, column=0, sticky="w", pady=5)
        self.blueprint_id_entry = ttk.Entry(main_content, state="readonly")
        self.blueprint_id_entry.grid(row=0, column=1, sticky="ew", pady=5)
        
        # Info label - initialize with blue message for selected documents
        info_text = f"Documento seleccionado - no se puede cambiar"
        self.info_label = ttk.Label(main_content, text=info_text, foreground="blue")
        self.info_label.grid(row=1, column=0, columnspan=2, pady=5)
        
        # New state field - this is the main field for changing state
        ttk.Label(main_content, text="Nuevo Estado:").grid(row=2, column=0, sticky="w", pady=5)
        self.new_state_combo = ttk.Combobox(
            main_content, 
            state="readonly",
            values=list(self.state_map.keys())
        )
        self.new_state_combo.grid(row=2, column=1, sticky="ew", pady=5)
        
        # Presupuesto Contratado field - shown only for licitaciones when state A is selected
        self.presupuesto_label = ttk.Label(main_content, text="Presupuesto Contratado (€):")
        self.presupuesto_entry = ttk.Entry(main_content)
        
        # Bind state change to show/hide presupuesto field
        self.new_state_combo.bind("<<ComboboxSelected>>", self._on_state_change)
        
        # Optional file upload section
        self._create_file_upload_section(main_content)
        
        # Auto-populate fields if document is pre-selected from dashboard
        if self.pre_selected_document:
            self._populate_preselected_document()
        
        # Button frame - ultra-simplified with only essential buttons
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(fill="x", pady=10)
        
        # Single action button - just change state
        ttk.Button(button_frame, text="Cambiar Estado", command=self.update_document_state, 
                  style="Accent.TButton").pack(side="left", padx=20)
        
        ttk.Button(button_frame, text="Cancelar", command=callbacks['back']).pack(side="right", padx=20)
        
        main_content.columnconfigure(1, weight=1)
        
        # Auto-populate form if document is pre-selected
        self._populate_preselected_document()

    def _create_file_upload_section(self, parent: ttk.Frame) -> None:
        """Create optional file upload section."""
        # File upload section (optional)
        separator = ttk.Separator(parent, orient="horizontal")
        separator.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(20, 10))
        
        file_label = ttk.Label(parent, text="Archivos adicionales (opcional):", font=("TkDefaultFont", 9, "bold"))
        file_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 5))
        
        help_label = ttk.Label(parent, text="Puedes adjuntar archivos relacionados con el cambio de estado", 
                              font=("TkDefaultFont", 8), foreground="gray")
        help_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 10))
        
        # File upload frame
        self.file_upload_frame = ttk.Frame(parent)
        self.file_upload_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=5)
        
        # Files listbox with scrollbar
        files_frame = ttk.Frame(self.file_upload_frame)
        files_frame.pack(fill="both", expand=True)
        
        self.files_listbox = tk.Listbox(files_frame, height=4, selectmode="extended")
        files_scrollbar = ttk.Scrollbar(files_frame, orient="vertical", command=self.files_listbox.yview)
        self.files_listbox.configure(yscrollcommand=files_scrollbar.set)
        
        self.files_listbox.pack(side="left", fill="both", expand=True)
        files_scrollbar.pack(side="right", fill="y")
        
        # File buttons frame
        file_buttons_frame = ttk.Frame(self.file_upload_frame)
        file_buttons_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Button(file_buttons_frame, text="Agregar Archivos", 
                  command=self._select_files).pack(side="left", padx=(0, 5))
        ttk.Button(file_buttons_frame, text="Eliminar Seleccionado", 
                  command=self._remove_selected_files).pack(side="left", padx=5)
        ttk.Button(file_buttons_frame, text="Limpiar Todo", 
                  command=self._clear_all_files).pack(side="left", padx=5)

    def _populate_preselected_document(self) -> None:
        """Auto-populate form fields with pre-selected document information."""
        if not self.pre_selected_document:
            return
        
        doc_id = self.pre_selected_document.get('id', '')
        doc_name = self.pre_selected_document.get('name', '')
        current_state = self.pre_selected_document.get('state', '')
        latest_version = self.pre_selected_document.get('version', '')
        
        if doc_id:
            # Populate the document ID field (temporarily enable it to set the value)
            self.blueprint_id_entry.config(state="normal")
            self.blueprint_id_entry.delete(0, tk.END)
            self.blueprint_id_entry.insert(0, doc_id)
            self.blueprint_id_entry.config(state="readonly")
            
            # Update info label to show it's pre-selected with essential information
            info_text = f"CAMBIAR ESTADO de: '{doc_name or doc_id}'"
            if latest_version:
                info_text += f". Versión: {latest_version}"
            if current_state:
                state_display = self.state_map.get(current_state, current_state)
                info_text += f" | Estado actual: {state_display}"
            info_text += " (seleccionado desde la tabla)"
            
            self.info_label.config(
                text=info_text,
                foreground="blue"
            )
            
            # Check form completeness after auto-population
            self.check_form_completeness()
    

    def find_document(self, event=None) -> None:
        """Find document by ID."""
        # This method is kept for backward compatibility and explicit checks
        # The main logic is now handled in on_id_change for real-time feedback
        self.on_id_change()
    
    def on_id_change(self, event=None) -> None:
        """Handle real-time ID changes for fuzzy matching."""
        doc_id = self.blueprint_id_entry.get().strip()
        if not doc_id:
            info_text = f"Introduce un ID de {self.doc_type_singular}."
            self.info_label.config(text=info_text, foreground="orange")
            return
        
        # Check for exact match first
        if 'check_document_exists' in self.callbacks:
            result = self.callbacks['check_document_exists'](doc_id)
            if result:
                doc_name, latest_version = result
                # Get current state for display
                current_state = "S0"  # Default
                if 'get_document' in self.callbacks:
                    document = self.callbacks['get_document'](doc_id)
                    if document:
                        current_state = document.current_state
                
                self.info_label.config(
                    text=f"Encontrado: '{doc_name}'. Versión: {latest_version} | Estado: {self.state_map.get(current_state, current_state)}",
                    foreground="green"
                )
                return
        
        # Check for fuzzy matches
        fuzzy_matches = self.get_fuzzy_matches(doc_id)
        
        # Clear previous click bindings
        self.info_label.unbind("<Button-1>")
        
        if fuzzy_matches:
            # Show the best match as a suggestion
            best_match, similarity = fuzzy_matches[0]
            if similarity > 0.6:  # High similarity
                self.info_label.config(
                    text=f"¿Quizás quisiste decir '{best_match}'? (Haz clic para usar)",
                    foreground="gold"
                )
                # Make the label clickable
                self.info_label.bind("<Button-1>", lambda e: self.use_suggestion(best_match))
            else:
                # Show multiple suggestions - create a more interactive display
                suggestions = [match for match, _ in fuzzy_matches[:3]]
                suggestions_text = f"Sugerencias: {', '.join(suggestions)} (Haz clic para opciones)"
                self.info_label.config(
                    text=suggestions_text,
                    foreground="purple"
                )
                # Make it clickable to show suggestion menu
                self.info_label.bind("<Button-1>", lambda e: self.show_suggestion_menu(suggestions))
        else:
            # No matches found - show positive message like New Version form
            self.info_label.config(
                text=f"No se encontraron coincidencias. Verificar nombre del {self.doc_type_singular}.",
                foreground="orange"
            )
        
        # Check form completeness for assignment button after any ID change
        self.check_form_completeness()
    
    def _on_state_change(self, event=None) -> None:
        """Handle state changes for licitaciones to show/hide conditional fields."""
        if self.doc_type != "licitaciones":
            return
            
        selected_state = self.new_state_combo.get()
        
        # Find the state key from display value
        state_key = None
        for key, display in self.state_map.items():
            if display == selected_state:
                state_key = key
                break
        
        # Show presupuesto field when state is A (Aprobado) for certificacion creation
        show_presupuesto = (state_key == "A")
        
        if show_presupuesto and self.presupuesto_label and self.presupuesto_entry:
            self.presupuesto_label.grid(row=3, column=0, sticky="w", pady=5)
            self.presupuesto_entry.grid(row=3, column=1, sticky="ew", pady=5)
        elif self.presupuesto_label and self.presupuesto_entry:
            self.presupuesto_label.grid_remove()
            self.presupuesto_entry.grid_remove()
    
    def get_fuzzy_matches(self, search_term: str, max_matches: int = 3) -> List[tuple]:
        """Get fuzzy matches for document IDs."""
        if not search_term or 'get_all_document_ids' not in self.callbacks:
            return []
        
        all_ids = self.callbacks['get_all_document_ids']()
        if not all_ids:
            return []
        
        # Use difflib for fuzzy matching
        matches = difflib.get_close_matches(
            search_term.upper(), 
            all_ids, 
            n=max_matches, 
            cutoff=0.3  # Lower cutoff for more lenient matching
        )
        
        # Return matches with their similarity scores
        result = []
        for match in matches:
            similarity = difflib.SequenceMatcher(None, search_term.upper(), match).ratio()
            result.append((match, similarity))
        
        return result

    def use_suggestion(self, suggested_id: str) -> None:
        """Use a suggested ID by filling it in the entry field."""
        self.blueprint_id_entry.delete(0, tk.END)
        self.blueprint_id_entry.insert(0, suggested_id)
        # Trigger the check after setting the suggestion
        self.on_id_change()

    def show_suggestion_menu(self, suggestions: List[str]) -> None:
        """Show a context menu with suggestions."""
        menu = tk.Menu(self.root, tearoff=0)
        for suggestion in suggestions:
            menu.add_command(
                label=suggestion,
                command=lambda s=suggestion: self.use_suggestion(s)
            )
        
        try:
            # Get the current mouse position
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def check_form_completeness(self, event=None) -> None:
        """Simplified form validation - no assignment complexity needed."""
        # Form is always complete if document is selected and state is chosen
        pass

    def update_document_state(self) -> None:
        """Update the document state - simplified validation."""
        doc_id = self.blueprint_id_entry.get().strip()
        new_state_display = self.new_state_combo.get()
        
        # Convert display name back to status code using reverse mapping
        # Handle both formats: "Display Name" and "CODE - Display Name"
        if " - " in new_state_display:
            # Format is "CODE - Display Name", extract the code
            new_state = new_state_display.split(" - ")[0]
        else:
            # Format is just "Display Name", use reverse mapping
            reverse_map = {v: k for k, v in self.state_map.items()}
            new_state = reverse_map.get(new_state_display, new_state_display)
        
        # Simplified validation - only require document name and new state
        missing_fields = []
        if not doc_id:
            missing_fields.append("Nombre del documento")
        if not new_state_display:
            missing_fields.append("Nuevo estado")
            
        if missing_fields:
            messagebox.showwarning("Campos Requeridos", 
                                 "Por favor, complete los siguientes campos:\n• " + "\n• ".join(missing_fields))
            return
        
        # Check if document exists
        if 'get_document' in self.callbacks:
            document = self.callbacks['get_document'](doc_id)
            if not document:
                messagebox.showerror("Error", f"ID de {self.doc_type_singular} no encontrado. Por favor, verifícalo.")
                return
        
        # Call the appropriate update callback directly (simplified approach)
        try:
            # Use the stored user_name or fall back to system username
            author = getattr(self, 'user_name', None) or ""
            if not author:
                import getpass
                try:
                    author = getpass.getuser()
                except:
                    author = "Usuario"
            
            # Try to call the appropriate callback based on document type
            if 'update_document_state' in self.callbacks:
                # Prepare file paths if any files are selected
                file_paths = [Path(fp) for fp in self.files_to_upload] if self.files_to_upload else None
                
                result = self.callbacks['update_document_state'](
                    doc_id=doc_id, 
                    new_state=new_state, 
                    author=author, 
                    notes="",  # No notes field in simplified form
                    file_paths=file_paths  # Pass optional file paths
                )
                
                if result and not result.startswith("Error"):
                    messagebox.showinfo("Éxito", result)
                    self.callbacks['back']()
                else:
                    messagebox.showerror("Error", result or "Error desconocido al actualizar el estado")
                    
            elif 'update_document_status' in self.callbacks:
                # Get presupuesto_contratado if needed for certificacion creation
                presupuesto_contratado = None
                
                # Check if presupuesto field is visible and has value
                if (self.doc_type == "licitaciones" and new_state == "A" and 
                    self.presupuesto_entry and self.presupuesto_entry.winfo_viewable()):
                    presupuesto_str = self.presupuesto_entry.get().strip()
                    if presupuesto_str:
                        try:
                            presupuesto_contratado = float(presupuesto_str.replace(',', '.'))
                            if presupuesto_contratado <= 0:
                                raise ValueError("El presupuesto debe ser mayor que cero")
                        except ValueError:
                            messagebox.showerror("Error", "El presupuesto contratado debe ser un número válido mayor que cero")
                            return
                    else:
                        messagebox.showerror("Error", "El presupuesto contratado es requerido para aprobar un presupuesto")
                        return
                
                # Prepare file paths if any files are selected
                file_paths = [Path(fp) for fp in self.files_to_upload] if self.files_to_upload else None
                
                result = self.callbacks['update_document_status'](
                    doc_id, 
                    new_state, 
                    author, 
                    "",  # No notes field
                    presupuesto_contratado,  # For certificacion creation
                    None,  # parent_licitacion_name
                    None,  # importe_adicional
                    True,  # create_certificacion
                    file_paths  # Pass optional file paths
                )
                
                if result and not result.startswith("Error"):
                    messagebox.showinfo("Éxito", result)
                    self.callbacks['back']()
                else:
                    messagebox.showerror("Error", result or "Error desconocido al actualizar el estado")
            else:
                messagebox.showerror("Error", "No se encontró el callback apropiado para actualizar el estado")
                
        except Exception as e:
            # Comprehensive error handling
            print(f"Error in update_document_state: {type(e).__name__}: {e}")
            messagebox.showerror("Error", f"Error al actualizar el estado: {str(e)}")
    
    def _update_document_state_fallback(self, doc_id: str, new_state: str, author: str):
        """Fallback method for document state updates without safe wrapper"""
        try:
            if 'update_document_state' in self.callbacks:
                # Prepare file paths if any files are selected
                file_paths = [Path(fp) for fp in self.files_to_upload] if self.files_to_upload else None
                
                result = self.callbacks['update_document_state'](
                    doc_id=doc_id, 
                    new_state=new_state, 
                    author=author, 
                    notes="",
                    file_paths=file_paths
                )
                messagebox.showinfo("Éxito", result)
                self.callbacks['back']()
            else:
                messagebox.showerror("Error", "No se encontró el callback apropiado para actualizar el estado")
        except Exception as e:
            messagebox.showerror("Error", f"Error al actualizar el estado: {str(e)}")

    def _select_files(self) -> None:
        """Open file dialog to select files for upload."""
        filetypes = [
            ("Archivos PDF", "*.pdf"),
            ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp"),
            ("Documentos Word", "*.doc *.docx"),
            ("Hojas Excel", "*.xls *.xlsx"),
            ("Todos los archivos", "*.*")
        ]
        
        filepaths = filedialog.askopenfilenames(
            title=f"Seleccionar archivos para adjuntar al cambio de estado",
            filetypes=filetypes
        )
        
        if filepaths:
            self._add_files_to_list(filepaths)
    
    def _add_files_to_list(self, filepaths: List[str]) -> None:
        """Add selected files to the upload list with validation."""
        MAX_FILE_SIZE_MB = 50
        ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.txt'}
        
        for filepath in filepaths:
            if filepath not in self.files_to_upload:
                # Validate file extension
                file_path = Path(filepath)
                extension = file_path.suffix.lower()
                
                if extension not in ALLOWED_EXTENSIONS:
                    messagebox.showwarning("Archivo no válido", 
                                         f"El archivo '{file_path.name}' no tiene una extensión permitida.\n"
                                         f"Extensiones permitidas: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
                    continue
                
                # Validate file size
                try:
                    file_size_mb = file_path.stat().st_size / (1024 * 1024)
                    if file_size_mb > MAX_FILE_SIZE_MB:
                        messagebox.showwarning("Archivo demasiado grande", 
                                             f"El archivo '{file_path.name}' ({file_size_mb:.1f} MB) "
                                             f"excede el límite de {MAX_FILE_SIZE_MB} MB")
                        continue
                except OSError:
                    messagebox.showerror("Error", f"No se puede acceder al archivo '{file_path.name}'")
                    continue
                
                self.files_to_upload.append(filepath)
                # Show filename with size info in the listbox for readability
                size_str = f" ({file_size_mb:.1f} MB)" if file_size_mb >= 1 else f" ({file_path.stat().st_size} bytes)"
                display_name = f"{file_path.name}{size_str}"
                self.files_listbox.insert(tk.END, display_name)
    
    def _remove_selected_files(self) -> None:
        """Remove selected files from the upload list."""
        selected_indices = self.files_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Selección", "Por favor, selecciona archivos para eliminar")
            return
        
        # Remove in reverse order to maintain indices
        for index in reversed(selected_indices):
            self.files_listbox.delete(index)
            if index < len(self.files_to_upload):
                self.files_to_upload.pop(index)
    
    def _clear_all_files(self) -> None:
        """Clear all files from the upload list."""
        if self.files_to_upload and messagebox.askyesno("Confirmar", "¿Eliminar todos los archivos seleccionados?"):
            self.files_to_upload.clear()
            self.files_listbox.delete(0, tk.END)

    def get_form_data(self) -> dict:
        """Get current form data - simplified for essential fields only."""
        return {
            'doc_id': self.blueprint_id_entry.get().strip() if self.blueprint_id_entry else "",
            'new_state': self.new_state_combo.get() if self.new_state_combo else "",
            'files_to_upload': self.files_to_upload.copy()
        }
    
