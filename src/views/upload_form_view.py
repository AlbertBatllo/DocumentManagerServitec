"""
UploadFormView (Fase 6): formulario de subida de nueva version de un
plano existente.

Reemplaza el uso del NewVersionForm legacy para el flujo nuevo (Fase 6).
Decision (acordada con el usuario): este boton del dashboard solo
cubre el CASO 2 (plano existente). Para crear planos nuevos, primero
se hacen via "Editar proyecto" (Fase 3) y luego se sube su primera
version aqui.

El formulario es reducido (REFACTOR_PLAN seccion 9.1):
    - Codigo del plano (read-only, mostrado como titulo).
    - Info: version actual + estado actual.
    - Version nueva (entry, formato `X.Y`).
    - Autor (entry, iniciales).
    - Motivo de subida (entry).
    - Selector de archivo (filedialog).
    - Botones Subir / Cancelar.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Callable, Optional

from .base_view import BaseView
from utils.version_validator import VersionValidator


class UploadFormView(BaseView):
    """Formulario de subida de nueva version (CASO 2 de Fase 6)."""

    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.archivo_seleccionado: Optional[Path] = None
        self._archivo_label_var: Optional[tk.StringVar] = None
        self._on_submit: Optional[Callable] = None
        self._on_cancel: Optional[Callable] = None
        self._plano_info: dict = {}

    def show_new_version(
        self,
        plano_info: dict,
        on_submit: Callable[[dict, Path], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """
        Muestra el formulario de nueva version.

        Args:
            plano_info: dict con `id`, `codigo`, `nombre`, `version`
                (actual), `estado` (actual) del plano seleccionado.
            on_submit: callback(form_data: dict, archivo_path: Path).
                form_data contiene `version`, `autor`, `motivo_subida`.
            on_cancel: callback() para volver al dashboard sin guardar.
        """
        self.clear_window()
        self.set_window_size(620, 460)

        self._plano_info = plano_info
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self.archivo_seleccionado = None

        self.create_header(self.root, "Nueva version")

        # Bottom buttons fixed first so the form scrollable area never
        # los oculta.
        bottom_frame = ttk.Frame(self.root, padding="15")
        bottom_frame.pack(side="bottom", fill="x")

        main = ttk.Frame(self.root, padding="20")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Titulo con el codigo del plano (read-only).
        ttk.Label(
            main,
            text=f"Plano: {plano_info.get('codigo', '?')}",
            font=("Arial", 13, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # Info: version y estado actuales para que el usuario sepa
        # contra que esta comparando.
        version_actual = plano_info.get("version") or "(sin version)"
        estado_actual = plano_info.get("estado") or "GRIS"
        info_text = (
            f"Version actual: {version_actual}    "
            f"Estado actual: {estado_actual}"
        )
        ttk.Label(main, text=info_text, foreground="#2E5984").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        # Version nueva.
        ttk.Label(main, text="Nueva version:").grid(
            row=2, column=0, sticky="w", pady=4
        )
        self.version_entry = ttk.Entry(main, width=14)
        self.version_entry.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(
            main,
            text="Formato: numero.numero (ej: 1.0, 2.1)",
            foreground="gray",
        ).grid(row=3, column=1, sticky="w", pady=(0, 8))

        # Autor.
        ttk.Label(main, text="Autor (iniciales):").grid(
            row=4, column=0, sticky="w", pady=4
        )
        self.autor_entry = ttk.Entry(main, width=14)
        self.autor_entry.grid(row=4, column=1, sticky="w", pady=4)

        # Motivo de subida.
        ttk.Label(main, text="Motivo de subida:").grid(
            row=5, column=0, sticky="w", pady=4
        )
        self.motivo_entry = ttk.Entry(main, width=46)
        self.motivo_entry.grid(row=5, column=1, sticky="w", pady=4)
        ttk.Label(
            main,
            text="Opcional. Recomendado si la nueva version es superior.",
            foreground="gray",
        ).grid(row=6, column=1, sticky="w", pady=(0, 8))

        # Selector de archivo.
        ttk.Label(main, text="Archivo:").grid(
            row=7, column=0, sticky="w", pady=4
        )
        archivo_frame = ttk.Frame(main)
        archivo_frame.grid(row=7, column=1, sticky="ew", pady=4)
        self._archivo_label_var = tk.StringVar(value="(ningun archivo seleccionado)")
        ttk.Label(
            archivo_frame,
            textvariable=self._archivo_label_var,
            foreground="gray",
            width=42,
            anchor="w",
        ).pack(side="left")
        ttk.Button(
            archivo_frame,
            text="Seleccionar...",
            command=self._on_pick_file,
        ).pack(side="left", padx=(6, 0))

        # Botones inferiores.
        ttk.Button(
            bottom_frame,
            text="Cancelar",
            command=self._on_cancel_clicked,
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            bottom_frame,
            text="Subir",
            command=self._on_submit_clicked,
        ).pack(side="right")

    # ----- Callbacks de los widgets ---------------------------------

    def _on_pick_file(self) -> None:
        path_str = filedialog.askopenfilename(
            title="Seleccionar archivo del plano",
            filetypes=[
                ("Archivos comunes", "*.pdf *.dwg *.dxf *.rvt"),
                ("PDF", "*.pdf"),
                ("DWG/DXF", "*.dwg *.dxf"),
                ("Revit", "*.rvt"),
                ("Todos", "*.*"),
            ],
        )
        if not path_str:
            return
        self.archivo_seleccionado = Path(path_str)
        # Mostrar solo el nombre del archivo (no la ruta entera).
        self._archivo_label_var.set(self.archivo_seleccionado.name)

    def _on_submit_clicked(self) -> None:
        version = self.version_entry.get().strip()
        autor = self.autor_entry.get().strip()
        motivo = self.motivo_entry.get().strip()

        if not version:
            messagebox.showerror("Faltan datos", "La version es obligatoria.")
            return
        if not VersionValidator.is_valid_version(version):
            messagebox.showerror(
                "Version invalida",
                "La version debe tener formato numero.numero (ej: 1.0, 2.1).",
            )
            return
        if not autor:
            messagebox.showerror("Faltan datos", "El autor (iniciales) es obligatorio.")
            return
        if self.archivo_seleccionado is None:
            messagebox.showerror("Faltan datos", "Selecciona un archivo a subir.")
            return
        if not self.archivo_seleccionado.exists():
            messagebox.showerror(
                "Archivo no encontrado",
                f"No existe el archivo:\n{self.archivo_seleccionado}",
            )
            return

        form_data = {
            "version": version,
            "autor": autor,
            "motivo_subida": motivo,
        }
        if self._on_submit:
            self._on_submit(form_data, self.archivo_seleccionado)

    def _on_cancel_clicked(self) -> None:
        if self._on_cancel:
            self._on_cancel()
