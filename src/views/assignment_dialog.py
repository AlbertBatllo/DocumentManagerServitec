import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Any, Optional, Tuple
# from controllers.notification_controller import NotificationController  # Removed


class AssignmentDialog:
    def __init__(self, parent, document_id: str, document_name: str, 
                 from_state: str, to_state: str, project_path=None):
        self.parent = parent
        self.document_id = document_id
        self.document_name = document_name
        self.from_state = from_state
        self.to_state = to_state
        self.project_path = project_path
        
        # self.notification_controller = NotificationController(project_path)  # Removed
        self.result = None  # Will contain assignment_id if created
        self.selected_users = []
        
        self.dialog = None
        self.user_vars = {}  # username -> tkinter.BooleanVar
        self.notes_text = None
        
    def show(self) -> Optional[str]:
        """Show assignment dialog and return assignment_id if created"""
        self._create_dialog()
        return self.result
    
    def _create_dialog(self):
        """Create and show the assignment dialog"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Asignar Responsables")
        self.dialog.geometry("500x600")
        self.dialog.resizable(True, True)
        
        # Make modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Add proper window protocol handling for Windows close button
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)
        
        # Center on parent
        self._center_on_parent()
        
        # Create UI
        self._create_header()
        self._create_user_selection()
        self._create_notes_section()
        self._create_buttons()
        
        # Focus and wait
        self.dialog.focus_set()
        self.dialog.wait_window()
    
    def _center_on_parent(self):
        """Center dialog on parent window"""
        self.dialog.update_idletasks()
        
        # Get parent position and size
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        # Get dialog size
        dialog_width = self.dialog.winfo_reqwidth()
        dialog_height = self.dialog.winfo_reqheight()
        
        # Calculate position
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        self.dialog.geometry(f"+{x}+{y}")
    
    def _create_header(self):
        """Create header with document information"""
        header_frame = ttk.Frame(self.dialog)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        # Title
        title_label = ttk.Label(header_frame, text="Asignar Responsables", 
                               font=("Arial", 14, "bold"))
        title_label.pack()
        
        # Document info
        info_frame = ttk.Frame(header_frame)
        info_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(info_frame, text="Documento:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Label(info_frame, text=f"{self.document_id} - {self.document_name}").grid(
            row=0, column=1, sticky=tk.W)
        
        ttk.Label(info_frame, text="Transición:", font=("Arial", 10, "bold")).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(5, 0))
        
        # State transition with colors
        transition_frame = ttk.Frame(info_frame)
        transition_frame.grid(row=1, column=1, sticky=tk.W, pady=(5, 0))
        
        from_label = tk.Label(transition_frame, text=self.from_state, 
                             bg="#E0E0E0", fg="black", padx=8, pady=2, 
                             relief=tk.RAISED, borderwidth=1)
        from_label.pack(side=tk.LEFT)
        
        arrow_label = ttk.Label(transition_frame, text=" → ", font=("Arial", 12, "bold"))
        arrow_label.pack(side=tk.LEFT)
        
        to_color = self._get_state_color(self.to_state)
        to_label = tk.Label(transition_frame, text=self.to_state, 
                           bg=to_color, fg="black" if to_color != "#FF0000" else "white", 
                           padx=8, pady=2, relief=tk.RAISED, borderwidth=1)
        to_label.pack(side=tk.LEFT)
    
    def _get_state_color(self, state: str) -> str:
        """Get color for state"""
        colors = {
            "S0": "#FFFFFF",
            "S1": "#FFFF00", 
            "S2": "#00AAE4",
            "S3": "#90EE90",
            "A": "#008F39",
            "B": "#FF0000"
        }
        return colors.get(state, "#E0E0E0")
    
    def _create_user_selection(self):
        """Create user selection area with checkboxes"""
        selection_frame = ttk.LabelFrame(self.dialog, text="Seleccionar Responsables", padding=10)
        selection_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Instructions
        instruction_label = ttk.Label(selection_frame, 
                                     text="Selecciona uno o más usuarios para asignar esta tarea:",
                                     font=("Arial", 10))
        instruction_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Get available users - DISABLED
        try:
            # available_users = self.notification_controller.get_available_users_for_assignment()  # Removed
            available_users = []  # Disabled - no users available
        except Exception as e:
            messagebox.showerror("Error", f"Error al obtener usuarios: {e}")
            self.dialog.destroy()
            return
        
        if not available_users:
            no_users_label = ttk.Label(selection_frame, 
                                      text="No hay usuarios disponibles para asignación.",
                                      foreground="red")
            no_users_label.pack(pady=20)
            return
        
        # Create scrollable frame for users
        canvas = tk.Canvas(selection_frame, height=200)
        scrollbar = ttk.Scrollbar(selection_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create checkboxes for users
        self.user_vars = {}
        for i, user in enumerate(available_users):
            var = tk.BooleanVar()
            self.user_vars[user["name"]] = var
            
            user_frame = ttk.Frame(scrollable_frame)
            user_frame.pack(fill=tk.X, pady=2)
            
            checkbox = ttk.Checkbutton(user_frame, variable=var, 
                                     text=user["name"],
                                     command=self._update_selection)
            checkbox.pack(side=tk.LEFT)
            
            # Show additional info if available
            if user.get("email"):
                email_label = ttk.Label(user_frame, text=f"({user['email']})", 
                                      foreground="blue", font=("Arial", 9))
                email_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Selection counter
        self.selection_label = ttk.Label(selection_frame, text="Usuarios seleccionados: 0")
        self.selection_label.pack(anchor=tk.W, pady=(10, 0))
    
    def _update_selection(self):
        """Update selection counter"""
        selected_count = sum(1 for var in self.user_vars.values() if var.get())
        self.selection_label.config(text=f"Usuarios seleccionados: {selected_count}")
        self.selected_users = [name for name, var in self.user_vars.items() if var.get()]
    
    def _create_notes_section(self):
        """Create notes section"""
        notes_frame = ttk.LabelFrame(self.dialog, text="Notas (opcional)", padding=10)
        notes_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.notes_text = tk.Text(notes_frame, height=4, wrap=tk.WORD)
        notes_scrollbar = ttk.Scrollbar(notes_frame, orient=tk.VERTICAL, 
                                       command=self.notes_text.yview)
        self.notes_text.configure(yscrollcommand=notes_scrollbar.set)
        
        self.notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        notes_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Placeholder text
        placeholder = "Agregar instrucciones adicionales para los responsables..."
        self.notes_text.insert("1.0", placeholder)
        self.notes_text.config(foreground="gray")
        
        def on_focus_in(event):
            if self.notes_text.get("1.0", tk.END).strip() == placeholder:
                self.notes_text.delete("1.0", tk.END)
                self.notes_text.config(foreground="black")
        
        def on_focus_out(event):
            if not self.notes_text.get("1.0", tk.END).strip():
                self.notes_text.insert("1.0", placeholder)
                self.notes_text.config(foreground="gray")
        
        self.notes_text.bind("<FocusIn>", on_focus_in)
        self.notes_text.bind("<FocusOut>", on_focus_out)
    
    def _create_buttons(self):
        """Create action buttons"""
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=(10, 20))
        
        # Cancel button
        cancel_btn = ttk.Button(button_frame, text="Cancelar", command=self._cancel)
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Create assignment button
        create_btn = ttk.Button(button_frame, text="Crear Asignación", 
                               command=self._create_assignment)
        create_btn.pack(side=tk.RIGHT)
        
        # Skip button (optional)
        skip_btn = ttk.Button(button_frame, text="Omitir", command=self._skip)
        skip_btn.pack(side=tk.LEFT)
    
    def _create_assignment(self):
        """Create the assignment"""
        if not self.selected_users:
            messagebox.showwarning("Advertencia", "Debes seleccionar al menos un usuario.")
            return
        
        # Get notes
        notes = self.notes_text.get("1.0", tk.END).strip()
        placeholder = "Agregar instrucciones adicionales para los responsables..."
        if notes == placeholder:
            notes = ""
        
        try:
            # assignment_id = self.notification_controller.create_assignment(
            #     document_id=self.document_id,
            #     document_name=self.document_name,
            #     from_state=self.from_state,
            #     to_state=self.to_state,
            #     assigned_users=self.selected_users,
            #     notes=notes
            # )  # Removed
            assignment_id = "disabled"  # Assignment functionality disabled
            
            self.result = assignment_id
            
            # Show success message
            users_text = ", ".join(self.selected_users)
            messagebox.showinfo("Éxito", 
                              f"Asignación creada exitosamente.\n\n"
                              f"Usuarios asignados: {users_text}\n"
                              f"ID de asignación: {assignment_id}")
            
            self.dialog.destroy()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al crear la asignación: {e}")
    
    def _cancel(self):
        """Cancel assignment creation"""
        self.result = None
        self.dialog.destroy()
    
    def _skip(self):
        """Skip assignment (don't create one)"""
        self.result = "skipped"
        self.dialog.destroy()