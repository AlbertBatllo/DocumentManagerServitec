"""
Unified XREF Manager with Background Processing

Keeps the UI responsive by processing XREFs in background threads.
Uses the unified dwg_xref module (LibreDWG only).
"""

from pathlib import Path
from typing import List, Dict, Optional, Callable
import sqlite3
import json
import logging
import threading
import time
import queue
from datetime import datetime

# Import the unified XREF extractor
try:
    from .dwg_xref import extract_dwg_references, is_xref_extraction_available, get_xref_extractor_info
except ImportError:
    from dwg_xref import extract_dwg_references, is_xref_extraction_available, get_xref_extractor_info

logger = logging.getLogger(__name__)


class AsyncXrefManager:
    """
    Unified XREF manager with background processing to keep UI responsive.
    """
    
    def __init__(self, db_path: Path, progress_callback: Optional[Callable] = None):
        self.db_path = db_path
        self.progress_callback = progress_callback
        
        # Background processing
        self._processing_queue = queue.Queue()
        self._lock = threading.Lock()
        self._worker_thread = None
        self._stop_worker = False
        
        self._ensure_schema()
        self._start_background_worker()
    
    def _ensure_schema(self):
        """Ensure required database schema exists."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Check if we need to run migration
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='planos'")
                if not cursor.fetchone():
                    logger.info("XREF schema not found, running migration...")
                    from .xref_database_migration import XrefDatabaseMigration
                    migration = XrefDatabaseMigration(self.db_path)
                    migration.migrate_database()
                
                # Verify planos view exists now
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='planos'")
                if cursor.fetchone():
                    logger.info("XREF schema ready")
                else:
                    logger.error("XREF schema migration failed")
                
        except Exception as e:
            logger.error(f"Schema setup error: {e}")
    
    def _start_background_worker(self):
        """Start background thread for XREF processing."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_worker = False
            self._worker_thread = threading.Thread(target=self._background_worker, daemon=True)
            self._worker_thread.start()
            logger.info("Started background XREF processing worker")
    
    def _background_worker(self):
        """Background worker that processes XREF extraction queue."""
        while not self._stop_worker:
            try:
                # Get next job from queue (timeout to allow checking stop flag)
                try:
                    job = self._processing_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                plano_id = job['plano_id']
                file_path = job['file_path']
                
                try:
                    # Update status to processing
                    self._update_processing_status(plano_id, "processing")

                    if self.progress_callback:
                        self.progress_callback(f"🔍 Analyzing references in {file_path.name}...")

                    # Extract XREFs using LibreDWG
                    start_time = time.time()
                    references = extract_dwg_references(file_path)
                    method_used = "libredwg"
                    extraction_success = True
                    processing_time = time.time() - start_time
                    
                    # Store results in database
                    with sqlite3.connect(str(self.db_path)) as conn:
                        conn.execute(
                            '''UPDATE planos SET 
                               plano_type = "main", 
                               xref_references = ?, 
                               xref_processing_status = "completed",
                               xref_method_used = ?,
                               xref_last_processed = CURRENT_TIMESTAMP
                               WHERE id = ?''',
                            (json.dumps(references) if references else None, method_used, plano_id)
                        )
                    
                    if extraction_success:
                        logger.info(f"Processed XREF for plano {plano_id}: {len(references)} references in {processing_time:.2f}s using {method_used}")
                        
                        if self.progress_callback:
                            self.progress_callback(f"✅ Found {len(references)} references in {file_path.name} ({method_used})")
                    else:
                        logger.warning(f"XREF extraction partially failed for plano {plano_id} using {method_used}")
                        
                        if self.progress_callback:
                            self.progress_callback(f"⚠️ Partial extraction for {file_path.name} ({method_used})")
                
                except Exception as e:
                    # Mark as failed
                    self._update_processing_status(plano_id, f"failed: {str(e)}")
                    logger.error(f"XREF processing failed for plano {plano_id}: {e}")
                    
                    if self.progress_callback:
                        self.progress_callback(f"❌ Failed to process {file_path.name}: {e}")
                
                finally:
                    self._processing_queue.task_done()
            
            except Exception as e:
                logger.error(f"Background worker error: {e}")
                time.sleep(1)
    
    def _update_processing_status(self, plano_id: int, status: str):
        """Update the processing status for a plano."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                'UPDATE planos SET xref_processing_status = ? WHERE id = ?',
                (status, plano_id)
            )
    
    def process_plano_upload(self, plano_id: int, file_path: Path) -> Dict:
        """
        Process plano upload with background XREF handling.
        
        Returns immediately for UI responsiveness. XREF processing happens in background.
        """
        filename = file_path.name
        
        result = {
            'plano_id': plano_id,
            'filename': filename,
            'is_reference': filename.startswith('X_'),
            'action_taken': None,
            'background_processing': False,
            'missing_references_resolved': 0
        }
        
        try:
            if filename.startswith('X_'):
                # Reference file - immediate processing (fast)
                self._mark_as_xref(plano_id)
                resolved_count = self._resolve_missing_references(plano_id, filename)
                
                result['action_taken'] = 'marked_as_xref'
                result['missing_references_resolved'] = resolved_count
                
                logger.info(f"Processed XREF file: {filename}, resolved {resolved_count} missing references")
            
            else:
                # Main file - queue for background processing
                self._mark_as_main_pending(plano_id)
                self._queue_for_background_processing(plano_id, file_path)
                
                result['action_taken'] = 'queued_for_processing'
                result['background_processing'] = True
                
                logger.info(f"Queued main file for background processing: {filename}")
        
        except Exception as e:
            logger.error(f"Error processing plano upload {plano_id}: {e}")
            result['error'] = str(e)
        
        return result
    
    def _mark_as_xref(self, plano_id: int):
        """Mark plano as XREF type."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                '''UPDATE planos SET 
                   plano_type = "xref", 
                   xref_processing_status = "completed",
                   xref_method_used = "filename_classification",
                   xref_last_processed = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (plano_id,)
            )
    
    def _mark_as_main_pending(self, plano_id: int):
        """Mark plano as main type with pending processing."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                'UPDATE planos SET plano_type = "main", xref_processing_status = "queued" WHERE id = ?',
                (plano_id,)
            )
    
    def _queue_for_background_processing(self, plano_id: int, file_path: Path):
        """Queue a main plano for background XREF processing."""
        job = {
            'plano_id': plano_id,
            'file_path': file_path
        }
        self._processing_queue.put(job)
    
    def _resolve_missing_references(self, xref_plano_id: int, filename: str) -> int:
        """Resolve missing references when an XREF file is uploaded."""
        resolved_count = 0
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Find all main planos that reference this filename
                cursor = conn.execute(
                    'SELECT id, xref_references FROM planos WHERE plano_type = "main" AND xref_references IS NOT NULL'
                )
                
                for plano_id, xref_references_json in cursor.fetchall():
                    if xref_references_json:
                        try:
                            references = json.loads(xref_references_json)
                            if filename in references:
                                resolved_count += 1
                        except (json.JSONDecodeError, TypeError):
                            continue
        
        except Exception as e:
            logger.error(f"Error resolving missing references: {e}")
        
        return resolved_count
    
    def get_processing_status(self, plano_id: int) -> Dict:
        """Get the current processing status of a plano."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    'SELECT name, plano_type, xref_processing_status, xref_references FROM planos WHERE id = ?',
                    (plano_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return {'error': 'Plano not found'}
                
                name, plano_type, processing_status, xref_references = row
                
                result = {
                    'plano_id': plano_id,
                    'name': name,
                    'plano_type': plano_type,
                    'processing_status': processing_status,
                    'references_count': 0,
                    'is_processing_complete': processing_status == 'completed'
                }
                
                if xref_references:
                    try:
                        refs = json.loads(xref_references)
                        result['references_count'] = len(refs)
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                return result
        
        except Exception as e:
            logger.error(f"Error getting processing status: {e}")
            return {'error': str(e)}
    
    def get_queue_status(self) -> Dict:
        """Get current background processing queue status."""
        return {
            'queue_size': self._processing_queue.qsize(),
            'worker_alive': self._worker_thread.is_alive() if self._worker_thread else False,
            'worker_thread_name': self._worker_thread.name if self._worker_thread else None
        }
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all queued processing to complete."""
        try:
            if timeout is None:
                self._processing_queue.join()
                return True
            else:
                # Poor man's timeout for queue.join()
                start_time = time.time()
                while not self._processing_queue.empty():
                    if time.time() - start_time > timeout:
                        return False
                    time.sleep(0.1)
                return True
        except Exception as e:
            logger.error(f"Error waiting for completion: {e}")
            return False
    
    def get_extraction_capabilities(self) -> Dict:
        """Get information about available XREF extraction methods."""
        return get_xref_extractor_info()

    def process_unprocessed_documents(self, storage_path: Path) -> Dict:
        """
        Scan and process all documents that haven't been XREF-processed yet.

        This is called on project load to handle existing documents that
        were created before XREF processing was added.

        Args:
            storage_path: Path to the project's 02_Planos folder

        Returns:
            Dict with processing statistics
        """
        stats = {
            'scanned': 0,
            'queued': 0,
            'skipped_no_dwg': 0,
            'skipped_already_processed': 0,
            'errors': 0
        }

        if not is_xref_extraction_available():
            logger.warning("XREF extraction not available - skipping bulk processing")
            return stats

        try:
            # Phase 1: Collect unprocessed documents (quick DB read)
            # Include both NULL (never processed) and 'queued' (interrupted processing)
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute('''
                    SELECT id, name, associated_dwg
                    FROM documents
                    WHERE document_type = 'planos'
                      AND (xref_processing_status IS NULL OR xref_processing_status = 'queued')
                ''')
                unprocessed = cursor.fetchall()
                stats['scanned'] = len(unprocessed)

            if not unprocessed:
                logger.info("No unprocessed documents found")
                return stats

            logger.info(f"Found {len(unprocessed)} unprocessed documents")

            # Phase 2: Find DWG files and categorize (no DB connection held)
            cad_working = storage_path / "CAD" / "Working"
            to_queue = []  # (plano_id, dwg_path)
            no_dwg_ids = []  # plano_ids with no DWG

            for plano_id, name, associated_dwg in unprocessed:
                try:
                    dwg_path = None

                    # First check associated_dwg
                    if associated_dwg:
                        potential_path = cad_working / associated_dwg
                        if potential_path.exists():
                            dwg_path = potential_path

                    # Fallback: search by document name
                    if not dwg_path and cad_working.exists():
                        for pattern in [f"{name}.dwg", f"{name.replace('-', '_')}.dwg"]:
                            potential = cad_working / pattern
                            if potential.exists():
                                dwg_path = potential
                                break

                        if not dwg_path:
                            sanitized = name.replace("-", "_").replace(" ", "_")
                            for dwg_file in cad_working.glob("*.dwg"):
                                if sanitized in dwg_file.stem or name in dwg_file.stem:
                                    dwg_path = dwg_file
                                    break

                    if dwg_path and dwg_path.exists():
                        to_queue.append((plano_id, dwg_path))
                    else:
                        no_dwg_ids.append(plano_id)

                except Exception as e:
                    logger.error(f"Error finding DWG for {name}: {e}")
                    stats['errors'] += 1

            # Phase 3: Update DB for documents without DWG (batch update)
            if no_dwg_ids:
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.executemany('''
                        UPDATE documents SET
                            xref_processing_status = 'completed',
                            xref_references = NULL,
                            xref_last_processed = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', [(pid,) for pid in no_dwg_ids])
                    conn.commit()
                stats['skipped_no_dwg'] = len(no_dwg_ids)

            # Phase 4: Queue documents with DWG for background processing
            for plano_id, dwg_path in to_queue:
                self._mark_as_main_pending(plano_id)
                self._queue_for_background_processing(plano_id, dwg_path)
                stats['queued'] += 1

            logger.info(f"Bulk XREF processing: queued={stats['queued']}, no_dwg={stats['skipped_no_dwg']}")

            if self.progress_callback and stats['queued'] > 0:
                self.progress_callback(f"⏳ Procesando {stats['queued']} archivos DWG...")

        except Exception as e:
            logger.error(f"Bulk XREF processing failed: {e}")
            stats['errors'] += 1

        return stats

    def shutdown(self):
        """Shutdown the background worker gracefully."""
        self._stop_worker = True
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
            logger.info("Background XREF worker stopped")


def demo_async_workflow():
    """Demo the async XREF workflow."""
    print("🚀 Async XREF Manager Demo")
    print("=" * 40)
    
    def progress_callback(message):
        print(f"📱 UI Update: {message}")
    
    # Create temp database
    db_path = Path("test_async.db")
    if db_path.exists():
        db_path.unlink()
    
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute('''
            CREATE TABLE planos (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        ''')
    
    manager = AsyncXrefManager(db_path, progress_callback)
    
    try:
        # Simulate uploads
        uploads = [
            {"id": 1, "name": "04_PLANTAS_ESTADO_REFORMADO.dwg"},
            {"id": 2, "name": "X_P1_ER.dwg"},
        ]
        
        # Insert test data
        with sqlite3.connect(str(db_path)) as conn:
            for upload in uploads:
                conn.execute('INSERT INTO planos (id, name) VALUES (?, ?)', 
                           (upload["id"], upload["name"]))
        
        # Process uploads
        for upload in uploads:
            file_path = Path(f"planos_prueba/{upload['name']}")  # Real test file
            if not file_path.exists():
                file_path = Path(f"test/{upload['name']}")  # Fallback
            
            print(f"\n📤 Upload: {upload['name']}")
            result = manager.process_plano_upload(upload["id"], file_path)
            
            print(f"   🏷️  Type: {'XREF' if result['is_reference'] else 'MAIN'}")
            print(f"   ⚡ Action: {result['action_taken']}")
            
            if result['background_processing']:
                print(f"   🔄 Background processing started...")
        
        # Show queue status
        queue_status = manager.get_queue_status()
        print(f"\n📊 Queue Status: {queue_status['queue_size']} items, worker alive: {queue_status['worker_alive']}")
        
        # Wait a moment for background processing
        print("\n⏳ Waiting for background processing to complete...")
        completed = manager.wait_for_completion(timeout=5.0)
        
        if completed:
            print("✅ All processing completed!")
        else:
            print("⏰ Processing still running (demo timeout reached)")
        
        # Show final status
        for upload in uploads:
            status = manager.get_processing_status(upload["id"])
            print(f"   {upload['name']}: {status['processing_status']} ({status['references_count']} refs)")
    
    finally:
        manager.shutdown()
        db_path.unlink()


if __name__ == "__main__":
    demo_async_workflow()