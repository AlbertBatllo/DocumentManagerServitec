import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional, List, Tuple
from .base_view import BaseView
from models.licitacion_document import LOTES_ESTANDAR, DOCUMENT_TYPES, TYPE_DISPLAY_NAMES
from utils.version_validator import VersionValidator


class CorrectionForm(BaseView):
    def __init__(self, root: tk.Tk, doc_type: str, state_map: dict):
        super().__init__(root)
        self.doc_type = doc_type
        self.doc_type_display = "Planos" if doc_type == "planos" else "Certificaciones"
        self.doc_type_singular = "plano" if doc_type == "planos" else "certificación"
        self.doc_type_gender = "female" if doc_type == "certificaciones" else "male"
        self.state_map = state_map
        self.callbacks = {}
        
        # Form fields
        self.search_entry = None
        self.search_info_label = None
        self.old_id_entry = None
        self.new_id_entry = None
        self.name_entry = None
        self.version_entry = None
        self.state_combo = None
        self.notes_entry = None
        self.autor_entry = None
        self.rev_tecnica_entry = None
        self.rev_gerencia_entry = None
        self.author_entry = None
        
        # Licitacion-specific fields
        self.valor_entry = None
        self.lote_combo = None
        self.empresa_entry = None
        self.tipo_combo = None

    def show(self, callbacks: dict, user_name: str = "", pre_selected_document_name: str = "") -> None:
        """Show the correction form.
        
        Args:
            callbacks: Dictionary of callback functions
            user_name: Name of the current user
            pre_selected_document_name: Optional document name to auto-populate the form
        """
        self.callbacks = callbacks
        self.clear_window()
        self.set_window_size(750, 700)  # Increased height for button visibility
        
        # Add notification widget if user and callbacks available
        if user_name and 'get_notification_data' in callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: callbacks.get('get_notification_data')(user_name),
                mark_read_callback=callbacks.get('mark_notification_as_read'),
                navigate_callback=callbacks.get('navigate_to_document'),
                delete_callback=callbacks.get('delete_notification'),
                current_user=user_name
            )
        
        # Header
        self.create_header(self.root, "Corregir Información")
        
        # Create main container structure
        # IMPORTANT: Bottom container FIRST - fixed at bottom for buttons
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(side="bottom", fill="x")

        # Content container - expandable (packed AFTER bottom frame)
        main_content = ttk.Frame(self.root, padding="20")
        main_content.pack(fill="both", expand=True)
        
        # Search section
        search_frame = ttk.LabelFrame(main_content, text="Buscar Documento", padding=10)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="Buscar por Nombre:").grid(row=0, column=0, sticky="w", pady=5)
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.grid(row=0, column=1, sticky="ew", pady=5)
        self.search_entry.bind("<FocusOut>", self.find_document_for_correction)
        
        self.search_info_label = ttk.Label(search_frame, text="", foreground="blue")
        self.search_info_label.grid(row=1, column=0, columnspan=2, pady=5)
        
        search_frame.columnconfigure(1, weight=1)
        
        # Edit section
        edit_frame = ttk.LabelFrame(main_content, text="Editar Información", padding=10)
        edit_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Current Name (read-only)
        ttk.Label(edit_frame, text="Nombre Actual:").grid(row=0, column=0, sticky="w", pady=5)
        self.old_id_entry = ttk.Entry(edit_frame, state="readonly")
        self.old_id_entry.grid(row=0, column=1, sticky="ew", pady=5)
        
        # Name
        ttk.Label(edit_frame, text="Nombre:").grid(row=1, column=0, sticky="w", pady=5)
        self.name_entry = ttk.Entry(edit_frame)
        self.name_entry.grid(row=1, column=1, sticky="ew", pady=5)
        
        # Create hidden new_id_entry for compatibility but populate it automatically
        self.new_id_entry = ttk.Entry(edit_frame)
        self.new_id_entry.grid_remove()  # Hide it
        
        # Version with validation
        ttk.Label(edit_frame, text="Versión:").grid(row=2, column=0, sticky="w", pady=5)
        self.version_entry = ttk.Entry(edit_frame)
        self.version_entry.grid(row=2, column=1, sticky="ew", pady=5)
        
        # Version validation label
        self.version_validation_label = ttk.Label(edit_frame, text="Formato: número.número (ej: 1.0, 2.1)", foreground="gray")
        self.version_validation_label.grid(row=2, column=2, sticky="w", padx=(10, 0), pady=5)
        
        # Bind version validation
        self.version_entry.bind("<KeyRelease>", self._validate_version_input)
        
        # State
        ttk.Label(edit_frame, text="Estado:").grid(row=3, column=0, sticky="w", pady=5)
        self.state_combo = ttk.Combobox(
            edit_frame,
            state="readonly",
            values=list(self.state_map.keys())
        )
        self.state_combo.grid(row=3, column=1, sticky="ew", pady=5)
        
        # Notes (multiline text field)
        ttk.Label(edit_frame, text="Notas (opcional):").grid(row=4, column=0, sticky="nw", pady=5)
        notes_frame = ttk.Frame(edit_frame)
        notes_frame.grid(row=4, column=1, sticky="ew", pady=5)
        self.notes_entry = tk.Text(notes_frame, height=3, width=40, wrap="word")
        self.notes_entry.pack(side="left", fill="x", expand=True)
        notes_scrollbar = ttk.Scrollbar(notes_frame, orient="vertical", command=self.notes_entry.yview)
        notes_scrollbar.pack(side="right", fill="y")
        self.notes_entry.configure(yscrollcommand=notes_scrollbar.set)
        
        # Autor (original uploader)
        ttk.Label(edit_frame, text="Autor:").grid(row=5, column=0, sticky="w", pady=5)
        self.autor_entry = ttk.Entry(edit_frame)
        self.autor_entry.grid(row=5, column=1, sticky="ew", pady=5)
        
        # Rev. Téc.
        ttk.Label(edit_frame, text="Rev. Téc.:").grid(row=6, column=0, sticky="w", pady=5)
        self.rev_tecnica_entry = ttk.Entry(edit_frame)
        self.rev_tecnica_entry.grid(row=6, column=1, sticky="ew", pady=5)
        
        # Rev. Ger.
        ttk.Label(edit_frame, text="Rev. Ger.:").grid(row=7, column=0, sticky="w", pady=5)
        self.rev_gerencia_entry = ttk.Entry(edit_frame)
        self.rev_gerencia_entry.grid(row=7, column=1, sticky="ew", pady=5)
        
        # Licitacion-specific fields (only show for licitaciones)
        current_row = 8
        if self.doc_type == "licitaciones":
            # Valor field
            ttk.Label(edit_frame, text="Valor/Importe (€):").grid(row=current_row, column=0, sticky="w", pady=5)
            self.valor_entry = ttk.Entry(edit_frame)
            self.valor_entry.grid(row=current_row, column=1, sticky="ew", pady=5)
            current_row += 1
            
            # Lote field
            ttk.Label(edit_frame, text="Lote:").grid(row=current_row, column=0, sticky="w", pady=5)
            self.lote_combo = ttk.Combobox(
                edit_frame,
                state="readonly",
                values=LOTES_ESTANDAR
            )
            self.lote_combo.grid(row=current_row, column=1, sticky="ew", pady=5)
            current_row += 1
            
            # Empresa field
            ttk.Label(edit_frame, text="Empresa:").grid(row=current_row, column=0, sticky="w", pady=5)
            self.empresa_entry = ttk.Entry(edit_frame)
            self.empresa_entry.grid(row=current_row, column=1, sticky="ew", pady=5)
            current_row += 1
            
            # Tipo de Documento field
            ttk.Label(edit_frame, text="Tipo de Documento:").grid(row=current_row, column=0, sticky="w", pady=5)
            self.tipo_combo = ttk.Combobox(
                edit_frame,
                state="readonly",
                values=list(TYPE_DISPLAY_NAMES.values())
            )
            self.tipo_combo.grid(row=current_row, column=1, sticky="ew", pady=5)
            current_row += 1
        
        # Author (current editor)
        ttk.Label(edit_frame, text="Tu Nombre:").grid(row=current_row, column=0, sticky="w", pady=5)
        self.author_entry = ttk.Entry(edit_frame)
        self.author_entry.grid(row=current_row, column=1, sticky="ew", pady=5)
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
        
        edit_frame.columnconfigure(1, weight=1)
        edit_frame.columnconfigure(2, weight=0)  # Version validation column
        
        # Button frame - moved to bottom container for always-visible buttons
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(fill="x")
        
        ttk.Button(button_frame, text="Guardar Corrección", command=self.save_correction).pack(side="left", padx=20)
        ttk.Button(button_frame, text="<< Volver", command=callbacks['back']).pack(side="right", padx=20)
        
        # Auto-populate form if pre-selected document name is provided
        if pre_selected_document_name:
            self.search_entry.insert(0, pre_selected_document_name)
            if 'get_document' in callbacks:
                document = callbacks['get_document'](pre_selected_document_name)
                if document:
                    self._populate_fields(document)

    def find_document_for_correction(self, event=None) -> None:
        """Find document for correction."""
        entered_id = self.search_entry.get().strip()
        if not entered_id:
            return
        
        # Check if exact match exists
        if 'get_document' in self.callbacks:
            document = self.callbacks['get_document'](entered_id)
            if document:
                self._populate_fields(document)
            else:
                self.search_info_label.config(
                    text=f"{self.doc_type_singular} no encontrado.",
                    foreground="red"
                )
                self._clear_fields()

    def _populate_fields(self, document) -> None:
        """Populate form fields with document data."""
        self.search_info_label.config(
            text=f"Documento encontrado: {document.name}",
            foreground="green"
        )
        
        # Populate common fields
        self.old_id_entry.config(state="normal")
        self.old_id_entry.delete(0, tk.END)
        self.old_id_entry.insert(0, document.name)
        self.old_id_entry.config(state="readonly")
        
        # Automatically set the hidden new_id_entry to the document name (for backend compatibility)
        self.new_id_entry.delete(0, tk.END)
        self.new_id_entry.insert(0, document.name)
        
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, document.name)
        
        # Handle version field - different attributes for different document types
        self.version_entry.delete(0, tk.END)
        if hasattr(document, 'current_version'):
            self.version_entry.insert(0, document.current_version)
        elif hasattr(document, 'version'):
            self.version_entry.insert(0, document.version)
        else:
            self.version_entry.insert(0, "1.0")
        
        # Handle state field - different attributes for different document types
        if hasattr(document, 'current_state'):
            self.state_combo.set(document.current_state)
        elif hasattr(document, 'current_status'):
            self.state_combo.set(document.current_status)
        
        # Populate common optional fields
        self.autor_entry.delete(0, tk.END)
        if hasattr(document, 'autor_display'):
            # For SQLite licitacion documents, use autor_display to avoid showing metadata JSON
            self.autor_entry.insert(0, document.autor_display)
        elif hasattr(document, 'document_autor'):
            # Alternative accessor for licitacion documents
            self.autor_entry.insert(0, document.document_autor)
        elif hasattr(document, 'autor'):
            # Fallback for regular documents
            self.autor_entry.insert(0, document.autor)
        
        self.rev_tecnica_entry.delete(0, tk.END)
        if hasattr(document, 'rev_tecnica'):
            self.rev_tecnica_entry.insert(0, document.rev_tecnica)
        
        self.rev_gerencia_entry.delete(0, tk.END)
        if hasattr(document, 'rev_gerencia'):
            self.rev_gerencia_entry.insert(0, document.rev_gerencia)

        # Populate notes field (using Text widget API)
        self.notes_entry.delete("1.0", tk.END)
        if hasattr(document, 'latest_notes'):
            self.notes_entry.insert("1.0", document.latest_notes or '')
        elif hasattr(document, 'notes'):
            self.notes_entry.insert("1.0", document.notes or '')

        # Populate licitacion-specific fields if available
        if self.doc_type == "licitaciones" and self.valor_entry:
            self.valor_entry.delete(0, tk.END)
            if hasattr(document, 'valor') and document.valor:
                self.valor_entry.insert(0, str(document.valor))
            
            if self.lote_combo and hasattr(document, 'lote'):
                self.lote_combo.set(document.lote)
            
            self.empresa_entry.delete(0, tk.END)
            if hasattr(document, 'company'):
                self.empresa_entry.insert(0, document.company)
            
            if self.tipo_combo and hasattr(document, 'document_type'):
                display_name = TYPE_DISPLAY_NAMES.get(document.document_type, document.document_type)
                self.tipo_combo.set(display_name)

    def _clear_fields(self) -> None:
        """Clear all form fields."""
        self.old_id_entry.config(state="normal")
        self.old_id_entry.delete(0, tk.END)
        self.old_id_entry.config(state="readonly")
        
        self.new_id_entry.delete(0, tk.END)
        self.name_entry.delete(0, tk.END)
        self.version_entry.delete(0, tk.END)
        self.state_combo.set("")
        self.autor_entry.delete(0, tk.END)
        self.rev_tecnica_entry.delete(0, tk.END)
        self.rev_gerencia_entry.delete(0, tk.END)
        self.notes_entry.delete("1.0", tk.END)  # Text widget API

        # Clear licitacion-specific fields if they exist
        if self.valor_entry:
            self.valor_entry.delete(0, tk.END)
        if self.lote_combo:
            self.lote_combo.set("")
        if self.empresa_entry:
            self.empresa_entry.delete(0, tk.END)
        if self.tipo_combo:
            self.tipo_combo.set("")

    def save_correction(self) -> None:
        """Save the correction."""
        old_id = self.old_id_entry.get().strip()
        name = self.name_entry.get().strip()
        
        # Automatically sync the hidden new_id_entry with the name_entry
        self.new_id_entry.delete(0, tk.END)
        self.new_id_entry.insert(0, name)
        new_id = self.new_id_entry.get().strip()
        
        version = self.version_entry.get().strip()
        state = self.state_combo.get()
        notes = self.notes_entry.get("1.0", "end-1c").strip()  # Text widget API
        autor = self.autor_entry.get().strip()
        rev_tecnica = self.rev_tecnica_entry.get().strip()
        rev_gerencia = self.rev_gerencia_entry.get().strip()
        author = self.author_entry.get().strip()
        
        # Get licitacion-specific fields
        valor = ""
        lote = ""
        empresa = ""
        tipo = ""
        
        if self.doc_type == "licitaciones":
            valor = self.valor_entry.get().strip() if self.valor_entry else ""
            lote = self.lote_combo.get() if self.lote_combo else ""
            empresa = self.empresa_entry.get().strip() if self.empresa_entry else ""
            tipo_display = self.tipo_combo.get() if self.tipo_combo else ""
            # Convert display name back to internal type
            tipo = {v: k for k, v in TYPE_DISPLAY_NAMES.items()}.get(tipo_display, tipo_display)
        
        # Validation - base fields required for all document types
        required_fields = [old_id, new_id, name, version, state, author]
        if not all(required_fields):
            messagebox.showwarning("Aviso", "Todos los campos básicos son obligatorios (excepto Autor, Rev. Téc., Rev. Ger. y Notas).")
            return
        
        # Additional validation for licitaciones
        if self.doc_type == "licitaciones":
            if not all([lote, empresa, tipo]):
                messagebox.showwarning("Aviso", "Los campos Lote, Empresa y Tipo de Documento son obligatorios para licitaciones.")
                return
            
            # Validate valor for presupuesto and adicional types
            if tipo in ["presupuesto", "adicional"]:
                try:
                    valor_float = float(valor) if valor else 0
                    if valor_float <= 0:
                        messagebox.showwarning("Aviso", f"El campo Valor es obligatorio y debe ser mayor que 0 para documentos de tipo {TYPE_DISPLAY_NAMES.get(tipo, tipo)}.")
                        return
                except ValueError:
                    messagebox.showwarning("Aviso", "El campo Valor debe ser un número válido.")
                    return
        
        # Build confirmation message with all fields
        confirmation_msg = (
            f"¿Estás seguro de que deseas corregir la información del documento?\n\n"
            f"Nombre: {old_id} → {name}\n"
            f"Versión: {version}\n"
            f"Estado: {self.state_map.get(state, state)}\n"
            f"Autor: {author}"
        )
        
        # Add licitacion-specific fields to confirmation
        if self.doc_type == "licitaciones":
            if valor:
                confirmation_msg += f"\nValor: €{valor}"
            if lote:
                confirmation_msg += f"\nLote: {lote}"
            if empresa:
                confirmation_msg += f"\nEmpresa: {empresa}"
            if tipo:
                confirmation_msg += f"\nTipo: {TYPE_DISPLAY_NAMES.get(tipo, tipo)}"
        
        # Add optional fields if they have values
        if autor:
            confirmation_msg += f"\nAutor (documento): {autor}"
        if rev_tecnica:
            confirmation_msg += f"\nRevisión Técnica: {rev_tecnica}"
        if rev_gerencia:
            confirmation_msg += f"\nRevisión Gerencia: {rev_gerencia}"
        if notes:
            confirmation_msg += f"\nNotas: {notes}"
        
        # Validate version format
        version_result = VersionValidator.validate_version(version)
        if not version_result['is_valid']:
            messagebox.showerror("Versión Inválida", version_result['message'])
            return
        
        # Confirmation
        if not messagebox.askyesno("Confirmar Corrección", confirmation_msg):
            return
        
        # Call the correction callback with appropriate parameters
        if 'update_document_info' in self.callbacks:
            try:
                if self.doc_type == "licitaciones":
                    # For licitaciones, include additional fields
                    result = self.callbacks['update_document_info'](
                        old_id, new_id, name, version, state, author, notes, autor, rev_tecnica, rev_gerencia,
                        valor=valor, lote=lote, empresa=empresa, tipo=tipo
                    )
                else:
                    # For other document types, use original signature
                    result = self.callbacks['update_document_info'](
                        old_id, new_id, name, version, state, author, notes, autor, rev_tecnica, rev_gerencia
                    )
                messagebox.showinfo("Éxito", result)
                # Navigate back to dashboard with edited document selected
                if 'back_to_document' in self.callbacks:
                    self.callbacks['back_to_document'](new_id)
                else:
                    self.callbacks['back']()
            except Exception as e:
                messagebox.showerror("Error", f"Error al guardar la corrección: {str(e)}")

    def get_form_data(self) -> dict:
        """Get current form data."""
        data = {
            'old_id': self.old_id_entry.get().strip() if self.old_id_entry else "",
            'new_id': self.new_id_entry.get().strip() if self.new_id_entry else "",
            'name': self.name_entry.get().strip() if self.name_entry else "",
            'version': self.version_entry.get().strip() if self.version_entry else "",
            'state': self.state_combo.get() if self.state_combo else "",
            'notes': self.notes_entry.get("1.0", "end-1c").strip() if self.notes_entry else "",
            'autor': self.autor_entry.get().strip() if self.autor_entry else "",
            'rev_tecnica': self.rev_tecnica_entry.get().strip() if self.rev_tecnica_entry else "",
            'rev_gerencia': self.rev_gerencia_entry.get().strip() if self.rev_gerencia_entry else "",
            'author': self.author_entry.get().strip() if self.author_entry else ""
        }
        
        # Add licitacion-specific fields if available
        if self.doc_type == "licitaciones":
            data.update({
                'valor': self.valor_entry.get().strip() if self.valor_entry else "",
                'lote': self.lote_combo.get() if self.lote_combo else "",
                'empresa': self.empresa_entry.get().strip() if self.empresa_entry else "",
                'tipo': self.tipo_combo.get() if self.tipo_combo else ""
            })
        
        return data
    
    def _validate_version_input(self, event=None) -> None:
        """Validate version input in real-time and update UI feedback."""
        version = self.version_entry.get().strip()
        
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