"""
BulkUploadFormView (Fase 7): pantalla intermedia de subida masiva.

Decisiones acordadas con el usuario:
    - Estructura: Frame scrollable con sub-frames por fila (Entries
      individuales). No Treeview editable.
    - Pre-poblado: Codigo y Nombre con Path(archivo).stem como default.
    - Pantalla de resumen: modal Toplevel separado con Treeview y
      colores verde/naranja/rojo segun resultado.

Flujo:
    1. El handler precarga existing_codigos (set) con un unico SELECT
       sobre planos. Lo pasa al view -> deteccion O(1) en cada KeyRelease
       del campo Codigo, sin queries adicionales.
    2. Por cada archivo se crea una _BulkRow con 5 Entries: Codigo,
       Nombre, Version, Autor, Comentarios/Motivo.
    3. Cuando el codigo introducido coincide con existing_codigos, la
       fila pasa a modo "nueva version" (label distinto + label del
       ultimo campo cambia a "Motivo de subida").
    4. Validacion en cliente antes del submit: si hay errores, marca
       las filas afectadas y NO inicia el proceso.

REFACTOR_PLAN.md secciones 9.2 y 9.3.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, List, Set, Optional

from .base_view import BaseView
from utils.version_validator import VersionValidator


# Colors per als status labels.
_COLOR_NUEVO = "#2E5984"        # azul: plano nuevo
_COLOR_VERSION = "#E67E22"      # naranja: nueva version de existente
_COLOR_ERROR = "#C0392B"        # rojo: validacion fallida
_COLOR_OK = "#27AE60"            # verde: resultat OK al resumen
_COLOR_NARANJA = "#E67E22"
_COLOR_ROJO = "#C0392B"


class _BulkRow:
    """Una fila editable per arxiu seleccionat."""

    def __init__(
        self,
        parent: tk.Widget,
        archivo_path: Path,
        existing_codigos: Set[str],
    ) -> None:
        self.archivo_path = archivo_path
        self.existing_codigos = existing_codigos

        self.frame = ttk.Frame(parent, relief="groove", padding=8)
        self.frame.pack(fill="x", pady=4)

        # Fila 0: nom de l'arxiu + status label.
        header = ttk.Frame(self.frame)
        header.pack(fill="x", pady=(0, 4))
        ttk.Label(
            header,
            text=archivo_path.name,
            font=("Arial", 10, "bold"),
        ).pack(side="left")
        self.status_label = ttk.Label(header, text="", foreground=_COLOR_NUEVO)
        self.status_label.pack(side="right")

        # Fila 1: Codigo + Nombre.
        row1 = ttk.Frame(self.frame)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Codigo:", width=12).pack(side="left")
        self.codigo_var = tk.StringVar(value=archivo_path.stem)
        self.codigo_entry = ttk.Entry(row1, textvariable=self.codigo_var, width=22)
        self.codigo_entry.pack(side="left", padx=(0, 12))
        self.codigo_var.trace_add("write", lambda *_: self._update_status())

        ttk.Label(row1, text="Nombre:", width=10).pack(side="left")
        self.nombre_var = tk.StringVar(value=archivo_path.stem)
        self.nombre_entry = ttk.Entry(row1, textvariable=self.nombre_var, width=28)
        self.nombre_entry.pack(side="left", fill="x", expand=True)

        # Fila 2: Version + Autor.
        row2 = ttk.Frame(self.frame)
        row2.pack(fill="x", pady=2)

        ttk.Label(row2, text="Version:", width=12).pack(side="left")
        self.version_var = tk.StringVar()
        self.version_entry = ttk.Entry(row2, textvariable=self.version_var, width=10)
        self.version_entry.pack(side="left", padx=(0, 12))

        ttk.Label(row2, text="Autor:", width=10).pack(side="left")
        self.autor_var = tk.StringVar()
        self.autor_entry = ttk.Entry(row2, textvariable=self.autor_var, width=10)
        self.autor_entry.pack(side="left")

        # Fila 3: Comentarios / Motivo de subida (label dinamic).
        row3 = ttk.Frame(self.frame)
        row3.pack(fill="x", pady=2)
        self.comentarios_label = ttk.Label(row3, text="Comentarios:", width=12)
        self.comentarios_label.pack(side="left")
        self.comentarios_var = tk.StringVar()
        self.comentarios_entry = ttk.Entry(row3, textvariable=self.comentarios_var)
        self.comentarios_entry.pack(side="left", fill="x", expand=True)

        # Fila 4: missatges d'error de validacio (oculta inicialment).
        self.error_label = ttk.Label(
            self.frame, text="", foreground=_COLOR_ERROR
        )
        self.error_label.pack(fill="x", pady=(2, 0))

        # Status inicial.
        self._update_status()

    def _update_status(self) -> None:
        """Recalcula 'plano nuevo' vs 'nueva version' segons existing_codigos."""
        codigo = self.codigo_var.get().strip()
        if not codigo:
            self.status_label.config(text="(falta codigo)", foreground=_COLOR_ERROR)
            self.comentarios_label.config(text="Comentarios:")
        elif codigo in self.existing_codigos:
            self.status_label.config(
                text=f"Nueva version (codigo existente)", foreground=_COLOR_VERSION
            )
            self.comentarios_label.config(text="Motivo:")
        else:
            self.status_label.config(
                text="Plano nuevo", foreground=_COLOR_NUEVO
            )
            self.comentarios_label.config(text="Comentarios:")

    def validate(self) -> Optional[str]:
        """
        Valida la fila i retorna un missatge d'error o None si tot OK.
        Marca visualment l'error.
        """
        codigo = self.codigo_var.get().strip()
        version = self.version_var.get().strip()
        autor = self.autor_var.get().strip()

        errors = []
        if not codigo:
            errors.append("codigo")
        if not version:
            errors.append("version")
        elif not VersionValidator.is_valid_version(version):
            errors.append("version (formato X.Y)")
        if not autor:
            errors.append("autor")
        if not self.archivo_path.exists():
            errors.append("archivo no encontrado")

        if errors:
            msg = "Falta/invalido: " + ", ".join(errors)
            self.error_label.config(text=msg)
            return msg
        self.error_label.config(text="")
        return None

    def to_item(self) -> dict:
        """Construeix el dict del item per a upload_service.subir_masivo."""
        codigo = self.codigo_var.get().strip()
        comentarios = self.comentarios_var.get().strip()
        es_existent = codigo in self.existing_codigos

        # En cas "nueva version" reinterpretem el text com a motivo_subida;
        # en cas "plano nuevo" com a comentarios.
        if es_existent:
            form_data = {
                "codigo": codigo,
                "version": self.version_var.get().strip(),
                "autor": self.autor_var.get().strip(),
                "motivo_subida": comentarios,
            }
        else:
            form_data = {
                "codigo": codigo,
                "nombre": self.nombre_var.get().strip() or codigo,
                "version": self.version_var.get().strip(),
                "autor": self.autor_var.get().strip(),
                "comentarios": comentarios,
            }
        return {"archivo_path": self.archivo_path, "form_data": form_data}


class BulkUploadFormView(BaseView):
    """Pantalla intermedia + modal de resumen per a la subida masiva."""

    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.rows: List[_BulkRow] = []
        self._on_submit: Optional[Callable] = None
        self._on_cancel: Optional[Callable] = None

    def show(
        self,
        file_paths: List[Path],
        existing_codigos: Set[str],
        on_submit: Callable[[list], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """
        Mostra la pantalla amb una fila per arxiu.

        Args:
            file_paths: llista de Paths absolutes als arxius seleccionats.
            existing_codigos: set de codis de planos del projecte.
            on_submit: callback(items: list) que processa el bulk.
            on_cancel: callback() que torna al dashboard.
        """
        self.clear_window()
        self.set_window_size(900, 700)

        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self.rows = []

        self.create_header(self.root, "Subida masiva")

        bottom_frame = ttk.Frame(self.root, padding="12")
        bottom_frame.pack(side="bottom", fill="x")

        info = ttk.Frame(self.root, padding="12 8 12 4")
        info.pack(fill="x")
        ttk.Label(
            info,
            text=f"{len(file_paths)} archivos seleccionados. "
                 "Revisa los datos y pulsa 'Procesar todos'.",
        ).pack(anchor="w")

        # Scrollable area amb les files.
        outer = ttk.Frame(self.root, padding="12")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        inner = ttk.Frame(canvas)
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(inner_window, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Suport scroll amb la roda del ratoli.
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self._mousewheel_bound = True

        for fp in file_paths:
            row = _BulkRow(inner, fp, existing_codigos)
            self.rows.append(row)

        ttk.Button(
            bottom_frame, text="Cancelar", command=self._on_cancel_clicked,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            bottom_frame, text="Procesar todos", command=self._on_submit_clicked,
        ).pack(side="right")

    def _on_submit_clicked(self) -> None:
        # Validacio client per fila.
        errors = [r for r in self.rows if r.validate() is not None]
        if errors:
            messagebox.showerror(
                "Errores de validacion",
                f"Hay {len(errors)} fila(s) con errores. "
                "Revisalas (marcadas en rojo) antes de continuar.",
            )
            return

        items = [r.to_item() for r in self.rows]
        if self._on_submit:
            self._on_submit(items)

    def _on_cancel_clicked(self) -> None:
        self._unbind_mousewheel()
        if self._on_cancel:
            self._on_cancel()

    def _unbind_mousewheel(self) -> None:
        """Allibera el binding global del mousewheel."""
        if getattr(self, "_mousewheel_bound", False):
            try:
                self.root.unbind_all("<MouseWheel>")
            except tk.TclError:
                pass
            self._mousewheel_bound = False

    def show_summary(
        self,
        results: List[dict],
        on_close: Callable[[], None],
    ) -> None:
        """
        Modal Toplevel amb el resum dels resultats. Colors verd/taronja/
        vermell segons resultat. Boton Cerrar dispara on_close.
        """
        self._unbind_mousewheel()

        win = tk.Toplevel(self.root)
        win.title("Resumen subida masiva")
        win.transient(self.root)
        win.grab_set()
        win.geometry("780x420")

        # Contadors per al header.
        n_ok = sum(1 for r in results if r["resultat"] == "ok")
        n_naranja = sum(1 for r in results if r["resultat"] == "naranja")
        n_error = sum(1 for r in results if r["resultat"] == "error")
        header = ttk.Frame(win, padding="12 12 12 4")
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"OK: {n_ok}    NARANJA: {n_naranja}    ERROR: {n_error}",
            font=("Arial", 11, "bold"),
        ).pack(anchor="w")

        # Treeview de resultats.
        body = ttk.Frame(win, padding="12 0 12 12")
        body.pack(fill="both", expand=True)

        cols = ("archivo", "codigo", "resultat", "detalls")
        tree = ttk.Treeview(body, columns=cols, show="headings", height=12)
        tree.heading("archivo", text="Archivo")
        tree.heading("codigo", text="Codigo")
        tree.heading("resultat", text="Resultado")
        tree.heading("detalls", text="Detalles")
        tree.column("archivo", width=200)
        tree.column("codigo", width=140)
        tree.column("resultat", width=90, anchor="center")
        tree.column("detalls", width=320)

        tree.tag_configure("ok", foreground=_COLOR_OK)
        tree.tag_configure("naranja", foreground=_COLOR_NARANJA)
        tree.tag_configure("error", foreground=_COLOR_ROJO)

        for r in results:
            tag = r["resultat"]
            tree.insert(
                "", "end",
                values=(
                    r.get("archivo", ""),
                    r.get("codigo", ""),
                    r.get("resultat", "").upper(),
                    r.get("detalls", ""),
                ),
                tags=(tag,),
            )

        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        footer = ttk.Frame(win, padding="12")
        footer.pack(fill="x")

        def _close():
            win.destroy()
            if on_close:
                on_close()

        ttk.Button(footer, text="Cerrar", command=_close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", _close)
