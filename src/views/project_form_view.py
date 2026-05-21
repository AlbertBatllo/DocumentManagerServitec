"""
Formulario de creacion / edicion de proyecto (Fase 2 + Fase 3).

Implementa la pantalla descrita en REFACTOR_PLAN.md seccion 8.1:
    - Tipo (radio: Obra nueva / Reforma)
    - Nombre, Codigo, Lugar, Descripcion
    - Listado de planos:
        * Seccion obligatorios: 5 filas precargadas Obligatori_1..5
          (create) o los obligatorios reales del proyecto (edit).
        * Seccion detalles: vacia con boton 'Anadir detalle' (create) o
          pre-rellenada con los detalles existentes mas el boton para
          anadir mas (edit).

API publica:
    - show_create(on_submit, on_cancel)
    - show_edit(project_data, on_submit, on_cancel, on_delete_check)

En modo edicion:
    - El campo Codigo es read-only (decision Fase 3: no se permite
      renombrar la carpeta del proyecto desde la UI).
    - Cada fila de plano tiene boton X para marcarla y, segun el callback
      on_delete_check(plano_id), se decide que dialogo mostrar
      (gestionado en `plano_delete_dialog.py`, fuera de esta vista).
    - Las acciones de borrar y revertir son DIFERIDAS: se acumulan en el
      estado del formulario y se aplican al pulsar 'Guardar'. Cancelar
      no aplica nada.
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
        # --- Estado compartido por show_create / show_edit ---
        self._tipo_var: Optional[tk.StringVar] = None
        self._nombre_var: Optional[tk.StringVar] = None
        self._codigo_var: Optional[tk.StringVar] = None
        self._lugar_var: Optional[tk.StringVar] = None
        self._descripcion_text: Optional[tk.Text] = None
        # En create: lista de StringVar con los 5 obligatorios.
        # En edit: lista de dicts {id, nombre_var, frame} para mostrar y
        # actualizar los planos obligatorios existentes.
        self._obligatorios_entries: List = []
        # En create: lista de dicts {frame, var}.
        # En edit: lista de dicts {frame, var, id} (id=None para los
        # detalles nuevos anadidos en esta sesion).
        self._detalles_rows: List[Dict] = []
        self._detalles_frame: Optional[ttk.Frame] = None
        # --- Estado especifico de edit ---
        self._mode: str = "create"
        self._planos_marcados_borrar: set = set()
        self._planos_marcados_revertir: set = set()
        self._planos_borrar_silencioso: set = set()

    # ==================================================================
    # API publica
    # ==================================================================

    def show_create(
        self,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Muestra el formulario en modo creacion."""
        self._mode = "create"
        self._planos_marcados_borrar = set()
        self._planos_marcados_revertir = set()
        self._planos_borrar_silencioso = set()

        self.clear_window()
        self.center_window(750, 700)
        self.create_header(self.root, "Crear proyecto nuevo")

        content = self._build_scrollable_content()
        self._build_common_fields(
            content,
            initial_tipo="OBRA_NUEVA",
            initial_nombre="",
            initial_codigo="",
            initial_lugar="",
            initial_descripcion="",
            codigo_readonly=False,
        )
        self._build_obligatorios_section_create(content)
        self._build_detalles_section(content, initial_detalles=[])
        self._build_bottom_buttons(
            submit_text="Crear proyecto",
            on_submit=lambda: self._submit_create(on_submit),
            on_cancel=on_cancel,
        )

    def show_edit(
        self,
        project_data: dict,
        on_submit: Callable[[dict], None],
        on_cancel: Callable[[], None],
        on_delete_check: Callable[[int, str, int], str],
    ) -> None:
        """
        Muestra el formulario en modo edicion.

        Args:
            project_data: dict tal y como lo devuelve
                project_edit_service.load_project_for_edit().
            on_submit: callback que recibe el dict con planos_existentes,
                planos_nuevos_detalle, planos_a_borrar, planos_a_revertir.
            on_cancel: callback sin parametros (no se aplica nada).
            on_delete_check: callback (plano_id, plano_nombre, n_archivos)
                que abre el dialogo apropiado y devuelve
                'delete' | 'revert' | 'cancel'. Internamente puede
                consultar la BD; esta vista no lo hace.
        """
        self._mode = "edit"
        self._planos_marcados_borrar = set()
        self._planos_marcados_revertir = set()
        self._planos_borrar_silencioso = set()

        self.clear_window()
        self.center_window(780, 720)
        codigo = project_data.get("codigo", "")
        self.create_header(self.root, f"Editar proyecto: {codigo}")

        content = self._build_scrollable_content()
        self._build_common_fields(
            content,
            initial_tipo=project_data.get("tipo") or "OBRA_NUEVA",
            initial_nombre=project_data.get("nombre", ""),
            initial_codigo=_strip_prefix(codigo),
            initial_lugar=project_data.get("lugar", ""),
            initial_descripcion=project_data.get("descripcion", ""),
            codigo_readonly=True,
        )

        planos = project_data.get("planos", [])
        obligatorios = [p for p in planos if p.get("obligatorio")]
        detalles = [p for p in planos if not p.get("obligatorio")]

        self._build_obligatorios_section_edit(content, obligatorios)
        self._build_detalles_section_edit(content, detalles)
        self._build_bottom_buttons(
            submit_text="Guardar cambios",
            on_submit=lambda: self._submit_edit(on_submit),
            on_cancel=on_cancel,
        )

        # Guardamos los callbacks que se usan al pulsar X en una fila.
        self._on_delete_check = on_delete_check

    # ==================================================================
    # Construccion de la UI (helpers compartidos)
    # ==================================================================

    def _build_scrollable_content(self) -> ttk.Frame:
        """Crea el frame scrollable principal y devuelve el contenedor."""
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
        return content

    def _build_common_fields(
        self,
        content: ttk.Frame,
        initial_tipo: str,
        initial_nombre: str,
        initial_codigo: str,
        initial_lugar: str,
        initial_descripcion: str,
        codigo_readonly: bool,
    ) -> None:
        """Construye tipo / nombre / codigo / lugar / descripcion."""
        # --- Tipo ---
        ttk.Label(content, text="Tipo:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self._tipo_var = tk.StringVar(value=initial_tipo)
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
        self._nombre_var = tk.StringVar(value=initial_nombre)
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
        self._codigo_var = tk.StringVar(value=initial_codigo)
        codigo_entry = ttk.Entry(
            codigo_frame, textvariable=self._codigo_var, width=44
        )
        codigo_entry.pack(side="left")
        if codigo_readonly:
            codigo_entry.configure(state="readonly")
            # Mensaje aclaratorio solo en edit.
            ttk.Label(
                codigo_frame,
                text="  (no editable)",
                foreground="gray",
                font=("Arial", 9, "italic"),
            ).pack(side="left")

        # --- Lugar ---
        ttk.Label(content, text="Lugar:").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self._lugar_var = tk.StringVar(value=initial_lugar)
        ttk.Entry(content, textvariable=self._lugar_var, width=50).grid(
            row=3, column=1, sticky="w", pady=4
        )

        # --- Descripcion ---
        ttk.Label(content, text="Descripcion:").grid(
            row=4, column=0, sticky="nw", pady=(8, 4)
        )
        self._descripcion_text = tk.Text(content, width=50, height=4, wrap="word")
        self._descripcion_text.grid(row=4, column=1, sticky="w", pady=(8, 4))
        if initial_descripcion:
            self._descripcion_text.insert("1.0", initial_descripcion)

        # Separador antes de la seccion de planos.
        ttk.Separator(content, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(14, 8)
        )

    def _build_obligatorios_section_create(self, content: ttk.Frame) -> None:
        """Seccion 'Obligatorios' en modo create: 5 placeholders."""
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

    def _build_obligatorios_section_edit(
        self,
        content: ttk.Frame,
        obligatorios: List[dict],
    ) -> None:
        """Seccion 'Obligatorios' en modo edit: filas pre-rellenadas."""
        ttk.Label(
            content, text="Planos obligatorios", font=("Arial", 11, "bold")
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 6))

        oblig_frame = ttk.Frame(content)
        oblig_frame.grid(row=7, column=0, columnspan=2, sticky="ew")
        self._obligatorios_entries = []

        if not obligatorios:
            ttk.Label(
                oblig_frame,
                text="(este proyecto no tiene planos obligatorios)",
                foreground="gray",
            ).pack(anchor="w", pady=4)
            return

        for i, plano in enumerate(obligatorios, start=1):
            row_frame = ttk.Frame(oblig_frame)
            row_frame.grid(row=i, column=0, sticky="ew", pady=2)
            ttk.Label(row_frame, text=f"{i}.").pack(side="left", padx=(0, 6))
            var = tk.StringVar(value=plano.get("nombre", ""))
            entry = ttk.Entry(row_frame, textvariable=var, width=50)
            entry.pack(side="left")
            del_btn = self.create_visible_button(
                row_frame,
                text="X",
                command=lambda p=plano, f=row_frame, e=entry: self._on_delete_existing(
                    p, f, e
                ),
            )
            del_btn.pack(side="left", padx=(6, 0))
            self._obligatorios_entries.append(
                {"id": plano.get("id"), "nombre_var": var,
                 "codigo": plano.get("codigo"), "frame": row_frame,
                 "entry": entry}
            )

    def _build_detalles_section(
        self,
        content: ttk.Frame,
        initial_detalles: List[str],
    ) -> None:
        """Seccion 'Detalles' en modo create: vacia + boton anadir."""
        ttk.Separator(content, orient="horizontal").grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(14, 8)
        )
        ttk.Label(
            content, text="Detalles", font=("Arial", 11, "bold")
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._detalles_frame = ttk.Frame(content)
        self._detalles_frame.grid(row=10, column=0, columnspan=2, sticky="ew")
        self._detalles_rows = []

        for nombre in initial_detalles:
            self._add_detalle_row(initial_value=nombre)

        add_btn = self.create_visible_button(
            content, text="+ Anadir detalle", command=self._add_detalle_row
        )
        add_btn.grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_detalles_section_edit(
        self,
        content: ttk.Frame,
        detalles: List[dict],
    ) -> None:
        """Seccion 'Detalles' en modo edit: filas existentes + boton anadir."""
        ttk.Separator(content, orient="horizontal").grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(14, 8)
        )
        ttk.Label(
            content, text="Detalles", font=("Arial", 11, "bold")
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._detalles_frame = ttk.Frame(content)
        self._detalles_frame.grid(row=10, column=0, columnspan=2, sticky="ew")
        self._detalles_rows = []

        # Filas para los detalles existentes (con id).
        for plano in detalles:
            self._add_detalle_row_existing(plano)

        add_btn = self.create_visible_button(
            content, text="+ Anadir detalle", command=self._add_detalle_row
        )
        add_btn.grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_bottom_buttons(
        self,
        submit_text: str,
        on_submit: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Botonera inferior con Cancelar / Submit."""
        btn_frame = ttk.Frame(self.root, padding=(20, 10))
        btn_frame.pack(side="bottom", fill="x")
        self.create_visible_button(
            btn_frame, text="Cancelar", command=on_cancel
        ).pack(side="right", padx=4)
        self.create_visible_button(
            btn_frame, text=submit_text, command=on_submit
        ).pack(side="right", padx=4)

    # ==================================================================
    # Filas dinamicas de detalles
    # ==================================================================

    def _add_detalle_row(self, initial_value: str = "") -> None:
        """Anade una fila editable a la seccion de detalles (nueva)."""
        row_idx = len(self._detalles_rows)
        row_frame = ttk.Frame(self._detalles_frame)
        row_frame.grid(row=row_idx, column=0, sticky="ew", pady=2)

        ttk.Label(row_frame, text=f"{row_idx + 1}.").pack(
            side="left", padx=(0, 6)
        )
        var = tk.StringVar(value=initial_value)
        entry = ttk.Entry(row_frame, textvariable=var, width=50)
        entry.pack(side="left")
        del_btn = self.create_visible_button(
            row_frame, text="X",
            command=lambda: self._remove_detalle_row(row_frame),
        )
        del_btn.pack(side="left", padx=(6, 0))

        self._detalles_rows.append(
            {"frame": row_frame, "var": var, "entry": entry, "id": None}
        )

    def _add_detalle_row_existing(self, plano: dict) -> None:
        """Anade una fila para un detalle ya existente (con id)."""
        row_idx = len(self._detalles_rows)
        row_frame = ttk.Frame(self._detalles_frame)
        row_frame.grid(row=row_idx, column=0, sticky="ew", pady=2)

        ttk.Label(row_frame, text=f"{row_idx + 1}.").pack(
            side="left", padx=(0, 6)
        )
        var = tk.StringVar(value=plano.get("nombre", ""))
        entry = ttk.Entry(row_frame, textvariable=var, width=50)
        entry.pack(side="left")

        entry_ref = entry
        plano_dict = plano
        frame_ref = row_frame

        del_btn = self.create_visible_button(
            row_frame, text="X",
            command=lambda p=plano_dict, f=frame_ref, e=entry_ref: self._on_delete_existing(
                p, f, e
            ),
        )
        del_btn.pack(side="left", padx=(6, 0))

        self._detalles_rows.append({
            "frame": row_frame,
            "var": var,
            "entry": entry,
            "id": plano.get("id"),
            "codigo": plano.get("codigo"),
        })

    def _remove_detalle_row(self, row_frame: ttk.Frame) -> None:
        """Elimina una fila de detalles (solo se llama para filas nuevas)."""
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

    # ==================================================================
    # Logica de marcado de planos existentes (solo edit)
    # ==================================================================

    def _on_delete_existing(
        self,
        plano: dict,
        row_frame: ttk.Frame,
        entry: ttk.Entry,
    ) -> None:
        """
        Maneja el click en el boton X de una fila correspondiente a un
        plano existente. Pregunta al callback del controller que dialogo
        mostrar y aplica el resultado al estado interno.
        """
        if self._mode != "edit":
            self._remove_detalle_row(row_frame)
            return

        plano_id = plano.get("id")
        plano_nombre = plano.get("nombre", "")
        if plano_id is None:
            self._remove_detalle_row(row_frame)
            return

        # Si ya estaba marcado, permitir DESMARCAR (toggle).
        if plano_id in self._planos_marcados_borrar:
            self._planos_marcados_borrar.discard(plano_id)
            self._planos_borrar_silencioso.discard(plano_id)
            self._restore_row_visual(row_frame, entry)
            return
        if plano_id in self._planos_marcados_revertir:
            self._planos_marcados_revertir.discard(plano_id)
            self._restore_row_visual(row_frame, entry)
            return

        action = self._on_delete_check(plano_id, plano_nombre, 0)
        if action == "delete":
            self._planos_marcados_borrar.add(plano_id)
            self._planos_borrar_silencioso.add(plano_id)
            self._mark_row_as_pending(row_frame, entry, action="delete")
        elif action == "revert":
            self._planos_marcados_revertir.add(plano_id)
            self._mark_row_as_pending(row_frame, entry, action="revert")
        # cancel -> no hacer nada.

    def _mark_row_as_pending(
        self,
        row_frame: ttk.Frame,
        entry: ttk.Entry,
        action: str,
    ) -> None:
        """Cambia la apariencia de la fila para reflejar la accion pendiente."""
        try:
            entry.configure(state="disabled")
        except tk.TclError:
            pass
        # Insertar etiqueta visual al final de la fila, junto al boton X.
        label_text = "✕ borrar" if action == "delete" else "↶ revertir"
        label_color = "#C0392B" if action == "delete" else "#2980B9"
        # Evitar duplicar etiquetas si se llama dos veces.
        for w in row_frame.winfo_children():
            if isinstance(w, ttk.Label) and getattr(w, "_pending_tag", False):
                w.destroy()
        marker = ttk.Label(
            row_frame, text=label_text, foreground=label_color,
            font=("Arial", 9, "italic"),
        )
        marker._pending_tag = True
        marker.pack(side="left", padx=(8, 0))

    def _restore_row_visual(
        self,
        row_frame: ttk.Frame,
        entry: ttk.Entry,
    ) -> None:
        """Restaura la fila a su estado normal (toggle off)."""
        try:
            entry.configure(state="normal")
        except tk.TclError:
            pass
        for w in row_frame.winfo_children():
            if isinstance(w, ttk.Label) and getattr(w, "_pending_tag", False):
                w.destroy()

    # ==================================================================
    # Submit
    # ==================================================================

    def _submit_create(self, on_submit: Callable[[dict], None]) -> None:
        """Submit del modo creacion. Mantiene la API de la Fase 2."""
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

    def _submit_edit(self, on_submit: Callable[[dict], None]) -> None:
        """Submit del modo edicion: empaqueta el batch para el servicio."""
        tipo = self._tipo_var.get()
        nombre = self._nombre_var.get().strip()
        lugar = self._lugar_var.get().strip()
        descripcion = self._descripcion_text.get("1.0", "end").strip()

        if tipo not in ("OBRA_NUEVA", "REFORMA"):
            messagebox.showerror("Datos incompletos", "Selecciona un tipo.")
            return
        if not nombre:
            messagebox.showerror("Datos incompletos", "El nombre es obligatorio.")
            return

        # Planos existentes: incluir tanto obligatorios como detalles
        # (los detalles existentes tienen id != None).
        planos_existentes: List[dict] = []
        for entry in self._obligatorios_entries:
            pid = entry["id"]
            if pid is None or pid in self._planos_marcados_borrar:
                continue
            planos_existentes.append({
                "id": pid,
                "nombre": entry["nombre_var"].get().strip(),
                "codigo": entry.get("codigo") or entry["nombre_var"].get().strip(),
            })
        for entry in self._detalles_rows:
            pid = entry.get("id")
            if pid is None:
                continue
            if pid in self._planos_marcados_borrar:
                continue
            planos_existentes.append({
                "id": pid,
                "nombre": entry["var"].get().strip(),
                "codigo": entry.get("codigo") or entry["var"].get().strip(),
            })

        # Detalles nuevos: filas con id=None.
        planos_nuevos_detalle = [
            r["var"].get().strip()
            for r in self._detalles_rows
            if r.get("id") is None and r["var"].get().strip()
        ]

        on_submit({
            "tipo": tipo,
            "nombre": nombre,
            "lugar": lugar,
            "descripcion": descripcion,
            "planos_existentes": planos_existentes,
            "planos_nuevos_detalle": planos_nuevos_detalle,
            "planos_a_borrar": list(self._planos_marcados_borrar),
            "planos_a_revertir": list(self._planos_marcados_revertir),
        })


def _strip_prefix(codigo: str) -> str:
    """Devuelve el codigo sin el prefijo PRJ-, para el campo editable."""
    if codigo and codigo.upper().startswith(PREFIX):
        return codigo[len(PREFIX):]
    return codigo or ""
