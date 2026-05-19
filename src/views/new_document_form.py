import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog
from pathlib import Path
import os
from typing import Callable, List, Optional
from .base_view import BaseView
from .assignment_dialog import AssignmentDialog


class NewDocumentForm(BaseView):
    def __init__(self, root: tk.Tk, doc_type: str):
        super().__init__(root)
        self.doc_type = doc_type
        self.doc_type_display = "Planos" if doc_type == "planos" else "Certificaciones"
        self.doc_type_singular = "plano" if doc_type == "planos" else "certificación"
        self.doc_type_gender = "female" if doc_type == "certificaciones" else "male"
        self.files_to_upload: List[str] = []
        self.callbacks = {}
        
        # Form fields
        self.doc_id_entry = None
        self.doc_name_entry = None
        self.version_entry = None
        self.initial_state_combo = None
        self.notes_entry = None
        self.author_entry = None
        self.info_label = None
        self.files_listbox = None
        self.dwg_name_entry = None
        self.dwg_name_label_widget = None
        self.dwg_name_help = None
        self.dwg_row = None
        self.details_frame = None  # Store reference to details frame
        self.dwg_name_visible = False

    def show(self, callbacks: dict, user_name: str = "") -> None:
        """Show the new document registration form."""
        self.callbacks = callbacks
        self.clear_window()
        self.set_window_size(800, 750)  # Increased height for button visibility
        
        # Header
        if self.doc_type_display == "Certificaciones":
            header_text = "Registrar Nueva Certificación"
        else:
            header_text = f"Registrar Nuevo {self.doc_type_display.rstrip('s')}"
        self.create_header(self.root, header_text)
        
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
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(side="bottom", fill="x")
        
        # Content container - expandable
        main_content = ttk.Frame(self.root, padding="20")
        main_content.pack(fill="both", expand=True)
        
        self.files_to_upload = []
        
        # Details frame
        self.details_frame = ttk.Frame(main_content)
        self.details_frame.pack(fill="x", pady=5)
        
        # Name field - use "Nombre" for all document types
        id_text = f"Nombre del nuevo {self.doc_type_singular}:" if self.doc_type_gender == 'male' else f"Nombre de la nueva {self.doc_type_singular}:"
        ttk.Label(self.details_frame, text=id_text).grid(row=0, column=0, sticky="w", pady=5)
        self.doc_id_entry = ttk.Entry(self.details_frame)
        self.doc_id_entry.grid(row=0, column=1, sticky="ew", pady=5)
        self.doc_id_entry.bind("<KeyRelease>", self.check_document_availability)
        self.doc_id_entry.bind("<KeyRelease>", self.check_form_completeness, add="+")
        
        # Info label for availability check
        self.info_label = ttk.Label(self.details_frame, text="", foreground="blue")
        self.info_label.grid(row=1, column=0, columnspan=2, pady=2)
        
        # Description field (optional)
        ttk.Label(self.details_frame, text="Descripción (opcional):").grid(row=2, column=0, sticky="w", pady=5)
        self.doc_name_entry = ttk.Entry(self.details_frame)
        self.doc_name_entry.grid(row=2, column=1, sticky="ew", pady=5)
        self.doc_name_entry.bind("<KeyRelease>", self.check_form_completeness)
        
        # Version field (different for certificaciones)
        if self.doc_type == "certificaciones":
            # Month and Year for certificaciones
            version_frame = ttk.Frame(self.details_frame)
            version_frame.grid(row=3, column=1, sticky="ew", pady=5)
            
            ttk.Label(self.details_frame, text="Mes y Año:").grid(row=3, column=0, sticky="w", pady=5)
            
            # Month combobox
            self.month_combo = ttk.Combobox(version_frame, values=[f"{i:02d}" for i in range(1, 13)], width=5, state="readonly")
            self.month_combo.pack(side="left", padx=(0, 5))
            self.month_combo.set("08")  # Default to August
            
            ttk.Label(version_frame, text="/").pack(side="left", padx=2)
            
            # Year entry
            self.year_entry = ttk.Entry(version_frame, width=8)
            self.year_entry.pack(side="left")
            self.year_entry.insert(0, "2025")  # Default to 2025
            
            # Store reference for compatibility
            self.version_entry = None
        else:
            # Traditional version for planos
            ttk.Label(self.details_frame, text="Versión inicial:").grid(row=3, column=0, sticky="w", pady=5)
            self.version_entry = ttk.Entry(self.details_frame)
            self.version_entry.grid(row=3, column=1, sticky="ew", pady=5)
            self.version_entry.insert(0, "1.0")  # Default version
        
        # Initial state selection
        ttk.Label(self.details_frame, text="Estado inicial:").grid(row=4, column=0, sticky="w", pady=5)
        self.initial_state_combo = ttk.Combobox(self.details_frame, values=["S0", "S1", "S2", "S3"], state="readonly")
        self.initial_state_combo.grid(row=4, column=1, sticky="ew", pady=5)
        self.initial_state_combo.set("S0")  # Default to S0
        self.initial_state_combo.bind("<<ComboboxSelected>>", self.check_form_completeness)
        
        # State description
        state_desc_label = ttk.Label(
            details_frame, 
            text="S0: Borrador • S1: Revisado por Delineación • S2: Revisado por Técnico Especialista • S3: Revisado por Director Proyecto • S3A: Aprobado por propiedad/promotor",
            font=("Arial", 8),
            foreground="gray"
        )
        state_desc_label.grid(row=5, column=0, columnspan=2, pady=2)
        
        # Notes field
        ttk.Label(self.details_frame, text="Notas (opcional):").grid(row=6, column=0, sticky="w", pady=5)
        self.notes_entry = ttk.Entry(self.details_frame)
        self.notes_entry.grid(row=6, column=1, sticky="ew", pady=5)

        # DWG Name field (only for planos) - shown when DWG is uploaded
        if self.doc_type == "planos":
            dwg_row = 7

            # DWG name label and entry (initially hidden)
            self.dwg_name_label_widget = ttk.Label(self.details_frame, text="Nombre del DWG:")
            self.dwg_name_entry = ttk.Entry(self.details_frame)
            self.dwg_name_help = ttk.Label(
                details_frame,
                text="Nombre con el que se guardará el archivo DWG (por defecto = nombre del plano)",
                font=("Arial", 8),
                foreground="gray"
            )
            # Store row for later showing/hiding
            self.dwg_row = dwg_row

            author_row = dwg_row  # DWG fields will shift author down when shown
        else:
            author_row = 7

        # Author field
        ttk.Label(self.details_frame, text="Tu Nombre:").grid(row=author_row, column=0, sticky="w", pady=5)
        self.author_entry = ttk.Entry(self.details_frame)
        self.author_entry.grid(row=author_row, column=1, sticky="ew", pady=5)
        self.author_entry.bind("<KeyRelease>", self.check_form_completeness)
        # Auto-fill username: use provided user_name or fall back to system username
        if user_name:
            self.author_entry.insert(0, user_name)
        else:
            # Fall back to system username if no user configured
            import getpass
            try:
                system_user = getpass.getuser()
                self.author_entry.insert(0, system_user)
            except:
                pass  # If system username fails, leave empty
        
        self.details_frame.columnconfigure(1, weight=1)
        
        # Files frame - more compact
        files_frame = ttk.LabelFrame(main_content, text="Archivos del Documento", padding=8)
        files_frame.pack(fill="both", expand=True, pady=5)
        
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
        
        # Instructions - moved to main content area
        instructions_text = (
            "• ID único • Estado inicial apropiado • Archivos relacionados (PDF, DWG, etc.)"
        )
        instructions_label = ttk.Label(main_content, text=instructions_text, font=("Arial", 9), foreground="darkblue")
        instructions_label.pack(pady=5)
        
        # Button frame - moved to bottom container for always-visible buttons
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(fill="x")
        
        if self.doc_type_display == "Certificaciones":
            register_text = "Registrar Certificación"
        else:
            register_text = f"Registrar {self.doc_type_display.rstrip('s')}"
        
        # Main action buttons
        ttk.Button(button_frame, text=register_text, command=self.submit_new_document).pack(side="left", padx=20)

        ttk.Button(button_frame, text="<< Volver", command=callbacks['back']).pack(side="right", padx=20)

    def check_document_availability(self, event=None) -> None:
        """Check if the document ID is available."""
        doc_id = self.doc_id_entry.get().strip()
        if not doc_id:
            self.info_label.config(text="", foreground="blue")
            return
        
        # Check if document already exists
        if 'check_document_exists' in self.callbacks:
            result = self.callbacks['check_document_exists'](doc_id)
            if result:
                doc_name, latest_version = result
                self.info_label.config(
                    text=f"⚠️ El nombre '{doc_id}' ya existe ('{doc_name}', versión {latest_version})",
                    foreground="red"
                )
            else:
                self.info_label.config(
                    text=f"✓ Nombre '{doc_id}' disponible para nuevo documento",
                    foreground="green"
                )
    
    def check_form_completeness(self, event=None) -> None:
        """Check if form is complete enough to enable assignment button."""
        form_data = self.get_form_data()
        
        # Check if core fields are filled
        # Allow assignments for any valid initial state (including S0)
        if (form_data['doc_id'] and 
            form_data['author'] and
            form_data['initial_state'] and  # Just need any state selected
            form_data['initial_state'] in ["S0", "S1", "S2", "S3"]):  # Valid workflow states
            self.enable_assignment_button()
        else:
            self.disable_assignment_button()

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
            except (OSError, AttributeError) as e:
                print(f"Warning: Could not determine initial directory: {e}")
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
                    filetypes=[
                        ("Archivos PDF", "*.pdf"),
                        ("Todos los Archivos", "*.*")
                    ]
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

    def submit_new_document(self) -> None:
        """Submit the new document registration form."""
        doc_id = self.doc_id_entry.get().strip()
        name = self.doc_name_entry.get().strip()
        
        # Get version based on document type
        if self.doc_type == "certificaciones":
            month = self.month_combo.get()
            year = self.year_entry.get().strip()
            if not all([month, year]):
                messagebox.showwarning("Aviso", "Debes especificar mes y año para la certificación.")
                return
            version = f"{month}/{year}"
        else:
            version = self.version_entry.get().strip()
            if not version:
                messagebox.showwarning("Aviso", "Debes especificar una versión.")
                return
        
        initial_state = self.initial_state_combo.get()
        notes = self.notes_entry.get().strip()
        author = self.author_entry.get().strip()
        
        # Validation - make name (description) optional
        if not all([doc_id, author]):
            messagebox.showwarning("Aviso", "Los campos ID y Autor son obligatorios.")
            return
        
        if not initial_state:
            messagebox.showwarning("Aviso", "Debes seleccionar un estado inicial.")
            return
        
        if not self.files_to_upload:
            messagebox.showwarning("Aviso", "Debes añadir al menos un archivo al documento.")
            return
        
        # Check if document already exists
        if 'check_document_exists' in self.callbacks:
            result = self.callbacks['check_document_exists'](doc_id)
            if result:
                messagebox.showerror("Error", f"El ID '{doc_id}' ya existe en el sistema. Usa un ID diferente.")
                return
        
        # Convert file paths to Path objects
        file_paths = [Path(fp) for fp in self.files_to_upload]

        # Get custom DWG name (only for planos)
        form_data = self.get_form_data()
        dwg_name = form_data.get('dwg_name', '')

        # Call the submission callback
        if 'submit_new_document' in self.callbacks:
            try:
                # Use the selected initial state instead of hardcoded "S0"
                self.callbacks['submit_new_document'](
                    doc_id, name, version, initial_state, file_paths, author, notes,
                    dwg_name=dwg_name
                )

                success_message = (
                    f"✅ {self.doc_type_singular.capitalize()} '{doc_id}' registrado exitosamente!\n\n"
                    f"📄 Nombre: {name}\n"
                    f"📊 Versión: {version}\n"
                    f"🔄 Estado: {initial_state}\n"
                    f"📁 Archivos: {len(file_paths)}"
                )

                if dwg_name and dwg_name != doc_id:
                    success_message += f"\n📐 DWG guardado como: {dwg_name}"

                messagebox.showinfo("Registro Exitoso", success_message)
                self.callbacks['back']()
            except Exception as e:
                messagebox.showerror("Error", f"Error al registrar el documento: {str(e)}")

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
                entry_name = self.doc_id_entry.get().strip() if self.doc_id_entry else ""
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
        # Handle version based on document type
        if self.doc_type == "certificaciones":
            month = self.month_combo.get() if hasattr(self, 'month_combo') else ""
            year = self.year_entry.get().strip() if hasattr(self, 'year_entry') else ""
            version = f"{month}/{year}" if month and year else ""
        else:
            version = self.version_entry.get().strip() if self.version_entry else ""

        # Get custom DWG name (only for planos, when DWG is uploaded)
        dwg_name = ""
        if self.dwg_name_entry and self.dwg_name_visible:
            dwg_name = self.dwg_name_entry.get().strip()

        return {
            'doc_id': self.doc_id_entry.get().strip() if self.doc_id_entry else "",
            'name': self.doc_name_entry.get().strip() if self.doc_name_entry else "",
            'version': version,
            'initial_state': self.initial_state_combo.get() if self.initial_state_combo else "S0",
            'notes': self.notes_entry.get().strip() if self.notes_entry else "",
            'author': self.author_entry.get().strip() if self.author_entry else "",
            'files': self.files_to_upload.copy(),
            'dwg_name': dwg_name
        }
    
    def show_assignment_dialog(self) -> None:
        """Show assignment dialog if document data is valid"""
        form_data = self.get_form_data()
        
        # Validate required fields
        if not all([form_data['doc_id'], form_data['author']]):
            messagebox.showwarning("Campos Incompletos", 
                                 "Completa los campos obligatorios (ID, Autor) antes de asignar responsables.")
            return
        
        # Allow assignment for all valid initial states
        if not form_data['initial_state']:
            messagebox.showwarning("Estado Requerido", 
                                 "Selecciona un estado inicial antes de asignar responsables.")
            return
        
        # Determine next state for assignment based on workflow
        current_state = form_data['initial_state']
        if current_state == "S0":
            next_state = "S1"  # S0 → S1: Technical review
        elif current_state == "S1":
            next_state = "S2"  # S1 → S2: Management approval  
        elif current_state == "S2":
            next_state = "S3"  # S2 → S3: Client review
        elif current_state == "S3":
            messagebox.showinfo("Información", 
                              "El estado S3 es final, no requiere asignación adicional.")
            return
        else:
            messagebox.showinfo("Información", 
                              f"El estado {current_state} no requiere asignación en este flujo.")
            return
        
        try:
            # Get project_path from callbacks if available
            project_path = None
            if 'get_project_path' in self.callbacks:
                project_path = self.callbacks['get_project_path']()
            
            dialog = AssignmentDialog(
                parent=self.root,
                document_id=form_data['doc_id'],
                document_name=form_data['name'],
                from_state=current_state,
                to_state=next_state,
                project_path=project_path
            )
            
            result = dialog.show()
            
            if result and result != "skipped":
                messagebox.showinfo("Asignación Creada", 
                                  f"Se ha creado la asignación para la transición {current_state}→{next_state}.\n\n"
                                  f"Los responsables serán notificados después de registrar el documento.")
            
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