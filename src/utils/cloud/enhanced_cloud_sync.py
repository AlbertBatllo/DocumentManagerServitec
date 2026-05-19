"""
Enhanced Cloud Sync Manager
Extends the basic cloud sync with version management and cleanup.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone

from .cloud_version_manager import CloudVersionManager, CloudFile


class EnhancedCloudSyncManager:
    """Enhanced cloud sync with automatic version cleanup"""
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        self.version_manager = CloudVersionManager(cloud_config)
        self._token_refresh_manager = None
    
    def should_sync_to_sharepoint(self, document_state: str) -> bool:
        """Check if document should be synced to SharePoint (S2 and S3 states)"""
        return (self.cloud_config.is_sharepoint_enabled() and 
                document_state in ["S2", "S3"])
    
    def should_sync_to_drive(self, document_state: str) -> bool:
        """Check if document should be synced to Google Drive (S3 and S3A states)"""
        return (self.cloud_config.is_google_drive_enabled() and 
                document_state in ["S3", "S3A"])
    
    def sync_document_with_cleanup(self, document, file_path: Path, auto_cleanup: bool = True):
        """
        Sync document to cloud and automatically clean up old versions.
        This is the main method to use instead of the basic sync_document.
        """
        if not self.cloud_config.is_cloud_sync_enabled():
            return {"message": "Cloud sync disabled"}
        
        # Only sync PDF files
        if not file_path.suffix.lower() == '.pdf':
            return {"message": f"Skipping non-PDF file: {file_path.name}"}
        
        document_state = document.current_state
        results = {
            "uploaded_to": [],
            "cleanup_results": {},
            "errors": []
        }
        
        try:
            # Upload to SharePoint (S2, S3, or A)
            if self.should_sync_to_sharepoint(document_state):
                if not self._is_sharepoint_authenticated():
                    raise RuntimeError("SharePoint authentication required")

                upload_result = self._upload_to_sharepoint(document, file_path)
                if upload_result["success"]:
                    results["uploaded_to"].append("SharePoint")

                    # Auto-cleanup old versions if requested
                    if auto_cleanup:
                        from .simple_cloud_cleanup import SimpleCloudCleanup
                        simple_cleanup = SimpleCloudCleanup(self.cloud_config)
                        uploaded_filename = upload_result.get("filename", document.filename)
                        cleanup_result = simple_cleanup.cleanup_after_upload(
                            uploaded_filename, "sharepoint"
                        )
                        results["cleanup_results"]["sharepoint"] = cleanup_result
                else:
                    results["errors"].append(f"SharePoint upload failed: {upload_result.get('error', 'Unknown error')}")
            
            # Upload to Google Drive (A only)
            if self.should_sync_to_drive(document_state):
                if not self._is_drive_authenticated():
                    raise RuntimeError("Google Drive authentication required")

                upload_result = self._upload_to_drive(document, file_path)
                if upload_result["success"]:
                    results["uploaded_to"].append("Google Drive")

                    # Auto-cleanup old versions if requested
                    if auto_cleanup:
                        from .simple_cloud_cleanup import SimpleCloudCleanup
                        simple_cleanup = SimpleCloudCleanup(self.cloud_config)
                        uploaded_filename = upload_result.get("filename", document.filename)
                        cleanup_result = simple_cleanup.cleanup_after_upload(
                            uploaded_filename, "google_drive"
                        )
                        results["cleanup_results"]["google_drive"] = cleanup_result
                else:
                    results["errors"].append(f"Google Drive upload failed: {upload_result.get('error', 'Unknown error')}")
            
            return results

        except Exception as e:
            results["errors"].append(str(e))
            return results

    def sync_multiple_files(self, document, file_paths: List[Path], auto_cleanup: bool = True):
        """
        Sync multiple PDF files to cloud for a single document.

        This handles the case where a document entry has multiple associated PDFs
        (e.g., numbered copies like _v1.0_S1.pdf, _v1.0_S1 1.pdf, _v1.0_S1 2.pdf).

        All files are uploaded, then cleanup runs ONCE after all uploads complete.

        Args:
            document: The document object
            file_paths: List of PDF file paths to upload
            auto_cleanup: Whether to clean up old versions after upload

        Returns:
            dict: Combined results from all uploads
        """
        if not self.cloud_config.is_cloud_sync_enabled():
            return {"message": "Cloud sync disabled"}

        # Filter to only PDF files
        pdf_paths = [p for p in file_paths if p.suffix.lower() == '.pdf']
        if not pdf_paths:
            return {"message": "No PDF files to sync"}

        document_state = document.current_state
        results = {
            "uploaded_to": [],
            "uploaded_files": [],
            "cleanup_results": {},
            "errors": []
        }

        # Track which files were uploaded to which service
        sharepoint_uploaded = []
        drive_uploaded = []

        try:
            # Upload ALL files to SharePoint (S2, S3)
            if self.should_sync_to_sharepoint(document_state):
                if not self._is_sharepoint_authenticated():
                    raise RuntimeError("SharePoint authentication required")

                for file_path in pdf_paths:
                    upload_result = self._upload_to_sharepoint(document, file_path)
                    if upload_result["success"]:
                        sharepoint_uploaded.append(upload_result.get("filename", file_path.name))
                        print(f"[SharePoint] ✓ Uploaded: {file_path.name}")
                    else:
                        results["errors"].append(
                            f"SharePoint upload failed for {file_path.name}: "
                            f"{upload_result.get('error', 'Unknown error')}"
                        )

                if sharepoint_uploaded:
                    results["uploaded_to"].append("SharePoint")
                    results["uploaded_files"].extend(sharepoint_uploaded)

            # Upload ALL files to Google Drive (S3, S3A)
            if self.should_sync_to_drive(document_state):
                if not self._is_drive_authenticated():
                    raise RuntimeError("Google Drive authentication required")

                for file_path in pdf_paths:
                    upload_result = self._upload_to_drive(document, file_path)
                    if upload_result["success"]:
                        drive_uploaded.append(upload_result.get("filename", file_path.name))
                        print(f"[Google Drive] ✓ Uploaded: {file_path.name}")
                    else:
                        results["errors"].append(
                            f"Google Drive upload failed for {file_path.name}: "
                            f"{upload_result.get('error', 'Unknown error')}"
                        )

                if drive_uploaded:
                    if "Google Drive" not in results["uploaded_to"]:
                        results["uploaded_to"].append("Google Drive")
                    # Only add filenames not already in list
                    for f in drive_uploaded:
                        if f not in results["uploaded_files"]:
                            results["uploaded_files"].append(f)

            # Run cleanup ONCE after all uploads, passing ALL uploaded filenames
            # (cleanup deletes old versions but preserves all just-uploaded files)
            if auto_cleanup:
                from .simple_cloud_cleanup import SimpleCloudCleanup
                simple_cleanup = SimpleCloudCleanup(self.cloud_config)

                if sharepoint_uploaded:
                    cleanup_result = simple_cleanup.cleanup_after_upload(
                        sharepoint_uploaded, "sharepoint"  # Pass full list
                    )
                    results["cleanup_results"]["sharepoint"] = cleanup_result

                if drive_uploaded:
                    cleanup_result = simple_cleanup.cleanup_after_upload(
                        drive_uploaded, "google_drive"  # Pass full list
                    )
                    results["cleanup_results"]["google_drive"] = cleanup_result

            return results

        except Exception as e:
            results["errors"].append(str(e))
            return results

    def manual_cleanup_all(self, dry_run: bool = True) -> Dict[str, any]:
        """
        Manually trigger cleanup of all documents in both cloud services.
        Use dry_run=True to preview what would be deleted.
        """
        return self.version_manager.cleanup_all_versions(dry_run=dry_run)
    
    def manual_cleanup_document(self, document_id: str, dry_run: bool = True) -> Dict[str, any]:
        """
        Manually trigger cleanup for a specific document.
        Use dry_run=True to preview what would be deleted.
        """
        return self.version_manager.cleanup_all_versions(document_id, dry_run=dry_run)
    
    def get_cleanup_preview(self, document_id: str = None) -> Dict[str, any]:
        """Get a preview of what files would be deleted without actually deleting them"""
        return self.version_manager.cleanup_all_versions(document_id, dry_run=True)
    
    def _upload_to_sharepoint(self, document, file_path: Path) -> Dict[str, any]:
        """Upload file to SharePoint with proper error handling"""
        try:
            from .sharepoint_upload import SharePointUploader
            from .conflict_resolver import ConflictResolver, ConflictStrategy

            # Use the ACTUAL filename from file_path (not document.filename)
            # This ensures multiple PDFs (e.g., _S1.pdf, _S1 1.pdf, _S1 2.pdf) are uploaded correctly
            filename = file_path.name
            
            # Initialize uploader and resolver
            uploader = SharePointUploader(self.cloud_config)
            resolver = ConflictResolver(ConflictStrategy.OVERWRITE)  # Default to overwrite for auto-sync
            
            # Get SharePoint config
            config = self.cloud_config.get_sharepoint_config()
            # For SharePoint, the base folder is already configured in the uploader
            # We pass empty folder_path to avoid duplication
            folder_path = ""
            
            # Check for conflicts
            exists, cloud_metadata = uploader.check_file_exists(filename, folder_path)
            conflict_strategy = "overwrite"  # Default strategy
            
            if exists:
                conflict_info = resolver.detect_conflict(file_path, cloud_metadata)
                if conflict_info.get("has_conflict"):
                    resolution = resolver.resolve_conflict(conflict_info)
                    
                    if resolution["action"] == "skip":
                        return {
                            "success": True,
                            "skipped": True,
                            "filename": filename,
                            "service": "SharePoint",
                            "message": f"Skipped due to conflict: {resolution['reason']}"
                        }
                    elif resolution["action"] == "rename":
                        filename = resolution["new_filename"]
                        conflict_strategy = "rename"
            
            # Upload file
            print(f"[SharePoint] Uploading: {filename}")
            print(f"[SharePoint] Source: {file_path}")
            print(f"[SharePoint] Document: {document.id} v{document.version} (state {document.current_state})")
            
            result = uploader.upload_file(file_path, filename, folder_path, conflict_strategy)
            
            if result.get("success"):
                return {
                    "success": True,
                    "filename": filename,
                    "service": "SharePoint",
                    "file_id": result.get("file_id"),
                    "web_url": result.get("web_url"),
                    "upload_method": result.get("upload_method")
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "service": "SharePoint"
                }
            
        except ImportError as e:
            # Fallback to simulation if libraries not available
            print(f"[SharePoint] Libraries not available, simulating upload: {e}")
            filename = self._generate_cloud_filename(document)
            print(f"[SharePoint] Would upload: {filename}")
            return {
                "success": True,
                "simulated": True,
                "filename": filename,
                "service": "SharePoint"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "service": "SharePoint"
            }
    
    def _upload_to_drive(self, document, file_path: Path) -> Dict[str, any]:
        """Upload file to Google Drive with proper error handling"""
        try:
            from .google_drive_upload import GoogleDriveUploader
            from .conflict_resolver import ConflictResolver, ConflictStrategy

            # Use the ACTUAL filename from file_path (not document.filename)
            # This ensures multiple PDFs (e.g., _S1.pdf, _S1 1.pdf, _S1 2.pdf) are uploaded correctly
            filename = file_path.name
            
            # Initialize uploader and resolver
            uploader = GoogleDriveUploader(self.cloud_config)
            resolver = ConflictResolver(ConflictStrategy.OVERWRITE)  # Default to overwrite for auto-sync
            
            # Get Google Drive config
            config = self.cloud_config.get_google_drive_config()
            folder_id = config.get("folder_id")
            
            # Check for conflicts
            exists, cloud_metadata = uploader.check_file_exists(filename, folder_id)
            conflict_strategy = "overwrite"  # Default strategy
            
            if exists:
                conflict_info = resolver.detect_conflict(file_path, cloud_metadata)
                if conflict_info.get("has_conflict"):
                    resolution = resolver.resolve_conflict(conflict_info)
                    
                    if resolution["action"] == "skip":
                        return {
                            "success": True,
                            "skipped": True,
                            "filename": filename,
                            "service": "Google Drive",
                            "message": f"Skipped due to conflict: {resolution['reason']}"
                        }
                    elif resolution["action"] == "rename":
                        filename = resolution["new_filename"]
                        conflict_strategy = "rename"
            
            # Upload file
            print(f"[Google Drive] Uploading: {filename}")
            print(f"[Google Drive] Source: {file_path}")
            print(f"[Google Drive] Document: {document.id} v{document.version} (state {document.current_state})")
            
            result = uploader.upload_file(file_path, filename, folder_path="", conflict_strategy=conflict_strategy)
            
            if result.get("success"):
                return {
                    "success": True,
                    "filename": filename,
                    "service": "Google Drive",
                    "file_id": result.get("file_id"),
                    "web_url": result.get("web_url"),
                    "upload_method": result.get("upload_method")
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "service": "Google Drive"
                }
            
        except ImportError as e:
            # Fallback to simulation if libraries not available
            print(f"[Google Drive] Libraries not available, simulating upload: {e}")
            filename = self._generate_cloud_filename(document)
            print(f"[Google Drive] Would upload: {filename}")
            return {
                "success": True,
                "simulated": True,
                "filename": filename,
                "service": "Google Drive"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "service": "Google Drive"
            }
    
    def _generate_cloud_filename(self, document) -> str:
        """Generate standardized filename for cloud storage"""
        # Simply use the original document filename
        return document.filename
    
    def _is_sharepoint_authenticated(self) -> bool:
        """Check if user has valid SharePoint authentication"""
        try:
            from .token_refresh import TokenRefreshManager
            refresh_manager = TokenRefreshManager(self.cloud_config)
            
            # Check token status and refresh if needed
            if refresh_manager._token_needs_refresh("sharepoint"):
                success = refresh_manager.refresh_sharepoint_token()
                if not success:
                    return False
            
            # Check if we have valid credentials
            creds = self.cloud_config.get_user_credentials("sharepoint")
            return bool(creds and creds.get("access_token"))
            
        except Exception as e:
            print(f"[SharePoint Auth] Error checking authentication: {e}")
            return False
    
    def _is_drive_authenticated(self) -> bool:
        """Check if user has valid Google Drive authentication"""
        try:
            from .token_refresh import TokenRefreshManager
            refresh_manager = TokenRefreshManager(self.cloud_config)
            
            # Check token status and refresh if needed
            if refresh_manager._token_needs_refresh("google_drive"):
                success = refresh_manager.refresh_google_drive_token()
                if not success:
                    return False
            
            # Check if we have valid credentials
            creds = self.cloud_config.get_user_credentials("google_drive")
            return bool(creds and creds.get("access_token"))
            
        except Exception as e:
            print(f"[Google Drive Auth] Error checking authentication: {e}")
            return False
    
    # Legacy methods for backward compatibility
    def sync_document(self, document, file_path: Path):
        """Legacy method - use sync_document_with_cleanup instead"""
        return self.sync_document_with_cleanup(document, file_path, auto_cleanup=True)
    
    def authenticate_sharepoint(self) -> bool:
        """Authenticate user with SharePoint using OAuth"""
        try:
            from .microsoft_auth_real import MicrosoftAuthReal
            auth = MicrosoftAuthReal(self.cloud_config)
            return auth.authenticate()
        except Exception as e:
            print(f"[SharePoint Auth] Authentication failed: {e}")
            return False
    
    def authenticate_drive(self) -> bool:
        """Authenticate user with Google Drive using OAuth"""
        try:
            from .google_auth_real import GoogleAuthReal
            auth = GoogleAuthReal(self.cloud_config)
            return auth.authenticate()
        except Exception as e:
            print(f"[Google Drive Auth] Authentication failed: {e}")
            return False
    
    def test_sharepoint_connection(self) -> bool:
        """Test SharePoint connection"""
        try:
            if not self._is_sharepoint_authenticated():
                return False
            
            # Try to access SharePoint API
            from .sharepoint_upload import SharePointUploader
            uploader = SharePointUploader(self.cloud_config)
            # Test connection by checking folder access
            config = self.cloud_config.get_sharepoint_config()
            folder_path = config.get("folder_path", "")
            return uploader.test_connection(folder_path)
        except Exception as e:
            print(f"[SharePoint Test] Connection test failed: {e}")
            return False
    
    def test_drive_connection(self) -> bool:
        """Test Google Drive connection"""
        try:
            if not self._is_drive_authenticated():
                return False
            
            # Try to access Google Drive API
            from .google_drive_upload import GoogleDriveUploader
            uploader = GoogleDriveUploader(self.cloud_config)
            config = self.cloud_config.get_google_drive_config()
            folder_id = config.get("folder_id")
            return uploader.test_connection(folder_id)
        except Exception as e:
            print(f"[Google Drive Test] Connection test failed: {e}")
            return False
    
    def get_authentication_status(self) -> Dict[str, Any]:
        """Get detailed authentication status for both services"""
        status = {
            "sharepoint": {
                "authenticated": False,
                "status": "unknown",
                "message": ""
            },
            "google_drive": {
                "authenticated": False,
                "status": "unknown", 
                "message": ""
            }
        }
        
        # Check SharePoint status
        try:
            from .microsoft_auth_real import MicrosoftAuthReal
            auth = MicrosoftAuthReal(self.cloud_config)
            is_auth, message = auth.check_status()
            status["sharepoint"]["authenticated"] = is_auth
            status["sharepoint"]["status"] = "authenticated" if is_auth else "not_authenticated"
            status["sharepoint"]["message"] = message
        except Exception as e:
            status["sharepoint"]["message"] = f"Error: {e}"
        
        # Check Google Drive status
        try:
            from .google_auth_real import GoogleAuthReal
            auth = GoogleAuthReal(self.cloud_config)
            is_auth, message = auth.check_status()
            status["google_drive"]["authenticated"] = is_auth
            status["google_drive"]["status"] = "authenticated" if is_auth else "not_authenticated"
            status["google_drive"]["message"] = message
        except Exception as e:
            status["google_drive"]["message"] = f"Error: {e}"
        
        return status


# Integration functions for the document controller
def integrate_enhanced_sync():
    """
    Helper function showing how to integrate enhanced sync into document_controller.py
    
    Replace the existing cloud_sync initialization with:
    
    from utils.enhanced_cloud_sync import EnhancedCloudSyncManager
    self.cloud_sync = EnhancedCloudSyncManager(self.cloud_config)
    
    Then replace sync calls with:
    result = self.cloud_sync.sync_document_with_cleanup(document, destination)
    """
    pass


# Example usage
def example_enhanced_sync():
    """Example of how to use the enhanced cloud sync"""
    
    print("🚀 Enhanced Cloud Sync Example")
    print("=" * 50)
    
    # Mock document
    class MockDocument:
        def __init__(self):
            self.id = "PL-001"
            self.name = "Planta Baja"
            self.version = "1.2"
            self.current_state = "S2"
            self.filename = "PL-001_Planta Baja_v1.2_S2.pdf"
    
    # Mock config
    class MockCloudConfig:
        def is_cloud_sync_enabled(self): return True
        def is_sharepoint_enabled(self): return True
        def is_google_drive_enabled(self): return True
    
    # Create enhanced sync manager
    config = MockCloudConfig()
    enhanced_sync = EnhancedCloudSyncManager(config)
    
    # Simulate document sync with cleanup
    mock_document = MockDocument()
    mock_file_path = Path("test.pdf")
    
    print(f"📄 Syncing: {mock_document.id} v{mock_document.version} ({mock_document.current_state})")
    print()
    
    # Sync with automatic cleanup
    result = enhanced_sync.sync_document_with_cleanup(mock_document, mock_file_path)
    
    print("📊 Sync Results:")
    print(f"   Uploaded to: {', '.join(result['uploaded_to'])}")
    if result['cleanup_results']:
        print(f"   Cleanup completed for {len(result['cleanup_results'])} services")
    if result['errors']:
        print(f"   ⚠️ Errors: {result['errors']}")
    
    print()
    
    # Preview cleanup for all documents
    cleanup_preview = enhanced_sync.get_cleanup_preview()
    print("🗑️ Cleanup Preview (All Documents):")
    if cleanup_preview.get('sharepoint', {}).get('dry_run'):
        sp_info = cleanup_preview['sharepoint']
        print(f"   SharePoint: {sp_info.get('files_to_delete', 0)} files to delete")
    if cleanup_preview.get('google_drive', {}).get('dry_run'):
        gd_info = cleanup_preview['google_drive']
        print(f"   Google Drive: {gd_info.get('files_to_delete', 0)} files to delete")


if __name__ == "__main__":
    example_enhanced_sync()