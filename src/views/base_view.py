import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, List, Callable
import shlex


class BaseView:
    # Class variable to store current window dimensions across all views
    _current_window_size = None
    # Class variable to store global TTK theme state
    _global_theme = None
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.logo_image = self._load_logo()
        self.notification_widget = None
        # Initialize global theme if not set
        self._init_global_theme()
        # Apply platform-specific styling
        self._apply_platform_styling()
        
    def _init_global_theme(self) -> None:
        """Initialize and store the global theme."""
        if BaseView._global_theme is None:
            try:
                style = ttk.Style()
                BaseView._global_theme = style.theme_use()
            except (AttributeError, tkinter.TclError) as e:
                print(f"Warning: Could not get theme, using default: {e}")
                BaseView._global_theme = 'default'
    
    @classmethod
    def preserve_theme(cls) -> str:
        """Get the current global theme."""
        try:
            style = ttk.Style()
            current_theme = style.theme_use()
            cls._global_theme = current_theme
            return current_theme
        except (AttributeError, tkinter.TclError) as e:
            print(f"Warning: Could not preserve theme: {e}")
            return cls._global_theme or 'default'
    
    @classmethod  
    def restore_global_theme(cls) -> None:
        """Restore the global theme."""
        if cls._global_theme:
            try:
                style = ttk.Style()
                if style.theme_use() != cls._global_theme:
                    style.theme_use(cls._global_theme)
            except Exception as e:
                print(f"Warning: Could not restore global theme: {e}")
    
    def _apply_platform_styling(self) -> None:
        """Apply platform-specific styling to ensure S0 white text visibility."""
        import platform
        import sys
        
        try:
            current_platform = platform.system()
            
            if current_platform == "Windows":
                # Apply dark background to ensure white S0 text is visible
                self.root.configure(bg="#2C2C2C")
                
                # Configure TTK styles for consistent dark theme
                style = ttk.Style()
                style.configure("TFrame", background="#2C2C2C")
                style.configure("TLabel", background="#2C2C2C", foreground="white")
                
                # Configure Treeview with dark background for S0 text visibility
                style.configure("Treeview", 
                              background="#404040",      # Dark background
                              foreground="white",        # Default text color
                              fieldbackground="#404040", # Field background
                              borderwidth=0)
                style.configure("Treeview.Heading", 
                              background="#505050", 
                              foreground="white",
                              relief="flat")
                
                # Preserve existing state colors but ensure they work on dark background
                # The S0 white color (#FFFFFF) will now be visible on dark background
                
        except Exception as e:
            # Silently continue if styling fails
            pass
        
    def _load_logo(self) -> Optional[tk.PhotoImage]:
        """Load the company logo."""
        try:
            # Try multiple possible logo locations
            logo_paths = [
                Path.cwd() / "Logo.png",  # Current working directory
                Path(__file__).parent.parent.parent / "Logo.png",  # Relative to source
                Path(__file__).parent / "Logo.png",  # Same directory as base_view.py
            ]
            
            for logo_path in logo_paths:
                if logo_path.exists():
                    return tk.PhotoImage(file=logo_path).subsample(5, 5)
            
            print("Warning: Logo.png not found. Continuing without logo.")
            return None
        except Exception as e:
            print(f"Warning: Could not load Logo.png: {e}")
            return None

    def create_header(self, parent: tk.Widget, title: str = "") -> ttk.Frame:
        """Create a standard header with logo."""
        header_frame = ttk.Frame(parent, padding=(10, 10, 10, 0))
        header_frame.pack(fill="x", expand=False)
        
        # Empty label to push content to the right
        ttk.Label(header_frame, text="").pack(side="left", expand=True)
        
        # Title if provided
        if title:
            title_label = ttk.Label(header_frame, text=title, font=("Arial", 14, "bold"))
            title_label.pack(side="left", padx=20)
        
        # Logo on the right
        if self.logo_image:
            logo_label = ttk.Label(header_frame, image=self.logo_image)
            logo_label.pack(side="right", padx=10)
        
        return header_frame

    def create_button_frame(self, parent: tk.Widget) -> ttk.Frame:
        """Create a standard button frame."""
        button_frame = ttk.Frame(parent, padding=(20, 10))
        button_frame.pack(fill="x", expand=False)
        return button_frame

    def create_visible_button(self, parent: tk.Widget, text: str, command, **kwargs) -> tk.Button:
        """Create a button with guaranteed text visibility on all platforms."""
        # For Windows compatibility, use tk.Button with explicit styling
        import sys
        
        if sys.platform.startswith('win'):
            # Windows: Use tk.Button with explicit colors for guaranteed visibility
            default_kwargs = {
                'bg': '#404040',          # Dark gray background
                'fg': '#FFFFFF',          # White text
                'activebackground': '#5A5A5A',  # Lighter gray when active
                'activeforeground': '#FFFFFF',   # White text when active
                'relief': 'raised',
                'borderwidth': 2,
                'font': ('Arial', 9, 'bold'),
                'cursor': 'hand2'
            }
            default_kwargs.update(kwargs)
            return tk.Button(parent, text=text, command=command, **default_kwargs)
        else:
            # macOS/Linux: Use ttk.Button (works fine on these platforms)
            return ttk.Button(parent, text=text, command=command, **kwargs)

    def clear_window(self) -> None:
        """Clear all widgets from the window and reset placement state."""
        # Hide notification widget first to ensure proper cleanup
        if hasattr(self, 'notification_widget') and self.notification_widget:
            try:
                self.notification_widget.hide_widget()
                self.notification_widget = None
            except (AttributeError, tkinter.TclError) as e:
                print(f"Warning: Could not hide notification widget: {e}")
                pass
        
        # Clear all children widgets
        for widget in self.root.winfo_children():
            try:
                # Reset all geometry managers to prevent sticky positioning
                widget.place_forget()
                widget.pack_forget()
                widget.grid_forget()
            except (AttributeError, tkinter.TclError) as e:
                print(f"Warning: Could not reset widget geometry: {e}")
                pass
            widget.destroy()
        
        # Force geometry update
        self.root.update_idletasks()

    def center_window(self, width: int = 800, height: int = 600) -> None:
        """Center the window on the screen, preserving user-expanded size if available."""
        # If user has previously expanded the window, use that size instead
        if BaseView._current_window_size is not None:
            current_width, current_height = BaseView._current_window_size
            # Only use the stored size if it's larger than the default
            if current_width >= width and current_height >= height:
                width, height = current_width, current_height
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Store this size and set up tracking for future changes
        BaseView._current_window_size = (width, height)
        self._setup_size_tracking()
    
    def _setup_size_tracking(self) -> None:
        """Set up tracking for window size changes."""
        def on_window_resize(event):
            # Only track if the event is for the main window
            if event.widget == self.root:
                new_geometry = self.root.geometry()
                # Parse width and height from geometry string (e.g., "800x600+100+100")
                size_part = new_geometry.split('+')[0]  # Get "800x600"
                if 'x' in size_part:
                    width_str, height_str = size_part.split('x')
                    try:
                        new_width = int(width_str)
                        new_height = int(height_str)
                        BaseView._current_window_size = (new_width, new_height)
                    except ValueError:
                        pass  # Ignore invalid geometry strings
        
        # Bind the resize event
        self.root.bind('<Configure>', on_window_resize)
    
    def set_window_size(self, width: int, height: int) -> None:
        """Set window size while preserving user-expanded dimensions."""
        # If user has previously expanded the window, use that size instead
        if BaseView._current_window_size is not None:
            current_width, current_height = BaseView._current_window_size
            # Only use the stored size if it's larger than the requested size
            if current_width >= width and current_height >= height:
                width, height = current_width, current_height
        
        self.root.geometry(f"{width}x{height}")
        
        # Store this size and set up tracking
        BaseView._current_window_size = (width, height)
        self._setup_size_tracking()
    
    def setup_notification_widget(self, get_notifications_callback, mark_read_callback, 
                                 navigate_callback, current_user: str, delete_callback=None):
        """Setup the notification widget for any view."""
        try:
            # Temporarily disable notification widget to avoid macOS crashes
            print(f"DEBUG: Notification widget setup skipped for {self.__class__.__name__} (macOS compatibility)")
            return
            
            # Import here to avoid circular imports
            # from .notification_widget import NotificationWidget  # Moved to future_implementations
            
            # Remove existing widget if any
            if self.notification_widget:
                try:
                    self.notification_widget.hide_widget()
                except (AttributeError, tkinter.TclError) as e:
                    print(f"Warning: Could not hide existing notification widget: {e}")
                    pass
            
            # Create new widget
            self.notification_widget = NotificationWidget(self.root)
            
            # Set callbacks
            self.notification_widget.set_callbacks(
                get_notifications=get_notifications_callback,
                mark_read=mark_read_callback,
                on_click=navigate_callback,
                delete_notification=delete_callback
            )
            
            # Set current user
            self.notification_widget.set_current_user(current_user)
            
            # Refresh and show
            self.notification_widget.refresh_count()
            self.notification_widget.show_widget()
            
            print(f"DEBUG: Notification widget setup for {self.__class__.__name__}")
            
        except Exception as e:
            print(f"ERROR: Failed to setup notification widget: {e}")
            import traceback
            traceback.print_exc()
    
    def ensure_notification_widget_visible(self):
        """Ensure the notification widget is visible and on top after UI creation."""
        # Temporarily disabled for macOS compatibility
        print("DEBUG: ensure_notification_widget_visible skipped (macOS compatibility)")
        return
        
        if self.notification_widget and hasattr(self.notification_widget, 'widget_frame'):
            if self.notification_widget.widget_frame and self.notification_widget.widget_frame.winfo_exists():
                self.notification_widget.show_widget()
            else:
                print("DEBUG: Notification widget frame not available for showing")
    
    def enable_drag_and_drop_for_listbox(self, listbox: tk.Listbox,
                                        on_files_dropped_callback: Callable[[List[Path]], None]) -> None:
        """Enable drag-and-drop on a listbox widget if tkdnd/TkinterDnD2 is available.

        Args:
            listbox: The Listbox widget to enable drag-and-drop on
            on_files_dropped_callback: Callback function that receives list of Path objects

        This is best-effort and will silently skip if not available in the environment.
        """
        try:
            # Lazy import to avoid hard dependency
            from tkinterdnd2 import DND_FILES  # type: ignore
        except Exception:
            print("DEBUG DnD: tkinterdnd2 not available, skipping listbox DnD")
            return

        if listbox is None:
            return

        # Store the callback for this specific listbox
        if not hasattr(self, '_drop_callbacks'):
            self._drop_callbacks = {}
        self._drop_callbacks[id(listbox)] = on_files_dropped_callback

        # Try direct method first, then fallback to tk.call
        registered = False
        try:
            listbox.drop_target_register(DND_FILES)
            registered = True
            print("DEBUG DnD: Listbox registered via drop_target_register")
        except (AttributeError, tk.TclError) as e:
            print(f"DEBUG DnD: drop_target_register failed for listbox: {e}, trying tk.call fallback")
            try:
                listbox.tk.call('tkdnd::drop_target', 'register', listbox._w, 'DND_Files')
                registered = True
                print("DEBUG DnD: Listbox registered via tk.call fallback")
            except tk.TclError as e2:
                print(f"DEBUG DnD: tk.call fallback also failed for listbox: {e2}")

        if not registered:
            return

        # Bind drop event
        try:
            listbox.dnd_bind('<<Drop>>',
                           lambda event: self._on_files_dropped_wrapper(event, listbox))
            print("DEBUG DnD: Listbox drop event bound via dnd_bind")
        except (AttributeError, tk.TclError) as e:
            print(f"DEBUG DnD: dnd_bind failed for listbox: {e}, trying tk.call fallback")
            try:
                listbox.tk.call('tkdnd::bind', listbox._w, '<<Drop>>',
                              listbox.register(lambda event: self._on_files_dropped_wrapper(event, listbox)))
                print("DEBUG DnD: Listbox drop event bound via tk.call fallback")
            except tk.TclError as e2:
                print(f"DEBUG DnD: Could not bind drop event for listbox: {e2}")
    
    def enable_drag_and_drop_for_treeview(self, treeview: ttk.Treeview,
                                         on_files_dropped_callback: Callable[[List[Path], Optional[str]], None]) -> None:
        """Enable drag-and-drop on a Treeview widget if tkinterdnd2 is available.

        Args:
            treeview: The Treeview widget to enable drag-and-drop on
            on_files_dropped_callback: Callback that receives (file_paths, row_id).
                row_id is the iid of the row under the cursor, or None if dropped on empty space.
        """
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore
        except Exception:
            print("DEBUG DnD: tkinterdnd2 not available, skipping treeview DnD")
            return

        if treeview is None:
            return

        if not hasattr(self, '_drop_callbacks'):
            self._drop_callbacks = {}
        self._drop_callbacks[id(treeview)] = on_files_dropped_callback

        # Try direct method first, then fallback to tk.call
        registered = False
        try:
            treeview.drop_target_register(DND_FILES)
            registered = True
            print("DEBUG DnD: Treeview registered via drop_target_register")
        except (AttributeError, tk.TclError) as e:
            print(f"DEBUG DnD: drop_target_register failed for treeview: {e}, trying tk.call fallback")
            try:
                treeview.tk.call('tkdnd::drop_target', 'register', treeview._w, 'DND_Files')
                registered = True
                print("DEBUG DnD: Treeview registered via tk.call fallback")
            except tk.TclError as e2:
                print(f"DEBUG DnD: tk.call fallback also failed for treeview: {e2}")

        if not registered:
            return

        # Bind drop event
        try:
            treeview.dnd_bind('<<Drop>>',
                              lambda event: self._on_files_dropped_treeview_wrapper(event, treeview))
            print("DEBUG DnD: Treeview drop event bound via dnd_bind")
        except (AttributeError, tk.TclError) as e:
            print(f"DEBUG DnD: dnd_bind failed for treeview: {e}, trying tk.call fallback")
            try:
                treeview.tk.call('tkdnd::bind', treeview._w, '<<Drop>>',
                              treeview.register(lambda event: self._on_files_dropped_treeview_wrapper(event, treeview)))
                print("DEBUG DnD: Treeview drop event bound via tk.call fallback")
            except tk.TclError as e2:
                print(f"DEBUG DnD: Could not bind drop event for treeview: {e2}")

    def _on_files_dropped_treeview_wrapper(self, event, treeview: ttk.Treeview) -> None:
        """Wrapper to handle dropped files on a Treeview and call the callback."""
        try:
            print(f"DEBUG DnD: Treeview drop event received, data={getattr(event, 'data', None)}")
            if not event or not getattr(event, 'data', None):
                return

            file_paths = self._parse_dropped_file_list(event.data)
            if not file_paths:
                print("DEBUG DnD: No file paths parsed from drop data")
                return

            path_objects = []
            for file_path in file_paths:
                try:
                    p = Path(file_path)
                    if p.exists():
                        path_objects.append(p)
                except (OSError, ValueError, TypeError):
                    continue

            if not path_objects:
                print("DEBUG DnD: No valid file paths found")
                return

            print(f"DEBUG DnD: {len(path_objects)} files dropped on treeview")

            # Determine which row is under the cursor
            # event.y from tkinterdnd2 may not be relative to the widget,
            # so use winfo_pointery - winfo_rooty as fallback
            row_id = None
            try:
                y = getattr(event, 'y', None)
                if y is not None:
                    row_id = treeview.identify_row(int(y))
                if not row_id:
                    # Fallback: compute y relative to widget from absolute pointer position
                    abs_y = treeview.winfo_pointery() - treeview.winfo_rooty()
                    row_id = treeview.identify_row(abs_y)
            except Exception as e:
                print(f"DEBUG DnD: Could not identify row: {e}")

            print(f"DEBUG DnD: Target row_id={row_id}")

            if hasattr(self, '_drop_callbacks') and id(treeview) in self._drop_callbacks:
                self._drop_callbacks[id(treeview)](path_objects, row_id if row_id else None)
        except Exception as e:
            print(f"Drag and drop treeview error: {e}")
            import traceback
            traceback.print_exc()

    def _on_files_dropped_wrapper(self, event, listbox: tk.Listbox) -> None:
        """Wrapper to handle dropped files and call the appropriate callback."""
        try:
            print(f"DEBUG DnD: Listbox drop event received, data={getattr(event, 'data', None)}")
            if not event or not getattr(event, 'data', None):
                return
            
            # Parse the dropped files
            file_paths = self._parse_dropped_file_list(event.data)
            if not file_paths:
                return
            
            # Convert to Path objects
            path_objects = []
            for file_path in file_paths:
                try:
                    path_obj = Path(file_path)
                    if path_obj.exists():
                        path_objects.append(path_obj)
                except (OSError, ValueError, TypeError):
                    # Path validation may fail due to invalid characters or system issues
                    continue
            
            # Call the specific callback for this listbox
            if hasattr(self, '_drop_callbacks') and id(listbox) in self._drop_callbacks:
                callback = self._drop_callbacks[id(listbox)]
                if path_objects:
                    callback(path_objects)
        except Exception as e:
            # Swallow DnD errors to keep UI responsive
            print(f"Drag and drop error: {e}")
    
    @staticmethod
    def _parse_dropped_file_list(data: str) -> List[str]:
        """Parse the OS-specific dropped files string into a list of file paths.
        
        Handles various formats:
        - Simple paths: /path/to/file.txt
        - Brace-enclosed paths (Windows/macOS with spaces): {C:/Users/A Name/file.pdf}
        - Mixed quotes and spaces
        
        This function is intentionally static so it can be unit-tested without a GUI.
        """
        if not data:
            return []
        
        # If it's a simple single path without braces or spaces between separate paths,
        # return it as-is
        if '{' not in data and not any(c.isspace() for c in data):
            return [data]
        
        # Commonly, tkdnd provides a Tcl-formatted list. Try to use robust parsing.
        # Handle different formats of file lists
        try:
            # First, try to handle brace-enclosed paths
            if '{' in data:
                import re
                # Find all brace-enclosed sections, including those with quotes inside
                pattern = r'\{([^}]*)\}'
                matches = re.findall(pattern, data)
                if matches:
                    # Remove any extra quotes that might be inside the braces
                    cleaned_matches = []
                    for match in matches:
                        # Strip quotes if the entire path is quoted
                        if match.startswith('"') and match.endswith('"'):
                            cleaned_matches.append(match[1:-1])
                        else:
                            cleaned_matches.append(match)
                    return cleaned_matches
                
            # Fallback: Handle quoted paths with shlex
            cleaned = data.replace('{', '"').replace('}', '"')
            parts = shlex.split(cleaned)
            return parts
        except Exception:
            # Final fallback: return the raw string as a single path
            return [data]