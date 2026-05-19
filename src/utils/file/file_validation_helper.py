"""
File Validation Helper

Utility to validate file-to-database consistency and help diagnose file management issues.
This tool helps identify orphaned files, missing files, and naming pattern inconsistencies.
"""

import glob
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional
from utils.file_manager import FileManager


class FileValidationHelper:
    """Helper class for validating file-to-database consistency."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.file_manager = FileManager()

        # Lazy import controllers to avoid circular imports
        from controllers.sqlite_document_controller import SQLiteDocumentController
        from controllers.sqlite_planos_controller import SQLitePlanosController
        from controllers.sqlite_licitacion_controller import SQLiteLicitacionController
        from controllers.certificacion_controller import CertificacionController

        # Initialize controllers for different document types
        self.controllers = {
            "presupuestos": SQLiteDocumentController("presupuestos", "presupuestos", project_path),
            "planos": SQLitePlanosController(project_path),
            "licitaciones": SQLiteLicitacionController(project_path),
            "certificaciones": CertificacionController(project_path)
        }
    
    def validate_all_document_types(self) -> Dict[str, Any]:
        """Validate all document types and return comprehensive report."""
        report = {
            "summary": {"total_orphaned": 0, "total_missing": 0, "total_inconsistent": 0},
            "details": {}
        }
        
        for doc_type, controller in self.controllers.items():
            try:
                type_report = self.validate_document_type(doc_type, controller)
                report["details"][doc_type] = type_report
                report["summary"]["total_orphaned"] += len(type_report["orphaned_files"])
                report["summary"]["total_missing"] += len(type_report["missing_files"])
                report["summary"]["total_inconsistent"] += len(type_report["naming_inconsistencies"])
            except Exception as e:
                report["details"][doc_type] = {"error": str(e)}
        
        return report
    
    def validate_document_type(self, doc_type: str, controller) -> Dict[str, Any]:
        """Validate a specific document type."""
        report = {
            "orphaned_files": [],
            "missing_files": [],
            "naming_inconsistencies": [],
            "valid_files": [],
            "statistics": {}
        }
        
        # Get all documents from database
        try:
            documents = controller.get_all_documents()
        except Exception as e:
            return {"error": f"Could not retrieve documents: {e}"}
        
        # Get storage path
        storage_path = getattr(controller, 'storage_path', None)
        if not storage_path or not storage_path.exists():
            return {"error": "Storage path not found or inaccessible"}
        
        # Find all actual files in storage
        actual_files = self._get_all_files_in_directory(storage_path)
        
        # Track which files are accounted for
        accounted_files: Set[str] = set()
        
        # Check each document's expected files
        for doc in documents:
            expected_files = self._generate_expected_filenames(doc, doc_type)
            
            for expected_file in expected_files:
                matching_files = self._find_matching_files(actual_files, expected_file, doc.name)
                
                if matching_files:
                    # Found matching files
                    for match in matching_files:
                        accounted_files.add(match)
                        if self._validate_filename_pattern(match, doc, doc_type):
                            report["valid_files"].append({
                                "file": match,
                                "document": doc.name,
                                "pattern": "standard"
                            })
                        else:
                            report["naming_inconsistencies"].append({
                                "file": match,
                                "document": doc.name,
                                "expected_pattern": expected_file,
                                "issue": "pattern_mismatch"
                            })
                else:
                    # Missing file
                    report["missing_files"].append({
                        "document": doc.name,
                        "expected_file": expected_file,
                        "doc_id": doc.id
                    })
        
        # Find orphaned files (files without corresponding database records)
        for file_path in actual_files:
            if file_path not in accounted_files:
                report["orphaned_files"].append({
                    "file": file_path,
                    "reason": "no_matching_document"
                })
        
        # Generate statistics
        report["statistics"] = {
            "total_documents": len(documents),
            "total_files": len(actual_files),
            "valid_files": len(report["valid_files"]),
            "orphaned_files": len(report["orphaned_files"]),
            "missing_files": len(report["missing_files"]),
            "naming_issues": len(report["naming_inconsistencies"])
        }
        
        return report
    
    def _get_all_files_in_directory(self, directory: Path) -> List[str]:
        """Get all files in a directory (relative to directory)."""
        files = []
        if directory.exists():
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    files.append(file_path.name)
        return files
    
    def _generate_expected_filenames(self, document, doc_type: str) -> List[str]:
        """Generate list of expected filenames for a document based on its entries."""
        expected_files = []
        
        # Common extensions based on document type
        extensions = {
            "presupuestos": ["pdf", "xlsx", "xls"],
            "planos": ["pdf", "dwg", "rvt", "xlsx"],
            "licitaciones": ["pdf", "xlsx", "xls"],
            "certificaciones": ["pdf", "xlsx"]
        }
        
        doc_extensions = extensions.get(doc_type, ["pdf"])
        
        # Generate filenames for each entry
        for entry in document.entries:
            for ext in doc_extensions:
                # Standard FileManager pattern
                filename = self.file_manager.generate_filename(
                    document.id, document.name, entry.version, entry.state, f".{ext}"
                )
                expected_files.append(filename)
        
        return expected_files
    
    def _find_matching_files(self, actual_files: List[str], expected_file: str, doc_name: str) -> List[str]:
        """Find files that might match the expected file using various patterns."""
        matches = []
        
        # Exact match
        if expected_file in actual_files:
            matches.append(expected_file)
            return matches
        
        # Fuzzy matching patterns
        doc_name_sanitized = self.file_manager.sanitize_for_filename(doc_name)
        
        for file_name in actual_files:
            # Check if file contains document name
            if doc_name_sanitized.lower() in file_name.lower():
                matches.append(file_name)
            # Check if file starts with document ID
            elif file_name.startswith(doc_name[:10]):  # First 10 chars of doc name
                matches.append(file_name)
        
        return matches
    
    def _validate_filename_pattern(self, filename: str, document, doc_type: str) -> bool:
        """Validate if a filename follows the expected pattern."""
        # Parse filename to check if it follows FileManager pattern
        parts = Path(filename).stem.split('_')
        
        # Expected pattern: doc_id_name_version_state
        if len(parts) >= 4:
            # Check if doc_id matches
            if parts[0] == document.id:
                return True
        
        return False
    
    def generate_cleanup_script(self, validation_report: Dict[str, Any]) -> str:
        """Generate a cleanup script based on validation report."""
        script_lines = [
            "#!/bin/bash",
            "# File cleanup script generated by FileValidationHelper",
            "# Review this script carefully before executing!",
            "",
            "# Backup orphaned files before deletion",
            "mkdir -p orphaned_files_backup",
            ""
        ]
        
        # Add commands to move orphaned files
        for doc_type, report in validation_report["details"].items():
            if "orphaned_files" in report:
                script_lines.append(f"# Orphaned files for {doc_type}")
                for orphaned in report["orphaned_files"]:
                    filename = orphaned["file"]
                    script_lines.append(f"mv '{filename}' orphaned_files_backup/")
                script_lines.append("")
        
        return "\n".join(script_lines)
    
    def fix_naming_inconsistencies(self, doc_type: str, dry_run: bool = True) -> List[str]:
        """Attempt to fix naming inconsistencies. Returns list of actions taken."""
        actions = []
        controller = self.controllers.get(doc_type)
        if not controller:
            return [f"No controller found for document type: {doc_type}"]
        
        # Get validation report for this document type
        report = self.validate_document_type(doc_type, controller)
        
        storage_path = getattr(controller, 'storage_path', None)
        if not storage_path:
            return ["Storage path not found"]
        
        # Fix naming inconsistencies
        for inconsistency in report["naming_inconsistencies"]:
            current_file = inconsistency["file"]
            expected_file = inconsistency["expected_pattern"]
            
            current_path = storage_path / current_file
            expected_path = storage_path / expected_file
            
            if current_path.exists() and not expected_path.exists():
                action = f"Rename: {current_file} -> {expected_file}"
                if not dry_run:
                    try:
                        current_path.rename(expected_path)
                        action += " (COMPLETED)"
                    except Exception as e:
                        action += f" (FAILED: {e})"
                else:
                    action += " (DRY RUN)"
                
                actions.append(action)
        
        return actions


def run_validation_report(project_path: Path = None) -> Dict[str, Any]:
    """Convenience function to run a full validation report."""
    if not project_path:
        project_path = Path.cwd()
    
    validator = FileValidationHelper(project_path)
    return validator.validate_all_document_types()


if __name__ == "__main__":
    # Example usage
    report = run_validation_report()
    
    print("=== FILE VALIDATION REPORT ===")
    print(f"Total orphaned files: {report['summary']['total_orphaned']}")
    print(f"Total missing files: {report['summary']['total_missing']}")
    print(f"Total naming inconsistencies: {report['summary']['total_inconsistent']}")
    print()
    
    for doc_type, details in report["details"].items():
        if "error" in details:
            print(f"{doc_type}: ERROR - {details['error']}")
        else:
            stats = details["statistics"]
            print(f"{doc_type}: {stats['total_documents']} docs, {stats['total_files']} files, "
                  f"{stats['orphaned_files']} orphaned, {stats['missing_files']} missing")