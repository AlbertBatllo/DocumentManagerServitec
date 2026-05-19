"""
Responsive Base View for Windows Compatibility
Provides adaptive window sizing for all forms.
"""

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional, Tuple
from .base_view import BaseView


class ResponsiveBaseView(BaseView):
    """
    Enhanced base view with responsive design and Windows compatibility features.
    Automatically adapts to different screen sizes.
    """
    
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        
        # Removed fullscreen variables - no longer needed for fixed-size windows
        
        # Screen dimensions
        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()
        
        # Keyboard shortcuts removed - no fullscreen functionality needed
    
    def get_adaptive_window_size(self, preferred_width: int, preferred_height: int, 
                                min_width: int = 800, min_height: int = 600) -> Tuple[int, int]:
        """
        Calculate adaptive window size based on screen dimensions.
        
        Args:
            preferred_width: Ideal window width
            preferred_height: Ideal window height  
            min_width: Minimum usable width
            min_height: Minimum usable height
            
        Returns:
            Tuple of (width, height) that fits the screen
        """
        # Use 85% of screen size maximum, but respect preferred size if it fits
        max_width = int(self.screen_width * 0.85)
        max_height = int(self.screen_height * 0.85)
        
        # Choose the best size
        width = min(max(preferred_width, min_width), max_width)
        height = min(max(preferred_height, min_height), max_height)
        
        return width, height
    
    def center_window_responsive(self, preferred_width: int, preferred_height: int,
                                min_width: int = 800, min_height: int = 600) -> None:
        """
        Center window with adaptive sizing for different screen sizes.
        
        Args:
            preferred_width: Ideal window width
            preferred_height: Ideal window height
            min_width: Minimum usable width  
            min_height: Minimum usable height
        """
        # Get adaptive size
        width, height = self.get_adaptive_window_size(preferred_width, preferred_height, 
                                                     min_width, min_height)
        
        # Center on screen
        x = (self.screen_width - width) // 2
        y = (self.screen_height - height) // 2
        
        # Set geometry
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Allow OS maximize/minimize functionality
        self.root.resizable(True, True)
        
        # Geometry set - no need to store for fixed-size windows
    
    def add_window_controls_toolbar(self, parent_frame: ttk.Frame) -> ttk.Frame:
        """
        Add empty window controls toolbar (maximize functionality disabled).
        
        Args:
            parent_frame: Parent frame to add toolbar to
            
        Returns:
            An empty toolbar frame for compatibility
        """
        # Return empty toolbar frame for compatibility
        toolbar_frame = ttk.Frame(parent_frame)
        # Don't pack it - no UI elements needed
        return toolbar_frame
    
    def create_bottom_button_frame(self, parent_frame: ttk.Frame, show_help: bool = True) -> ttk.Frame:
        """
        Create a responsive bottom button frame that's always accessible.
        
        Args:
            parent_frame: Parent frame
            show_help: Whether to show help text for small screens
            
        Returns:
            The button frame for adding buttons
        """
        # Bottom container - fixed at bottom
        bottom_container = ttk.Frame(parent_frame)
        bottom_container.pack(side="bottom", fill="x", pady=(10, 0))
        
        # Button frame with padding
        button_frame = ttk.Frame(bottom_container, padding="10")
        button_frame.pack(fill="x")
        
        # Help text for small screens
        if show_help:
            help_label = ttk.Label(
                button_frame,
                text="💡 Usa las barras de desplazamiento si no ves todos los elementos",
                font=("Arial", 8),
                foreground="#999999"
            )
            help_label.pack(side="left")
        
        return button_frame
    
    # Fullscreen methods removed - no maximize functionality needed
    
    def create_scrollable_content_frame(self, parent_frame: ttk.Frame) -> Tuple[tk.Canvas, ttk.Frame]:
        """
        Create a scrollable content frame for forms with many elements.
        
        Args:
            parent_frame: Parent frame
            
        Returns:
            Tuple of (canvas, scrollable_frame) for adding content
        """
        # Create canvas and scrollbar
        canvas = tk.Canvas(parent_frame)
        scrollbar = ttk.Scrollbar(parent_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        # Configure scrolling
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', 
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        # Bind mousewheel to canvas and scrollable frame
        canvas.bind("<MouseWheel>", _on_mousewheel)  # Windows
        canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))  # Linux
        canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))   # Linux
        
        # Create window in canvas
        canvas_frame = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # Make scrollable frame expand with canvas
        def configure_scroll_frame(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Make scrollable frame width match canvas width
            canvas_width = event.width
            canvas.itemconfig(canvas_frame, width=canvas_width)
        
        canvas.bind('<Configure>', configure_scroll_frame)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        return canvas, scrollable_frame
    
    def ensure_buttons_visible(self, button_frame: ttk.Frame) -> None:
        """
        Ensure buttons are visible and accessible by updating layout.
        
        Args:
            button_frame: Frame containing buttons
        """
        # Update layout
        button_frame.update_idletasks()
        
        # Check if window is too small for content
        window_height = self.root.winfo_height()
        required_height = self.root.winfo_reqheight()
        
        if required_height > window_height:
            # Window is too small, suggest scrollbars
            current_buttons = button_frame.winfo_children()
            def _has_help_text(child):
                try:
                    return "💡" in str(child.cget('text'))
                except Exception:
                    return False
            if current_buttons and not any(_has_help_text(child) for child in current_buttons):
                help_label = ttk.Label(
                    button_frame,
                    text="💡 Ventana pequeña - usa las barras de desplazamiento",
                    font=("Arial", 8),
                    foreground="#FF6600"  # Orange to draw attention
                )
                help_label.pack(side="left", padx=(20, 0))
    
    def get_screen_info(self) -> dict:
        """Get screen information for debugging."""
        return {
            'screen_width': self.screen_width,
            'screen_height': self.screen_height,
            'window_geometry': self.root.geometry(),
            'platform': self.root.tk.call('tk', 'windowingsystem')
        }