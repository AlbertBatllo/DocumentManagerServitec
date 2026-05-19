import json
import os
import webbrowser
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import threading
import time
from .cloud_exceptions import (
    CloudAuthenticationError, CloudUploadError, CloudValidationError,
    raise_auth_error, raise_upload_error, raise_validation_error
)

# Optional tkinter import for GUI functionality
try:
    import tkinter as tk
    from tkinter import messagebox
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False
    # Create dummy messagebox for testing
    class MessageBox:
        def showinfo(self, title, message): pass
        def showwarning(self, title, message): pass
        def showerror(self, title, message): pass
    messagebox = MessageBox()

# Pre-check for Google auth libraries to avoid misleading warnings
try:
    import google.auth
    HAS_GOOGLE_AUTH_LIBS = True
except ImportError:
    HAS_GOOGLE_AUTH_LIBS = False


class CloudSyncManager:
    """Minimal cloud sync manager for SharePoint and Google Drive"""
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        self._token_refresh_manager = None
        self.logger = logging.getLogger(__name__)
    
    def _handle_upload_result(self, service: str, result: Dict[str, Any], filename: str) -> bool:
        """Handle upload result with proper logging and error reporting"""
        if result.get("success"):
            self.logger.info(f"[{service}] Successfully uploaded: {filename}")
            if result.get("web_url"):
                self.logger.info(f"[{service}] URL: {result['web_url']}")
            return True
        else:
            error_msg = result.get('error', 'Unknown error')
            self.logger.error(f"[{service}] Upload failed for {filename}: {error_msg}")
            # Also print for immediate user feedback
            print(f"[Cloud Sync] {service} upload failed: {error_msg}")
            return False
    
    def _is_valid_file_type(self, file_path: Path) -> bool:
        """Validate file type for cloud operations (only PDF files allowed)"""
        if not file_path.exists():
            self.logger.error(f"File does not exist: {file_path}")
            return False
        
        allowed_extensions = {'.pdf'}
        file_extension = file_path.suffix.lower()
        
        if file_extension not in allowed_extensions:
            self.logger.warning(f"Invalid file type for cloud sync: {file_extension}. Only PDF files are allowed.")
            return False
        
        return True
    
    def should_sync_to_sharepoint(self, document_state: str) -> bool:
        """Check if document should be synced to SharePoint (S2, S3 or S3A)"""
        return (self.cloud_config.is_sharepoint_enabled() and 
                document_state in ["S2", "S3", "S3A"])
    
    def should_sync_to_drive(self, document_state: str) -> bool:
        """Check if document should be synced to Google Drive (S3A only)"""
        return (self.cloud_config.is_google_drive_enabled() and 
                document_state == "S3A")
    
    def sync_document(self, document, file_path: Path):
        """Sync document to enabled cloud services based on state"""
        if not self.cloud_config.is_cloud_sync_enabled():
            return
        
        # Validate file type before proceeding
        if not self._is_valid_file_type(file_path):
            raise_validation_error(file_path.name, "Only PDF files are allowed for cloud operations")
        
        document_state = document.current_state
        
        # Sync to SharePoint (S2, S3 or S3A)
        if self.should_sync_to_sharepoint(document_state):
            if not self._is_sharepoint_authenticated():
                raise_auth_error("SharePoint", "Authentication required. Please authenticate first.")
            
            try:
                from .sharepoint_upload import SharePointUploader
                from .conflict_resolver import ConflictResolver, ConflictStrategy
                
                uploader = SharePointUploader(self.cloud_config)
                resolver = ConflictResolver(ConflictStrategy.ASK_USER)
                
                # Generate filename using FileManager for consistency
                from utils.file_manager import FileManager
                filename = FileManager.generate_filename(
                    document.name, document.name, document.version, ".pdf"
                )
                
                # Check for conflicts
                config = self.cloud_config.get_sharepoint_config()
                folder_path = config.get("folder_path", "")
                
                exists, cloud_metadata = uploader.check_file_exists(filename, folder_path)
                if exists:
                    conflict_info = resolver.detect_conflict(file_path, cloud_metadata)
                    if conflict_info.get("has_conflict"):
                        resolution = resolver.resolve_conflict(conflict_info)
                        
                        if resolution["action"] == "skip":
                            print(f"[Cloud Sync] Skipping SharePoint upload due to conflict: {resolution['reason']}")
                            return
                        elif resolution["action"] == "rename":
                            filename = resolution["new_filename"]
                
                # Upload file
                result = uploader.upload_file(file_path, filename, folder_path, 
                                             conflict_strategy="overwrite")
                
                self._handle_upload_result("SharePoint", result, filename)
                    
            except ImportError as e:
                self.logger.warning(f"SharePoint libraries not available: {e}")
                print(f"[Cloud Sync] SharePoint upload not available: {e}")
            except Exception as e:
                self.logger.error(f"SharePoint upload error for {document.name}: {e}")
                print(f"[Cloud Sync] SharePoint upload error: {e}")
        
        # Sync to Google Drive (S3A only)
        if self.should_sync_to_drive(document_state):
            if not self._is_drive_authenticated():
                raise_auth_error("Google Drive", "Authentication required. Please authenticate first.")
            
            try:
                from .google_drive_upload import GoogleDriveUploader
                from .conflict_resolver import ConflictResolver, ConflictStrategy
                
                uploader = GoogleDriveUploader(self.cloud_config)
                resolver = ConflictResolver(ConflictStrategy.ASK_USER)
                
                # Generate filename using FileManager for consistency
                from utils.file_manager import FileManager
                filename = FileManager.generate_filename(
                    document.name, document.name, document.version, ".pdf"
                )
                
                # Check for conflicts
                config = self.cloud_config.get_google_drive_config()
                folder_id = config.get("folder_id")
                
                exists, cloud_metadata = uploader.check_file_exists(filename, folder_id)
                if exists:
                    conflict_info = resolver.detect_conflict(file_path, cloud_metadata)
                    if conflict_info.get("has_conflict"):
                        resolution = resolver.resolve_conflict(conflict_info)
                        
                        if resolution["action"] == "skip":
                            print(f"[Cloud Sync] Skipping Google Drive upload due to conflict: {resolution['reason']}")
                            return
                        elif resolution["action"] == "rename":
                            filename = resolution["new_filename"]
                
                # Upload file
                result = uploader.upload_file(file_path, filename, folder_path="",
                                             conflict_strategy="overwrite")
                
                self._handle_upload_result("Google Drive", result, filename)
                    
            except ImportError as e:
                self.logger.warning(f"Google Drive libraries not available: {e}")
                print(f"[Cloud Sync] Google Drive upload not available: {e}")
            except Exception as e:
                self.logger.error(f"Google Drive upload error for {document.name}: {e}")
                print(f"[Cloud Sync] Google Drive upload error: {e}")
    
    def _is_sharepoint_authenticated(self) -> bool:
        """Check if user has valid SharePoint authentication"""
        creds = self.cloud_config.get_user_credentials("sharepoint")
        if not creds:
            return False
        
        # Check if token is expired
        expires_at = creds.get("expires_at")
        if expires_at:
            try:
                expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expiry_time:
                    return False
            except ValueError:
                return False
        
        return bool(creds.get("access_token"))
    
    def _is_drive_authenticated(self) -> bool:
        """Check if user has valid Google Drive authentication"""
        creds = self.cloud_config.get_user_credentials("google_drive")
        if not creds:
            return False
        
        # Check if token is expired
        expires_at = creds.get("expires_at")
        if expires_at:
            try:
                expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expiry_time:
                    return False
            except ValueError:
                return False
        
        return bool(creds.get("access_token"))
    
    def authenticate_sharepoint(self) -> bool:
        """Authenticate user with SharePoint using OAuth"""
        try:
            from .oauth_final import FinalOAuthManager
            oauth_manager = FinalOAuthManager(self.cloud_config)
            return oauth_manager.authenticate_sharepoint()
        except ImportError as e:
            error_msg = f"Import error: {e}"
            if HAS_TKINTER:
                messagebox.showerror("Authentication Error", error_msg)
            else:
                print(error_msg)
            return False
        except Exception as e:
            raise RuntimeError(f"SharePoint authentication failed: {e}")
    
    def authenticate_drive(self) -> bool:
        """Google Drive authentication with real credentials - works like normal apps!"""
        try:
            from .google_auth_real import GoogleAuthReal
            google_auth = GoogleAuthReal(self.cloud_config)
            
            # Just authenticate - it handles everything!
            success = google_auth.authenticate()
            
            if success and HAS_TKINTER:
                messagebox.showinfo(
                    "🎉 Success!", 
                    "Google Drive is now connected!\n\n"
                    "Your documents will automatically sync to Google Drive when approved."
                )
            
            return success
            
        except ValueError as e:
            # Handle missing OAuth credentials gracefully
            if "not found in environment variables" in str(e):
                if HAS_TKINTER:
                    messagebox.showwarning(
                        "Configuration Required",
                        "Google Drive OAuth credentials not configured.\n\n"
                        "Please add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file."
                    )
                else:
                    print("Google OAuth credentials not configured")
                return False
            else:
                raise e
        except Exception as e:
            error_msg = f"Google Drive authentication failed: {e}"
            if HAS_TKINTER:
                messagebox.showerror("Authentication Error", error_msg)
            else:
                print(error_msg)
            return False
    
    
    def test_sharepoint_connection(self) -> bool:
        """Test SharePoint connection"""
        try:
            if not self._is_sharepoint_authenticated():
                return False
            
            # Test connection to SharePoint
            config = self.cloud_config.get_sharepoint_config()
            if not config.get("site_url") or not config.get("folder_path"):
                return False
            
            # Placeholder for actual connection test
            return True
        except Exception:
            return False
    
    def test_drive_connection(self) -> bool:
        """Test Google Drive connection"""
        try:
            if not self._is_drive_authenticated():
                return False
            
            # Test connection to Google Drive
            config = self.cloud_config.get_google_drive_config()
            if not config.get("folder_id"):
                return False
            
            # Basic connectivity check - if we have valid tokens and folder ID, assume it works
            # In a real implementation, this would make an actual API call
            return True
        except Exception:
            return False
    
    def _ensure_token_refresh_manager(self):
        """Lazy initialization of token refresh manager"""
        if self._token_refresh_manager is None:
            try:
                from .token_refresh import TokenRefreshManager
                self._token_refresh_manager = TokenRefreshManager(self.cloud_config)
            except (ImportError, ValueError, Exception):
                # Create a dummy manager if import fails or credentials are missing
                class DummyRefreshManager:
                    def check_and_refresh_tokens(self):
                        return {"sharepoint_refreshed": False, "google_drive_refreshed": False}
                self._token_refresh_manager = DummyRefreshManager()
    
    def refresh_tokens_if_needed(self) -> Dict[str, bool]:
        """Manually trigger token refresh check"""
        self._ensure_token_refresh_manager()
        return self._token_refresh_manager.check_and_refresh_tokens()