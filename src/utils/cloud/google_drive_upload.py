"""
Google Drive Upload Module
Handles real file uploads to Google Drive using Google Drive API v3
"""

import os
import json
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import hashlib

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
    from googleapiclient.errors import HttpError
    import io
    HAS_GOOGLE_LIBS = True
except ImportError:
    HAS_GOOGLE_LIBS = False
    print("Warning: Google Drive libraries not installed. Install with: pip install google-api-python-client google-auth")


class GoogleDriveUploader:
    """Handles file uploads to Google Drive using Google Drive API v3"""
    
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        self.service = None
        # Load configurable chunk size
        from config.cloud_settings import get_cloud_settings
        self.settings = get_cloud_settings()
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize Google Drive service with credentials"""
        if not HAS_GOOGLE_LIBS:
            raise ImportError("Google Drive libraries not installed")
        
        try:
            creds_data = self.cloud_config.get_user_credentials("google_drive")
            if not creds_data:
                raise ValueError("No Google Drive credentials found. Please authenticate first.")
            
            # Create credentials from stored token data
            creds = Credentials(
                token=creds_data.get("access_token"),
                refresh_token=creds_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=self.SCOPES
            )
            
            # Build service
            self.service = build('drive', 'v3', credentials=creds)
            
        except Exception as e:
            print(f"Error initializing Google Drive service: {e}")
            raise
    
    def create_folder_if_needed(self, folder_name: str, parent_folder_id: str = None) -> Optional[str]:
        """
        Create folder in Google Drive if it doesn't exist
        Returns folder ID
        """
        try:
            # Check if folder already exists
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_folder_id:
                query += f" and '{parent_folder_id}' in parents"
            query += " and trashed=false"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                # Folder exists, return its ID
                return files[0]['id']
            
            # Create new folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            return folder.get('id')
            
        except HttpError as e:
            print(f"Error creating folder: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error creating folder: {e}")
            return None
    
    def create_folder_hierarchy(self, folder_path: str, base_folder_id: str = None) -> Optional[str]:
        """
        Create folder hierarchy in Google Drive
        Returns the ID of the deepest folder
        """
        try:
            folder_parts = [f for f in folder_path.strip('/').split('/') if f]
            current_parent_id = base_folder_id
            
            for folder_name in folder_parts:
                folder_id = self.create_folder_if_needed(folder_name, current_parent_id)
                if not folder_id:
                    return None
                current_parent_id = folder_id
            
            return current_parent_id
            
        except Exception as e:
            print(f"Error creating folder hierarchy: {e}")
            return None
    
    def check_file_exists(self, filename: str, folder_id: str = None) -> Tuple[bool, Optional[Dict]]:
        """
        Check if file already exists in Google Drive
        Returns: (exists: bool, file_metadata: dict or None)
        """
        try:
            query = f"name='{filename}'"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            query += " and trashed=false"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, size, modifiedTime, md5Checksum, webViewLink, webContentLink)'
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                file_data = files[0]
                return True, {
                    "id": file_data.get("id"),
                    "name": file_data.get("name"),
                    "size": file_data.get("size"),
                    "lastModified": file_data.get("modifiedTime"),
                    "md5": file_data.get("md5Checksum"),
                    "webViewLink": file_data.get("webViewLink"),
                    "downloadUrl": file_data.get("webContentLink")
                }
            else:
                return False, None
                
        except HttpError as e:
            print(f"Error checking file existence: {e}")
            return False, None
        except Exception as e:
            print(f"Unexpected error checking file: {e}")
            return False, None
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file for integrity check (Google Drive uses MD5)"""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
        return md5_hash.hexdigest()
    
    def upload_file(self, file_path: Path, filename: str, folder_path: str = None,
                   conflict_strategy: str = "rename") -> Dict[str, Any]:
        """
        Upload file to Google Drive
        
        Args:
            file_path: Local file path
            filename: Target filename in Google Drive
            folder_path: Target folder path in Google Drive (optional)
            conflict_strategy: "overwrite", "rename", or "skip"
            
        Returns:
            Dict with upload result
        """
        try:
            # Validate inputs
            if not file_path.exists():
                return {"success": False, "error": "File does not exist"}
            
            if not self.service:
                return {"success": False, "error": "Google Drive service not initialized"}
            
            # Get configured folder ID
            config = self.cloud_config.get_google_drive_config()
            base_folder_id = config.get("folder_id")
            
            # Create folder hierarchy if needed
            target_folder_id = base_folder_id
            if folder_path:
                target_folder_id = self.create_folder_hierarchy(folder_path, base_folder_id)
                if not target_folder_id:
                    return {"success": False, "error": "Could not create folder structure"}
            
            # Check if file exists
            exists, existing_file = self.check_file_exists(filename, target_folder_id)
            
            if exists:
                if conflict_strategy == "skip":
                    return {
                        "success": True,
                        "skipped": True,
                        "message": "File already exists, skipping upload",
                        "existing_file": existing_file
                    }
                elif conflict_strategy == "overwrite":
                    # Delete existing file first
                    try:
                        self.service.files().delete(fileId=existing_file["id"]).execute()
                    except:
                        pass  # Continue even if delete fails
                elif conflict_strategy == "rename":
                    # Append number to filename
                    base_name = Path(filename).stem
                    extension = Path(filename).suffix
                    counter = 1
                    new_filename = filename
                    
                    while exists:
                        new_filename = f"{base_name}_{counter}{extension}"
                        exists, _ = self.check_file_exists(new_filename, target_folder_id)
                        counter += 1
                    
                    filename = new_filename
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Prepare file metadata
            file_metadata = {
                'name': filename
            }
            
            if target_folder_id:
                file_metadata['parents'] = [target_folder_id]
            
            # Determine upload strategy based on file size
            file_size = file_path.stat().st_size
            
            if file_size < 5 * 1024 * 1024:  # Less than 5MB - simple upload
                result = self._simple_upload(file_path, file_metadata, mime_type)
            else:  # Large file - use resumable upload
                result = self._resumable_upload(file_path, file_metadata, mime_type)
            
            # Add file hash for integrity verification
            if result.get("success"):
                result["file_hash"] = self.calculate_file_hash(file_path)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": f"Upload failed: {str(e)}"}
    
    def _simple_upload(self, file_path: Path, file_metadata: Dict, mime_type: str) -> Dict[str, Any]:
        """Simple upload for small files (< 5MB)"""
        try:
            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=False
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, size, webViewLink, webContentLink, md5Checksum'
            ).execute()
            
            return {
                "success": True,
                "file_id": file.get("id"),
                "file_name": file.get("name"),
                "web_url": file.get("webViewLink"),
                "download_url": file.get("webContentLink"),
                "size": file.get("size"),
                "md5": file.get("md5Checksum"),
                "upload_method": "simple"
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Simple upload failed: {e.reason}",
                "status_code": e.resp.status
            }
        except Exception as e:
            return {"success": False, "error": f"Simple upload error: {str(e)}"}
    
    def _resumable_upload(self, file_path: Path, file_metadata: Dict, mime_type: str) -> Dict[str, Any]:
        """Resumable upload for large files (>= 5MB)"""
        try:
            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                chunksize=self.settings.google_drive_chunk_size,
                resumable=True
            )
            
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, size, webViewLink, webContentLink, md5Checksum'
            )
            
            response = None
            chunks_uploaded = 0
            
            while response is None:
                status, response = request.next_chunk()
                if status:
                    chunks_uploaded += 1
                    progress = int(status.progress() * 100)
                    print(f"Upload progress: {progress}% (chunk {chunks_uploaded})")
            
            file = response
            
            return {
                "success": True,
                "file_id": file.get("id"),
                "file_name": file.get("name"),
                "web_url": file.get("webViewLink"),
                "download_url": file.get("webContentLink"),
                "size": file.get("size"),
                "md5": file.get("md5Checksum"),
                "upload_method": "resumable",
                "chunks_uploaded": chunks_uploaded
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Resumable upload failed: {e.reason}",
                "status_code": e.resp.status
            }
        except Exception as e:
            return {"success": False, "error": f"Resumable upload error: {str(e)}"}
    
    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for an uploaded file"""
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields='id, name, size, modifiedTime, md5Checksum, webViewLink, webContentLink, parents'
            ).execute()
            
            return file
            
        except HttpError as e:
            print(f"Error getting file metadata: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error getting metadata: {e}")
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive (move to trash)"""
        try:
            self.service.files().delete(fileId=file_id).execute()
            return True
            
        except HttpError as e:
            print(f"Error deleting file: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error deleting file: {e}")
            return False
    
    def list_files_in_folder(self, folder_id: str = None, max_results: int = 100) -> List[Dict]:
        """List files in a Google Drive folder"""
        try:
            query = "mimeType != 'application/vnd.google-apps.folder'"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            query += " and trashed=false"
            
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, size, modifiedTime, md5Checksum)',
                pageSize=max_results
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            print(f"Error listing files: {e}")
            return []