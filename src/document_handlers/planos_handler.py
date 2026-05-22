"""
Planos Document Handler

Handles Planos (CAD drawings, plans) specific operations.
Extends BaseDocumentHandler with Planos-specific functionality.
"""

from pathlib import Path
from typing import Dict, List, Optional
from tkinter import messagebox

from .base_handler import BaseDocumentHandler
from utils.folder_resolver import FolderResolver


class PlanosHandler(BaseDocumentHandler):
    """
    Handler for Planos (CAD drawings, plans) documents.

    Planos have specific requirements:
    - Support for DWG, RVT, PDF file types
    - XREF reference tracking for CAD files
    - Organized folder structure (Working/Old/REF)
    """

    def __init__(self, app_controller, controller, view_factory: Dict = None):
        super().__init__(app_controller, controller, view_factory)
        self._xref_progress_callback = None

        # Set up XREF progress callback if controller exists
        if self.controller and hasattr(self.controller, 'set_xref_progress_callback'):
            self.controller.set_xref_progress_callback(self.on_xref_progress)

    def get_document_type(self) -> str:
        return "planos"

    def get_storage_path(self) -> Path:
        """
        Get the storage path for Planos documents.

        Returns:
            Path to 02_Planos folder within the current project.
            Falls back to current directory if no project is selected.

        Note:
            Use get_validated_storage_path() when you need to ensure
            the path exists before file operations.
        """
        if not self.app.current_project_path:
            return Path(".")

        project_path = Path(self.app.current_project_path)
        if not project_path.exists():
            print(f"[WARNING] Project path does not exist: {project_path}")
            return Path(".")

        return FolderResolver.resolve_planos(project_path)

    def get_display_name(self) -> str:
        return "Planos"

    def get_state_map(self) -> Dict[str, str]:
        from models.plano_document import STATE_DISPLAY_NAMES
        return STATE_DISPLAY_NAMES

    # === Planos-specific Methods ===

    def set_xref_progress_callback(self, callback):
        """Set callback for XREF processing progress updates."""
        self._xref_progress_callback = callback
        if self.controller and hasattr(self.controller, 'set_xref_progress_callback'):
            self.controller.set_xref_progress_callback(callback)

    def on_xref_progress(self, message: str):
        """Handle XREF progress updates."""
        if self._xref_progress_callback:
            self._xref_progress_callback(message)

    def get_document_files(self, document_name: str) -> Dict:
        """Get file information for a plano document."""
        if not self.controller:
            return {}
        if hasattr(self.controller, 'get_document_files'):
            return self.controller.get_document_files(document_name)
        return {}

    def get_document_file_extensions(self, document_name: str) -> List[str]:
        """Get file extensions from filesystem (source of truth)."""
        if not self.controller:
            return []
        if hasattr(self.controller, 'get_document_file_extensions'):
            return self.controller.get_document_file_extensions(document_name)

        # Fallback: scan filesystem
        storage_path = self.get_storage_path()
        extensions = set()
        for folder in ['Working', 'Old']:
            folder_path = storage_path / "CAD" / folder
            if folder_path.exists():
                for file in folder_path.glob(f"*{document_name}*"):
                    extensions.add(file.suffix.lower())
        return list(extensions)

    def replace_file(self, document_name: str, current_path: str, new_file: str) -> bool:
        """Replace a file for a plano document."""
        if not self.controller:
            return False
        if hasattr(self.controller, 'replace_file'):
            return self.controller.replace_file(document_name, current_path, new_file)
        return False

    def add_file(self, document_name: str, file_path: str, file_type: str) -> bool:
        """Add a file to a plano document."""
        if not self.controller:
            return False
        if hasattr(self.controller, 'add_file'):
            return self.controller.add_file(document_name, file_path, file_type)
        return False

    def refresh_data(self):
        """Refresh planos data with optimized loading."""
        if self.controller and hasattr(self.controller, 'refresh_data'):
            return self.controller.refresh_data()
        return self.get_documents()

    def submit_new_document(self, doc_id: str, name: str, version: str, state: str,
                            file_paths: list, author: str, notes: str, dwg_name: str = "",
                            entry_timestamp: str = None):
        """Submit a new plano document.

        Args:
            entry_timestamp: Optional ISO timestamp to assign to the initial entry.
                Bulk upload passes the source file mtime so the dashboard "Fecha"
                column reflects the file's date instead of the upload moment.
        """
        if not self.controller:
            raise Exception("Planos controller not initialized")
        # Controller signature: add_new_document(name, state, version, file_paths, author, rev_tecnica, rev_gerencia, notes, dwg_name, entry_timestamp)
        # Ensure file_paths are Path objects
        from pathlib import Path
        path_objects = [Path(fp) if isinstance(fp, str) else fp for fp in file_paths]
        return self.controller.add_new_document(doc_id, state, version, path_objects, author, "", "", notes,
                                                dwg_name=dwg_name, entry_timestamp=entry_timestamp)

    def submit_new_version(self, doc_id: str, name: str, version: str, state: str,
                           file_paths: list, author: str, notes: str, dwg_name: str = "",
                           entry_timestamp: str = None):
        """Submit a new version of a plano document (legacy path).

        Mantenido por compatibilidad con NewVersionForm legacy. El flujo
        de Fase 6 entra por show_new_version_form -> UploadFormView ->
        upload_service.subir_nueva_version y NO pasa por aqui.
        """
        if not self.controller:
            raise Exception("Planos controller not initialized")
        # Controller signature: add_new_version(doc_name, version, state, file_paths, author, rev_tecnica, rev_gerencia, notes, dwg_name, entry_timestamp)
        # Ensure file_paths are Path objects
        from pathlib import Path
        path_objects = [Path(fp) if isinstance(fp, str) else fp for fp in file_paths]
        return self.controller.add_new_version(doc_id, version, state, path_objects, author, "", "", notes,
                                               dwg_name=dwg_name, entry_timestamp=entry_timestamp)

    # === Fase 6: nuevo flujo de subida individual ===================

    def show_new_version_form(self, back_to_dashboard: bool = False, pre_selected=None):
        """
        Sobreescribe el flujo del boton 'Registrar Nueva Version' para
        usar el nuevo UploadFormView y upload_service (Fase 6) en lugar
        del NewVersionForm legacy.

        Solo cubre el CASO 2 (plano existente). Para crear un plano
        nuevo, el usuario debe pasar por "Editar proyecto" (Fase 3) y
        luego subir la primera version aqui.

        Args:
            back_to_dashboard: ignorado (siempre vuelve al dashboard).
            pre_selected: dict con `id` del plano seleccionado en el
                tree (formato actual del dashboard), o `None`.
        """
        from pathlib import Path
        from tkinter import messagebox

        if pre_selected is None:
            messagebox.showinfo(
                "Selecciona un plano",
                "Para subir una nueva version, selecciona primero el plano "
                "en la tabla.\n\n"
                "Si quieres anadir un plano nuevo, usa 'Editar proyecto' "
                "para crearlo y despues sube su primera version desde aqui."
            )
            return

        # `pre_selected` viene del dashboard como dict {'id': nombre, ...}.
        # En el modelo nuevo, ese 'id' es planos.codigo.
        codigo = pre_selected.get('id') if isinstance(pre_selected, dict) else str(pre_selected)
        if not codigo:
            messagebox.showerror("Error", "No se ha podido identificar el plano seleccionado.")
            return

        project_path = getattr(self.app, 'current_project_path', None)
        if not project_path:
            messagebox.showerror("Error", "No hay proyecto activo.")
            return
        project_path = Path(project_path)

        # Leer estado y version actuales para mostrar en el form.
        from utils.database.project_database_manager import ensure_project_database
        db = ensure_project_database(project_path)
        with db.connection() as conn:
            row = conn.execute(
                "SELECT id, codigo, nombre, estado, version FROM planos WHERE codigo = ?",
                (codigo,)
            ).fetchone()
        if row is None:
            messagebox.showerror(
                "Plano no encontrado",
                f"No existe un plano con codigo {codigo!r} en este proyecto."
            )
            return

        plano_info = {
            'id': row['id'],
            'codigo': row['codigo'],
            'nombre': row['nombre'],
            'estado': row['estado'],
            'version': row['version'],
        }

        from views.upload_form_view import UploadFormView
        view = UploadFormView(self.app.root)

        def on_submit(form_data: dict, archivo_path: Path):
            from services.upload_service import subir_nueva_version, UploadError
            try:
                result = subir_nueva_version(
                    project_path,
                    plano_info['id'],
                    form_data,
                    archivo_path,
                )
            except UploadError as e:
                messagebox.showerror("Error al subir", str(e))
                return
            except Exception as e:
                messagebox.showerror("Error inesperado", f"{e}")
                return

            # Mensaje informativo del resultado.
            if result['es_version_superior']:
                msg = (
                    f"Version subida correctamente.\n\n"
                    f"Estado tras la subida: {result['estado_nuevo']}\n"
                    f"Archivo: {result['ruta_archivo']}"
                )
                messagebox.showinfo("Subida correcta", msg)
            else:
                msg = (
                    f"La version introducida NO es superior a la actual.\n"
                    f"El plano queda marcado como 'NARANJA' (version incoherente).\n\n"
                    f"Archivo registrado en: {result['ruta_archivo']}"
                )
                messagebox.showwarning("Version incoherente", msg)

            self.show_dashboard()

        def on_cancel():
            self.show_dashboard()

        view.show_new_version(plano_info, on_submit, on_cancel)

    # === Fase 7: subida masiva ======================================

    def _show_bulk_upload(self, file_paths: list) -> None:
        """
        Obre la pantalla intermedia de Fase 7 amb una fila editable per
        cada arxiu seleccionat. Al confirmar, crida
        upload_service.subir_masivo i mostra el modal de resumen.

        Args:
            file_paths: list de Path / str amb els arxius seleccionats
                pel filedialog del dashboard.
        """
        from pathlib import Path
        from tkinter import messagebox

        paths = [Path(p) if not isinstance(p, Path) else p for p in (file_paths or [])]
        if not paths:
            return

        project_path = getattr(self.app, 'current_project_path', None)
        if not project_path:
            messagebox.showerror("Error", "No hay proyecto activo.")
            return
        project_path = Path(project_path)

        # Precarregar codis existents (1 sola query, deteccio O(1) per fila).
        from utils.database.project_database_manager import ensure_project_database
        db = ensure_project_database(project_path)
        with db.connection() as conn:
            existing_codigos = {
                row["codigo"]
                for row in conn.execute("SELECT codigo FROM planos")
            }

        from views.bulk_upload_form_view import BulkUploadFormView
        view = BulkUploadFormView(self.app.root)

        def on_submit(items: list):
            from services.upload_service import subir_masivo
            results = subir_masivo(project_path, items)
            view.show_summary(results, on_close=self.show_dashboard)

        def on_cancel():
            self.show_dashboard()

        view.show(paths, existing_codigos, on_submit, on_cancel)

    def _annotate_document_by_id(self, doc_id: str):
        """Launch PDF annotation for a plano document."""
        document = self.get_document_by_id(doc_id)
        if not document:
            messagebox.showerror("Error", f"Documento no encontrado: {doc_id}")
            return

        pdf_corrector = getattr(self.app, 'pdf_corrector', None)
        if not pdf_corrector:
            messagebox.showerror("Error", "Corrector PDF no disponible")
            return

        # Find PDF file for this document
        storage_path = self.get_storage_path()
        pdf_path = None

        # Search in PDF folders
        for folder in ['CAD/Working', 'CAD/Old', 'PDF/Working', 'PDF/Old']:
            folder_path = storage_path / folder
            if folder_path.exists():
                for pdf_file in folder_path.glob(f"*{document.name}*.pdf"):
                    pdf_path = pdf_file
                    break
            if pdf_path:
                break

        if not pdf_path or not pdf_path.exists():
            messagebox.showerror(
                "Error",
                f"No se encontró el archivo PDF para el documento {document.name}"
            )
            return

        # Launch annotation
        callbacks = {
            'save_annotations': lambda anns: self._save_annotations(doc_id, anns),
            'back': self.show_dashboard,
        }
        pdf_corrector.annotate_pdf(str(pdf_path), callbacks)

    def _save_annotations(self, doc_id: str, annotations: dict):
        """Save PDF annotations for a plano document."""
        # Annotations are typically saved by the PDF corrector itself
        pass

    # === Override Dashboard Callbacks ===

    def get_dashboard_callbacks(self) -> Dict:
        """
        Get callbacks for planos dashboard with all planos-specific functionality.

        Includes:
        - Base callbacks from parent
        - XREF status and missing references
        - File management (replace, add, populate)
        - Cloud sync
        - Document editing
        """
        from typing import Callable

        # Get base callbacks
        callbacks = super().get_dashboard_callbacks()

        # Add planos-specific callbacks
        if self.controller:
            # XREF callbacks
            if hasattr(self.controller, 'get_plano_xref_status'):
                callbacks['get_plano_xref_status'] = self.controller.get_plano_xref_status
            if hasattr(self.controller, 'get_missing_references'):
                callbacks['get_missing_references'] = self.controller.get_missing_references

            # File management callbacks
            if hasattr(self.controller, 'get_document_files_info'):
                callbacks['get_current_files'] = self._get_current_files_wrapper
            if hasattr(self.controller, 'replace_file_for_document'):
                callbacks['replace_file'] = self._replace_file_wrapper
            if hasattr(self.controller, 'add_file_to_document'):
                callbacks['add_file'] = self._add_file_wrapper
            if hasattr(self.controller, 'populate_missing_file_paths'):
                callbacks['populate_files'] = self.controller.populate_missing_file_paths
            if hasattr(self.controller, 'promote_file_to_last'):
                callbacks['promote_file'] = self.controller.promote_file_to_last

            # DWG association callbacks
            if hasattr(self.controller, 'get_available_dwgs'):
                callbacks['get_available_dwgs'] = self.controller.get_available_dwgs
            if hasattr(self.controller, 'set_associated_dwg'):
                callbacks['set_associated_dwg'] = self.controller.set_associated_dwg

            # Document info editing
            if hasattr(self.controller, 'update_document_info'):
                callbacks['edit_document_info'] = self.show_edit_document_info_form
                callbacks['update_document_info'] = self._update_document_info
            if hasattr(self.controller, 'update_plano_phase'):
                callbacks['update_plano_phase'] = self.controller.update_plano_phase

            # Cloud sync
            if hasattr(self.controller, 'sync_document_to_cloud'):
                callbacks['sync_to_cloud'] = self.controller.sync_document_to_cloud
            if hasattr(self.controller, 'is_cloud_sync_enabled'):
                callbacks['is_cloud_enabled'] = self.controller.is_cloud_sync_enabled

        # Refresh callback specific to planos
        callbacks['refresh_planos'] = self.refresh_data

        # Fase 7: subida masiva. El dashboard fa askopenfilenames i ens
        # delega la creacio de la pantalla intermedia + processament.
        callbacks['bulk_upload'] = self._show_bulk_upload

        # History, annotation, and export callbacks
        callbacks['view_history'] = self.show_history_window
        callbacks['annotate_document'] = self.annotate_selected_document
        callbacks['export_multiple'] = self.show_export_dialog

        # Edicion de proyecto (Fase 3): boton "✎ Editar" en el dashboard.
        if hasattr(self.app, 'show_project_edit'):
            callbacks['edit_project'] = self.app.show_project_edit

        return callbacks

    def show_history_window(self, doc_name: str = None):
        """
        Show document history window with file type filters and double-click to open.

        Uses stored file paths from document entries and file_paths list.
        Falls back to filesystem scan if no stored paths exist.
        Includes PDF, DWG, RVT filters.

        Args:
            doc_name: Document name to show history for
        """
        import tkinter as tk
        from tkinter import ttk
        from datetime import datetime
        from pathlib import Path

        if not doc_name:
            messagebox.showwarning("Aviso", "Por favor seleccione un documento")
            return

        # Get the full document
        document = self.get_document_by_id(doc_name)
        if not document:
            messagebox.showerror("Error", f"No se encontró el documento {doc_name}")
            return

        storage_path = self.get_storage_path()

        def get_files_from_stored_paths():
            """Get files from document's stored file_paths and scan Old folders."""
            files = []
            seen_paths = set()

            def add_file(file_path: Path):
                """Add a file to the list if it exists and hasn't been added."""
                if not file_path.exists() or not file_path.is_file():
                    return

                path_str = str(file_path)
                if path_str in seen_paths:
                    return
                seen_paths.add(path_str)

                # Determine file type from extension
                ext = file_path.suffix.lower()
                if ext == '.pdf':
                    file_type = 'PDF'
                elif ext == '.dwg':
                    file_type = 'DWG'
                elif ext == '.rvt':
                    file_type = 'RVT'
                else:
                    return  # Skip unknown types

                # Determine location from path
                try:
                    rel_path = file_path.relative_to(storage_path)
                    parts = rel_path.parts
                    if len(parts) >= 2:
                        location = parts[1]  # Working or Old
                        if location == "Old" and len(parts) >= 3:
                            location = f"Old/{parts[2]}"
                    else:
                        location = "Working"
                except ValueError:
                    location = "External"

                stat = file_path.stat()
                files.append({
                    'type': file_type,
                    'location': location,
                    'filename': file_path.name,
                    'path': file_path,
                    'modified': datetime.fromtimestamp(stat.st_mtime),
                    'size': stat.st_size
                })

            # 1. Get files from stored paths
            stored_paths = []
            if hasattr(document, 'file_paths') and document.file_paths:
                stored_paths.extend(document.file_paths)
            if hasattr(document, 'get_file_paths'):
                stored_paths.extend(document.get_file_paths())
            if hasattr(document, 'entries'):
                for entry in document.entries:
                    if hasattr(entry, 'file_path') and entry.file_path:
                        stored_paths.append(entry.file_path)
            if hasattr(document, 'associated_dwg') and document.associated_dwg:
                stored_paths.append(document.associated_dwg)

            for path_str in stored_paths:
                if not path_str:
                    continue
                # Cross-platform path normalization
                normalized_path = path_str.replace('\\', '/')
                file_path = Path(normalized_path)
                if not file_path.is_absolute():
                    file_path = storage_path / normalized_path
                add_file(file_path)

            # 2. Scan Old folders for archived files matching this document
            display_name = getattr(document, 'display_name', '') or doc_name
            sanitized_name = doc_name.replace("-", "_").replace(" ", "_")
            sanitized_display = display_name.replace("-", "_").replace(" ", "_")

            old_folders = [
                ("PDF", storage_path / "PDF" / "Old"),
                ("DWG", storage_path / "CAD" / "Old"),
                ("RVT", storage_path / "RVT" / "Old"),
            ]

            for file_type, old_folder in old_folders:
                if not old_folder.exists():
                    continue

                ext = ".pdf" if file_type == "PDF" else f".{file_type.lower()}"

                # Direct files in Old folder
                for file_path in old_folder.glob(f"*{ext}"):
                    if file_path.is_file():
                        stem = file_path.stem
                        if (sanitized_name in stem or doc_name in stem or
                            sanitized_display in stem or display_name in stem):
                            add_file(file_path)

                # Timestamped subfolders in Old (e.g., v1.0_backup_20251219, 202512181255-DOC_NAME-v1.0-S0)
                for subfolder in old_folder.iterdir():
                    if subfolder.is_dir():
                        folder_name = subfolder.name
                        # Check if folder name matches document
                        folder_matches = (sanitized_name in folder_name or doc_name in folder_name or
                                         sanitized_display in folder_name or display_name in folder_name)

                        # Scan files in subfolder
                        for file_path in subfolder.glob(f"*{ext}"):
                            if file_path.is_file():
                                stem = file_path.stem
                                # Add if folder matches OR filename matches document
                                if folder_matches or (sanitized_name in stem or doc_name in stem or
                                                     sanitized_display in stem or display_name in stem):
                                    add_file(file_path)

            # Sort by modified date, newest first
            files.sort(key=lambda x: x['modified'], reverse=True)
            return files

        all_files = get_files_from_stored_paths()

        if not all_files:
            messagebox.showinfo("Historial", f"No se encontraron archivos para {doc_name}")
            return

        # Create history window
        win = tk.Toplevel(self.app.root)
        win.title(f"Historial de Archivos - {document.name}")
        win.geometry("950x550")
        win.transient(self.app.root)

        # Header
        header = ttk.Frame(win, padding=(10, 10, 10, 5))
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"Archivos de: {document.name}",
            font=("Arial", 12, "bold")
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="Doble clic para abrir ubicación del archivo",
            font=("Arial", 9),
            foreground="gray"
        ).pack(anchor="w")

        # Filter frame
        filter_frame = ttk.Frame(win, padding=(10, 5, 10, 5))
        filter_frame.pack(fill="x")

        ttk.Label(filter_frame, text="Filtrar por tipo:").pack(side="left", padx=(0, 10))

        # Filter variable
        filter_var = tk.StringVar(value="Todos")

        def apply_filter(*args):
            """Filter the treeview based on selected file type."""
            selected = filter_var.get()
            tree.delete(*tree.get_children())

            for file_info in all_files:
                if selected == "Todos" or file_info['type'] == selected:
                    # Format size
                    size_kb = file_info['size'] / 1024
                    if size_kb > 1024:
                        size_str = f"{size_kb/1024:.1f} MB"
                    else:
                        size_str = f"{size_kb:.1f} KB"

                    tree.insert(
                        "",
                        "end",
                        values=(
                            file_info['type'],
                            file_info['location'],
                            file_info['filename'],
                            file_info['modified'].strftime("%Y-%m-%d %H:%M"),
                            size_str
                        ),
                        tags=(str(file_info['path']),)
                    )

        # Filter buttons
        for filter_type in ["Todos", "PDF", "DWG", "RVT"]:
            ttk.Radiobutton(
                filter_frame,
                text=filter_type,
                variable=filter_var,
                value=filter_type,
                command=apply_filter
            ).pack(side="left", padx=5)

        # Count labels
        count_frame = ttk.Frame(filter_frame)
        count_frame.pack(side="right")

        pdf_count = sum(1 for f in all_files if f['type'] == 'PDF')
        dwg_count = sum(1 for f in all_files if f['type'] == 'DWG')
        rvt_count = sum(1 for f in all_files if f['type'] == 'RVT')

        ttk.Label(count_frame, text=f"PDF: {pdf_count}", foreground="gray").pack(side="left", padx=5)
        ttk.Label(count_frame, text=f"DWG: {dwg_count}", foreground="gray").pack(side="left", padx=5)
        ttk.Label(count_frame, text=f"RVT: {rvt_count}", foreground="gray").pack(side="left", padx=5)

        # Table frame
        table_frame = ttk.Frame(win, padding=10)
        table_frame.pack(fill="both", expand=True)

        # Table columns
        columns = ("Tipo", "Ubicación", "Archivo", "Modificado", "Tamaño")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)

        tree.heading("Tipo", text="Tipo")
        tree.heading("Ubicación", text="Ubicación")
        tree.heading("Archivo", text="Archivo")
        tree.heading("Modificado", text="Modificado")
        tree.heading("Tamaño", text="Tamaño")

        tree.column("Tipo", width=60, minwidth=50, anchor="center")
        tree.column("Ubicación", width=180, minwidth=120)
        tree.column("Archivo", width=350, minwidth=250)
        tree.column("Modificado", width=140, minwidth=100, anchor="center")
        tree.column("Tamaño", width=80, minwidth=60, anchor="e")

        # Scrollbars
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        # Initial populate
        apply_filter()

        # Double-click handler to open file location
        def on_double_click(event):
            selection = tree.selection()
            if not selection:
                return

            item = tree.item(selection[0])
            tags = item.get('tags', [])
            if tags:
                file_path = Path(tags[0])
                if file_path.exists():
                    try:
                        from utils.file.file_manager import FileManager
                        FileManager.open_file_location(file_path)
                    except Exception as e:
                        messagebox.showerror("Error", f"No se pudo abrir la ubicación: {e}")
                else:
                    messagebox.showwarning("Archivo no encontrado", f"El archivo ya no existe:\n{file_path}")

        tree.bind("<Double-1>", on_double_click)

        # Footer with buttons
        footer = ttk.Frame(win, padding=(10, 5, 10, 10))
        footer.pack(fill="x")

        def refresh_files():
            """Refresh file list."""
            nonlocal all_files
            all_files = get_files_from_stored_paths()
            apply_filter()

        ttk.Button(footer, text="Actualizar", command=refresh_files).pack(side="left")
        ttk.Button(footer, text="Cerrar", command=win.destroy).pack(side="right")

    def _open_history_file(self, doc_name: str, filename: str, version: str, state: str):
        """
        Open file location for a history entry.

        Searches in Working and Old folders, including timestamped backup folders.

        Args:
            doc_name: Document name
            filename: Filename from history entry
            version: Version string
            state: State string
        """
        from utils.file.file_manager import FileManager

        storage_path = self.get_storage_path()

        # Sanitize doc_name for filename matching (dashes become underscores)
        sanitized_name = doc_name.replace("-", "_").replace(" ", "_")

        # Get display_name for file matching (files are named with display_name)
        document = self.get_document_by_id(doc_name)
        display_name = getattr(document, 'display_name', '') or doc_name if document else doc_name
        sanitized_display_name = display_name.replace("-", "_").replace(" ", "_")

        # Build list of possible filenames
        possible_filenames = [filename] if filename else []

        # Add constructed filenames based on naming conventions
        # PDF: DOC_NAME_vX.Y_SZ.pdf (using both name and display_name)
        # DWG: DOC_NAME.dwg (stable name)
        possible_filenames.extend([
            f"{sanitized_name}_v{version}_{state}.pdf",
            f"{sanitized_name}.dwg",
            f"{sanitized_name}.rvt",
            f"{doc_name}_v{version}_{state}.pdf",
            f"{doc_name}.dwg",
            # Also add display_name variants
            f"{sanitized_display_name}_v{version}_{state}.pdf",
            f"{sanitized_display_name}.dwg",
            f"{sanitized_display_name}.rvt",
            f"{display_name}_v{version}_{state}.pdf",
            f"{display_name}.dwg",
        ])

        # Search paths for Working folders
        search_paths = []
        for fname in possible_filenames:
            if fname:
                search_paths.extend([
                    storage_path / "PDF" / "Working" / fname,
                    storage_path / "CAD" / "Working" / fname,
                    storage_path / "RVT" / "Working" / fname,
                ])

        # Search paths for Old folders (direct files)
        for fname in possible_filenames:
            if fname:
                search_paths.extend([
                    storage_path / "PDF" / "Old" / fname,
                    storage_path / "CAD" / "Old" / fname,
                    storage_path / "RVT" / "Old" / fname,
                ])

        # Try direct file paths first
        for file_path in search_paths:
            if file_path.exists() and file_path.is_file():
                try:
                    FileManager.open_file_location(file_path)
                    return
                except Exception as e:
                    print(f"Error opening file location: {e}")

        # Search in timestamped backup folders (CAD/Old/TIMESTAMP-NAME-vX.Y-SZ/)
        # Pattern: YYYYMMDDHHMM-DOC_NAME-vX.Y-SZ
        old_cad_folder = storage_path / "CAD" / "Old"
        if old_cad_folder.exists():
            # Look for folders matching this document
            for folder in old_cad_folder.iterdir():
                if folder.is_dir():
                    folder_name = folder.name
                    # Check if folder name contains our document name or display_name
                    matches_name = sanitized_name in folder_name or doc_name in folder_name
                    matches_display = sanitized_display_name in folder_name or display_name in folder_name
                    if matches_name or matches_display:
                        # Check if version/state match (if provided)
                        version_match = f"-v{version}-" in folder_name or f"-v{version}" in folder_name
                        state_match = f"-{state}" in folder_name or folder_name.endswith(f"-{state}")

                        if version_match or state_match or (not version and not state):
                            # Look for DWG files inside this folder
                            for dwg_file in folder.glob("*.dwg"):
                                try:
                                    FileManager.open_file_location(dwg_file)
                                    return
                                except Exception as e:
                                    print(f"Error opening file location: {e}")

        # Search in timestamped backup folders for RVT
        old_rvt_folder = storage_path / "RVT" / "Old"
        if old_rvt_folder.exists():
            for folder in old_rvt_folder.iterdir():
                if folder.is_dir():
                    folder_name = folder.name
                    matches_name = sanitized_name in folder_name or doc_name in folder_name
                    matches_display = sanitized_display_name in folder_name or display_name in folder_name
                    if matches_name or matches_display:
                        for rvt_file in folder.glob("*.rvt"):
                            try:
                                FileManager.open_file_location(rvt_file)
                                return
                            except Exception as e:
                                print(f"Error opening file location: {e}")

        # File not found - try using file service as last resort
        if self.controller and hasattr(self.controller, 'open_specific_file'):
            self.controller.open_specific_file(doc_name, filename)
        else:
            messagebox.showwarning(
                "Archivo no encontrado",
                f"No se encontró el archivo para: {doc_name}\n"
                f"Versión: {version}, Estado: {state}\n\n"
                f"El archivo puede haber sido movido o eliminado."
            )

    def annotate_selected_document(self, doc_name: str = None):
        """Annotate the selected document."""
        if doc_name:
            self._annotate_document_by_id(doc_name)
        else:
            messagebox.showwarning("Aviso", "Por favor seleccione un documento para anotar")

    def show_export_dialog(self):
        """Show export dialog for multiple documents."""
        # Export functionality - delegate to app if available
        if hasattr(self.app, 'show_export_dialog'):
            self.app.show_export_dialog()
        else:
            messagebox.showinfo("Info", "Exportación múltiple en desarrollo")

    def _get_current_files_wrapper(self, doc_name: str) -> list:
        """Wrapper that extracts files list from controller response."""
        if not self.controller:
            return []
        if hasattr(self.controller, 'get_document_files_info'):
            result = self.controller.get_document_files_info(doc_name)
            # Controller returns {'success': True, 'files': [...]} format
            if isinstance(result, dict):
                if result.get('success', False):
                    return result.get('files', [])
                return []
            # If it's already a list, return it directly
            if isinstance(result, list):
                return result
        return []

    def _replace_file_wrapper(self, doc_name: str, current_path: str, new_path: str):
        """Wrapper for replace file that returns (success, message) tuple."""
        if not self.controller:
            return False, "Controller not initialized"
        if hasattr(self.controller, 'replace_file_for_document'):
            from pathlib import Path
            # Controller expects Path object for new_path
            path_obj = Path(new_path) if isinstance(new_path, str) else new_path
            result = self.controller.replace_file_for_document(doc_name, current_path, path_obj)
            # Controller returns dict, convert to tuple
            if isinstance(result, dict):
                return result.get('success', False), result.get('message', 'Unknown error')
            return result
        return False, "Replace file not supported"

    def _add_file_wrapper(self, doc_name: str, file_path: str, file_type: str, dwg_name: str = None):
        """Wrapper for add file that returns (success, message) tuple."""
        if not self.controller:
            return False, "Controller not initialized"
        if hasattr(self.controller, 'add_file_to_document'):
            from pathlib import Path
            # Controller expects Path object
            path_obj = Path(file_path) if isinstance(file_path, str) else file_path
            result = self.controller.add_file_to_document(doc_name, path_obj, file_type, dwg_name)
            # Controller returns dict, convert to tuple
            if isinstance(result, dict):
                return result.get('success', False), result.get('message', 'Unknown error')
            return result
        return False, "Add file not supported"

    def show_edit_document_info_form(self, doc_name: str = None):
        """Show form to edit document information using CorrectionForm."""
        # Validate that we have a document name
        if not doc_name:
            messagebox.showwarning("Aviso", "Por favor seleccione un documento para editar")
            return

        # Verify document exists
        document = self.get_document_by_id(doc_name)
        if not document:
            messagebox.showerror("Error", f"No se encontró el documento: {doc_name}")
            return

        # Lazy import and create CorrectionForm
        from views.correction_form import CorrectionForm

        # Create form instance if not already created
        if not hasattr(self, '_correction_form') or self._correction_form is None:
            self._correction_form = CorrectionForm(
                self.app.root,
                "planos",
                self.get_state_map()
            )

        # Set up callbacks for the correction form
        callbacks = {
            'back': self._back_to_dashboard,
            'get_document': self._get_document_for_edit,
            'update_document_info': self._update_document_info,
            'navigate_to_document': self._navigate_to_document,
        }

        # Get current user
        user_name = ""
        if hasattr(self.app, 'user_config') and self.app.user_config:
            user_name = self.app.user_config.get_user_name()
        elif hasattr(self.app, 'get_current_user'):
            user_name = self.app.get_current_user()

        # Show the form with the pre-selected document
        self._correction_form.show(callbacks, user_name, pre_selected_document_name=doc_name)

    def _back_to_dashboard(self):
        """Navigate back to planos dashboard."""
        self.show_dashboard()

    def _get_document_for_edit(self, doc_name: str):
        """Get document object for editing."""
        return self.get_document_by_id(doc_name)

    def _navigate_to_document(self, doc_name: str):
        """Navigate to a specific document."""
        if hasattr(self.app, 'navigate_to_document'):
            self.app.navigate_to_document(doc_name)

    def _update_document_info(self, old_name: str, new_name: str, display_name: str,
                              version: str, state: str, author: str, notes: str,
                              autor: str = "", rev_tecnica: str = "", rev_gerencia: str = ""):
        """Update document information via controller."""
        if not self.controller:
            raise Exception("Controller not initialized")

        if not hasattr(self.controller, 'update_document_info'):
            raise Exception("Controller does not support update_document_info")

        return self.controller.update_document_info(
            old_name, new_name, display_name,
            version, state, author, notes,
            autor, rev_tecnica, rev_gerencia
        )
