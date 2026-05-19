import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable
from .base_view import BaseView


class TypeSelectionView(BaseView):
    def __init__(self, root: tk.Tk):
        super().__init__(root)

    def show(self, on_select_callback: Callable[[str, str], None]) -> None:
        """Show the document type selection menu."""
        self.clear_window()
        self.center_window(750, 650)
        
        # Header
        self.create_header(self.root, "Selección de Tipo de Documento")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="40")
        main_frame.pack(fill="both", expand=True)
        
        # Instructions
        ttk.Label(
            main_frame,
            text="Seleccione el tipo de documento a gestionar:",
            font=("Arial", 12)
        ).grid(row=0, column=0, columnspan=2, pady=20)
        
        # Document type buttons
        btn_planos = ttk.Button(
            main_frame,
            text="Planos",
            command=lambda: on_select_callback("planos", "05_Planos"),
            width=20
        )
        btn_planos.grid(row=1, column=0, padx=10, pady=10)
        
        btn_cert = ttk.Button(
            main_frame,
            text="Certificaciones",
            command=lambda: on_select_callback("certificaciones", "04_Certificaciones"),
            width=20
        )
        btn_cert.grid(row=1, column=1, padx=10, pady=10)
        
        # Descriptions
        ttk.Label(
            main_frame,
            text="Gestionar planos técnicos\ny dibujos de ingeniería",
            font=("Arial", 9),
            justify="center"
        ).grid(row=2, column=0, padx=10, pady=5)
        
        ttk.Label(
            main_frame,
            text="Gestionar certificados\ny documentos de calidad",
            font=("Arial", 9),
            justify="center"
        ).grid(row=2, column=1, padx=10, pady=5)
        
        
        # Configure grid
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
