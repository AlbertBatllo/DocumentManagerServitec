#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Document Manager Application - Main Entry Point

Clean entry point for the Document Manager application.
Uses AppController for orchestration and document handlers for type-specific operations.
"""

import sys
from pathlib import Path

# Set UTF-8 encoding for Windows compatibility (only if stdout exists)
# In windowed GUI apps, stdout/stderr may be None
if sys.platform.startswith('win'):
    import codecs
    try:
        if sys.stdout is not None and hasattr(sys.stdout, 'detach'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
        if sys.stderr is not None and hasattr(sys.stderr, 'detach'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
    except (OSError, AttributeError):
        # In windowed mode, stdout/stderr may not be available - ignore
        pass

# Add src directory to path - handle both frozen (PyInstaller) and non-frozen cases
if getattr(sys, 'frozen', False):
    exe_dir = Path(sys.executable).parent
    internal_dir = exe_dir / '_internal'
    possible_src_paths = [
        internal_dir / 'src',
        getattr(sys, '_MEIPASS', None) and Path(sys._MEIPASS) / 'src',
        exe_dir / 'src',
    ]
    for src_path in possible_src_paths:
        if src_path and src_path.exists():
            sys.path.insert(0, str(src_path))
            break
else:
    sys.path.insert(0, str(Path(__file__).parent))


def main():
    """Main entry point for the Document Manager application."""
    # Import AppController from the refactored app module
    from app.app_controller import AppController

    # Create and run the application
    app = AppController()
    app.run()


if __name__ == "__main__":
    main()
