import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Callable, Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
from .base_view import BaseView
from models.certificacion_document import CertificacionDocument, CertificacionEntry
import shlex


class MonthlyCertificacionForm(BaseView):
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.certificacion: Optional[CertificacionDocument] = None
        self.available_adicionales: List[Dict[str, Any]] = []
        self.selected_adicionales: List[str] = []
        self.callbacks = {}
        
        # Form fields
        self.fecha_entry = None
        self.importe_entry = None
        self.retencion_entry = None
        self.prorrata_entry = None
        self.notes_entry = None
        self.author_entry = None
        self.adicionales_listbox = None
        self.selected_listbox = None
        self.total_adicionales_var = None
        self.total_certificado_var = None
        
        # File attachment fields
        self.selected_files = []
        self.files_listbox = None
        self.available_adicionales_files = []
        self.selected_adicionales_files = []
        self.adicionales_files_listbox = None

    def show(self, certificacion: CertificacionDocument, callbacks: dict, user_name: str = "") -> None:
        """Show the monthly certificacion form."""
        self.callbacks = callbacks
        self.certificacion = certificacion
        self.clear_window()
        self.set_window_size(900, 700)
        
        # Header
        self.create_header(self.root)
        
        # Create main container structure
        # IMPORTANT: Bottom container FIRST - fixed at bottom for buttons
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(side="bottom", fill="x")
        
        # Content container - expandable
        main_content = ttk.Frame(self.root, padding="20")
        main_content.pack(fill="both", expand=True)
        
        # Title
        title_label = ttk.Label(
            main_content,
            text=f"Nueva Certificación Mensual - {certificacion.nombre}",
            font=("Arial", 16, "bold")
        )
        title_label.pack(pady=(0, 10))
        
        # Certificacion info
        info_frame = ttk.LabelFrame(main_content, text="Información de la Certificación", padding="10")
        info_frame.pack(fill="x", pady=(0, 10))
        
        info_text = f"Proyecto: {certificacion.nombre}\nLote: {certificacion.lote}\nEmpresa: {certificacion.empresa}\n"
        info_text += f"Presupuesto Contratado: {certificacion.presupuesto_contratado:,.2f} €\n"
        info_text += f"Certificado Acumulado: {certificacion.cumulative_certificado:,.2f} € ({certificacion.porcentaje_completado_actual:.1f}%)"
        
        ttk.Label(info_frame, text=info_text, justify="left").pack(anchor="w")
        
        # Create notebook for organized layout
        notebook = ttk.Notebook(main_content)
        notebook.pack(fill="both", expand=True, pady=(0, 10))
        
        # Basic certification tab
        basic_frame = ttk.Frame(notebook)
        notebook.add(basic_frame, text="Datos de Certificación")
        self._create_basic_fields(basic_frame, user_name)
        
        # Adicionales tab
        adicionales_frame = ttk.Frame(notebook)
        notebook.add(adicionales_frame, text="Adicionales")
        self._create_adicionales_section(adicionales_frame)
        
        # File attachments tab
        files_frame = ttk.Frame(notebook)
        notebook.add(files_frame, text="Archivos Adjuntos")
        self._create_file_attachments_section(files_frame)
        
        # Summary tab
        summary_frame = ttk.Frame(notebook)
        notebook.add(summary_frame, text="Resumen")
        self._create_summary_section(summary_frame)
        
        # Buttons - moved to bottom container for always-visible buttons
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(fill="x")
        
        ttk.Button(
            button_frame,
            text="Crear Certificación",
            command=self._submit_certificacion
        ).pack(side="left", padx=10)
        
        ttk.Button(
            button_frame,
            text="Cancelar",
            command=callbacks.get('back', lambda: None)
        ).pack(side="right", padx=10)
        
        # Load available adicionales
        self._load_available_adicionales()

    def _create_basic_fields(self, parent: tk.Widget, user_name: str) -> None:
        """Create basic certification fields."""
        fields_frame = ttk.Frame(parent, padding="10")
        fields_frame.pack(fill="both", expand=True)
        
        # Date field
        ttk.Label(fields_frame, text="Fecha de Certificación:").grid(row=0, column=0, sticky="w", pady=5)
        self.fecha_entry = ttk.Entry(fields_frame, width=20)
        self.fecha_entry.grid(row=0, column=1, sticky="w", pady=5, padx=10)
        # Set default to current date
        self.fecha_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        # Amount field
        ttk.Label(fields_frame, text="Importe Certificado (€):").grid(row=1, column=0, sticky="w", pady=5)
        self.importe_entry = ttk.Entry(fields_frame, width=20)
        self.importe_entry.grid(row=1, column=1, sticky="w", pady=5, padx=10)
        self.importe_entry.bind("<KeyRelease>", self._update_summary)
        
        # Retention field
        ttk.Label(fields_frame, text="Retención (€):").grid(row=2, column=0, sticky="w", pady=5)
        self.retencion_entry = ttk.Entry(fields_frame, width=20)
        self.retencion_entry.grid(row=2, column=1, sticky="w", pady=5, padx=10)
        self.retencion_entry.insert(0, "0.00")
        self.retencion_entry.bind("<KeyRelease>", self._update_summary)
        
        # Prorated account field
        ttk.Label(fields_frame, text="Cuenta Prorrata (€):").grid(row=3, column=0, sticky="w", pady=5)
        self.prorrata_entry = ttk.Entry(fields_frame, width=20)
        self.prorrata_entry.grid(row=3, column=1, sticky="w", pady=5, padx=10)
        self.prorrata_entry.insert(0, "0.00")
        self.prorrata_entry.bind("<KeyRelease>", self._update_summary)
        
        # Notes field
        ttk.Label(fields_frame, text="Notas:").grid(row=4, column=0, sticky="nw", pady=5)
        self.notes_entry = tk.Text(fields_frame, width=50, height=4)
        self.notes_entry.grid(row=4, column=1, sticky="ew", pady=5, padx=10)
        
        # Author field
        ttk.Label(fields_frame, text="Autor:").grid(row=5, column=0, sticky="w", pady=5)
        self.author_entry = ttk.Entry(fields_frame, width=30)
        self.author_entry.grid(row=5, column=1, sticky="w", pady=5, padx=10)
        if user_name:
            self.author_entry.insert(0, user_name)
        
        fields_frame.columnconfigure(1, weight=1)

    def _create_adicionales_section(self, parent: tk.Widget) -> None:
        """Create adicionales selection section."""
        adicionales_frame = ttk.Frame(parent, padding="10")
        adicionales_frame.pack(fill="both", expand=True)
        
        # Instructions
        instruction_label = ttk.Label(
            adicionales_frame,
            text="Selecciona los adicionales a incluir en esta certificación mensual:",
            font=("Arial", 10, "bold")
        )
        instruction_label.pack(anchor="w", pady=(0, 10))
        
        # Create two-column layout
        columns_frame = ttk.Frame(adicionales_frame)
        columns_frame.pack(fill="both", expand=True)
        
        # Available adicionales (left side)
        left_frame = ttk.LabelFrame(columns_frame, text="Adicionales Disponibles", padding="5")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # Listbox with scrollbar for available adicionales
        available_frame = ttk.Frame(left_frame)
        available_frame.pack(fill="both", expand=True)
        
        available_scroll = ttk.Scrollbar(available_frame)
        available_scroll.pack(side="right", fill="y")
        
        self.adicionales_listbox = tk.Listbox(
            available_frame,
            selectmode=tk.MULTIPLE,
            yscrollcommand=available_scroll.set,
            height=10
        )
        self.adicionales_listbox.pack(side="left", fill="both", expand=True)
        available_scroll.config(command=self.adicionales_listbox.yview)
        
        # Buttons in the middle
        buttons_frame = ttk.Frame(columns_frame)
        buttons_frame.pack(side="left", padx=10, pady=50)
        
        ttk.Button(
            buttons_frame,
            text="→ Añadir",
            command=self._add_adicionales
        ).pack(pady=5)
        
        ttk.Button(
            buttons_frame,
            text="← Quitar",
            command=self._remove_adicionales
        ).pack(pady=5)
        
        # Selected adicionales (right side)
        right_frame = ttk.LabelFrame(columns_frame, text="Adicionales Seleccionados", padding="5")
        right_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        
        selected_frame = ttk.Frame(right_frame)
        selected_frame.pack(fill="both", expand=True)
        
        selected_scroll = ttk.Scrollbar(selected_frame)
        selected_scroll.pack(side="right", fill="y")
        
        self.selected_listbox = tk.Listbox(
            selected_frame,
            selectmode=tk.MULTIPLE,
            yscrollcommand=selected_scroll.set,
            height=10
        )
        self.selected_listbox.pack(side="left", fill="both", expand=True)
        selected_scroll.config(command=self.selected_listbox.yview)
        
        # Bind selection events to update summary
        self.selected_listbox.bind("<<ListboxSelect>>", self._update_summary)

    def _create_summary_section(self, parent: tk.Widget) -> None:
        """Create summary section."""
        summary_frame = ttk.Frame(parent, padding="10")
        summary_frame.pack(fill="both", expand=True)
        
        # Summary title
        ttk.Label(
            summary_frame,
            text="Resumen de la Certificación",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", pady=(0, 20))
        
        # Summary grid
        grid_frame = ttk.Frame(summary_frame)
        grid_frame.pack(fill="x")
        
        # Configure columns
        for i in range(4):
            grid_frame.columnconfigure(i, weight=1)
        
        # Create summary items
        self.lbl_importe_base = self._create_summary_item(
            grid_frame, "IMPORTE BASE", "0.00 €", 0, 0, "#2E7D32"
        )
        
        self.total_adicionales_var = tk.StringVar(value="0.00 €")
        self.lbl_total_adicionales = self._create_summary_item(
            grid_frame, "TOTAL ADICIONALES", "0.00 €", 0, 1, "#7B1FA2"
        )
        
        self.total_certificado_var = tk.StringVar(value="0.00 €")
        self.lbl_total_certificado = self._create_summary_item(
            grid_frame, "TOTAL CERTIFICADO", "0.00 €", 0, 2, "#1565C0"
        )
        
        self.lbl_porcentaje_nuevo = self._create_summary_item(
            grid_frame, "% COMPLETADO NUEVO", "0.00%", 0, 3, "#E65100"
        )

    def _create_summary_item(self, parent: tk.Widget, title: str, value: str, 
                            row: int, col: int, color: str) -> ttk.Label:
        """Create a summary display item."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, padx=10, pady=5, sticky="ew")
        
        ttk.Label(
            frame,
            text=title,
            font=("Arial", 9, "bold")
        ).pack(anchor="w")
        
        value_label = ttk.Label(
            frame,
            text=value,
            font=("Arial", 12, "bold"),
            foreground=color
        )
        value_label.pack(anchor="w")
        
        return value_label

    def _load_available_adicionales(self) -> None:
        """Load available adicionales for this certificacion."""
        if 'get_available_adicionales' in self.callbacks:
            try:
                self.available_adicionales = self.callbacks['get_available_adicionales'](
                    self.certificacion.licitacion_name
                )
                self._refresh_adicionales_lists()
            except Exception as e:
                messagebox.showerror("Error", f"Error al cargar adicionales: {str(e)}")

    def _refresh_adicionales_lists(self) -> None:
        """Refresh the adicionales listboxes."""
        # Clear listboxes
        self.adicionales_listbox.delete(0, tk.END)
        self.selected_listbox.delete(0, tk.END)
        
        # Populate available adicionales (not yet selected)
        # Note: IDs are used internally for tracking but not shown in UI
        for adicional in self.available_adicionales:
            if adicional['id'] not in self.selected_adicionales:
                # Show name, company and amount for clarity
                name = adicional.get('name') or adicional.get('id')
                company = adicional.get('company', '')
                amount = adicional.get('importe_adicional', 0.0)
                display_text = f"{name} — {company} — {amount:,.2f} €"
                self.adicionales_listbox.insert(tk.END, display_text)
        
        # Populate selected adicionales
        for adicional_id in self.selected_adicionales:
            adicional = next((a for a in self.available_adicionales if a['id'] == adicional_id), None)
            if adicional:
                name = adicional.get('name') or adicional.get('id')
                company = adicional.get('company', '')
                amount = adicional.get('importe_adicional', 0.0)
                display_text = f"{name} — {company} — {amount:,.2f} €"
                self.selected_listbox.insert(tk.END, display_text)

    def _add_adicionales(self) -> None:
        """Add selected adicionales to the certification."""
        selection = self.adicionales_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selección", "Selecciona al menos un adicional para añadir.")
            return
        
        # Get available adicionales not yet selected
        available_not_selected = [a for a in self.available_adicionales if a['id'] not in self.selected_adicionales]
        
        for index in selection:
            if index < len(available_not_selected):
                adicional = available_not_selected[index]
                if adicional['id'] not in self.selected_adicionales:
                    self.selected_adicionales.append(adicional['id'])
        
        self._refresh_adicionales_lists()
        self._update_summary()

    def _remove_adicionales(self) -> None:
        """Remove selected adicionales from the certification."""
        selection = self.selected_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selección", "Selecciona al menos un adicional para quitar.")
            return
        
        # Remove in reverse order to maintain indices
        for index in reversed(selection):
            if index < len(self.selected_adicionales):
                self.selected_adicionales.pop(index)
        
        self._refresh_adicionales_lists()
        self._update_summary()

    def _update_summary(self, event=None) -> None:
        """Update the summary calculations."""
        try:
            # Get base amount
            importe_text = self.importe_entry.get().strip() if self.importe_entry else "0"
            importe_base = float(importe_text.replace(',', '.')) if importe_text else 0.0
            
            # Calculate total adicionales
            total_adicionales = 0.0
            for adicional_id in self.selected_adicionales:
                adicional = next((a for a in self.available_adicionales if a['id'] == adicional_id), None)
                if adicional:
                    total_adicionales += adicional['importe_adicional']
            
            # Calculate total certificado
            total_certificado = importe_base + total_adicionales
            
            # Calculate new percentage
            if self.certificacion:
                new_cumulative = self.certificacion.cumulative_certificado + importe_base
                porcentaje_nuevo = (new_cumulative / self.certificacion.presupuesto_contratado) * 100 if self.certificacion.presupuesto_contratado > 0 else 0
            else:
                porcentaje_nuevo = 0
            
            # Update labels
            self.lbl_importe_base.config(text=f"{importe_base:,.2f} €")
            self.lbl_total_adicionales.config(text=f"{total_adicionales:,.2f} €")
            self.lbl_total_certificado.config(text=f"{total_certificado:,.2f} €")
            self.lbl_porcentaje_nuevo.config(text=f"{porcentaje_nuevo:.1f}%")
            
        except ValueError:
            # Invalid number input, show zeros
            self.lbl_importe_base.config(text="0.00 €")
            self.lbl_total_adicionales.config(text="0.00 €")
            self.lbl_total_certificado.config(text="0.00 €")
            self.lbl_porcentaje_nuevo.config(text="0.00%")

    def _submit_certificacion(self) -> None:
        """Submit the new monthly certificacion."""
        try:
            # Validate required fields
            if not all([
                self.fecha_entry.get().strip(),
                self.importe_entry.get().strip(),
                self.author_entry.get().strip()
            ]):
                messagebox.showwarning("Campos Requeridos", "Completa todos los campos obligatorios.")
                return
            
            # Parse values
            fecha = self.fecha_entry.get().strip()
            importe_certificado = float(self.importe_entry.get().replace(',', '.'))
            retencion = float(self.retencion_entry.get().replace(',', '.')) if self.retencion_entry.get().strip() else 0.0
            cuenta_prorrata = float(self.prorrata_entry.get().replace(',', '.')) if self.prorrata_entry.get().strip() else 0.0
            notes = self.notes_entry.get("1.0", tk.END).strip()
            author = self.author_entry.get().strip()
            
            # Validate amounts
            if importe_certificado < 0:
                messagebox.showerror("Error", "El importe certificado no puede ser negativo.")
                return
            
            # Calculate total adicionales
            total_adicionales = 0.0
            for adicional_id in self.selected_adicionales:
                adicional = next((a for a in self.available_adicionales if a['id'] == adicional_id), None)
                if adicional:
                    total_adicionales += adicional['importe_adicional']
            
            # Create certificacion data
            # Validate files before submission
            file_validation_results = self._validate_all_files()
            invalid_files = [r for r in file_validation_results if not r['valid']]
            
            if invalid_files:
                error_msg = "Los siguientes archivos tienen errores:\n"
                for result in invalid_files:
                    error_msg += f"• {result['file_path'].name}: {', '.join(result['errors'])}\n"
                messagebox.showerror("Error de Validación", error_msg)
                return
            
            certificacion_data = {
                'certificacion_id': self.certificacion.nombre,
                'fecha': fecha,
                'importe_certificado': importe_certificado,
                'retencion': retencion,
                'cuenta_prorrata': cuenta_prorrata,
                'adicionales_ids': self.selected_adicionales.copy(),
                'total_adicionales': total_adicionales,
                'notes': notes,
                'author': author,
                'attached_files': self.selected_files.copy()  # Add attached files
            }
            
            # Submit via callback
            if 'create_monthly_certificacion' in self.callbacks:
                result = self.callbacks['create_monthly_certificacion'](certificacion_data)
                messagebox.showinfo("Éxito", result)
                self.callbacks['back']()
            else:
                messagebox.showerror("Error", "No se puede procesar la certificación.")
                
        except ValueError as e:
            messagebox.showerror("Error", f"Valores inválidos: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"Error al crear certificación: {str(e)}")
    
    def _create_file_attachments_section(self, parent: tk.Widget) -> None:
        """Create the file attachments section."""
        
        # Main container with scrollable area
        main_container = ttk.Frame(parent)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create two-column layout
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        right_frame = ttk.Frame(main_container)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        # LEFT SIDE: Regular file attachments
        attachments_frame = ttk.LabelFrame(left_frame, text="Documentos de Certificación", padding="10")
        attachments_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Instructions
        ttk.Label(
            attachments_frame,
            text="Adjunte documentos relacionados con esta certificación mensual:",
            font=("Arial", 10)
        ).pack(anchor="w", pady=(0, 10))
        
        # File selection buttons
        button_frame = ttk.Frame(attachments_frame)
        button_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(
            button_frame,
            text="📎 Seleccionar Archivos",
            command=self._select_files
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            button_frame,
            text="🗑️ Quitar Seleccionado",
            command=self._remove_selected_file
        ).pack(side="left")
        
        # Files listbox
        files_list_frame = ttk.Frame(attachments_frame)
        files_list_frame.pack(fill="both", expand=True)
        
        ttk.Label(files_list_frame, text="Archivos seleccionados:").pack(anchor="w")
        
        # Listbox with scrollbar
        list_container = ttk.Frame(files_list_frame)
        list_container.pack(fill="both", expand=True, pady=(5, 0))
        
        self.files_listbox = tk.Listbox(list_container, height=6)
        files_scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.files_listbox.yview)
        self.files_listbox.configure(yscrollcommand=files_scrollbar.set)
        
        self.files_listbox.pack(side="left", fill="both", expand=True)
        files_scrollbar.pack(side="right", fill="y")
        
        # Live count under the list
        self.files_count_label = ttk.Label(attachments_frame, text="0 archivos seleccionados", foreground="#666666")
        self.files_count_label.pack(anchor="w", pady=(5, 0))
        
        # RIGHT SIDE: Adicionales files management
        adicionales_files_frame = ttk.LabelFrame(right_frame, text="Archivos de Adicionales", padding="10")
        adicionales_files_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Instructions
        ttk.Label(
            adicionales_files_frame,
            text="Archivos de adicionales que se moverán automáticamente:",
            font=("Arial", 10)
        ).pack(anchor="w", pady=(0, 10))
        
        # Info text
        info_text = ("Los archivos de adicionales seleccionados en la pestaña 'Adicionales' "
                    "se moverán automáticamente desde la carpeta de licitaciones a la "
                    "carpeta de certificaciones correspondiente.")
        
        info_label = ttk.Label(
            adicionales_files_frame,
            text=info_text,
            wraplength=300,
            justify="left",
            font=("Arial", 9),
            foreground="#666666"
        )
        info_label.pack(anchor="w", pady=(0, 10))
        
        # Adicionales files preview
        ttk.Label(adicionales_files_frame, text="Vista previa de archivos de adicionales:").pack(anchor="w")
        
        adicionales_list_container = ttk.Frame(adicionales_files_frame)
        adicionales_list_container.pack(fill="both", expand=True, pady=(5, 0))
        
        self.adicionales_files_listbox = tk.Listbox(adicionales_list_container, height=6)
        adicionales_scrollbar = ttk.Scrollbar(adicionales_list_container, orient="vertical", 
                                            command=self.adicionales_files_listbox.yview)
        self.adicionales_files_listbox.configure(yscrollcommand=adicionales_scrollbar.set)
        
        self.adicionales_files_listbox.pack(side="left", fill="both", expand=True)
        adicionales_scrollbar.pack(side="right", fill="y")
        
        # Refresh button for adicionales files
        ttk.Button(
            adicionales_files_frame,
            text="🔄 Actualizar Lista",
            command=self._refresh_adicionales_files
        ).pack(pady=(10, 0))
        
        # File validation summary
        validation_frame = ttk.LabelFrame(main_container, text="Resumen de Archivos", padding="10")
        validation_frame.pack(fill="x", pady=(10, 0))
        
        self.files_summary_label = ttk.Label(
            validation_frame,
            text="No hay archivos seleccionados",
            font=("Arial", 10),
            foreground="#666666"
        )
        self.files_summary_label.pack(anchor="w")
        
        # Load initial state
        self._refresh_files_display()
        self._refresh_adicionales_files()
        
        # Try to enable drag-and-drop (best-effort, optional dependency)
        self._enable_drag_and_drop_for_files()
    
    def _select_files(self) -> None:
        """Open file dialog to select files for attachment."""
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
            except Exception as e:
                from utils.error_logger import logger
                logger.warning(f"Failed to determine initial directory for file dialog", {"error": str(e)})
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
                    title="Seleccionar archivos para certificación",
                    initialdir=initial_dir,
                    filetypes=[
                        ("Archivos PDF", "*.pdf"),
                        ("Archivos Excel", "*.xlsx *.xls"),
                        ("Archivos Word", "*.docx *.doc"),
                        ("Archivos AutoCAD", "*.dwg"),
                        ("Archivos Revit", "*.rvt"),
                        ("Todos los archivos", "*.*")
                    ]
                )
            except Exception as dialog_error:
                print(f"File dialog error: {dialog_error}")
                # Fallback: try without parent
                file_paths = filedialog.askopenfilenames(
                    title="Seleccionar archivos para certificación",
                    initialdir=initial_dir,
                    filetypes=[
                        ("Archivos PDF", "*.pdf"),
                        ("Todos los archivos", "*.*")
                    ]
                )
            
            if file_paths:
                added_count = 0
                for file_path in file_paths:
                    try:
                        path_obj = Path(file_path)
                        if path_obj.exists() and path_obj not in self.selected_files:
                            self.selected_files.append(path_obj)
                            added_count += 1
                    except Exception as path_error:
                        print(f"Error processing file path {file_path}: {path_error}")
                        continue
                
                if added_count > 0:
                    self._refresh_files_display()
                    messagebox.showinfo("Éxito", f"Se agregaron {added_count} archivos correctamente.")
                else:
                    messagebox.showwarning("Aviso", "No se pudieron agregar archivos o ya estaban en la lista.")
            else:
                print("No files selected or dialog cancelled")
                
        except Exception as e:
            import traceback
            error_msg = f"Error al seleccionar archivos: {str(e)}"
            print(f"{error_msg}\n{traceback.format_exc()}")
            messagebox.showerror("Error", f"No se pudo abrir el selector de archivos.\n\nDetalles técnicos: {str(e)}")
    
    def _enable_drag_and_drop_for_files(self) -> None:
        """Enable drag-and-drop on the files list area if tkdnd/TkinterDnD2 is available.
        This is best-effort and will silently skip if not available in the environment."""
        try:
            # Lazy import to avoid hard dependency
            from TkinterDnD2 import DND_FILES  # type: ignore
        except Exception:
            # Drag-and-drop not available; skip gracefully
            return

        try:
            # Register the listbox as a drop target
            if self.files_listbox is not None:
                # Some environments provide drop_target_register via tkdnd
                if hasattr(self.files_listbox, 'drop_target_register'):
                    self.files_listbox.drop_target_register(DND_FILES)
                # Bind drop event
                if hasattr(self.files_listbox, 'dnd_bind'):
                    self.files_listbox.dnd_bind('<<Drop>>', self._on_files_dropped)
        except Exception:
            # Any issue enabling DnD: ignore to avoid breaking normal usage
            pass

    def _on_files_dropped(self, event) -> None:
        """Handle files dropped onto the listbox.
        Attempts to parse the platform-specific file list and add them to selection."""
        try:
            if not event or not getattr(event, 'data', None):
                return

            file_paths = self._parse_dropped_file_list(event.data)
            if not file_paths:
                return

            added_count = 0
            for file_path in file_paths:
                try:
                    path_obj = Path(file_path)
                    if path_obj.exists() and path_obj not in self.selected_files:
                        self.selected_files.append(path_obj)
                        added_count += 1
                except Exception:
                    continue

            if added_count > 0:
                self._refresh_files_display()
        except Exception:
            # Swallow DnD errors to keep UI responsive
            pass

    @staticmethod
    def _parse_dropped_file_list(data: str) -> List[str]:
        """Parse the OS-specific dropped files string into a list of file paths.
        Prefer using Tcl list splitting when available; fallback to shlex for robustness.
        This function is intentionally static so it can be unit-tested without a GUI.
        """
        if not data:
            return []

        # Commonly, tkdnd provides a Tcl-formatted list. Try to use Tcl splitlist if available.
        # We cannot access a Tcl interpreter here without a Tk root, so use a robust fallback.
        # Fallback approach: replace braces used by tkdnd for paths with spaces, then shlex split.
        try:
            cleaned = data.replace('{', '"').replace('}', '"')
            parts = shlex.split(cleaned)
            return parts
        except Exception:
            # Final fallback: return the raw string as a single path
            return [data]
    def _remove_selected_file(self) -> None:
        """Remove selected file from the list."""
        try:
            selection = self.files_listbox.curselection()
            if not selection:
                messagebox.showwarning("Aviso", "Por favor, seleccione un archivo para quitar.")
                return
            
            # Remove in reverse order to maintain indices
            for index in reversed(selection):
                if 0 <= index < len(self.selected_files):
                    self.selected_files.pop(index)
            
            self._refresh_files_display()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al quitar archivo: {str(e)}")
    
    def _refresh_files_display(self) -> None:
        """Refresh the files listbox display."""
        try:
            self.files_listbox.delete(0, tk.END)
            
            for file_path in self.selected_files:
                display_name = f"{file_path.name} ({file_path.parent.name})"
                self.files_listbox.insert(tk.END, display_name)
            
            # Update summary
            self._update_files_summary()
            
            # Update live count label
            count = len(self.selected_files)
            if hasattr(self, 'files_count_label') and self.files_count_label is not None:
                if count == 0:
                    self.files_count_label.config(text="0 archivos seleccionados", foreground="#666666")
                elif count == 1:
                    self.files_count_label.config(text="1 archivo seleccionado", foreground="green")
                else:
                    self.files_count_label.config(text=f"{count} archivos seleccionados", foreground="green")
            
        except Exception as e:
            print(f"Error refreshing files display: {e}")
    
    def _refresh_adicionales_files(self) -> None:
        """Refresh the adicionales files preview."""
        try:
            self.adicionales_files_listbox.delete(0, tk.END)
            
            # Get files for selected adicionales
            if hasattr(self, 'selected_adicionales') and self.selected_adicionales:
                # Get files from callbacks if available
                if 'get_adicionales_files' in self.callbacks:
                    files_info = self.callbacks['get_adicionales_files'](self.selected_adicionales)
                    
                    for adicional_id, files in files_info.items():
                        # Find the adicional details to show company name instead of ID
                        adicional = next((a for a in self.available_adicionales if a['id'] == adicional_id), None)
                        if adicional:
                            name = adicional.get('name') or adicional.get('id')
                            company = adicional.get('company', '')
                            adicional_label = f"{name} — {company}" if company else f"{name}"
                        else:
                            adicional_label = adicional_id
                        
                        for file_path in files:
                            display_name = f"[{adicional_label}] {Path(file_path).name}"
                            self.adicionales_files_listbox.insert(tk.END, display_name)
                
                if self.adicionales_files_listbox.size() == 0:
                    self.adicionales_files_listbox.insert(tk.END, "No hay archivos para los adicionales seleccionados")
            else:
                self.adicionales_files_listbox.insert(tk.END, "No hay adicionales seleccionados")
                
        except Exception as e:
            print(f"Error refreshing adicionales files: {e}")
    
    def _update_files_summary(self) -> None:
        """Update the files summary label."""
        try:
            if not self.selected_files:
                summary_text = "No hay archivos seleccionados"
            else:
                total_size = 0
                for file_path in self.selected_files:
                    if file_path.exists():
                        total_size += file_path.stat().st_size
                
                size_mb = total_size / (1024 * 1024)
                summary_text = f"{len(self.selected_files)} archivo(s) seleccionado(s), {size_mb:.1f} MB total"
            
            self.files_summary_label.config(text=summary_text)
            
        except Exception as e:
            self.files_summary_label.config(text="Error calculando resumen de archivos")
    
    def _validate_all_files(self) -> List[Dict[str, Any]]:
        """Validate all selected files and return validation results."""
        results = []
        
        for file_path in self.selected_files:
            validation = self._validate_file(file_path)
            results.append(validation)
        
        return results
    
    def _validate_file(self, file_path: Path) -> Dict[str, Any]:
        """Validate a single file."""
        result = {
            'file_path': file_path,
            'valid': True,
            'warnings': [],
            'errors': []
        }
        
        if not file_path.exists():
            result['valid'] = False
            result['errors'].append('El archivo no existe')
            return result
        
        # Check file size
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            result['warnings'].append(f'Archivo grande: {size_mb:.1f} MB')
        
        # Check file extension
        ext = file_path.suffix.lower()
        allowed_extensions = {'.pdf', '.xlsx', '.xls', '.docx', '.doc', '.dwg', '.rvt'}
        if ext not in allowed_extensions:
            result['warnings'].append(f'Tipo de archivo inusual: {ext}')
        
        return result