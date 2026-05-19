import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog, colorchooser
from typing import Callable, Optional, List, Tuple, Dict
from pathlib import Path
import json
from datetime import datetime
import subprocess
import os
from .base_view import BaseView


class SimplePDFCorrector(BaseView):
    """Simple PDF correction tool - minimal and efficient."""
    
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.document_info = {}
        self.corrections = []  # All corrections for this document - JSON-based storage
        self.current_tool = "text"
        self.current_color = "#FF0000"  # Red
        self.current_thickness = 2
        self.colors = ["#FF0000", "#0000FF", "#00AA00", "#000000"]  # Red, Blue, Green, Black
        self.canvas = None
        self.scale_factor = 1.0  # Current scale factor for responsive scaling
        self.base_font_size = 12  # Base font size for text
        self.canvas_width = 800  # Default canvas width
        self.canvas_height = 600  # Default canvas height
        self.base_canvas_width = 800  # Reference canvas width for scaling
        self.base_canvas_height = 600  # Reference canvas height for scaling
        
        # Performance optimization: minimal state tracking
        self.corrections_loaded = False
        self.last_scale_factor = 1.0

    def show(self, pdf_path: str, callbacks: dict, document_info: dict = None, user_name: str = "") -> None:
        """Show the simple PDF corrector."""
        self.callbacks = callbacks
        self.document_info = document_info or {}
        self.pdf_path = pdf_path
        
        # Load existing corrections
        self.load_corrections()
        
        self.clear_window()
        self.set_window_size(1200, 800)
        
        # Add notification widget if user and callbacks available
        if user_name and 'get_notification_data' in callbacks:
            self.setup_notification_widget(
                get_notifications_callback=lambda: callbacks.get('get_notification_data')(user_name),
                mark_read_callback=callbacks.get('mark_notification_as_read'),
                navigate_callback=callbacks.get('navigate_to_document'),
                current_user=user_name,
                delete_callback=callbacks.get('delete_notification')
            )
        
        self.create_corrector_interface()

    def create_corrector_interface(self) -> None:
        """Create the correction interface."""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))
        
        doc_name = self.document_info.get('name', 'Documento')
        doc_id = self.document_info.get('id', 'N/A')
        version = self.document_info.get('version', 'N/A')
        status = self.document_info.get('status', 'N/A')
        
        ttk.Label(
            header_frame, 
            text=f"Proceso de Corrección: {doc_name} (ID: {doc_id}, v{version}, Estado: {status})",
            font=("Arial", 12, "bold")
        ).pack(side="left")
        
        # Toolbar
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.pack(fill="x", pady=(0, 10))
        
        # Tools
        tools_frame = ttk.LabelFrame(toolbar_frame, text="Herramientas", padding=5)
        tools_frame.pack(side="left", padx=(0, 10))
        
        self.tool_var = tk.StringVar(value="text")
        
        ttk.Radiobutton(
            tools_frame, text="Texto", variable=self.tool_var, 
            value="text", command=self.change_tool
        ).pack(side="left", padx=2)
        
        ttk.Radiobutton(
            tools_frame, text="Lápiz", variable=self.tool_var, 
            value="draw", command=self.change_tool
        ).pack(side="left", padx=2)
        
        
        # Colors
        colors_frame = ttk.LabelFrame(toolbar_frame, text="Colores", padding=5)
        colors_frame.pack(side="left", padx=(0, 10))
        
        # Store color buttons for later reference
        self.color_buttons = []
        
        for i, color in enumerate(self.colors):
            # Create a solid colored canvas instead of button to avoid color issues
            color_canvas = tk.Canvas(
                colors_frame, bg=color, width=25, height=20,
                highlightthickness=2, highlightbackground="black",
                cursor="hand2"
            )
            color_canvas.pack(side="left", padx=2, pady=2)
            
            # Bind click event to canvas
            color_canvas.bind("<Button-1>", lambda e, c=color, idx=i: self.set_color(c, idx))
            self.color_buttons.append(color_canvas)
        
        # Thickness
        thickness_frame = ttk.LabelFrame(toolbar_frame, text="Grosor", padding=5)
        thickness_frame.pack(side="left", padx=(0, 10))
        
        # Create a slider for thickness from 2 to 5
        self.thickness_var = tk.IntVar(value=self.current_thickness)
        thickness_slider = tk.Scale(
            thickness_frame, from_=2, to=5, orient="horizontal",
            variable=self.thickness_var, command=self.set_thickness,
            length=80, showvalue=True
        )
        thickness_slider.pack(side="left", padx=5)
        
        # Current settings display
        settings_frame = ttk.LabelFrame(toolbar_frame, text="Actual", padding=5)
        settings_frame.pack(side="left", padx=(0, 10))
        
        self.current_display = tk.Label(
            settings_frame, 
            text=f"Color: {self.current_color}, Grosor: {self.current_thickness}",
            bg=self.current_color, fg="white", padx=10
        )
        self.current_display.pack()
        
        # PDF Actions
        pdf_frame = ttk.LabelFrame(toolbar_frame, text="PDF", padding=5)
        pdf_frame.pack(side="right")
        
        ttk.Button(
            pdf_frame, text="Abrir PDF", 
            command=self.open_pdf_external
        ).pack(side="left", padx=2)
        
        # Content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True)
        
        # Left side - Drawing canvas (simulates PDF) - 3/5 of screen
        canvas_frame = ttk.LabelFrame(content_frame, text="Área de Corrección", padding=5)
        canvas_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # Instructions
        ttk.Label(
            canvas_frame, 
            text="Haz clic para agregar texto, dibujar o comentar. El PDF se abre externamente.",
            font=("Arial", 10, "italic")
        ).pack(pady=5)
        
        # Canvas for annotations - no scrollbars, everything scales
        self.canvas = tk.Canvas(canvas_frame, bg="white")
        self.canvas.pack(fill="both", expand=True, pady=5)
        
        # Bind canvas events
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Right side - Corrections panel - 2/5 of screen
        corrections_frame = ttk.LabelFrame(content_frame, text="Registro de Correcciones", padding=5)
        corrections_frame.pack(side="right", fill="both", padx=(10, 0))
        
        # Configure the frame to take up about 2/5 of the screen
        def configure_corrections_width(event=None):
            total_width = content_frame.winfo_width()
            if total_width > 1:
                corrections_width = int(total_width * 0.4)  # 2/5 of screen
                corrections_frame.configure(width=corrections_width)
                
                # Update scale factor based on canvas dimensions
                canvas_width = int(total_width * 0.6)  # 3/5 of screen
                # We need to get the actual canvas height, but use a reasonable default
                canvas_height = self.canvas.winfo_height() if hasattr(self, 'canvas') else 600
                if canvas_width > 100 and canvas_height > 100:  # Avoid invalid dimensions
                    self.update_scale_factor(canvas_width, canvas_height)
        
        content_frame.bind("<Configure>", configure_corrections_width)
        
        # Corrections list
        list_frame = ttk.Frame(corrections_frame)
        list_frame.pack(fill="both", expand=True)
        
        # Headers
        ttk.Label(list_frame, text="Historial de Correcciones", font=("Arial", 10, "bold")).pack()
        
        # Scrollable frame for correction cards
        canvas_frame = ttk.Frame(list_frame)
        canvas_frame.pack(fill="both", expand=True, pady=5)
        
        self.corrections_canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.corrections_canvas.yview)
        self.corrections_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.corrections_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Scrollable frame inside canvas
        self.corrections_scroll_frame = tk.Frame(self.corrections_canvas, bg="white")
        self.corrections_canvas_window = self.corrections_canvas.create_window((0, 0), window=self.corrections_scroll_frame, anchor="nw")
        
        # Bind scrolling and canvas resizing
        self.corrections_scroll_frame.bind("<Configure>", self.on_corrections_frame_configure)
        self.corrections_canvas.bind("<Configure>", self.on_corrections_canvas_configure)
        
        # Bind mousewheel to canvas
        self.corrections_canvas.bind("<MouseWheel>", self.on_mousewheel)
        
        # Comment input
        comment_frame = ttk.LabelFrame(corrections_frame, text="Agregar Comentario", padding=5)
        comment_frame.pack(fill="x", pady=(10, 0))
        
        self.comment_entry = tk.Text(comment_frame, height=4, wrap="word", font=("Arial", 9))
        comment_scroll = ttk.Scrollbar(comment_frame, orient="vertical", command=self.comment_entry.yview)
        self.comment_entry.configure(yscrollcommand=comment_scroll.set)
        
        self.comment_entry.pack(side="left", fill="both", expand=True)
        comment_scroll.pack(side="right", fill="y")
        
        # Comment buttons
        comment_buttons_frame = ttk.Frame(corrections_frame)
        comment_buttons_frame.pack(fill="x", pady=5)
        
        ttk.Button(
            comment_buttons_frame, text="Publicar Comentario",
            command=self.add_global_comment_from_entry
        ).pack(fill="x", padx=2)
        
        # Bottom buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(
            button_frame, text="Guardar Correcciones",
            command=self.save_corrections
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame, text="Limpiar Cambios Actuales",
            command=self.clear_unsaved_corrections
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame, text="<< Volver",
            command=self.callbacks.get('back', lambda: None)
        ).pack(side="right", padx=5)
        
        # Load and display existing corrections
        self.update_corrections_display()
        self.redraw_canvas()

    def change_tool(self) -> None:
        """Change the current tool."""
        self.current_tool = self.tool_var.get()
        
        cursor = "crosshair" if self.current_tool == "draw" else "arrow"
        self.canvas.configure(cursor=cursor)

    def set_color(self, color: str, button_index: int = None) -> None:
        """Set current color."""
        self.current_color = color
        self.update_display()
        
        # Update canvas states to show selection
        if hasattr(self, 'color_buttons') and button_index is not None:
            for i, canvas in enumerate(self.color_buttons):
                if i == button_index:
                    # Selected canvas - thicker border
                    canvas.configure(highlightthickness=3, highlightbackground="white")
                else:
                    # Unselected canvas - normal border
                    canvas.configure(highlightthickness=2, highlightbackground="black")

    def set_thickness(self, thickness) -> None:
        """Set current thickness."""
        self.current_thickness = int(thickness)
        self.update_display()

    def update_display(self) -> None:
        """Update the current settings display."""
        self.current_display.configure(
            text=f"Color: {self.current_color}, Grosor: {self.current_thickness}",
            bg=self.current_color,
            fg="white" if self.current_color != "#FFFF00" else "black"
        )

    def on_canvas_click(self, event) -> None:
        """Handle canvas click."""
        if self.current_tool == "text":
            self.add_text_annotation(event.x, event.y)
        elif self.current_tool == "draw":
            self.start_drawing(event.x, event.y)

    def on_canvas_drag(self, event) -> None:
        """Handle canvas drag for drawing."""
        if self.current_tool == "draw" and hasattr(self, 'drawing'):
            self.continue_drawing(event.x, event.y)

    def on_canvas_release(self, event) -> None:
        """Handle canvas release."""
        if self.current_tool == "draw" and hasattr(self, 'drawing'):
            self.finish_drawing()

    def add_text_annotation(self, x: int, y: int) -> None:
        """Add text annotation at position."""
        text = tk.simpledialog.askstring(
            "Agregar Texto",
            "Ingrese el texto:"
        )
        
        if text:
            # Add to canvas with scaled font based on thickness
            base_font_size = self.base_font_size + (self.current_thickness - 2) * 3  # Scale font with thickness
            scaled_font_size = max(8, int(base_font_size * self.scale_factor))
            text_id = self.canvas.create_text(
                x, y, text=text, fill=self.current_color,
                font=("Arial", scaled_font_size, "bold"), anchor="nw"
            )
            
            # Add to corrections
            correction = {
                "id": len(self.corrections) + 1,
                "type": "text",
                "content": text,
                "x": x,
                "y": y,
                "color": self.current_color,
                "thickness": self.current_thickness,
                "author": self.document_info.get('current_user', 'Usuario'),
                "timestamp": datetime.now().isoformat(),
                "canvas_id": text_id,
                "saved": False
            }
            
            self.corrections.append(correction)
            self.update_corrections_display()
            self.update_canvas_scroll_region()

    def add_position_comment(self, x: int, y: int) -> None:
        """Add positioned comment."""
        comment = tk.simpledialog.askstring(
            "Agregar Comentario",
            "Ingrese su comentario:"
        )
        
        if comment:
            # Add marker to canvas with scaled size
            marker_size = max(3, int(5 * self.scale_factor))
            marker_id = self.canvas.create_oval(
                x-marker_size, y-marker_size, x+marker_size, y+marker_size, 
                fill=self.current_color, outline="black", width=max(1, int(2 * self.scale_factor))
            )
            
            # Add to corrections
            correction = {
                "id": len(self.corrections) + 1,
                "type": "comment",
                "content": comment,
                "x": x,
                "y": y,
                "color": self.current_color,
                "thickness": self.current_thickness,
                "author": self.document_info.get('current_user', 'Usuario'),
                "timestamp": datetime.now().isoformat(),
                "canvas_id": marker_id,
                "saved": False
            }
            
            self.corrections.append(correction)
            self.update_corrections_display()
            self.update_canvas_scroll_region()

    def start_drawing(self, x: int, y: int) -> None:
        """Start drawing."""
        self.drawing = {
            "points": [(x, y)],
            "color": self.current_color,
            "thickness": self.current_thickness,
            "line_ids": []
        }

    def continue_drawing(self, x: int, y: int) -> None:
        """Continue drawing."""
        if hasattr(self, 'drawing'):
            last_point = self.drawing["points"][-1]
            
            # Draw line segment with scaled thickness
            scaled_thickness = max(1, int(self.drawing["thickness"] * self.scale_factor))
            line_id = self.canvas.create_line(
                last_point[0], last_point[1], x, y,
                fill=self.drawing["color"],
                width=scaled_thickness,
                capstyle="round", smooth=True
            )
            
            self.drawing["points"].append((x, y))
            self.drawing["line_ids"].append(line_id)

    def finish_drawing(self) -> None:
        """Finish drawing."""
        if hasattr(self, 'drawing'):
            # Add to corrections
            correction = {
                "id": len(self.corrections) + 1,
                "type": "drawing",
                "content": f"Dibujo de {len(self.drawing['points'])} puntos",
                "points": self.drawing["points"],
                "color": self.drawing["color"],
                "thickness": self.drawing["thickness"],
                "author": self.document_info.get('current_user', 'Usuario'),
                "timestamp": datetime.now().isoformat(),
                "canvas_ids": self.drawing["line_ids"],
                "saved": False
            }
            
            self.corrections.append(correction)
            self.update_corrections_display()
            self.update_canvas_scroll_region()
            
            del self.drawing

    def add_global_comment(self) -> None:
        """Add global comment."""
        comment = tk.simpledialog.askstring(
            "Comentario Global",
            "Ingrese comentario general del documento:"
        )
        
        if comment:
            correction = {
                "id": len(self.corrections) + 1,
                "type": "global_comment",
                "content": comment,
                "color": "#000000",
                "thickness": 0,
                "author": self.document_info.get('current_user', 'Usuario'),
                "timestamp": datetime.now().isoformat(),
                "saved": False
            }
            
            self.corrections.append(correction)
            self.update_corrections_display()
            self.update_canvas_scroll_region()
    
    def add_global_comment_from_entry(self) -> None:
        """Add global comment from entry box."""
        comment = self.comment_entry.get("1.0", tk.END).strip()
        
        if comment:
            correction = {
                "id": len(self.corrections) + 1,
                "type": "global_comment",
                "content": comment,
                "color": "#000000",
                "thickness": 0,
                "author": self.document_info.get('current_user', 'Usuario'),
                "timestamp": datetime.now().isoformat(),
                "saved": False
            }
            
            self.corrections.append(correction)
            self.update_corrections_display()
            self.update_canvas_scroll_region()
            
            # Clear the entry
            self.comment_entry.delete("1.0", tk.END)
        else:
            messagebox.showwarning("Advertencia", "Ingrese un comentario antes de guardarlo.")
    

    def on_corrections_frame_configure(self, event=None) -> None:
        """Handle corrections frame configuration."""
        self.corrections_canvas.configure(scrollregion=self.corrections_canvas.bbox("all"))
    
    def on_corrections_canvas_configure(self, event=None) -> None:
        """Handle corrections canvas configuration to adjust window width."""
        canvas_width = self.corrections_canvas.winfo_width()
        self.corrections_canvas.itemconfig(self.corrections_canvas_window, width=canvas_width)
    
    def on_mousewheel(self, event) -> None:
        """Handle mousewheel scrolling in corrections list."""
        self.corrections_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def update_corrections_display(self) -> None:
        """Update the corrections list display with card-like interface that adapts to window size."""
        # Clear existing widgets
        for widget in self.corrections_scroll_frame.winfo_children():
            widget.destroy()
        
        # Sort corrections by timestamp (newest first)
        sorted_corrections = sorted(self.corrections, key=lambda x: x["timestamp"], reverse=True)
        
        # Calculate adaptive scaling for correction cards based on window size
        corrections_scale = max(0.8, min(1.5, self.scale_factor))
        
        # Scale fonts and padding based on window size
        base_author_font_size = 14
        base_time_font_size = 12
        base_content_font_size = 13
        base_padding_x = 12
        base_padding_y = 8
        base_card_padding_y = 3
        base_card_internal_padding = 5
        
        scaled_author_font_size = max(12, int(base_author_font_size * corrections_scale))
        scaled_time_font_size = max(10, int(base_time_font_size * corrections_scale))
        scaled_content_font_size = max(11, int(base_content_font_size * corrections_scale))
        scaled_padding_x = max(8, int(base_padding_x * corrections_scale))
        scaled_padding_y = max(6, int(base_padding_y * corrections_scale))
        scaled_card_padding_y = max(2, int(base_card_padding_y * corrections_scale))
        scaled_card_internal_padding = max(4, int(base_card_internal_padding * corrections_scale))
        
        for i, correction in enumerate(sorted_corrections):
            # Create card frame with different styling for saved/unsaved
            is_saved = correction.get('saved', False)
            card_bg = "#d0d0d0" if is_saved else "#f5f5f5"
            
            card_frame = tk.Frame(self.corrections_scroll_frame, relief="solid", borderwidth=1, bg=card_bg)
            card_frame.pack(fill="x", padx=0, pady=scaled_card_padding_y, ipady=scaled_card_internal_padding)
            
            # Author and timestamp header
            header_frame = tk.Frame(card_frame, bg=card_bg)
            header_frame.pack(fill="x", padx=scaled_padding_x, pady=scaled_padding_y)
            
            author_text = correction["author"]
            if is_saved:
                author_text += " ✓"  # Checkmark for saved corrections
            
            author_label = tk.Label(
                header_frame, 
                text=author_text, 
                font=("Arial", scaled_author_font_size, "bold"),
                bg=card_bg,
                fg="#444444" if is_saved else "black"
            )
            author_label.pack(side="left")
            
            time_str = correction["timestamp"][:16].replace("T", " ")
            time_label = tk.Label(
                header_frame, 
                text=time_str, 
                font=("Arial", scaled_time_font_size),
                foreground="gray",
                bg=card_bg
            )
            time_label.pack(side="right")
            
            # Content
            content_frame = tk.Frame(card_frame, bg=card_bg)
            content_frame.pack(fill="x", padx=scaled_padding_x, pady=(0, scaled_padding_y))
            
            type_icon = {"text": "📝", "drawing": "✏️", "comment": "💬", "global_comment": "📋"}
            icon = type_icon.get(correction['type'], '•')
            
            # Show drawing comment or allow editing
            if correction['type'] == 'drawing':
                comment_text = correction.get('comment', '')
                if is_saved:
                    content_text = f"{icon} {comment_text}" if comment_text else f"{icon} (Dibujo guardado)"
                else:
                    content_text = f"{icon} {comment_text}" if comment_text else f"{icon} (Doble-clic para comentar)"
            else:
                content_text = f"{icon} {correction['content']}"
            
            # Calculate adaptive wrap length based on corrections panel width
            base_wrap_length = 400
            scaled_wrap_length = max(200, int(base_wrap_length * corrections_scale))
            
            content_label = tk.Label(
                content_frame,
                text=content_text,
                font=("Arial", scaled_content_font_size),
                wraplength=scaled_wrap_length,
                justify="left",
                anchor="w",
                bg=card_bg,
                fg="#444444" if is_saved else "black"
            )
            content_label.pack(fill="x", expand=True, anchor="w")
            
            # Make card clickable
            def on_card_click(event, idx=i):
                self.highlight_correction(sorted_corrections[idx])
            
            # Make drawing corrections double-clickable for editing
            def on_drawing_double_click(event, idx=i):
                if sorted_corrections[idx]['type'] == 'drawing':
                    self.edit_drawing_comment(sorted_corrections[idx])
                else:
                    self.highlight_correction(sorted_corrections[idx])
            
            # Bind click events to all widgets in the card
            for widget in [card_frame, header_frame, content_frame, author_label, time_label]:
                widget.bind("<Button-1>", on_card_click)
                widget.bind("<Double-Button-1>", on_drawing_double_click)
            
            # Special handling for content label
            content_label.bind("<Button-1>", on_card_click)
            if correction['type'] == 'drawing':
                content_label.bind("<Double-Button-1>", on_drawing_double_click)
            else:
                content_label.bind("<Double-Button-1>", on_card_click)
        
        # Update scroll region
        self.corrections_scroll_frame.update_idletasks()
        self.corrections_canvas.configure(scrollregion=self.corrections_canvas.bbox("all"))
    
    def update_scale_factor(self, canvas_width, canvas_height) -> None:
        """Update scale factor based on canvas dimensions."""
        # Base scale factor on both width and height - use the smaller ratio to fit content
        width_scale = canvas_width / self.base_canvas_width
        height_scale = canvas_height / self.base_canvas_height
        
        # Use the smaller scale to ensure content fits in both dimensions
        new_scale_factor = max(0.3, min(3.0, min(width_scale, height_scale)))
        
        # Performance optimization: only redraw if scale changed significantly
        if abs(new_scale_factor - self.last_scale_factor) > 0.05:
            self.scale_factor = new_scale_factor
            self.last_scale_factor = new_scale_factor
            
            # Update current canvas dimensions
            self.canvas_width = canvas_width
            self.canvas_height = canvas_height
            
            # Redraw all corrections with new scale
            self.redraw_canvas()
            
            # Update corrections display with new scale
            self.update_corrections_display()
    
    def on_canvas_configure(self, event) -> None:
        """Handle canvas resize events."""
        # Update canvas dimensions
        self.canvas_width = event.width
        self.canvas_height = event.height
        
        # Update scale factor based on new size
        if self.canvas_width > 100 and self.canvas_height > 100:  # Avoid invalid dimensions
            self.update_scale_factor(self.canvas_width, self.canvas_height)
    
    def edit_drawing_comment(self, correction) -> None:
        """Edit comment for a drawing correction."""
        # Only allow editing if the correction is not saved
        if correction.get('saved', False):
            messagebox.showwarning(
                "Corrección guardada",
                "No se puede editar una corrección que ya ha sido guardada."
            )
            return
            
        current_comment = correction.get('comment', '')
        
        comment = tk.simpledialog.askstring(
            "Editar Comentario de Dibujo",
            "Ingrese comentario para este dibujo:",
            initialvalue=current_comment
        )
        
        if comment is not None:  # User didn't cancel
            correction['comment'] = comment
            self.update_corrections_display()
    
    def highlight_correction(self, correction) -> None:
        """Highlight the selected correction on the canvas."""
        # Remove previous highlights
        self.canvas.delete("highlight")
        
        # Find and highlight the correction
        if correction["type"] == "text":
            # Find text item and add highlight around it
            if "canvas_id" in correction:
                coords = self.canvas.coords(correction["canvas_id"])
                if coords:
                    x, y = coords[0], coords[1]
                    # Create scaled highlight rectangle around text
                    highlight_padding = 5 * self.scale_factor
                    highlight_width = 150 * self.scale_factor
                    highlight_height = 20 * self.scale_factor
                    self.canvas.create_rectangle(
                        x-highlight_padding, y-highlight_padding, 
                        x+highlight_width, y+highlight_height,
                        outline="yellow", width=max(1, int(3 * self.scale_factor)), 
                        fill="yellow", stipple="gray50",
                        tags="highlight"
                    )
        
        elif correction["type"] == "drawing":
            # Highlight drawing by adding outline
            if "canvas_ids" in correction:
                for canvas_id in correction["canvas_ids"]:
                    try:
                        coords = self.canvas.coords(canvas_id)
                        if len(coords) >= 4:
                            # Create scaled highlight around line
                            highlight_width = max(1, int((correction["thickness"] + 4) * self.scale_factor))
                            self.canvas.create_line(
                                coords[0], coords[1], coords[2], coords[3],
                                fill="yellow", width=highlight_width,
                                capstyle="round", smooth=True, tags="highlight"
                            )
                    except (ValueError, TypeError, AttributeError) as e:
                        # Skip invalid coordinates or canvas operations
                        print(f"Warning: Failed to draw highlight for correction: {e}")
                        continue
        
        elif correction["type"] == "comment":
            # Highlight comment marker
            if "canvas_id" in correction:
                coords = self.canvas.coords(correction["canvas_id"])
                if len(coords) >= 4:
                    x1, y1, x2, y2 = coords[:4]
                    # Create scaled highlight ring around comment
                    highlight_padding = 8 * self.scale_factor
                    highlight_width = max(1, int(3 * self.scale_factor))
                    self.canvas.create_oval(
                        x1-highlight_padding, y1-highlight_padding, 
                        x2+highlight_padding, y2+highlight_padding,
                        outline="yellow", width=highlight_width, fill="", tags="highlight"
                    )


    def redraw_canvas(self) -> None:
        """Redraw all corrections on canvas."""
        self.canvas.delete("all")
        
        # Update scroll region to accommodate all content
        self.update_canvas_scroll_region()
        
        for correction in self.corrections:
            if correction["type"] == "text":
                # Scale both position and font size based on thickness
                scaled_x = correction["x"] * self.scale_factor
                scaled_y = correction["y"] * self.scale_factor
                base_font_size = self.base_font_size + (correction["thickness"] - 2) * 3  # Scale font with thickness
                scaled_font_size = max(8, int(base_font_size * self.scale_factor))
                text_id = self.canvas.create_text(
                    scaled_x, scaled_y, 
                    text=correction["content"], 
                    fill=correction["color"],
                    font=("Arial", scaled_font_size, "bold"), anchor="nw"
                )
                correction["canvas_id"] = text_id
                
            elif correction["type"] == "comment":
                # Scale both position and marker size
                scaled_x = correction["x"] * self.scale_factor
                scaled_y = correction["y"] * self.scale_factor
                marker_size = max(3, int(5 * self.scale_factor))
                marker_width = max(1, int(2 * self.scale_factor))
                marker_id = self.canvas.create_oval(
                    scaled_x-marker_size, scaled_y-marker_size, 
                    scaled_x+marker_size, scaled_y+marker_size,
                    fill=correction["color"], outline="black", width=marker_width
                )
                correction["canvas_id"] = marker_id
                
            elif correction["type"] == "drawing" and "points" in correction:
                line_ids = []
                points = correction["points"]
                # Scale line thickness and all coordinates
                scaled_thickness = max(1, int(correction["thickness"] * self.scale_factor))
                for i in range(1, len(points)):
                    # Scale all coordinates
                    scaled_x1 = points[i-1][0] * self.scale_factor
                    scaled_y1 = points[i-1][1] * self.scale_factor
                    scaled_x2 = points[i][0] * self.scale_factor
                    scaled_y2 = points[i][1] * self.scale_factor
                    
                    line_id = self.canvas.create_line(
                        scaled_x1, scaled_y1, scaled_x2, scaled_y2,
                        fill=correction["color"],
                        width=scaled_thickness,
                        capstyle="round", smooth=True
                    )
                    line_ids.append(line_id)
                correction["canvas_ids"] = line_ids
    
    def update_canvas_scroll_region(self) -> None:
        """Update canvas scroll region - not needed anymore since we removed scrollbars."""
        # This method is kept for compatibility but does nothing
        # since we removed scrollbars and everything scales instead
        pass

    def open_pdf_external(self) -> None:
        """Open PDF in external viewer."""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(self.pdf_path)
            elif os.name == 'posix':  # macOS and Linux
                subprocess.Popen(['open', self.pdf_path])
        except (FileNotFoundError, OSError) as e:
            messagebox.showerror("Error", f"No se pudo abrir el PDF: {str(e)}")

    def clear_corrections(self) -> None:
        """Clear all corrections."""
        if messagebox.askyesno("Confirmar", "¿Eliminar todas las correcciones?"):
            self.corrections = []
            self.canvas.delete("all")
            self.update_corrections_display()
            self.comment_entry.delete("1.0", tk.END)
    
    def clear_unsaved_corrections(self) -> None:
        """Clear only unsaved corrections (changes since last save)."""
        if messagebox.askyesno("Confirmar", "¿Eliminar solo los cambios actuales no guardados?"):
            # Reload corrections from file to get last saved state
            self.load_corrections()
            self.canvas.delete("all")
            self.redraw_canvas()
            self.update_corrections_display()
            self.comment_entry.delete("1.0", tk.END)

    def save_corrections(self) -> None:
        """Save corrections to JSON file."""
        doc_id = self.document_info.get('id', 'unknown')
        version = self.document_info.get('version', 'unknown')
        
        # Determine document type and create appropriate directory
        doc_type = self.document_info.get('doc_type', 'planos')  # Default to planos
        from utils.path_helper import PathHelper
        pm_path = PathHelper.get_project_manager_path()
        corrections_dir = pm_path / doc_type / "corrections"
        corrections_dir.mkdir(parents=True, exist_ok=True)
        
        corrections_file = corrections_dir / f"corrections_{doc_id}_{version}.json"
        
        # Prepare data for JSON (remove canvas IDs)
        json_corrections = []
        for correction in self.corrections:
            json_correction = correction.copy()
            # Remove canvas-specific data
            json_correction.pop('canvas_id', None)
            json_correction.pop('canvas_ids', None)
            json_corrections.append(json_correction)
        
        data = {
            "document_id": doc_id,
            "version": version,
            "document_name": self.document_info.get('name', ''),
            "corrections": json_corrections,
            "total_corrections": len(json_corrections),
            "last_modified": datetime.now().isoformat(),
            "last_author": self.document_info.get('current_user', 'Usuario')
        }
        
        try:
            from utils.file_manager import FileManager
            FileManager.safe_json_write(str(corrections_file), data)
            
            # Mark all corrections as saved after successful save
            for correction in self.corrections:
                correction['saved'] = True
                
            messagebox.showinfo("Éxito", f"Correcciones guardadas:\n{corrections_file}")
        except Exception as e:
            messagebox.showerror("Error", f"Error al guardar: {str(e)}")

    def load_corrections(self) -> None:
        """Load existing corrections from JSON file."""
        doc_id = self.document_info.get('id', 'unknown')
        version = self.document_info.get('version', 'unknown')
        
        # Determine document type and check appropriate directory
        doc_type = self.document_info.get('doc_type', 'planos')  # Default to planos
        from utils.path_helper import PathHelper
        pm_path = PathHelper.get_project_manager_path()
        corrections_dir = pm_path / doc_type / "corrections"
        corrections_file = corrections_dir / f"corrections_{doc_id}_{version}.json"
        
        if corrections_file.exists():
            try:
                from utils.file_manager import FileManager
                data = FileManager.safe_json_read(str(corrections_file))
                self.corrections = data.get('corrections', [])
                # Mark all loaded corrections as saved
                for correction in self.corrections:
                    correction['saved'] = True
            except Exception as e:
                print(f"Error loading corrections: {e}")
                self.corrections = []
        else:
            self.corrections = []


# Add missing imports at the top
import tkinter.simpledialog