"""
Refresh Indicator Component for Document Management System

Provides visual feedback for smart refresh operations including:
- Status indication (checking, updating, success)
- Change counts and timestamps
- Manual refresh button integration
- Error state visualization
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Optional, Callable


class RefreshIndicator:
    """
    Visual indicator for refresh status and operations.
    
    Shows current refresh state with appropriate icons and colors:
    - Gray checkmark: Up to date
    - Gray magnifying glass: Checking for changes
    - Orange rotating arrow: Updating data
    - Green checkmark with count: Successfully updated with N changes
    - Red warning: Error occurred
    """
    
    def __init__(self, parent: tk.Widget, show_timestamp: bool = True, show_manual_button: bool = True):
        """
        Initialize refresh indicator.
        
        Args:
            parent: Parent widget to contain the indicator
            show_timestamp: Whether to show last update timestamp
            show_manual_button: Whether to show manual refresh button
        """
        self.parent = parent
        self.show_timestamp = show_timestamp
        self.show_manual_button = show_manual_button
        
        # Callback for manual refresh
        self.manual_refresh_callback: Optional[Callable[[], None]] = None
        
        # Create the indicator frame
        self.indicator_frame = ttk.Frame(parent)
        self.indicator_frame.pack(side="top", fill="x", padx=5, pady=2)
        
        # Status indicator label
        self.status_label = ttk.Label(
            self.indicator_frame, 
            text="✓", 
            font=("Arial", 10),
            foreground="gray"
        )
        self.status_label.pack(side="right", padx=(5, 0))
        
        # Timestamp label (if enabled)
        if self.show_timestamp:
            self.timestamp_label = ttk.Label(
                self.indicator_frame,
                text="",
                font=("Arial", 8),
                foreground="gray"
            )
            self.timestamp_label.pack(side="right", padx=(0, 5))
        
        # Manual refresh button (if enabled)
        if self.show_manual_button:
            self.refresh_button = ttk.Button(
                self.indicator_frame,
                text="🔄",
                width=3,
                command=self._on_manual_refresh
            )
            self.refresh_button.pack(side="right", padx=(0, 5))
            
            # Add tooltip-like behavior
            self._add_button_tooltip()
        
        # Initialize with default state
        self.show_up_to_date()
    
    def _add_button_tooltip(self):
        """Add hover tooltip for refresh button."""
        def on_enter(event):
            self.refresh_button.config(text="↻")
        
        def on_leave(event):
            self.refresh_button.config(text="🔄")
        
        self.refresh_button.bind("<Enter>", on_enter)
        self.refresh_button.bind("<Leave>", on_leave)
    
    def _on_manual_refresh(self):
        """Handle manual refresh button click."""
        if self.manual_refresh_callback:
            # Show updating state immediately
            self.show_updating("Manual")
            # Call the refresh callback
            try:
                self.manual_refresh_callback()
                # If we get here without exception, show success
                self.show_up_to_date()
            except Exception as e:
                print(f"RefreshIndicator: Manual refresh error: {e}")
                self.show_error("Error en actualización manual")
    
    def set_manual_refresh_callback(self, callback: Callable[[], None]) -> None:
        """
        Set the callback for manual refresh operations.
        
        Args:
            callback: Function to call when manual refresh is triggered
        """
        self.manual_refresh_callback = callback
    
    def show_checking(self) -> None:
        """Show 'checking for changes' state."""
        self.status_label.config(text="🔍", foreground="gray")
        if self.show_timestamp:
            self.timestamp_label.config(text="verificando...")
    
    def show_updating(self, source: str = "Auto") -> None:
        """
        Show 'updating data' state.
        
        Args:
            source: Source of the update ("Auto" or "Manual")
        """
        self.status_label.config(text="🔄", foreground="orange")
        if self.show_timestamp:
            self.timestamp_label.config(text=f"actualizando ({source.lower()})...")
    
    def show_success(self, changes_count: int = 0, timestamp: Optional[datetime] = None) -> None:
        """
        Show successful refresh state.
        
        Args:
            changes_count: Number of changes detected (0 = no changes)
            timestamp: When the refresh occurred (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        if changes_count > 0:
            # Changes detected
            self.status_label.config(text=f"✓ {changes_count}", foreground="green")
            if self.show_timestamp:
                time_str = timestamp.strftime("%H:%M:%S")
                change_text = "cambio" if changes_count == 1 else "cambios"
                self.timestamp_label.config(text=f"{changes_count} {change_text} - {time_str}")
            
            # Clear the change count after 3 seconds
            self.parent.after(3000, lambda: self._fade_to_normal(timestamp))
        else:
            # No changes
            self.show_up_to_date(timestamp)
    
    def show_up_to_date(self, timestamp: Optional[datetime] = None) -> None:
        """
        Show 'up to date' state.
        
        Args:
            timestamp: When last checked (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        self.status_label.config(text="✓", foreground="gray")
        if self.show_timestamp:
            time_str = timestamp.strftime("%H:%M:%S")
            self.timestamp_label.config(text=f"actualizado {time_str}")
    
    def show_error(self, error_message: str = "Error de conexión") -> None:
        """
        Show error state.
        
        Args:
            error_message: Error message to display
        """
        self.status_label.config(text="⚠️", foreground="red")
        if self.show_timestamp:
            self.timestamp_label.config(text=error_message)
        
        # Auto-clear error after 5 seconds
        self.parent.after(5000, self.show_up_to_date)
    
    def _fade_to_normal(self, last_update: datetime) -> None:
        """Fade from success state back to normal state."""
        self.show_up_to_date(last_update)
    
    def hide(self) -> None:
        """Hide the refresh indicator."""
        self.indicator_frame.pack_forget()
    
    def show(self) -> None:
        """Show the refresh indicator."""
        self.indicator_frame.pack(side="top", fill="x", padx=5, pady=2)
    
    def destroy(self) -> None:
        """Destroy the indicator and cleanup."""
        self.indicator_frame.destroy()


class CompactRefreshIndicator(RefreshIndicator):
    """
    Compact version of refresh indicator with minimal visual footprint.
    
    Shows only the status icon without timestamp or manual button.
    Useful for crowded UIs where space is at a premium.
    """
    
    def __init__(self, parent: tk.Widget):
        super().__init__(parent, show_timestamp=False, show_manual_button=False)
        
        # Make it even more compact
        self.indicator_frame.pack(side="top", fill="x", padx=2, pady=1)
        self.status_label.config(font=("Arial", 8))


class DetailedRefreshIndicator(RefreshIndicator):
    """
    Detailed version with additional status information.
    
    Shows file monitoring status, error counts, and additional debugging info.
    Useful for development or when troubleshooting refresh issues.
    """
    
    def __init__(self, parent: tk.Widget):
        super().__init__(parent, show_timestamp=True, show_manual_button=True)
        
        # Add detailed status label
        self.detail_label = ttk.Label(
            self.indicator_frame,
            text="",
            font=("Arial", 7),
            foreground="lightgray"
        )
        self.detail_label.pack(side="left")
    
    def show_file_status(self, file_path: str, is_monitoring: bool = True) -> None:
        """
        Show file monitoring status.
        
        Args:
            file_path: Path being monitored
            is_monitoring: Whether monitoring is active
        """
        filename = file_path.split('/')[-1] if '/' in file_path else file_path
        status = "monitoreando" if is_monitoring else "pausado"
        self.detail_label.config(text=f"{filename} - {status}")
    
    def show_error_count(self, error_count: int) -> None:
        """Show current error count."""
        if error_count > 0:
            self.detail_label.config(
                text=f"{error_count} errores de conexión",
                foreground="orange"
            )
        else:
            self.detail_label.config(text="conexión estable", foreground="lightgray")