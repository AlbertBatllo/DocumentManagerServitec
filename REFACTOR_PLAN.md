# Refactor Plan — DocumentManagerServitec

> Plan de refactorización del gestor documental. Documento maestro de contexto + prompts por fases para ejecutar con Antigravity (Claude Desktop).
>
> **Cómo usar este documento:**
> 1. Guardar este fichero en la raíz del proyecto (o en `docs/`).
> 2. Para cada fase, abrir Antigravity y pegar el prompt correspondiente del **Anexo A**.
> 3. Cada prompt referencia este documento, por lo que Antigravity tendrá siempre el contexto completo.
> 4. **No saltarse fases**: cada una depende de las anteriores. Validar manualmente antes de pasar a la siguiente.

---

## 1. Contexto del proyecto

`DocumentManagerServitec` es una aplicación de escritorio Python (tkinter) para gestionar la documentación de proyectos de ingeniería. Hasta ahora, los proyectos se accedían entrando manualmente a una carpeta existente al lado del `.exe`. Esta refactorización introduce:

- Creación y edición de proyectos desde la propia aplicación.
- Listado normalizado de planos (obligatorios + detalles) por proyecto.
- Sistema de estados con código de color en el texto de cada fila.
- Subida masiva con asignación de metadatos por archivo.
- Layout renovado de la pantalla principal "Ver estado de archivos".

## 2. Stack y decisiones técnicas

- **Lenguaje y UI**: Python + tkinter (+ `tkinterdnd2` para drag & drop).
- **Persistencia**: SQLite.
- **Empaquetado**: PyInstaller (mantener el `.spec` existente, actualizar si es necesario).
- **Lectura DWG/DXF**: `ezdxf` + LibreDWG (carpeta `vendor/libredwg/windows`).

**Decisión clave**: **NO se cambia de stack**. Se mantiene tkinter para evitar regresiones masivas. Cualquier "face-lift" visual (p.ej. migrar a CustomTkinter) se hará en una fase posterior, una vez la lógica nueva esté estable.

**Idioma**:
- UI: castellano (mantener el actual).
- Código y comentarios nuevos: castellano (consistencia con el resto del proyecto).
- Identificadores SQL: castellano sin acentos (`proyectos`, `planos`, `revision_tecnica`).

## 3. Sistema de estados

Cada plano tiene un campo `estado`. El estado determina el **color del texto** de la fila en la tabla principal (NO el color de fondo).

| Estado interno | Nombre mostrado | Color del texto | Significado |
|---|---|---|---|
| `GRIS` | Pendiente | Gris | Estado inicial al crear el proyecto. Sin actividad. |
| `BLANCO` | Habilitado | Blanco (sobre fondo oscuro) o Negro (sobre fondo claro) | Se puede trabajar en él. |
| `S1` | Pendiente revisión técnica ⚠️ | Amarillo | Subido, pendiente de revisión técnica. |
| `S2` | Aprobado técnicamente ⚠️ | Verde | Revisión técnica OK. |
| `S3` | Aprobado gerencia ⚠️ | Azul | Aprobado por gerencia. |
| `ROJO` | Incorrecto | Rojo | Revisado y rechazado. |
| `NARANJA` | Versión incoherente | Naranja | La versión subida no coincide con la esperada. |

> ⚠️ **A confirmar con Albert**: los nombres "Pendiente revisión técnica", "Aprobado técnicamente" y "Aprobado gerencia" son una interpretación inicial. Si en el dominio real son otros (p.ej. "Sello 1 / Sello 2 / Sello 3"), actualizar esta tabla **antes** de empezar la Fase 1.

**Flujo típico** (orientativo, las transiciones son libres):
```
GRIS → BLANCO → S1 → S2 → S3
              ↓
            ROJO (rechazado, vuelve a estado anterior tras nueva subida)
            NARANJA (versión incoherente)
```

## 4. Tipos de proyecto

Al crear un proyecto se elige uno de dos tipos:
- `OBRA_NUEVA`
- `REFORMA`

De momento ambos tipos tienen **el mismo comportamiento**. Sólo se almacena el valor para futura diferenciación.

## 5. Modelo de datos propuesto

> ⚠️ El agente debe **primero inspeccionar la BD actual** (`PRAGMA table_info(...)`) para identificar qué tablas existen ya. La propuesta siguiente es una guía: si hay tablas equivalentes, se extienden; si no, se crean.

### 5.1 Tabla `proyectos` (nueva)

```sql
CREATE TABLE proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK(tipo IN ('OBRA_NUEVA', 'REFORMA')),
    lugar TEXT,
    descripcion TEXT,
    ruta_carpeta TEXT NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modificado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 Tabla `planos` (puede existir ya, extender si es necesario)

```sql
CREATE TABLE planos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    tipo_archivo TEXT,
    obligatorio INTEGER NOT NULL DEFAULT 0,  -- 1 = obligatorio, 0 = detalle
    orden INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'GRIS'
        CHECK(estado IN ('GRIS','BLANCO','S1','S2','S3','ROJO','NARANJA')),
    -- Metadatos del último archivo subido (denormalizados)
    version TEXT,
    fase_requerida TEXT,
    fecha TIMESTAMP,
    autor TEXT,                    -- iniciales
    revision_tecnica TEXT,         -- iniciales
    revision_gerencia TEXT,        -- iniciales
    FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
);
```

### 5.3 Tabla `archivos` (historial de subidas)

```sql
CREATE TABLE archivos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plano_id INTEGER NOT NULL,
    version TEXT NOT NULL,
    autor TEXT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    comentarios TEXT,
    motivo_subida TEXT,           -- sólo si es versión superior a otra existente
    ruta_archivo TEXT NOT NULL,
    FOREIGN KEY (plano_id) REFERENCES planos(id) ON DELETE CASCADE
);
```

### 5.4 Tabla `plano_estado_historial` (para "recuperar estado anterior")

```sql
CREATE TABLE plano_estado_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plano_id INTEGER NOT NULL,
    estado_anterior TEXT,
    estado_nuevo TEXT NOT NULL,
    cambiado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plano_id) REFERENCES planos(id) ON DELETE CASCADE
);
```

## 6. Columnas de la tabla principal "Ver estado de archivos"

Orden exacto, en castellano:

1. `Código`
2. `Nombre`
3. `Tipo archivo`
4. `Estado`
5. `Versión`
6. `Fase requerida`
7. `Fecha`
8. `Autor` (iniciales)
9. `Revisión Técnica` (iniciales)
10. `Revisión Gerencia` (iniciales)

## 7. Layout de la pantalla "Ver estado de archivos"

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [▼ Filtratge]    PLANOS                       [✎ Editar]  [Leyenda]    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ Código │ Nombre │ Tipo │ Estado │ Vers │ Fase │ Fecha │ Aut │ ...  ││
│  ├─────────────────────────────────────────────────────────────────────┤│
│  │  ...    (filas con TEXTO coloreado según estado)                    ││
│  │  ...                                                                ││
│  │  ...                                                                ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  [Subir plano] [Subida masiva] [Eliminar] [...]             [Volver]    │
└──────────────────────────────────────────────────────────────────────────┘
```

- **`Filtratge`** (arriba izquierda): botón que despliega un panel con los mismos filtros que ya existen en la versión actual. Por defecto el panel está colapsado para que la tabla ocupe el máximo espacio posible.
- **`Editar`** (arriba derecha): icono de lápiz + texto "Editar". Abre la pantalla de edición del proyecto (la misma que la de creación, en modo edit).
- **`Leyenda`** (arriba derecha): abre un modal con la tabla de estados y colores (sección 3 de este documento). Modal porque no roba espacio permanente.
- **Botones inferiores izquierda**: los mismos que ya están en la versión actual (subir plano, subida masiva, etc.). El agente debe inspeccionar el código existente para reproducirlos.
- **`Volver`** (abajo derecha): vuelve a la lista de proyectos.

## 8. Comportamiento de la creación / edición de proyecto

### 8.1 Pantalla común (mismo formulario para crear y editar)

Campos:
1. **Tipo** (radio buttons): Obra nueva / Reforma
2. **Nombre**
3. **Código** (único)
4. **Lugar**
5. **Descripción**
6. **Listado de planos**:
   - **Sección obligatorios**: 4-5 filas con placeholders `Obligatori_1`, `Obligatori_2`... Editables.
   - **Sección detalles**: vacía por defecto, con botón "Añadir detalle" para crear filas nuevas. Cada fila se puede borrar.

### 8.2 Al crear

- Se crea físicamente la carpeta del proyecto en disco (al lado del `.exe`, igual que ahora).
- Se inserta el proyecto en BD.
- Se crean las filas de `planos` con `estado = 'GRIS'`.

### 8.3 Al editar planos con archivos ya subidos

Si el usuario **elimina** un plano que ya tiene archivos asociados, mostrar diálogo con tres opciones:

1. **Recuperar estado anterior** (si existe registro en `plano_estado_historial`): revierte al estado previo, sin borrar archivos.
2. **Borrar completamente** (con confirmación destructiva adicional): borra el plano, sus archivos y registros asociados.
3. **Cancelar**.

Si el plano **no tiene** estado anterior, mostrar sólo confirmación destructiva antes de borrar.

## 9. Comportamiento de subida

### 9.1 Subida individual (`Subir Plano`)

Si es un plano **nuevo**: pedir `Código`, `Nombre`, `Versión`, `Autor`, `Comentarios`.

Si es una **versión superior** de un plano existente (detectado por código + comparación de versión): pedir sólo `Versión`, `Autor`, `Motivo de subida`.

> ⚠️ La detección de "versión superior" es por **código de plano**: si el código ya existe en el proyecto, se asume actualización. Si la versión introducida no es superior a la actual, marcar el estado del plano como `NARANJA` (versión incoherente).

### 9.2 Subida masiva

1. El usuario selecciona N archivos.
2. Aparece una pantalla con **una fila por archivo**, cada una con campos editables: `Código`, `Nombre`, `Versión`, `Autor`, `Comentarios`.
3. Al confirmar, se procesa cada archivo como una subida individual (con la misma lógica de detección de versión superior).

### 9.3 Asignación de archivos a planos no listados

Si un archivo subido no coincide con ningún plano del listado del proyecto, el usuario debe asignarlo manualmente desde la pantalla de subida. No se rechaza, no se añade automáticamente.

## 10. Roadmap por fases

| Fase | Objetivo | Salida verificable |
|---|---|---|
| 1 | Esquema de datos | BD migrada, tablas nuevas, scripts de migración. |
| 2 | Pantalla creación de proyecto | Se puede crear un proyecto desde la app y se ve en disco + BD. |
| 3 | Pantalla edición de proyecto | Se puede editar un proyecto existente, incluida la lógica de borrado seguro. |
| 4 | Layout nuevo de "Ver estado de archivos" | Pantalla con tabla central, filtratge colapsable, botones reordenados. |
| 5 | Sistema de estados y colores | Cada fila muestra el color correcto según `estado`. Modal de leyenda funcional. |
| 6 | Subida individual con detección de versión superior | Diálogos correctos en cada caso. |
| 7 | Subida masiva | Pantalla con fila por archivo, procesamiento en bulk. |

## 11. Convenciones para todas las fases

- **No introducir librerías nuevas** sin justificación clara y aprobación.
- **No tocar `vendor/`** ni el `.spec` salvo que sea estrictamente necesario.
- **No romper funcionalidad existente**: si una fase impacta código actual, listar en el PR/commit qué se ha tocado.
- **Cada fase debe ser ejecutable y testeable** antes de pasar a la siguiente. Incluir notas de test manual en cada commit.
- **Mensajes de commit**: prefijo `[Fase N]` seguido del cambio. Ej.: `[Fase 1] Crear tabla proyectos y migración`.

---

# Anexo A — Prompts por fase para Antigravity

> Copiar cada prompt y pegarlo en Antigravity cuando toque ejecutar esa fase. Cada prompt es autocontenido pero referencia el documento maestro para el contexto.

---

## 📋 PROMPT FASE 1 — Esquema de datos

```
Estás trabajando en el proyecto DocumentManagerServitec. Lee primero el archivo
REFACTOR_PLAN.md de la raíz del proyecto: contiene el contexto completo, las
decisiones técnicas, el modelo de datos propuesto y las convenciones a seguir.

OBJETIVO DE ESTA FASE (Fase 1):
Migrar el esquema de la BD SQLite para soportar la nueva funcionalidad,
preservando los datos existentes.

PASOS:
1. Identifica la BD actual (probablemente en la carpeta del .exe o en src/).
   Inspecciona su esquema con PRAGMA table_info para cada tabla existente.
2. Compara con el modelo propuesto en la sección 5 del REFACTOR_PLAN.md.
3. Diseña una migración:
   - Crear las tablas que no existan (proyectos, archivos,
     plano_estado_historial).
   - Si `planos` ya existe, añadir columnas que falten con ALTER TABLE.
   - Si los datos actuales pueden encajar en el nuevo modelo, escribir un
     script de migración que los traslade.
4. Crea un módulo `src/db/migrations.py` (o equivalente acorde a la estructura
   actual) con la función que aplica la migración de forma idempotente
   (detecta si ya está aplicada y no la repite).
5. Asegúrate de que la app, al arrancar, ejecuta la migración automáticamente.

ANTES DE TOCAR NADA:
- Muéstrame el esquema actual de la BD.
- Muéstrame el plan de migración propuesto.
- Espera mi confirmación antes de aplicar cambios destructivos sobre la BD.

CRITERIOS DE ACEPTACIÓN:
- La app sigue arrancando sin errores tras la migración.
- Las tablas nuevas existen y tienen las constraints correctas.
- Los datos existentes (si los había) se preservan.
- Hay un script de rollback documentado, aunque sea manual.

NO HAGAS NADA MÁS de las fases 2-7. Limita el cambio a la BD.
```

---

## 📋 PROMPT FASE 2 — Creación de proyecto

```
Continúa con el proyecto DocumentManagerServitec. Lee REFACTOR_PLAN.md
(secciones 4, 5.1, 5.2, 8.1, 8.2) para el contexto.

OBJETIVO DE ESTA FASE (Fase 2):
Añadir la funcionalidad de crear un proyecto nuevo desde la pantalla inicial
de la aplicación.

PASOS:
1. En la pantalla inicial (donde ahora se listan los proyectos existentes),
   añade un botón "Crear proyecto nuevo".
2. Al pulsarlo, abre una pantalla con el formulario descrito en la sección
   8.1 del REFACTOR_PLAN.md:
   - Tipo (radio: Obra nueva / Reforma)
   - Nombre
   - Código (único, validar)
   - Lugar
   - Descripción
   - Listado de planos:
     * Sección obligatorios: 5 filas precargadas con placeholders
       (Obligatori_1...Obligatori_5), nombre editable.
     * Sección detalles: vacía con botón "Añadir detalle" para crear filas
       nuevas. Cada fila con botón de borrar.
3. Al confirmar:
   - Validar que el código no exista ya (consulta SQL).
   - Crear la carpeta física del proyecto en la misma ruta donde están las
     demás (al lado del .exe).
   - Insertar el proyecto en la tabla `proyectos`.
   - Insertar las filas en `planos`, con `obligatorio = 1` para los
     obligatorios y `obligatorio = 0` para los detalles, todas con
     `estado = 'GRIS'`.
4. Tras crear, volver a la pantalla inicial y mostrar el proyecto nuevo en
   la lista.

CRITERIOS DE ACEPTACIÓN:
- Botón visible en la pantalla inicial.
- Formulario funcional con validación.
- La carpeta se crea físicamente.
- La BD queda consistente (proyecto + planos asociados).
- Si algo falla a mitad (ej. carpeta creada pero BD falla), hacer rollback de
  la carpeta.

NO TOQUES la pantalla "Ver estado de archivos" todavía. Eso es la Fase 4.
```

---

## 📋 PROMPT FASE 3 — Edición de proyecto

```
Continúa con DocumentManagerServitec. Lee REFACTOR_PLAN.md (secciones 8.1 y
8.3) para el contexto.

OBJETIVO DE ESTA FASE (Fase 3):
Permitir editar un proyecto existente, reutilizando el formulario de la
Fase 2 en modo edición. Manejar correctamente el borrado de planos con
archivos asociados.

PASOS:
1. Añadir un botón "Editar" (icono lápiz + texto) en la pantalla
   "Ver estado de archivos", arriba a la derecha. Por ahora la pantalla
   sigue siendo la antigua, eso se rediseñará en la Fase 4. Solo añade
   el botón en un sitio razonable.
2. Al pulsarlo, abrir el mismo formulario de la Fase 2 pero pre-rellenado
   con los datos del proyecto actual.
3. Permitir modificar todos los campos. El código sigue siendo único.
4. Para el listado de planos:
   - Mostrar todos los planos existentes (obligatorios y detalles).
   - Permitir editar nombre.
   - Permitir borrar planos.
5. AL BORRAR UN PLANO QUE TIENE ARCHIVOS ASOCIADOS:
   - Comprobar si existe registro en `plano_estado_historial`.
   - Si SÍ existe: mostrar diálogo con tres opciones:
     a) "Recuperar estado anterior" → revertir estado, no borrar.
     b) "Borrar completamente" → segunda confirmación, luego borrar plano
        + archivos + historial (CASCADE).
     c) "Cancelar".
   - Si NO existe historial: mostrar solo confirmación destructiva antes
     de borrar.
6. Al guardar, actualizar `proyectos.modificado_en` y persistir cambios en
   `planos`.

CRITERIOS DE ACEPTACIÓN:
- Botón "Editar" visible y funcional.
- Formulario en modo edición carga datos correctos.
- Lógica de borrado segura y con avisos claros.
- Cancelar no aplica ningún cambio.
```

---

## 📋 PROMPT FASE 4 — Layout nuevo de "Ver estado de archivos"

```
Continúa con DocumentManagerServitec. Lee REFACTOR_PLAN.md (secciones 6 y 7)
para el contexto.

OBJETIVO DE ESTA FASE (Fase 4):
Rediseñar la pantalla "Ver estado de archivos" siguiendo el layout descrito
en la sección 7. NO toques la lógica de filtrado, subida, etc.: solo el
layout y la organización visual.

PASOS:
1. Identifica el módulo actual de esta pantalla.
2. Reorganiza la estructura:
   - Barra superior: [▼ Filtratge] a la izquierda, "PLANOS" centrado o a la
     izquierda del centro, [✎ Editar] y [Leyenda] a la derecha.
   - Centro: tabla con las 10 columnas exactas de la sección 6 del
     REFACTOR_PLAN.md, en el orden indicado. La tabla debe ocupar el máximo
     espacio posible.
   - Barra inferior: botones existentes (subir plano, subida masiva, etc.)
     a la izquierda, [Volver] a la derecha.
3. El botón "Filtratge" debe abrir/cerrar un panel colapsable con los
   filtros que ya existían. Por defecto colapsado.
4. El botón "Leyenda" abre un modal con la tabla de estados (sección 3
   del REFACTOR_PLAN.md). El modal es informativo: solo se cierra.
5. "Editar" lleva al formulario de la Fase 3 (ya implementado).

REQUISITOS:
- No romper ninguna funcionalidad existente (filtros, botones, subida...).
- Las columnas Autor / Revisión Técnica / Revisión Gerencia muestran
  iniciales (texto plano, sin desplegable de momento).
- Hacer la tabla redimensionable y con scroll vertical.

CRITERIOS DE ACEPTACIÓN:
- La pantalla se ve organizada como el ASCII art del REFACTOR_PLAN.md
  sección 7.
- Filtratge se despliega/colapsa.
- Leyenda modal funciona.
- Editar y Volver llevan a los sitios correctos.
- Las acciones existentes siguen funcionando.

NO TOQUES los colores de las filas ni la lógica de estados todavía. Eso es
la Fase 5.
```

---

## 📋 PROMPT FASE 5 — Sistema de estados y colores

```
Continúa con DocumentManagerServitec. Lee REFACTOR_PLAN.md (sección 3) para
el contexto.

OBJETIVO DE ESTA FASE (Fase 5):
Aplicar el color al texto de cada fila de la tabla principal según el
estado del plano, y centralizar la gestión de estados.

PASOS:
1. Crea un módulo `src/domain/estados.py` (o equivalente) con:
   - Enum / constantes con los 7 estados (GRIS, BLANCO, S1, S2, S3, ROJO,
     NARANJA).
   - Mapa `ESTADO_A_COLOR` con el color hex de cada estado:
     * GRIS    → #808080
     * BLANCO  → #FFFFFF (o #000000 si el fondo es claro)
     * S1      → #F1C40F (amarillo)
     * S2      → #27AE60 (verde)
     * S3      → #2980B9 (azul)
     * ROJO    → #C0392B
     * NARANJA → #E67E22
   - Mapa `ESTADO_A_NOMBRE` con el nombre mostrado en español.
2. Al renderizar las filas de la tabla de "Ver estado de archivos", aplicar
   el color al TEXTO de la fila (foreground), NO al fondo.
3. Registrar cualquier cambio de estado en `plano_estado_historial`
   (insertar fila con estado_anterior y estado_nuevo). Esto es la base para
   la funcionalidad "recuperar estado anterior" de la Fase 3.
4. Asegurar que el modal de leyenda (Fase 4) refleja los mismos colores y
   nombres que el módulo de estados (importarlos desde ahí, no duplicarlos).

CRITERIOS DE ACEPTACIÓN:
- Cada fila muestra el texto con el color correcto según su estado.
- Los proyectos nuevos arrancan todos sus planos en GRIS.
- El cambio de estado se registra en historial.
- Centralización: solo hay UN lugar donde se definen los estados/colores.
```

---

## 📋 PROMPT FASE 6 — Subida individual con detección de versión superior

```
Continúa con DocumentManagerServitec. Lee REFACTOR_PLAN.md (sección 9.1)
para el contexto.

OBJETIVO DE ESTA FASE (Fase 6):
Implementar la lógica diferenciada de subida individual: si es un plano
nuevo, pedir todos los campos; si es una versión superior, pedir solo
los relevantes.

PASOS:
1. Al pulsar "Subir Plano" (o equivalente), primero pedir el código del
   plano que se va a subir (o seleccionarlo de un desplegable con los
   planos existentes del proyecto).
2. Si el código NO existe en el proyecto:
   - Mostrar formulario completo: Código, Nombre, Versión, Autor,
     Comentarios + selector de archivo.
   - Al confirmar, crear el plano en BD y registrar el archivo.
3. Si el código SÍ existe:
   - Mostrar formulario reducido: Versión, Autor, Motivo de subida +
     selector de archivo.
   - Comparar la versión introducida con la versión actual del plano:
     * Si es superior: actualizar `planos.version` y demás metadatos,
       insertar archivo en `archivos` con motivo_subida poblado.
     * Si NO es superior: marcar `planos.estado = 'NARANJA'` (versión
       incoherente) e igualmente registrar el archivo. Mostrar aviso al
       usuario explicándolo.
4. En cualquier caso, registrar el cambio de estado en
   `plano_estado_historial`.
5. Mover el archivo físico a la carpeta del proyecto.

CRITERIOS DE ACEPTACIÓN:
- Diálogos correctos según caso (nuevo vs. versión superior).
- Detección de versión incoherente con marcado naranja.
- Historial de estados actualizado.
- Archivo físicamente en su carpeta.

PREGUNTA SI TIENES DUDAS sobre el formato esperado del campo Versión
(¿numérico, alfanumérico?). Si no hay convención, asume string y compara
lexicográficamente, anotándolo como TODO para revisión.
```

---

## 📋 PROMPT FASE 7 — Subida masiva

```
Continúa con DocumentManagerServitec. Lee REFACTOR_PLAN.md (sección 9.2)
para el contexto.

OBJETIVO DE ESTA FASE (Fase 7):
Permitir subir varios archivos a la vez, asignando metadatos a cada uno
en una pantalla intermedia.

PASOS:
1. Al pulsar "Subida masiva", abrir selector de archivos múltiple.
2. Tras seleccionar N archivos, abrir una pantalla con UNA FILA POR ARCHIVO,
   cada una con los campos editables: Código, Nombre, Versión, Autor,
   Comentarios.
3. El nombre del archivo seleccionado se muestra como referencia al
   principio de cada fila.
4. Si el código que el usuario introduce coincide con un plano existente
   del proyecto, marcar visualmente esa fila (p.ej. icono o color del
   borde) para indicar "esto es una nueva versión, no un plano nuevo".
   En ese caso, el campo "Comentarios" se reinterpreta como "Motivo de
   subida".
5. Al confirmar, procesar cada fila como una subida individual usando la
   misma lógica de la Fase 6.
6. Mostrar un resumen final con éxitos y errores por archivo.

CRITERIOS DE ACEPTACIÓN:
- Pantalla intermedia con una fila por archivo, todos los campos editables.
- Detección visual de "nuevo vs. nueva versión" en cada fila.
- Procesamiento en bulk con resumen final.
- Si una fila falla, las demás siguen procesándose.

NOTAS:
- Esta es la última fase del refactor. Tras ella, conviene hacer una pasada
  de QA manual completa siguiendo todos los flujos.
```

---

# Anexo B — Checklist de QA final

Tras completar las 7 fases, hacer estas pruebas manuales:

- [ ] Crear un proyecto Obra nueva con 5 obligatorios y 2 detalles.
- [ ] Crear un proyecto Reforma con 5 obligatorios y 0 detalles.
- [ ] Verificar que las dos carpetas existen físicamente.
- [ ] Editar un proyecto existente, cambiar nombre y descripción.
- [ ] Borrar un detalle sin archivos asociados (debe ir directo con confirmación).
- [ ] Subir un archivo a un detalle, luego intentar borrar el detalle (debe ofrecer "recuperar estado anterior" o "borrar completo").
- [ ] Subir un plano nuevo individual con formulario completo.
- [ ] Subir una versión superior del mismo plano (formulario reducido).
- [ ] Subir una versión INFERIOR del mismo plano (debe quedar NARANJA).
- [ ] Subida masiva de 3 archivos: 2 nuevos + 1 versión superior. Verificar resumen.
- [ ] Abrir el modal de Leyenda y verificar que muestra los 7 estados con los colores correctos.
- [ ] Verificar que los textos de las filas tienen el color que corresponde a su estado.
- [ ] Volver desde "Ver estado de archivos" a la lista de proyectos.
- [ ] Compilar el `.exe` con PyInstaller y verificar que funciona sin Python instalado.
