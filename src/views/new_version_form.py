import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
from pathlib import Path
import os
from typing import Callable, List, Optional
from .base_view import BaseView
from .assignment_dialog import AssignmentDialog
from utils.version_validator import VersionValidator
import difflib


class NewVersionForm(BaseView):
    def __init__(self, root: tk.Tk, doc_type: str):
        super().__init__(root)
        self.doc_type = doc_type
        self.doc_type_display = "Planos" if doc_type == "planos" else "Certificaciones"
        self.doc_type_singular = "plano" if doc_type == "planos" else "certificación"
        self.doc_type_gender = "female" if doc_type == "certificaciones" else "male"
        self.files_to_upload: List[str] = []
        self.callbacks = {}
        
        # Form fields
        self.submit_id_entry = None
        self.submit_name_entry = None
        self.submit_version_entry = None
        self.submit_notes_entry = None
        self.submit_author_entry = None
        self.submit_info_label = None
        self.files_listbox = None

        # DWG name field (for planos)
        self.dwg_name_entry = None
        self.dwg_name_label_widget = None
        self.dwg_name_help = None
        self.dwg_row = None
        self.details_frame = None
        self.dwg_name_visible = False

    def show(self, callbacks: dict, user_name: str = "", pre_selected_document: dict = None) -> None:
        """Show the new version form."""
        self.callbacks = callbacks
        self.user_name = user_name  # Store user_name for later use
        self.pre_selected_document = pre_selected_document
        self.clear_window()
        self.set_window_size(750, 700)  # Increased height for better button visibility
        
        # Header
        self.create_header(self.root)
        
        # Setup notification widget if callbacks are available
        if user_name and 'get_notification_data' in callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: callbacks.get('get_notification_data')(user_name),
                mark_read_callback=callbacks.get('mark_notification_as_read'),
                navigate_callback=callbacks.get('navigate_to_document'),
                current_user=user_name
            )
        
        # Create main container structure
        # IMPORTANT: Bottom container FIRST - fixed at bottom for buttons
        bottom_frame = ttk.Frame(self.root, padding="15")
        bottom_frame.pack(side="bottom", fill="x", expand=False)
        
        # Content container - expandable with proper separation from bottom
        main_content = ttk.Frame(self.root, padding="20")
        main_content.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.files_to_upload = []
        
        # Details frame
        details_frame = ttk.Frame(main_content)
        details_frame.pack(fill="x", pady=5)
        
        # Name field - read-only (already completed, cannot be changed)
        id_text = f"Nombre de la {self.doc_type_singular}:" if self.doc_type_gender == 'female' else f"Nombre del {self.doc_type_singular}:"
        ttk.Label(details_frame, text=id_text).grid(row=0, column=0, sticky="w", pady=5)
        self.submit_id_entry = ttk.Entry(details_frame, state="readonly")
        self.submit_id_entry.grid(row=0, column=1, sticky="ew", pady=5)
        
        # Info label
        info_text = f"Documento seleccionado - no se puede cambiar"
        self.submit_info_label = ttk.Label(details_frame, text=info_text, foreground="blue")
        self.submit_info_label.grid(row=1, column=0, columnspan=2, pady=5)
        
        # Status field (simplified)
        ttk.Label(details_frame, text="Estado:").grid(row=2, column=0, sticky="w", pady=5)
        self.status_combo = ttk.Combobox(details_frame, state="readonly")
        self.status_combo['values'] = ('S0 - Borrador', 'S1 - Revisado por Delineación', 'S2 - Revisado por Técnico Especialista', 'S3 - Revisado por Director Proyecto', 'S3A - Aprobado por propiedad/promotor')
        self.status_combo.set('S0 - Borrador')  # Default to S0
        self.status_combo.grid(row=2, column=1, sticky="ew", pady=5)
        
        # Version field with validation
        ttk.Label(details_frame, text="Nueva Versión:").grid(row=3, column=0, sticky="w", pady=5)
        self.submit_version_entry = ttk.Entry(details_frame)
        self.submit_version_entry.grid(row=3, column=1, sticky="ew", pady=5)
        
        # Version validation label
        self.version_validation_label = ttk.Label(details_frame, text="Formato: número.número (ej: 1.0, 2.1)", foreground="gray")
        self.version_validation_label.grid(row=3, column=2, sticky="w", padx=(10, 0), pady=5)
        
        # Bind version validation
        self.submit_version_entry.bind("<KeyRelease>", self._validate_version_input)
        
        # Notes field (optional)
        ttk.Label(details_frame, text="Notas (opcional):").grid(row=4, column=0, sticky="w", pady=5)
        self.submit_notes_entry = ttk.Entry(details_frame)
        self.submit_notes_entry.grid(row=4, column=1, sticky="ew", pady=5)

        # DWG Name field (only for planos) - shown when DWG is uploaded
        if self.doc_type == "planos":
            self.dwg_row = 5
            self.details_frame = details_frame

            # DWG name label and entry (initially hidden)
            self.dwg_name_label_widget = ttk.Label(details_frame, text="Nombre del DWG:")
            self.dwg_name_entry = ttk.Entry(details_frame)
            self.dwg_name_help = ttk.Label(
                details_frame,
                text="Nombre con el que se guardará el archivo DWG (por defecto = nombre del plano)",
                font=("Arial", 8),
                foreground="gray"
            )

        # Auto-populate fields if document is pre-selected from dashboard
        if self.pre_selected_document:
            self._populate_preselected_document()

        details_frame.columnconfigure(1, weight=1)
        details_frame.columnconfigure(2, weight=0)  # Version validation column
        
        # Files frame
        files_frame = ttk.LabelFrame(main_content, text="Archivos para la Versión", padding=10)
        files_frame.pack(fill="both", expand=True, pady=10)
        
        self.files_listbox = tk.Listbox(files_frame)
        self.files_listbox.pack(side="left", fill="both", expand=True)
        
        # Enable drag-and-drop for the files listbox
        self.enable_drag_and_drop_for_listbox(
            self.files_listbox,
            self._on_files_dropped
        )
        
        files_button_frame = ttk.Frame(files_frame)
        files_button_frame.pack(side="right", fill="y", padx=5)
        ttk.Button(files_button_frame, text="Añadir Archivo...", command=self.add_file_to_list).pack(pady=5)
        ttk.Button(files_button_frame, text="Quitar Archivo", command=self.remove_file_from_list).pack(pady=5)
        
        # Button frame
        # Button frame - moved to bottom container for always-visible buttons
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        # Main action button
        ttk.Button(button_frame, text="Registrar Versión", command=self.submit_new_version).pack(side="left", padx=20)
        
        # Approve button (for certificaciones, submit and approve in one step)
        if self.doc_type == "certificaciones":
            ttk.Button(button_frame, text="Registrar y Aprobar", command=self.submit_and_approve_version).pack(side="left", padx=10)
        
        ttk.Button(button_frame, text="<< Volver", command=callbacks['back']).pack(side="right", padx=20)

    def _populate_preselected_document(self) -> None:
        """Auto-populate form fields with pre-selected document information."""
        if not self.pre_selected_document:
            return
        
        doc_id = self.pre_selected_document.get('id', '')
        doc_name = self.pre_selected_document.get('name', '')
        latest_version = self.pre_selected_document.get('version', '')
        current_state = self.pre_selected_document.get('state', 'S0')
        
        if doc_id:
            # Populate the document ID field (temporarily enable it to set the value)
            self.submit_id_entry.config(state="normal")
            self.submit_id_entry.delete(0, tk.END)
            self.submit_id_entry.insert(0, doc_id)
            self.submit_id_entry.config(state="readonly")
            
            # Update info label to show it's pre-selected
            info_text = f"DOCUMENTO SELECCIONADO: '{doc_name or doc_id}'"
            if latest_version:
                info_text += f". Última versión: {latest_version}"
            info_text += " (seleccionado desde la tabla)"
            
            self.submit_info_label.config(
                text=info_text,
                foreground="blue"
            )
            
            # Set default status based on current document state
            status_mapping = {
                'S0': 'S0 - Borrador',
                'S1': 'S1 - Revisado por Delineación', 
                'S2': 'S2 - Revisado por Técnico Especialista',
                'S3': 'S3 - Revisado por Director Proyecto',
                'S3A': 'S3A - Aprobado por propiedad/promotor'
            }
            if current_state in status_mapping:
                self.status_combo.set(status_mapping[current_state])

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
        self.submit_id_entry.delete(0, tk.END)
        self.submit_id_entry.insert(0, suggested_id)
        # Trigger the check after setting the suggestion
        self.check_document_id()

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

    def on_id_change(self, event=None) -> None:
        """Handle real-time ID changes for fuzzy matching."""
        doc_id = self.submit_id_entry.get().strip()
        if not doc_id:
            info_text = f"Introduce un ID de {self.doc_type_singular}."
            self.submit_info_label.config(text=info_text, foreground="orange")
            return
        
        # Check for exact match first
        if 'check_document_exists' in self.callbacks:
            result = self.callbacks['check_document_exists'](doc_id)
            if result:
                doc_name, latest_version = result
                self.submit_info_label.config(
                    text=f"ACTUALIZACIÓN para '{doc_name}'. Última versión: {latest_version}",
                    foreground="green"
                )
                self.submit_name_entry.config(state="normal")
                self.submit_name_entry.delete(0, tk.END)
                self.submit_name_entry.insert(0, doc_name)
                self.submit_name_entry.config(state="disabled")
                return
        
        # Check for fuzzy matches
        fuzzy_matches = self.get_fuzzy_matches(doc_id)
        
        # Clear previous click bindings
        self.submit_info_label.unbind("<Button-1>")
        
        if fuzzy_matches:
            # Show the best match as a suggestion
            best_match, similarity = fuzzy_matches[0]
            if similarity > 0.6:  # High similarity
                self.submit_info_label.config(
                    text=f"¿Quizás quisiste decir '{best_match}'? (Haz clic para usar)",
                    foreground="gold"
                )
                # Make the label clickable
                self.submit_info_label.bind("<Button-1>", lambda e: self.use_suggestion(best_match))
            else:
                # Show multiple suggestions - create a more interactive display
                suggestions = [match for match, _ in fuzzy_matches[:3]]
                suggestions_text = f"Sugerencias: {', '.join(suggestions)} (Haz clic para opciones)"
                self.submit_info_label.config(
                    text=suggestions_text,
                    foreground="purple"
                )
                # Make it clickable to show suggestion menu
                self.submit_info_label.bind("<Button-1>", lambda e: self.show_suggestion_menu(suggestions))
        else:
            # No matches found
            self.submit_info_label.config(
                text=f"NUEVO {self.doc_type_singular.upper()}. Se creará un nuevo registro.",
                foreground="orange"
            )
            self.submit_name_entry.config(state="normal")
            self.submit_name_entry.delete(0, tk.END)

    def check_document_id(self, event=None) -> None:
        """Check if document ID exists and update UI accordingly."""
        # This method is kept for backward compatibility and explicit checks
        # The main logic is now handled in on_id_change for real-time feedback
        self.on_id_change()

    def add_file_to_list(self) -> None:
        """Add files to the upload list."""
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
            except:
                initial_dir = os.getcwd()
            
            # Force focus to root window first
            self.root.focus_force()
            self.root.lift()
            
            # Use a more robust file dialog approach
            filepaths = None
            try:
                # On macOS, sometimes the parent needs to be None to avoid crashes
                parent_window = None if sys.platform == 'darwin' else self.root
                
                filepaths = filedialog.askopenfilenames(
                    parent=parent_window,
                    title="Seleccionar Archivos (PDF, DWG, etc.)",
                    initialdir=initial_dir,
                    filetypes=[
                        ("Archivos PDF", "*.pdf"),
                        ("Archivos DWG", "*.dwg"),
                        ("Todos los Archivos", "*.*")
                    ]
                )
            except Exception as dialog_error:
                print(f"File dialog error: {dialog_error}")
                # Fallback: try without parent
                filepaths = filedialog.askopenfilenames(
                    title="Seleccionar Archivos (PDF, DWG, etc.)",
                    initialdir=initial_dir,
                    filetypes=[("Todos los Archivos", "*.*")]
                )
            
            if filepaths:
                added_count = 0
                for filepath in filepaths:
                    try:
                        if os.path.exists(filepath) and filepath not in self.files_to_upload:
                            self.files_to_upload.append(filepath)
                            added_count += 1
                    except Exception as path_error:
                        print(f"Error processing file path {filepath}: {path_error}")
                        continue

                # Validate: only one DWG allowed per entry
                dwg_files = [f for f in self.files_to_upload if f.lower().endswith('.dwg')]
                if len(dwg_files) > 1:
                    # Remove all but the first DWG
                    first_dwg = dwg_files[0]
                    extra_dwgs = dwg_files[1:]
                    for dwg in extra_dwgs:
                        self.files_to_upload.remove(dwg)
                        added_count -= 1
                    messagebox.showwarning(
                        "Solo un DWG permitido",
                        f"Solo se permite un archivo DWG por entrada.\n\n"
                        f"Se mantuvo: {os.path.basename(first_dwg)}\n"
                        f"Se eliminaron: {', '.join(os.path.basename(d) for d in extra_dwgs)}"
                    )

                if added_count > 0:
                    self.refresh_files_listbox()
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

    def remove_file_from_list(self) -> None:
        """Remove selected files from the upload list."""
        selection_indices = self.files_listbox.curselection()
        if not selection_indices:
            messagebox.showwarning("Aviso", "Por favor, selecciona un archivo de la lista para quitar.")
            return
        
        for index in reversed(selection_indices):
            self.files_to_upload.pop(index)
        self.refresh_files_listbox()

    def refresh_files_listbox(self) -> None:
        """Refresh the files listbox display."""
        self.files_listbox.delete(0, tk.END)
        for filepath in self.files_to_upload:
            self.files_listbox.insert(tk.END, os.path.basename(filepath))

        # Update DWG name field visibility (for planos)
        self._update_dwg_name_visibility()
    
    def _on_files_dropped(self, path_objects: List[Path]) -> None:
        """Handle files dropped onto the listbox.

        Args:
            path_objects: List of Path objects for the dropped files
        """
        try:
            added_count = 0
            for path_obj in path_objects:
                # Convert Path to string for consistency with existing code
                filepath = str(path_obj)
                if filepath not in self.files_to_upload:
                    self.files_to_upload.append(filepath)
                    added_count += 1

            # Validate: only one DWG allowed per entry
            dwg_files = [f for f in self.files_to_upload if f.lower().endswith('.dwg')]
            if len(dwg_files) > 1:
                # Remove all but the first DWG
                first_dwg = dwg_files[0]
                extra_dwgs = dwg_files[1:]
                for dwg in extra_dwgs:
                    self.files_to_upload.remove(dwg)
                    added_count -= 1
                messagebox.showwarning(
                    "Solo un DWG permitido",
                    f"Solo se permite un archivo DWG por entrada.\n\n"
                    f"Se mantuvo: {os.path.basename(first_dwg)}\n"
                    f"Se eliminaron: {', '.join(os.path.basename(d) for d in extra_dwgs)}"
                )

            if added_count > 0:
                self.refresh_files_listbox()
                messagebox.showinfo("Éxito", f"Se agregaron {added_count} archivos mediante arrastrar y soltar.")
        except Exception as e:
            print(f"Error handling dropped files: {e}")

    def submit_new_version(self) -> None:
        """Submit the new version form at state S0."""
        self._submit_version_with_state("S0", "registrado")
    
    def submit_and_approve_version(self) -> None:
        """Submit and approve the new version form at state A (Approved)."""
        self._submit_version_with_state("A", "registrado y aprobado")
    
    def _submit_version_with_state(self, state: str, action_description: str) -> None:
        """Internal method to submit version with specified state."""
        doc_id = self.submit_id_entry.get().strip()
        version = self.submit_version_entry.get().strip()
        notes = self.submit_notes_entry.get().strip()
        
        # Get status from combo box
        status_selection = self.status_combo.get()
        if status_selection and " - " in status_selection:
            status = status_selection.split(" - ")[0]  # Extract S0, S1, etc.
        else:
            status = state  # Fallback to passed state
        
        # Get document name from pre-selected document if available
        doc_name = ""
        if self.pre_selected_document:
            doc_name = self.pre_selected_document.get('name', '') or self.pre_selected_document.get('id', '')
        
        # Validation - simplified to essential fields only
        missing_fields = []
        if not doc_id:
            missing_fields.append("Nombre del documento")
        if not version:
            missing_fields.append("Versión")
        if not self.files_to_upload:
            missing_fields.append("Al menos un archivo")
            
        if missing_fields:
            messagebox.showwarning("Campos Requeridos", 
                                 "Por favor, complete los siguientes campos:\n• " + "\n• ".join(missing_fields))
            return
        
        # Validate version format
        version_result = VersionValidator.validate_version(version)
        if not version_result['is_valid']:
            messagebox.showerror("Versión Inválida", version_result['message'])
            return
        
        # Convert file paths to Path objects
        file_paths = [Path(fp) for fp in self.files_to_upload]

        # Get custom DWG name (only for planos, when DWG is uploaded)
        dwg_name = ""
        if self.dwg_name_entry and self.dwg_name_visible:
            dwg_name = self.dwg_name_entry.get().strip()

        # Call the submission callback
        if 'submit_new_version' in self.callbacks:
            try:
                # Use the stored user_name or fall back to system username
                author = getattr(self, 'user_name', None) or ""
                if not author:
                    import getpass
                    try:
                        author = getpass.getuser()
                    except:
                        author = "Usuario"
                self.callbacks['submit_new_version'](doc_id, doc_name or doc_id, version, status, file_paths, author, notes, dwg_name=dwg_name)
                messagebox.showinfo("Éxito", f"{self.doc_type_singular} '{doc_id}' versión '{version}' {action_description} con éxito.")
                self.callbacks['back']()
            except Exception as e:
                messagebox.showerror("Error", f"Error al registrar la versión: {str(e)}")

    def _update_dwg_name_visibility(self):
        """Show/hide DWG name field based on whether a DWG file is uploaded."""
        if self.doc_type != "planos" or not self.dwg_name_entry:
            return

        # Check if any DWG file is in the upload list
        has_dwg = any(fp.lower().endswith('.dwg') for fp in self.files_to_upload)

        if has_dwg and not self.dwg_name_visible:
            # Show DWG name field
            self.dwg_name_label_widget.grid(row=self.dwg_row, column=0, sticky="w", pady=5)
            self.dwg_name_entry.grid(row=self.dwg_row, column=1, sticky="ew", pady=5)
            self.dwg_name_help.grid(row=self.dwg_row + 1, column=0, columnspan=2, pady=2)

            # Set default value to entry name if empty
            if not self.dwg_name_entry.get().strip():
                entry_name = self.submit_id_entry.get().strip() if self.submit_id_entry else ""
                if entry_name:
                    self.dwg_name_entry.delete(0, tk.END)
                    self.dwg_name_entry.insert(0, entry_name)

            self.dwg_name_visible = True

        elif not has_dwg and self.dwg_name_visible:
            # Hide DWG name field
            self.dwg_name_label_widget.grid_forget()
            self.dwg_name_entry.grid_forget()
            self.dwg_name_help.grid_forget()
            self.dwg_name_visible = False

    def get_form_data(self) -> dict:
        """Get current form data."""
        # Get custom DWG name (only for planos, when DWG is uploaded)
        dwg_name = ""
        if self.dwg_name_entry and self.dwg_name_visible:
            dwg_name = self.dwg_name_entry.get().strip()

        return {
            'doc_id': self.submit_id_entry.get().strip() if self.submit_id_entry else "",
            'version': self.submit_version_entry.get().strip() if self.submit_version_entry else "",
            'notes': self.submit_notes_entry.get().strip() if self.submit_notes_entry else "",
            'status': self.status_combo.get() if hasattr(self, 'status_combo') else "",
            'files': self.files_to_upload.copy(),
            'dwg_name': dwg_name
        }
    
    def check_form_completeness(self, event=None) -> None:
        """Check if form is complete enough to enable assignment button."""
        form_data = self.get_form_data()
        
        # Check if document exists (this is a new version of existing document)
        # and has basic form data filled
        if (form_data['doc_id'] and 
            form_data['version'] and
            form_data['status']):
            self.enable_assignment_button()
        else:
            self.disable_assignment_button()
    
    def show_assignment_dialog(self) -> None:
        """Show assignment dialog for version workflow assignment"""
        form_data = self.get_form_data()
        
        # Validate required fields
        if not all([form_data['doc_id'], form_data['version'], form_data['status']]):
            messagebox.showwarning("Campos Incompletos", 
                                 "Completa los campos obligatorios antes de asignar responsables.")
            return
        
        # Check if document exists to determine current state
        current_doc = None
        if 'check_document_exists' in self.callbacks:
            result = self.callbacks['check_document_exists'](form_data['doc_id'])
            if result:
                # Document exists, get current state
                if 'get_document' in self.callbacks:
                    current_doc = self.callbacks['get_document'](form_data['doc_id'])
            else:
                messagebox.showwarning("Documento No Encontrado", 
                                     "El documento especificado no existe. Registra el documento primero.")
                return
        
        if not current_doc:
            messagebox.showwarning("Error", "No se pudo obtener la información del documento.")
            return
        
        current_state = current_doc.current_state
        
        # Determine next state for new version workflow
        # New versions typically start in S0 and need assignment to S1
        next_state = "S1"  # New versions need technical review
        
        try:
            # Get project_path from callbacks if available
            project_path = None
            if 'get_project_path' in self.callbacks:
                project_path = self.callbacks['get_project_path']()
            
            dialog = AssignmentDialog(
                parent=self.root,
                document_id=form_data['doc_id'],
                document_name=form_data.get('name', form_data['doc_id']),  # Use doc_id as fallback for name
                from_state="S0",  # New versions start at S0
                to_state=next_state,
                project_path=project_path
            )
            
            result = dialog.show()
            
            if result and result != "skipped":
                messagebox.showinfo("Asignación Creada", 
                                  f"Se ha creado la asignación para la nueva versión S0→{next_state}.\n\n"
                                  f"Los responsables serán notificados después de registrar la versión.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al mostrar el diálogo de asignación: {e}")
    
    def enable_assignment_button(self) -> None:
        """Enable assignment button when form is valid"""
        if hasattr(self, 'assign_btn'):
            self.assign_btn.config(state="normal")
    
    def disable_assignment_button(self) -> None:
        """Disable assignment button"""
        if hasattr(self, 'assign_btn'):
            self.assign_btn.config(state="disabled")
    
    def _validate_version_input(self, event=None) -> None:
        """Validate version input in real-time and update UI feedback."""
        version = self.submit_version_entry.get().strip()
        
        if not version:
            # Empty field - show format hint
            self.version_validation_label.config(
                text="Formato: número.número (ej: 1.0, 2.1)",
                foreground="gray"
            )
            return
        
        # Validate version format
        result = VersionValidator.validate_version(version)
        
        if result['is_valid']:
            # Valid version - show success
            self.version_validation_label.config(
                text=f"✅ {result['normalized']}",
                foreground="green"
            )
        else:
            # Invalid version - show error
            self.version_validation_label.config(
                text=f"❌ {result['message']}",
                foreground="red"
            )