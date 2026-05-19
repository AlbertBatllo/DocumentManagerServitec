"""
Unified XREF Manager - Single Database, Simple Resolution

Uses main documents.db only with JSON storage and ID-based resolution.
No caching, no separate databases, clean and simple.
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple
import sqlite3
import json
import logging
from datetime import datetime

try:
    from .dwg_xref import extract_dwg_references
except ImportError:
    # For standalone testing
    from dwg_xref import extract_dwg_references

logger = logging.getLogger(__name__)


class UnifiedXrefManager:
    """
    Unified XREF manager using single database with JSON storage.
    
    Database schema additions:
    - planos.plano_type: "main" or "xref"  
    - planos.xref_references: JSON array of reference filenames
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()
    
    def _ensure_schema(self):
        """Ensure required database schema exists."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Add plano_type column if not exists
                try:
                    conn.execute('ALTER TABLE planos ADD COLUMN plano_type TEXT DEFAULT "main"')
                    logger.info("Added plano_type column")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                # Add xref_references column if not exists
                try:
                    conn.execute('ALTER TABLE planos ADD COLUMN xref_references TEXT DEFAULT NULL')
                    logger.info("Added xref_references column")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                # Optional: Create index for faster lookups
                try:
                    conn.execute('CREATE INDEX IF NOT EXISTS idx_planos_type ON planos(plano_type)')
                    conn.execute('CREATE INDEX IF NOT EXISTS idx_planos_name_type ON planos(name, plano_type)')
                except sqlite3.OperationalError:
                    pass
                
        except Exception as e:
            logger.error(f"Schema setup error: {e}")
    
    def process_plano_upload(self, plano_id: int, file_path: Path) -> Dict:
        """
        Process plano upload with unified XREF handling.
        
        Args:
            plano_id: Database ID of the uploaded plano
            file_path: Path to the uploaded DWG file
            
        Returns:
            Processing results dictionary
        """
        filename = file_path.name
        
        result = {
            'plano_id': plano_id,
            'filename': filename,
            'is_reference': filename.startswith('X_'),
            'action_taken': None,
            'references_found': [],
            'references_resolved_count': 0,
            'missing_references_resolved': 0
        }
        
        try:
            if filename.startswith('X_'):
                # Reference file - mark as XREF and resolve missing references
                self._mark_as_xref(plano_id)
                resolved_count = self._resolve_missing_references(plano_id, filename)
                
                result['action_taken'] = 'marked_as_xref'
                result['missing_references_resolved'] = resolved_count
                
                logger.info(f"Processed XREF file: {filename}, resolved {resolved_count} missing references")
            
            else:
                # Main file - extract references and store
                references = self._extract_and_store_references(plano_id, file_path)
                resolved_count = self._count_resolved_references(references)
                
                result['action_taken'] = 'processed_main_file'
                result['references_found'] = references
                result['references_resolved_count'] = resolved_count
                
                logger.info(f"Processed main file: {filename}, found {len(references)} references, {resolved_count} resolved")
        
        except Exception as e:
            logger.error(f"Error processing plano upload {plano_id}: {e}")
            result['error'] = str(e)
        
        return result
    
    def _mark_as_xref(self, plano_id: int):
        """Mark plano as XREF type."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                'UPDATE planos SET plano_type = "xref" WHERE id = ?',
                (plano_id,)
            )
    
    def _extract_and_store_references(self, plano_id: int, file_path: Path) -> List[str]:
        """Extract XREF references from DWG and store in database."""
        try:
            # Extract references using simple extractor
            references = extract_dwg_references(file_path)
            
            # Store in database as JSON
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    'UPDATE planos SET plano_type = "main", xref_references = ? WHERE id = ?',
                    (json.dumps(references) if references else None, plano_id)
                )
            
            return references
        
        except Exception as e:
            logger.error(f"Failed to extract/store references for {file_path}: {e}")
            return []
    
    def _resolve_missing_references(self, xref_plano_id: int, filename: str) -> int:
        """
        Resolve missing references when an XREF file is uploaded.
        
        Updates all main planos that reference this filename to include the plano_id.
        """
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
                            
                            # Check if this plano references the uploaded XREF file
                            if filename in references:
                                # This could be used for detailed tracking if needed
                                # For now, we just count the resolution
                                resolved_count += 1
                        
                        except (json.JSONDecodeError, TypeError):
                            continue
        
        except Exception as e:
            logger.error(f"Error resolving missing references: {e}")
        
        return resolved_count
    
    def _count_resolved_references(self, references: List[str]) -> int:
        """Count how many of the references are already uploaded."""
        if not references:
            return 0

        resolved_count = 0

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                for ref_name in references:
                    # Try both with and without .dwg extension for compatibility
                    ref_name_without_ext = ref_name.replace('.dwg', '').replace('.DWG', '')

                    cursor = conn.execute(
                        '''SELECT COUNT(*) FROM planos
                           WHERE (name = ? OR name = ? OR name = ?)
                           AND plano_type = "xref"''',
                        (ref_name, ref_name_without_ext, ref_name_without_ext + '.dwg')
                    )
                    if cursor.fetchone()[0] > 0:
                        resolved_count += 1

        except Exception as e:
            logger.error(f"Error counting resolved references: {e}")

        return resolved_count
    
    def get_plano_references(self, plano_id: int) -> Dict:
        """
        Get detailed reference information for a plano.
        
        Returns:
            Dictionary with reference details and resolution status
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    'SELECT name, plano_type, xref_references FROM planos WHERE id = ?',
                    (plano_id,)
                )
                plano_data = cursor.fetchone()
                
                if not plano_data:
                    return {'error': 'Plano not found'}
                
                name, plano_type, xref_references_json = plano_data
                
                result = {
                    'plano_id': plano_id,
                    'name': name,
                    'plano_type': plano_type,
                    'references': [],
                    'referenced_by': []
                }
                
                if plano_type == 'main' and xref_references_json:
                    # Get references this plano uses
                    try:
                        references = json.loads(xref_references_json)
                        
                        for ref_name in references:
                            # Check if reference is resolved
                            # Try both with and without .dwg extension for compatibility
                            ref_name_without_ext = ref_name.replace('.dwg', '').replace('.DWG', '')

                            cursor = conn.execute(
                                '''SELECT id, name FROM planos
                                   WHERE (name = ? OR name = ? OR name = ?)
                                   AND plano_type = "xref"''',
                                (ref_name, ref_name_without_ext, ref_name_without_ext + '.dwg')
                            )
                            ref_plano = cursor.fetchone()

                            result['references'].append({
                                'reference_name': ref_name,
                                'status': 'found' if ref_plano else 'missing',
                                'reference_plano_id': ref_plano[0] if ref_plano else None
                            })
                    
                    except (json.JSONDecodeError, TypeError):
                        result['error'] = 'Invalid references data'
                
                elif plano_type == 'xref':
                    # Find planos that reference this one
                    cursor = conn.execute(
                        'SELECT id, name, xref_references FROM planos WHERE plano_type = "main" AND xref_references IS NOT NULL'
                    )
                    
                    for main_id, main_name, main_refs_json in cursor.fetchall():
                        if main_refs_json:
                            try:
                                main_refs = json.loads(main_refs_json)
                                if name in main_refs:
                                    result['referenced_by'].append({
                                        'main_plano_id': main_id,
                                        'main_plano_name': main_name
                                    })
                            except (json.JSONDecodeError, TypeError):
                                continue
                
                return result
        
        except Exception as e:
            logger.error(f"Error getting plano references: {e}")
            return {'error': str(e)}
    
    def get_project_xref_summary(self) -> Dict:
        """Get project-wide XREF summary statistics."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                stats = {}
                
                # Count by type
                cursor = conn.execute(
                    'SELECT plano_type, COUNT(*) FROM planos GROUP BY plano_type'
                )
                stats['plano_counts'] = dict(cursor.fetchall())
                
                # Count total references and missing references
                cursor = conn.execute(
                    'SELECT xref_references FROM planos WHERE plano_type = "main" AND xref_references IS NOT NULL'
                )
                
                total_refs = 0
                missing_refs = 0
                all_references = []
                
                for (xref_refs_json,) in cursor.fetchall():
                    if xref_refs_json:
                        try:
                            refs = json.loads(xref_refs_json)
                            total_refs += len(refs)
                            all_references.extend(refs)
                            
                            # Check which are missing
                            for ref in refs:
                                # Try both with and without .dwg extension
                                ref_without_ext = ref.replace('.dwg', '').replace('.DWG', '')
                                cursor_check = conn.execute(
                                    '''SELECT COUNT(*) FROM planos
                                       WHERE (name = ? OR name = ? OR name = ?)
                                       AND plano_type = "xref"''',
                                    (ref, ref_without_ext, ref_without_ext + '.dwg')
                                )
                                if cursor_check.fetchone()[0] == 0:
                                    missing_refs += 1
                        
                        except (json.JSONDecodeError, TypeError):
                            continue
                
                stats['total_references'] = total_refs
                stats['resolved_references'] = total_refs - missing_refs
                stats['missing_references'] = missing_refs
                
                # Most used XREFs
                from collections import Counter
                if all_references:
                    most_used = Counter(all_references).most_common(5)
                    stats['most_used_xrefs'] = [{'name': name, 'count': count} for name, count in most_used]
                else:
                    stats['most_used_xrefs'] = []
                
                return stats
        
        except Exception as e:
            logger.error(f"Error getting project XREF summary: {e}")
            return {'error': str(e)}
    
    def get_missing_references(self) -> List[Dict]:
        """Get all missing XREF references in the project."""
        missing = []
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    'SELECT id, name, xref_references FROM planos WHERE plano_type = "main" AND xref_references IS NOT NULL'
                )
                
                for plano_id, plano_name, xref_refs_json in cursor.fetchall():
                    if xref_refs_json:
                        try:
                            references = json.loads(xref_refs_json)
                            
                            for ref_name in references:
                                # Check if reference exists (try both with and without .dwg)
                                ref_without_ext = ref_name.replace('.dwg', '').replace('.DWG', '')
                                cursor_check = conn.execute(
                                    '''SELECT COUNT(*) FROM planos
                                       WHERE (name = ? OR name = ? OR name = ?)
                                       AND plano_type = "xref"''',
                                    (ref_name, ref_without_ext, ref_without_ext + '.dwg')
                                )

                                if cursor_check.fetchone()[0] == 0:
                                    missing.append({
                                        'main_plano_id': plano_id,
                                        'main_plano_name': plano_name,
                                        'missing_reference': ref_name
                                    })
                        
                        except (json.JSONDecodeError, TypeError):
                            continue
        
        except Exception as e:
            logger.error(f"Error getting missing references: {e}")
        
        return missing


def demo_unified_workflow():
    """Demo the unified XREF workflow."""
    print("🚀 Unified XREF Manager Demo")
    print("=" * 40)
    
    # Use existing database or create temp one
    db_path = Path("documents.db")
    if not db_path.exists():
        # Create minimal test database
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute('''
                CREATE TABLE planos (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            ''')
            print("Created test database")
    
    manager = UnifiedXrefManager(db_path)
    
    # Simulate plano uploads
    test_uploads = [
        {"id": 1, "name": "04_PLANTAS_ESTADO_REFORMADO.dwg", "refs": ["X_P1_ER.dwg", "X_PB_PS_ER.dwg"]},
        {"id": 2, "name": "X_P1_ER.dwg", "refs": []},
        {"id": 3, "name": "X_PB_PS_ER.dwg", "refs": []},
    ]
    
    # Insert test data
    with sqlite3.connect(str(db_path)) as conn:
        for upload in test_uploads:
            conn.execute('INSERT OR REPLACE INTO planos (id, name) VALUES (?, ?)', 
                        (upload["id"], upload["name"]))
    
    # Process each upload
    for upload in test_uploads:
        # Simulate file path
        file_path = Path(f"test/{upload['name']}")
        
        # Process upload (would extract XREFs from real file)
        print(f"\n📤 Processing: {upload['name']}")
        
        # For demo, manually set references for main files
        if not upload["name"].startswith("X_") and upload["refs"]:
            # Manually store references for demo
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    'UPDATE planos SET plano_type = "main", xref_references = ? WHERE id = ?',
                    (json.dumps(upload["refs"]), upload["id"])
                )
            print(f"   📋 References: {upload['refs']}")
        else:
            result = manager.process_plano_upload(upload["id"], file_path)
            print(f"   🏷️  Type: {'XREF' if result['is_reference'] else 'MAIN'}")
            print(f"   ⚡ Action: {result['action_taken']}")
    
    # Show project summary
    print(f"\n📊 Project Summary:")
    summary = manager.get_project_xref_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")
    
    # Show missing references
    missing = manager.get_missing_references()
    if missing:
        print(f"\n⚠️  Missing References:")
        for miss in missing:
            print(f"   {miss['main_plano_name']} needs {miss['missing_reference']}")
    else:
        print(f"\n✅ All references resolved!")


if __name__ == "__main__":
    demo_unified_workflow()