"""
Modulo central de estados de planos (Fase 5).

Centraliza la definicion de los 7 estados validos del campo
`planos.estado`, sus colores hex (texto de la fila en el dashboard) y
sus nombres mostrados en castellano. Tambien expone el helper
`cambiar_estado()` que actualiza la BD y registra la transicion en
`plano_estado_historial` de forma atomica.

Cualquier modulo que necesite mostrar un estado o cambiarlo debe leer
de aqui. No duplicar mapeos en `planos_dashboard.py` u otros sitios.

REFACTOR_PLAN.md seccion 3 documenta la semantica de cada estado.
"""

from __future__ import annotations

import sqlite3
from typing import Optional


# Tupla ordenada con los 7 estados validos. El orden se usa al renderizar
# la leyenda en el modal, por eso es deliberado (de "mas neutro" a
# "mas alarma").
ESTADOS = ("GRIS", "BLANCO", "S1", "S2", "S3", "ROJO", "NARANJA")


# Color hex usado como foreground del texto en el Treeview del dashboard
# y como mostra en el modal de leyenda. El fondo del Treeview se mantiene
# oscuro (#1A1A1A) en `planos_dashboard._configure_state_colors` para
# garantizar contraste con BLANCO (#FFFFFF), tal como prevee
# REFACTOR_PLAN.md seccion 3 ("Blanco sobre fondo oscuro o Negro sobre
# fondo claro": el dashboard usa fondo oscuro).
ESTADO_A_COLOR = {
    "GRIS":    "#808080",
    "BLANCO":  "#FFFFFF",
    "S1":      "#F1C40F",
    "S2":      "#27AE60",
    "S3":      "#2980B9",
    "ROJO":    "#C0392B",
    "NARANJA": "#E67E22",
}


# Nombre castellano mostrado al usuario (modal de leyenda y, en el futuro,
# combobox de filtro cuando se reescriba en una fase posterior).
ESTADO_A_NOMBRE = {
    "GRIS":    "Pendiente",
    "BLANCO":  "Habilitado",
    "S1":      "Pendiente revision tecnica",
    "S2":      "Aprobado tecnicamente",
    "S3":      "Aprobado gerencia",
    "ROJO":    "Incorrecto",
    "NARANJA": "Version incoherente",
}


# Mapeo de estados legacy (S0/S1/S2/S3/S3A/D del modelo PlanoDocument
# antiguo) al nuevo conjunto. Usado por el controller como fallback
# cuando un documento existe en la tabla legacy `documents` pero no
# tiene fila correspondiente en la tabla nueva `planos` (caso defensivo;
# la migracion de Fase 1 deberia haber poblado planos para todos los
# documentos legacy).
#
# Decisiones de mapeo (consistentes con utils/database/migrations.py):
#   S0 -> BLANCO       (consensuado en Fase 1: "Borrador" ~ "Habilitado")
#   S1 -> S1, S2 -> S2 (codigos compartidos entre ambos sistemas)
#   S3 -> S3           (natural; no mapeado explicitamente en migrations)
#   S3A -> S3          ("Aprobado por propiedad" ~ "Aprobado gerencia")
#   D -> ROJO          ("Denegado" ~ "Incorrecto")
#   ""/None/desconocido -> GRIS (estado pendiente por defecto)
_LEGACY_A_ESTADO = {
    "S0":  "BLANCO",
    "S1":  "S1",
    "S2":  "S2",
    "S3":  "S3",
    "S3A": "S3",
    "D":   "ROJO",
    "":    "GRIS",
}


def obtener_color(estado: str) -> str:
    """Color hex del estado. Si no es valido, devuelve el de GRIS."""
    return ESTADO_A_COLOR.get(estado, ESTADO_A_COLOR["GRIS"])


def obtener_nombre(estado: str) -> str:
    """Nombre castellano del estado. Si no es valido, devuelve el codigo."""
    return ESTADO_A_NOMBRE.get(estado, estado)


def derivar_estado_desde_legacy(legacy: Optional[str]) -> str:
    """
    Convierte un estado legacy (S0/S1/S2/S3/S3A/D/""/None) a uno nuevo.

    Usado como fallback en el controller para documentos sin fila en la
    tabla `planos` nueva. No se usa en flujos de produccion normales.
    """
    if legacy is None:
        return "GRIS"
    return _LEGACY_A_ESTADO.get(legacy, "GRIS")


def cambiar_estado(
    conn: sqlite3.Connection,
    plano_id: int,
    nuevo_estado: str,
) -> None:
    """
    Cambia el estado de un plano y registra la transicion en
    `plano_estado_historial`. Atomico dentro de la conexion proporcionada
    (el caller decide si abrir transaccion / commit).

    Pensado para los servicios de subida (Fases 6 y 7) y cualquier otro
    punto que actualice `planos.estado`. La Fase 3 (revert) ya hace este
    mismo trabajo inline en project_edit_service; cuando se refactorice
    deberia usar este helper.

    Raises:
        ValueError: si `nuevo_estado` no es uno de los 7 validos.
    """
    if nuevo_estado not in ESTADOS:
        raise ValueError(
            f"Estado invalido: {nuevo_estado!r}. Debe ser uno de {ESTADOS}."
        )

    row = conn.execute(
        "SELECT estado FROM planos WHERE id = ?",
        (plano_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No existe plano con id={plano_id}.")

    estado_actual = row[0] if not hasattr(row, "keys") else row["estado"]
    if estado_actual == nuevo_estado:
        return

    conn.execute(
        "UPDATE planos SET estado = ? WHERE id = ?",
        (nuevo_estado, plano_id),
    )
    conn.execute(
        """
        INSERT INTO plano_estado_historial
        (plano_id, estado_anterior, estado_nuevo)
        VALUES (?, ?, ?)
        """,
        (plano_id, estado_actual, nuevo_estado),
    )
