"""
Formulario de creacion / edicion de proyecto (Fase 2 + futura Fase 3).

Implementa la pantalla descrita en REFACTOR_PLAN.md seccion 8.1:
    - Tipo (radio: Obra nueva / Reforma)
    - Nombre, Codigo, Lugar, Descripcion
    - Listado de planos:
        * Seccion obligatorios: 5 filas precargadas Obligatori_1..5
        * Seccion detalles: vacia, con boton 'Anadir detalle'
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, List, Optional

from .base_view import BaseView


OBLIGATORIOS_INICIALES = [f"Obligatori_{i}" for i in range(1, 6)]
PREFIX = "PRJ-"


class ProjectFormView(BaseView):
    """Formulario reutilizable para crear (Fase 2) y editar (Fase 3) proyectos."""

    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self._tipo_var: Optional[tk.StringVar] = None
        self._nombre_var: Optional[tk.StringVar] = None
        self._codigo_var: Optional[tk.StringVar] = None
        self._lugar_var: Optional[tk.StringVar] = None
        self._descripcion_text: Optional[tk.Text] = None
        self._obligatorios_entries: List[tk.StringVar] = []
        self._detalles_rows: List[Dict] = []
        self._detalles_frame: Optional[ttk.Frame] = None

    def show_create(
        self,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Muestra el formulario en modo creacion."""
        self.clear_window()
        self.center_window(750, 700)
        self.create_header(self.root, "Crear proyecto nuevo")

        # Marco principal con scroll vertical
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=20, pady=10)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- Tipo ---
        ttk.Label(content, text="Tipo:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self._tipo_var = tk.StringVar(value="OBRA_NUEVA")
        tipo_frame = ttk.Frame(content)
        tipo_frame.grid(row=0, column=1, sticky="w", pady=(0, 6))
        ttk.Radiobutton(
            tipo_frame, text="Obra nueva", variable=self._tipo_var,
            value="OBRA_NUEVA",
        ).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            tipo_frame, text="Reforma", variable=self._tipo_var,
            value="REFORMA",
        ).pack(side="left")

        # --- Nombre ---
        ttk.Label(content, text="Nombre:").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self._nombre_var = tk.StringVar()
        ttk.Entry(content, textvariable=self._nombre_var, width=50).grid(
            row=1, column=1, sticky="w", pady=4
        )

        # --- Codigo ---
        ttk.Label(content, text="Codigo:").grid(
            row=2, column=0, sticky="w", pady=4
        )
        codigo_frame = ttk.Frame(content)
        codigo_frame.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(
            codigo_frame, text=PREFIX, font=("Arial", 10, "bold"),
            foreground="gray",
        ).pack(side="left")
        self._codigo_var = tk.StringVar()
        ttk.Entry(codigo_frame, textvariable=self._codigo_var, width=44).pack(
            side="left"
        )

        # --- Lugar ---
        ttk.Label(content, text="Lugar:").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self._lugar_var = tk.StringVar()
        ttk.Entry(content, textvariable=self._lugar_var, width=50).grid(
            row=3, column=1, sticky="w", pady=4
        )

        # --- Descripcion ---
        ttk.Label(content, text="Descripcion:").grid(
            row=4, column=0, sticky="nw", pady=(8, 4)
        )
        self._descripcion_text = tk.Text(content, width=50, height=4, wrap="word")
        self._descripcion_text.grid(row=4, column=1, sticky="w", pady=(8, 4))

        # --- Planos obligatorios ---
        ttk.Separator(content, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(14, 8)
        )
        ttk.Label(
            content, text="Planos obligatorios", font=("Arial", 11, "bold")
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 6))

        oblig_frame = ttk.Frame(content)
        oblig_frame.grid(row=7, column=0, columnspan=2, sticky="ew")
        self._obligatorios_entries = []
        for i, placeholder in enumerate(OBLIGATORIOS_INICIALES, start=1):
            ttk.Label(oblig_frame, text=f"{i}.").grid(
                row=i, column=0, sticky="w", padx=(0, 6), pady=2
            )
            var = tk.StringVar(value=placeholder)
            ttk.Entry(oblig_frame, textvariable=var, width=55).grid(
                row=i, column=1, sticky="w", pady=2
            )
            self._obligatorios_entries.append(var)

        # --- Detalles ---
        ttk.Separator(content, orient="horizontal").grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(14, 8)
        )
        ttk.Label(
            content, text="Detalles", font=("Arial", 11, "bold")
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._detalles_frame = ttk.Frame(content)
        self._detalles_frame.grid(row=10, column=0, columnspan=2, sticky="ew")
        self._detalles_rows = []

        add_btn = self.create_visible_button(
            content, text="+ Anadir detalle", command=self._add_detalle_row
        )
        add_btn.grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # --- Botones ---
        btn_frame = ttk.Frame(self.root, padding=(20, 10))
        btn_frame.pack(side="bottom", fill="x")

        self.create_visible_button(
            btn_frame, text="Cancelar", command=on_cancel
        ).pack(side="right", padx=4)
        self.create_visible_button(
            btn_frame, text="Crear proyecto",
            command=lambda: self._submit(on_submit),
        ).pack(side="right", padx=4)

    # ------------------------------------------------------------------
    # Detalles dinamicos
    # ------------------------------------------------------------------

    def _add_detalle_row(self) -> None:
        """Anade una fila editable a la seccion de detalles."""
        row_idx = len(self._detalles_rows)
        row_frame = ttk.Frame(self._detalles_frame)
        row_frame.grid(row=row_idx, column=0, sticky="ew", pady=2)

        ttk.Label(row_frame, text=f"{row_idx + 1}.").pack(
            side="left", padx=(0, 6)
        )
        var = tk.StringVar()
        ttk.Entry(row_frame, textvariable=var, width=55).pack(side="left")
        del_btn = self.create_visible_button(
            row_frame, text="X", command=lambda: self._remove_detalle_row(row_frame)
        )
        del_btn.pack(side="left", padx=(6, 0))

        self._detalles_rows.append({"frame": row_frame, "var": var})

    def _remove_detalle_row(self, row_frame: ttk.Frame) -> None:
        """Elimina una fila de detalles."""
        for entry in self._detalles_rows:
            if entry["frame"] is row_frame:
                entry["frame"].destroy()
                self._detalles_rows.remove(entry)
                break
        self._renumber_detalles()

    def _renumber_detalles(self) -> None:
        """Actualiza los numeros visibles tras un borrado."""
        for i, entry in enumerate(self._detalles_rows, start=1):
            children = entry["frame"].winfo_children()
            if children and isinstance(children[0], ttk.Label):
                children[0].configure(text=f"{i}.")

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _submit(self, on_submit: Callable[[dict], None]) -> None:
        """Recoge los datos, valida en cliente y dispara on_submit."""
        tipo = self._tipo_var.get()
        nombre = self._nombre_var.get().strip()
        codigo_sufijo = self._codigo_var.get().strip()
        lugar = self._lugar_var.get().strip()
        descripcion = self._descripcion_text.get("1.0", "end").strip()

        if tipo not in ("OBRA_NUEVA", "REFORMA"):
            messagebox.showerror("Datos incompletos", "Selecciona un tipo.")
            return
        if not nombre:
            messagebox.showerror("Datos incompletos", "El nombre es obligatorio.")
            return
        if not codigo_sufijo:
            messagebox.showerror("Datos incompletos", "El codigo es obligatorio.")
            return

        obligatorios = [v.get().strip() for v in self._obligatorios_entries]
        # Decision del usuario: mantener placeholder como nombre real.
        # Por tanto NO filtramos los Obligatori_X que el usuario no edito.
        # Solo descartamos cadenas totalmente vacias (si el usuario las
        # borro a proposito).
        obligatorios = [n for n in obligatorios if n]

        detalles = [r["var"].get().strip() for r in self._detalles_rows]
        detalles = [n for n in detalles if n]

        on_submit({
            "tipo": tipo,
            "nombre": nombre,
            "codigo": codigo_sufijo,
            "lugar": lugar,
            "descripcion": descripcion,
            "obligatorios": obligatorios,
            "detalles": detalles,
        })
