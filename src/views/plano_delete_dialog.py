"""
Dialogo de seguridad al borrar un plano desde el formulario de edicion
(Fase 3).

Tres rutas segun el estado del plano:

    - safe (sin archivos):
        Confirmacion simple con messagebox.askyesno.

    - no_history (con archivos, sin historial de estados):
        Confirmacion destructiva con messagebox.askyesno explicando que
        se perderan N archivos.

    - has_history (con archivos y al menos un cambio de estado):
        Modal con 3 opciones explicitas:
            * "Recuperar estado anterior" -> action='revert' (diferido).
            * "Borrar completamente" -> segunda confirmacion -> 'delete'.
            * "Cancelar" -> action='cancel'.

La funcion expuesta es `ask_delete_action(...)` y devuelve siempre uno
de los strings: 'delete', 'revert' o 'cancel'.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional


def ask_delete_action(
    parent: tk.Misc,
    plano_nombre: str,
    severity: str,
    n_archivos: Optional[int] = None,
) -> str:
    """
    Pide al usuario que decida que hacer con el plano marcado para
    borrar.

    Args:
        parent: ventana padre (para transient / grab_set).
        plano_nombre: nombre legible del plano (se muestra en los
            dialogos).
        severity: uno de "safe", "no_history", "has_history".
        n_archivos: numero de archivos asociados, solo para mejorar el
            mensaje en no_history / has_history.

    Returns:
        'delete' | 'revert' | 'cancel'.
    """
    if severity == "safe":
        ok = messagebox.askyesno(
            "Confirmar borrado",
            f"¿Eliminar el plano '{plano_nombre}'?",
            parent=parent,
        )
        return "delete" if ok else "cancel"

    if severity == "no_history":
        msg = (
            f"El plano '{plano_nombre}' tiene "
            f"{n_archivos or 'varios'} archivo(s) asociado(s) que se "
            "perderan al borrarlo.\n\n"
            "Esta accion es IRREVERSIBLE.\n\n"
            "¿Continuar?"
        )
        ok = messagebox.askyesno(
            "Confirmar borrado destructivo",
            msg,
            icon="warning",
            parent=parent,
        )
        return "delete" if ok else "cancel"

    if severity == "has_history":
        return _ask_three_option_dialog(parent, plano_nombre, n_archivos)

    # severity desconocida -> tratar como cancelar por seguridad.
    return "cancel"


def _ask_three_option_dialog(
    parent: tk.Misc,
    plano_nombre: str,
    n_archivos: Optional[int],
) -> str:
    """
    Modal Toplevel con los 3 botones explicados en el docstring del
    modulo. Bloquea hasta que el usuario decide.
    """
    result = {"action": "cancel"}

    win = tk.Toplevel(parent)
    win.title("Plano con historial")
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    container = ttk.Frame(win, padding=20)
    container.pack(fill="both", expand=True)

    ttk.Label(
        container,
        text=f"El plano '{plano_nombre}' tiene historial de estados.",
        font=("Arial", 11, "bold"),
        wraplength=420,
        justify="left",
    ).pack(anchor="w", pady=(0, 8))

    archivos_text = (
        f"Hay {n_archivos} archivo(s) asociado(s).\n"
        if n_archivos
        else "Hay archivos asociados.\n"
    )
    ttk.Label(
        container,
        text=(
            archivos_text
            + "¿Que quieres hacer?"
        ),
        wraplength=420,
        justify="left",
    ).pack(anchor="w", pady=(0, 16))

    opt_frame = ttk.Frame(container)
    opt_frame.pack(fill="x")

    def choose_revert():
        result["action"] = "revert"
        win.destroy()

    def choose_delete():
        confirm = messagebox.askyesno(
            "Borrado definitivo",
            (
                f"Vas a borrar el plano '{plano_nombre}', todos sus "
                "archivos y su historial de estados.\n\n"
                "Esta accion es IRREVERSIBLE.\n\n"
                "¿Continuar?"
            ),
            icon="warning",
            parent=win,
        )
        if confirm:
            result["action"] = "delete"
            win.destroy()

    def choose_cancel():
        result["action"] = "cancel"
        win.destroy()

    ttk.Button(
        opt_frame,
        text="↶ Recuperar estado anterior",
        command=choose_revert,
        width=32,
    ).pack(fill="x", pady=2)

    ttk.Button(
        opt_frame,
        text="🗑  Borrar completamente",
        command=choose_delete,
        width=32,
    ).pack(fill="x", pady=2)

    ttk.Button(
        opt_frame,
        text="Cancelar",
        command=choose_cancel,
        width=32,
    ).pack(fill="x", pady=(8, 0))

    # Centrar en pantalla relativo al padre.
    win.update_idletasks()
    try:
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        ww = win.winfo_width()
        wh = win.winfo_height()
        x = px + (pw - ww) // 2
        y = py + (ph - wh) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    except tk.TclError:
        pass

    win.protocol("WM_DELETE_WINDOW", choose_cancel)
    win.wait_window()
    return result["action"]
