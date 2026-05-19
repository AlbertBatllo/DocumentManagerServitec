"""
Preset Creation Dialog
UI for creating plano presets with project phases.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, List, Any
from .base_view import BaseView


class PresetCreationDialog(BaseView):
    """Dialog for creating plano presets from templates or custom presets."""
    
    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.dialog = None
        self.callbacks = {}
        
        # UI Variables
        self.template_var = tk.StringVar()
        self.custom_name_var = tk.StringVar()
        self.custom_phase_var = tk.StringVar()
        self.checkbox_vars = {}
        self.selected_count_label = None
        self.fullscreen_button = None
        
        # Window state
        self.is_fullscreen = False
        self.normal_geometry = None
        
        # Data
        self.available_templates = {}
        self.project_phases = [
            "Implantación",
            "Proyecto Básico", 
            "Proyecto Ejecutivo",
            "Dirección Obra"
        ]
    
    def show(self, callbacks: Dict[str, Callable]) -> None:
        """Show the preset creation dialog."""
        self.callbacks = callbacks
        
        # Load available templates
        try:
            self.available_templates = callbacks.get('get_preset_templates', lambda: {})()
        except Exception as e:
            print(f"Error loading preset templates: {e}")
            self.available_templates = {}
        
        # Create dialog window
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Crear Presets de Planos")
        
        # Better sizing for Windows compatibility
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        
        # Use 80% of screen size, minimum 900x700 for Windows
        window_width = max(900, int(screen_width * 0.8))
        window_height = max(700, int(screen_height * 0.8))
        
        self.dialog.geometry(f"{window_width}x{window_height}")
        self.dialog.resizable(True, True)
        
        # Make dialog modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Keyboard shortcuts removed - no fullscreen functionality needed
        
        # Center the dialog
        self._center_dialog()
        
        # Create UI
        self._create_ui()
        
        # Initialize with first template if available
        if self.available_templates:
            first_template = list(self.available_templates.keys())[0]
            self.template_var.set(first_template)
            print(f"DEBUG: Initialized dialog with template: {first_template}")
        else:
            print("DEBUG: No templates available for initialization")
    
    def _center_dialog(self) -> None:
        """Center the dialog on the parent window."""
        self.dialog.update_idletasks()
        
        # Get dialog dimensions
        dialog_width = self.dialog.winfo_reqwidth()
        dialog_height = self.dialog.winfo_reqheight()
        
        # Get parent window position and size
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        # Calculate center position
        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
    
    def _create_ui(self) -> None:
        """Create the dialog UI."""
        # Window controls toolbar at the top
        toolbar_frame = ttk.Frame(self.dialog)
        toolbar_frame.pack(fill="x", padx=5, pady=5)
        
        # Window controls removed - no maximize functionality needed
        
        # Main container
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="Crear Presets de Planos",
            font=("Arial", 16, "bold")
        )
        title_label.pack(pady=(0, 20))
        
        # Create notebook for different creation methods
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=(0, 15))
        
        # Tab 1: From Template
        template_frame = ttk.Frame(notebook, padding="15")
        notebook.add(template_frame, text="Desde Plantilla")
        self._create_template_tab(template_frame)
        
        # Tab 2: Custom Preset
        custom_frame = ttk.Frame(notebook, padding="15")
        notebook.add(custom_frame, text="Preset Personalizado")
        self._create_custom_tab(custom_frame)
        
        # Tab 3: Phase Status
        status_frame = ttk.Frame(notebook, padding="15")
        notebook.add(status_frame, text="Estado de Fases")
        self._create_status_tab(status_frame)
        
        # Bottom buttons with improved layout
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0), side="bottom")
        
        # Add some padding and make buttons more prominent
        ttk.Button(
            button_frame,
            text="Cerrar",
            command=self._close_dialog,
            width=15
        ).pack(side="right", padx=(10, 0))
        
        # Help text for Windows users
        help_label = ttk.Label(
            button_frame,
            text="💡 Si no ves todos los elementos, usa las barras de desplazamiento",
            font=("Arial", 8),
            foreground="#999999"
        )
        help_label.pack(side="left")
    
    def _create_template_tab(self, parent: ttk.Frame) -> None:
        """Create the template-based creation tab with checkbox interface."""
        # Instructions
        instructions = ttk.Label(
            parent,
            text="Selecciona los planos que deseas crear como presets. Se crearán con el nombre y fase especificados, en estado S0 (sin archivos).",
            font=("Arial", 10),
            foreground="#666666",
            wraplength=700,
            justify="left"
        )
        instructions.pack(anchor="w", pady=(0, 15))
        
        # Template info
        template_info_frame = ttk.Frame(parent)
        template_info_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(
            template_info_frame,
            text="Plantilla: Proyecto de Construcción (90 planos)",
            font=("Arial", 12, "bold")
        ).pack(side="left")
        
        ttk.Button(
            template_info_frame,
            text="Ver Resumen por Fases",
            command=self._show_phase_summary
        ).pack(side="right")
        
        # Create notebook for phases
        phases_notebook = ttk.Notebook(parent)
        phases_notebook.pack(fill="both", expand=True, pady=(0, 15))
        
        # Store checkbox variables
        self.checkbox_vars = {}
        
        # Get template data
        template = self.available_templates.get('construction_project', {})
        presets = template.get('presets', [])
        
        # Group presets by phase
        presets_by_phase = {}
        for preset in presets:
            phase = preset.get('phase', 'Sin fase')
            if phase not in presets_by_phase:
                presets_by_phase[phase] = []
            presets_by_phase[phase].append(preset)
        
        # Create tab for each phase
        for phase in self.project_phases:
            if phase in presets_by_phase:
                phase_frame = ttk.Frame(phases_notebook, padding="10")
                phases_notebook.add(phase_frame, text=f"{phase} ({len(presets_by_phase[phase])})")
                self._create_phase_checkboxes(phase_frame, phase, presets_by_phase[phase])
        
        # Selection buttons
        selection_frame = ttk.Frame(parent)
        selection_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Button(
            selection_frame,
            text="Seleccionar Todos",
            command=self._select_all_checkboxes
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            selection_frame,
            text="Deseleccionar Todos",
            command=self._deselect_all_checkboxes
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            selection_frame,
            text="Solo Proyecto Básico",
            command=lambda: self._select_phase_only("Proyecto Básico")
        ).pack(side="left", padx=(0, 10))
        
        ttk.Button(
            selection_frame,
            text="Solo Proyecto Ejecutivo",
            command=lambda: self._select_phase_only("Proyecto Ejecutivo")
        ).pack(side="left")
        
        # Create button
        create_frame = ttk.Frame(parent)
        create_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(
            create_frame,
            text="📋 Crear Estructura de Proyecto",
            command=self._create_template_from_checkboxes,
            width=30
        ).pack(side="left", padx=(0, 10))
        
        ttk.Label(
            create_frame,
            text="→ Crea todos los planos seleccionados como documentos sin estado",
            font=("Arial", 9),
            foreground="#666666"
        ).pack(side="left")
        
        # Selected count label
        self.selected_count_label = ttk.Label(
            create_frame,
            text="0 planos seleccionados",
            foreground="#666666"
        )
        self.selected_count_label.pack(side="right")
    
    def _create_phase_checkboxes(self, parent: ttk.Frame, phase: str, presets: List[Dict]) -> None:
        """Create checkboxes for presets in a phase."""
        # Create scrollable frame
        canvas = tk.Canvas(parent, height=300)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Phase header
        phase_header = ttk.Label(
            scrollable_frame,
            text=f"Fase: {phase} ({len(presets)} planos)",
            font=("Arial", 11, "bold")
        )
        phase_header.pack(anchor="w", pady=(0, 10))
        
        # Create checkboxes for each preset
        for i, preset in enumerate(presets):
            preset_name = preset.get('name', '')
            description = preset.get('description', '')
            
            # Create frame for checkbox and description
            preset_frame = ttk.Frame(scrollable_frame)
            preset_frame.pack(fill="x", pady=2, padx=5)
            
            # Checkbox variable
            var = tk.BooleanVar()
            checkbox_key = f"{phase}:{preset_name}"
            self.checkbox_vars[checkbox_key] = var
            var.trace_add('write', self._update_selected_count)
            
            # Checkbox
            checkbox = ttk.Checkbutton(
                preset_frame,
                text=preset_name,
                variable=var,
                width=35
            )
            checkbox.pack(side="left", anchor="w")
            
            # Description label
            if description and description != preset_name:
                desc_label = ttk.Label(
                    preset_frame,
                    text=f"({description})",
                    font=("Arial", 9),
                    foreground="#666666"
                )
                desc_label.pack(side="left", padx=(10, 0))
        
        # Update scrollregion
        scrollable_frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
    
    def _create_custom_tab(self, parent: ttk.Frame) -> None:
        """Create the custom preset creation tab."""
        # Instructions
        instructions = ttk.Label(
            parent,
            text="Crear un preset personalizado especificando el nombre y la fase del proyecto:",
            font=("Arial", 10),
            foreground="#666666"
        )
        instructions.pack(anchor="w", pady=(0, 20))
        
        # Custom preset form
        form_frame = ttk.Frame(parent)
        form_frame.pack(fill="x", pady=(0, 20))
        
        # Name field
        ttk.Label(form_frame, text="Nombre del Plano:").grid(row=0, column=0, sticky="w", pady=5)
        name_entry = ttk.Entry(form_frame, textvariable=self.custom_name_var, width=40)
        name_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)
        
        # Phase field
        ttk.Label(form_frame, text="Fase del Proyecto:").grid(row=1, column=0, sticky="w", pady=5)
        phase_combo = ttk.Combobox(
            form_frame,
            textvariable=self.custom_phase_var,
            values=self.project_phases,
            state="readonly",
            width=37
        )
        phase_combo.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=5)
        phase_combo.set(self.project_phases[0])  # Default to first phase
        
        # Configure grid weights
        form_frame.columnconfigure(1, weight=1)
        
        # Create button
        ttk.Button(
            parent,
            text="Crear Preset Personalizado",
            command=self._create_custom_preset
        ).pack(pady=(10, 0))
        
        # Info about custom presets
        info_text = (
            "Los presets personalizados se crean en estado S0 (Borrador) y pueden ser "
            "completados por tu equipo. Utiliza nombres descriptivos como "
            "'Planta Baja', 'Instalación Eléctrica', etc."
        )
        info_label = ttk.Label(
            parent,
            text=info_text,
            font=("Arial", 9),
            foreground="#666666",
            wraplength=600,
            justify="left"
        )
        info_label.pack(anchor="w", pady=(20, 0))
    
    def _create_status_tab(self, parent: ttk.Frame) -> None:
        """Create the phase status overview tab."""
        # Title
        ttk.Label(
            parent,
            text="Estado de Completitud por Fase",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", pady=(0, 15))
        
        # Get phase completion status
        try:
            phase_status = self.callbacks.get('get_phase_status', lambda: {})()
        except Exception as e:
            print(f"Error getting phase status: {e}")
            phase_status = {}
        
        if not phase_status:
            # Show message if no data
            ttk.Label(
                parent,
                text="No hay datos de planos disponibles.",
                font=("Arial", 10),
                foreground="#666666"
            ).pack(anchor="w", pady=20)
            return
        
        # Create progress display for each phase
        for phase, stats in phase_status.items():
            phase_frame = ttk.LabelFrame(parent, text=phase, padding="10")
            phase_frame.pack(fill="x", pady=(0, 10))
            
            total = stats.get('total', 0)
            completed = stats.get('completed_count', 0)
            s3_count = stats.get('s3_count', 0)
            s3a_count = stats.get('s3a_count', 0)
            
            if total == 0:
                progress_text = "Sin planos registrados"
                progress_percent = 0
            else:
                progress_percent = (completed / total) * 100
                progress_text = f"{completed}/{total} planos listos ({progress_percent:.1f}%)"
            
            # Progress bar
            progress_frame = ttk.Frame(phase_frame)
            progress_frame.pack(fill="x", pady=(0, 5))
            
            progress_bar = ttk.Progressbar(
                progress_frame,
                length=300,
                mode='determinate',
                value=progress_percent
            )
            progress_bar.pack(side="left", padx=(0, 10))
            
            ttk.Label(progress_frame, text=progress_text).pack(side="left")
            
            # Detail breakdown
            if total > 0:
                detail_text = f"S3 (Revisado): {s3_count} • S3A (Aprobado): {s3a_count}"
                ttk.Label(
                    phase_frame,
                    text=detail_text,
                    font=("Arial", 9),
                    foreground="#666666"
                ).pack(anchor="w")
        
        # Refresh button
        ttk.Button(
            parent,
            text="Actualizar Estado",
            command=lambda: self._create_status_tab(parent)
        ).pack(pady=(15, 0))
    
    
    def _create_custom_preset(self) -> None:
        """Create a custom preset."""
        name = self.custom_name_var.get().strip()
        phase = self.custom_phase_var.get()
        
        if not name:
            messagebox.showwarning("Nombre requerido", "Por favor, ingresa un nombre para el plano.")
            return
        
        if not phase:
            messagebox.showwarning("Fase requerida", "Por favor, selecciona una fase del proyecto.")
            return
        
        # Create custom preset
        try:
            success = self.callbacks.get('create_custom_preset', lambda x, y: False)(name, phase)
            
            if success:
                messagebox.showinfo(
                    "Preset Creado",
                    f"Se creó el preset '{name}' para la fase '{phase}' exitosamente."
                )
                
                # Clear form
                self.custom_name_var.set("")
                self.custom_phase_var.set(self.project_phases[0])
                
                # Refresh the parent view if callback available
                if 'refresh_view' in self.callbacks:
                    self.callbacks['refresh_view']()
            else:
                messagebox.showwarning(
                    "Preset Existente", 
                    f"Ya existe un plano con el nombre '{name}'."
                )
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al crear preset: {e}")
    
    def _show_phase_summary(self) -> None:
        """Show phase summary information."""
        summary_text = """Resumen por Fases del Proyecto de Construcción:

• Implantación (1 plano):
  - Topográfico inicial

• Proyecto Básico (7 planos):
  - Portada, situación, ordenación, accesos
  - Justificación urbanística y condicionantes
  - Acometidas

• Proyecto Ejecutivo (76 planos):
  - Arquitectura: Plantas, fachadas, detalles (16 planos)
  - Estructura: Cimentación, vertical, horizontal (10 planos)  
  - Instalaciones: PCI, electricidad, fontanería, etc. (50 planos)

• Dirección Obra (6 planos):
  - Organización de obra y seguridad (ESS)
  - Residuos, desvíos, conexiones provisionales"""
        
        messagebox.showinfo("Resumen por Fases", summary_text)
    
    def _update_selected_count(self, *args) -> None:
        """Update the selected count label."""
        if hasattr(self, 'checkbox_vars') and hasattr(self, 'selected_count_label'):
            selected_count = sum(1 for var in self.checkbox_vars.values() if var.get())
            self.selected_count_label.config(text=f"{selected_count} planos seleccionados")
    
    def _select_all_checkboxes(self) -> None:
        """Select all checkboxes."""
        for var in self.checkbox_vars.values():
            var.set(True)
    
    def _deselect_all_checkboxes(self) -> None:
        """Deselect all checkboxes."""
        for var in self.checkbox_vars.values():
            var.set(False)
    
    def _select_phase_only(self, target_phase: str) -> None:
        """Select only checkboxes for a specific phase."""
        for key, var in self.checkbox_vars.items():
            phase = key.split(':')[0]
            var.set(phase == target_phase)
    
    def _create_template_from_checkboxes(self) -> None:
        """Create project template structure from selected checkboxes."""
        # Get selected presets
        selected_presets = []
        for key, var in self.checkbox_vars.items():
            if var.get():
                phase, preset_name = key.split(':', 1)
                selected_presets.append(preset_name)
        
        if not selected_presets:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona al menos un plano para crear la estructura del proyecto.")
            return
        
        # Show confirmation dialog
        count = len(selected_presets)
        phases = {}
        for key, var in self.checkbox_vars.items():
            if var.get():
                phase, preset_name = key.split(':', 1)
                if phase not in phases:
                    phases[phase] = 0
                phases[phase] += 1
        
        phase_summary = ", ".join([f"{phase}: {count}" for phase, count in phases.items()])
        
        confirm_message = (
            f"¿Crear estructura de proyecto con {count} planos?\n\n"
            f"Distribución por fases:\n{phase_summary}\n\n"
            f"Los planos se crearán como documentos sin estado (plantillas vacías) "
            f"que tu equipo puede completar subiendo archivos."
        )
        
        if not messagebox.askyesno("Confirmar Creación de Estructura", confirm_message):
            return
        
        # Create template structure
        try:
            created_presets = self.callbacks.get('create_presets_from_template', lambda x, y: [])(
                'construction_project', selected_presets
            )
            
            if created_presets:
                created_count = len(created_presets)
                skipped_count = count - created_count
                
                success_message = f"✅ Estructura de proyecto creada exitosamente!\n\n"
                success_message += f"📋 {created_count} planos creados como plantillas sin estado\n"
                
                if skipped_count > 0:
                    success_message += f"⚠️ {skipped_count} planos ya existían (omitidos)\n"
                
                success_message += f"\n🎯 Los planos aparecen en el dashboard como plantillas vacías\n"
                success_message += f"🚀 Tu equipo puede empezar a subir archivos para activarlos"
                
                messagebox.showinfo("Estructura Creada", success_message)
                
                # Refresh the parent view if callback available
                if 'refresh_view' in self.callbacks:
                    self.callbacks['refresh_view']()
                    
                # Close dialog after successful creation
                self._close_dialog()
            else:
                messagebox.showinfo("Sin Cambios", 
                    "Todos los planos seleccionados ya existían en el proyecto.\n\n"
                    "💡 Los planos existentes aparecen en el dashboard organizados por fase.\n"
                    "📋 Puedes agregar entradas para convertir plantillas en planos activos.")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al crear estructura del proyecto: {e}")
    
    # Fullscreen toggle method removed - no maximize functionality needed

    def _close_dialog(self) -> None:
        """Close the dialog."""
        if self.dialog:
            self.dialog.destroy()