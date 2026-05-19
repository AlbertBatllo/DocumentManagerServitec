"""
Navigation Manager

Centralizes application navigation state and context management.
Replaces scattered navigation logic from the monolithic centralized_main.py.
"""

from pathlib import Path
from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass, field


@dataclass
class NavigationState:
    """Represents the current navigation state of the application."""
    current_project_name: Optional[str] = None
    current_project_path: Optional[Path] = None
    current_doc_type: Optional[str] = None
    context: str = "project_selection"
    context_stack: List[str] = field(default_factory=list)


class NavigationManager:
    """
    Manages application navigation state and context.

    Centralizes navigation logic that was previously scattered across
    the CentralizedDocumentManagerApp class.
    """

    # Valid navigation contexts
    CONTEXTS = {
        'project_selection': 'Project Selection',
        'type_selection': 'Document Type Selection',
        'main_menu': 'Main Menu',
        'dashboard': 'Dashboard',
        'status_viewer': 'Status Viewer',
        'form': 'Form',
        'config': 'Configuration',
    }

    def __init__(self, view_callbacks: Dict[str, Callable] = None):
        """
        Initialize the navigation manager.

        Args:
            view_callbacks: Dictionary mapping context names to show methods
        """
        self._state = NavigationState()
        self._view_callbacks = view_callbacks or {}
        self._on_state_change_callbacks: List[Callable] = []

    # === State Properties ===

    @property
    def current_project_name(self) -> Optional[str]:
        return self._state.current_project_name

    @property
    def current_project_path(self) -> Optional[Path]:
        return self._state.current_project_path

    @property
    def current_doc_type(self) -> Optional[str]:
        return self._state.current_doc_type

    @property
    def context(self) -> str:
        return self._state.context

    @property
    def navigation_context(self) -> str:
        """Alias for context (backwards compatibility)."""
        return self._state.context

    @navigation_context.setter
    def navigation_context(self, value: str):
        """Set navigation context (backwards compatibility)."""
        self.set_context(value)

    # === State Modification ===

    def set_project(self, name: str, path: str):
        """Set the current project."""
        self._state.current_project_name = name
        self._state.current_project_path = Path(path) if path else None
        self._notify_state_change()

    def set_doc_type(self, doc_type: str):
        """Set the current document type."""
        self._state.current_doc_type = doc_type
        self._notify_state_change()

    def set_context(self, context: str, push_to_stack: bool = True):
        """
        Set the current navigation context.

        Args:
            context: The new context to set
            push_to_stack: Whether to push the previous context to the stack
        """
        if push_to_stack and self._state.context:
            self._state.context_stack.append(self._state.context)
        self._state.context = context
        self._notify_state_change()

    def push_context(self, context: str):
        """Push a new context onto the stack and set it as current."""
        self.set_context(context, push_to_stack=True)

    def pop_context(self) -> Optional[str]:
        """Pop the previous context from the stack."""
        if self._state.context_stack:
            return self._state.context_stack.pop()
        return None

    def clear_project(self):
        """Clear the current project selection."""
        self._state.current_project_name = None
        self._state.current_project_path = None
        self._state.current_doc_type = None
        self._state.context = "project_selection"
        self._state.context_stack.clear()
        self._notify_state_change()

    def clear_doc_type(self):
        """Clear the current document type selection."""
        self._state.current_doc_type = None
        self._state.context = "type_selection"
        self._notify_state_change()

    # === Navigation Methods ===

    def get_back_destination(self) -> str:
        """
        Determine where to navigate on back action.

        Returns:
            The context to navigate to
        """
        if self._state.context_stack:
            return self._state.context_stack[-1]

        # Default back navigation based on current context
        back_map = {
            'config': 'main_menu',
            'form': 'dashboard',
            'dashboard': 'main_menu',
            'status_viewer': 'main_menu',
            'main_menu': 'type_selection',
            'type_selection': 'project_selection',
        }
        return back_map.get(self._state.context, 'main_menu')

    def go_back(self, optimize: bool = False) -> str:
        """
        Navigate back to the previous context.

        Args:
            optimize: Whether to optimize the back navigation (e.g., preserve scroll position)

        Returns:
            The context navigated to
        """
        destination = self.pop_context() or self.get_back_destination()
        self._state.context = destination
        self._notify_state_change()

        # Execute view callback if available
        if destination in self._view_callbacks:
            callback = self._view_callbacks[destination]
            if optimize and hasattr(callback, 'optimized'):
                callback.optimized()
            else:
                callback()

        return destination

    def navigate_to(self, context: str, push_current: bool = True):
        """
        Navigate to a specific context.

        Args:
            context: The context to navigate to
            push_current: Whether to push the current context to the stack
        """
        self.set_context(context, push_to_stack=push_current)

        if context in self._view_callbacks:
            self._view_callbacks[context]()

    # === Callbacks ===

    def register_view_callback(self, context: str, callback: Callable):
        """Register a callback for a navigation context."""
        self._view_callbacks[context] = callback

    def register_state_change_callback(self, callback: Callable):
        """Register a callback to be notified of state changes."""
        self._on_state_change_callbacks.append(callback)

    def _notify_state_change(self):
        """Notify all registered callbacks of a state change."""
        for callback in self._on_state_change_callbacks:
            try:
                callback(self._state)
            except Exception as e:
                print(f"Warning: State change callback error: {e}")

    # === State Inspection ===

    def has_project(self) -> bool:
        """Check if a project is currently selected."""
        return self._state.current_project_path is not None

    def has_doc_type(self) -> bool:
        """Check if a document type is currently selected."""
        return self._state.current_doc_type is not None

    def is_at_root(self) -> bool:
        """Check if at the root (project selection) context."""
        return self._state.context == "project_selection"

    def get_window_title(self) -> str:
        """Generate a window title based on current state."""
        base_title = "Gestor de Documentos"
        if self._state.current_project_name:
            return f"{base_title} - {self._state.current_project_name}"
        return base_title

    def get_state_dict(self) -> Dict[str, Any]:
        """Get the current navigation state as a dictionary."""
        return {
            'project_name': self._state.current_project_name,
            'project_path': str(self._state.current_project_path) if self._state.current_project_path else None,
            'doc_type': self._state.current_doc_type,
            'context': self._state.context,
            'context_stack': list(self._state.context_stack),
        }
