#!/usr/bin/env python3
"""Automatic token refresh functionality for cloud services"""

import requests
import json
import threading
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from .token_monitor import get_token_monitor, monitor_token_operation


class TokenRefreshManager:
    """Thread-safe token refresh manager for cloud services"""
    
    # Class-level locks for different services to prevent race conditions
    _sharepoint_lock = threading.RLock()
    _google_drive_lock = threading.RLock()
    _token_refresh_times = {}  # Track last refresh attempts to prevent rapid retries
    _refresh_timeout = 30  # Maximum time to wait for token refresh
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        self.logger = logging.getLogger(__name__)
        # Instance lock for general operations
        self._instance_lock = threading.RLock()
        # Get token operation monitor
        self.monitor = get_token_monitor()
        
    def refresh_sharepoint_token(self) -> bool:
        """Thread-safe SharePoint token refresh"""
        service_key = "sharepoint_refresh"
        
        # Start monitoring the operation
        operation_id = self.monitor.start_operation("refresh", "sharepoint", {
            "thread_id": threading.current_thread().ident,
            "service_key": service_key
        })
        
        try:
            # Check if another thread is already refreshing this token
            with TokenRefreshManager._sharepoint_lock:
                # Check if we recently attempted a refresh (avoid rapid retries)
                last_attempt = TokenRefreshManager._token_refresh_times.get(service_key, 0)
                if time.time() - last_attempt < 60:  # Don't retry within 60 seconds
                    self.logger.info("SharePoint token refresh attempted too recently, skipping")
                    self.monitor.end_operation(operation_id, success=False, error="Rate limited")
                    return False
                
                # Mark that we're attempting a refresh
                TokenRefreshManager._token_refresh_times[service_key] = time.time()
                
                # Double-check if token is still expired after acquiring lock
                if not self._token_needs_refresh("sharepoint"):
                    self.logger.info("SharePoint token no longer needs refresh (refreshed by another thread)")
                    self.monitor.end_operation(operation_id, success=True)
                    return True
            
            self.logger.info("Starting SharePoint token refresh")
            # Get credentials with lock protection
            with self._instance_lock:
                creds = self.cloud_config.get_user_credentials("sharepoint")
                if not creds or not creds.get("refresh_token"):
                    self.logger.warning("No SharePoint refresh token available")
                    return False
            
            # Microsoft OAuth token endpoint (use organizations instead of common for single-tenant apps)
            token_url = "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"
            
            # Load Microsoft client ID from environment
            from config.oauth_config import OAuthConfig
            oauth_config = OAuthConfig()
            microsoft_creds = oauth_config.get_microsoft_credentials()
            client_id = microsoft_creds['client_id']
            
            # Prepare refresh token request
            client_secret = microsoft_creds.get('client_secret')
            if not client_secret:
                self.logger.error("Microsoft client_secret not found in environment variables")
                self.monitor.end_operation(operation_id, success=False, error="Missing client_secret")
                return False
            
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"]
                # Note: No explicit scope - SharePoint refresh works better without it
            }
            
            response = requests.post(token_url, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                with TokenRefreshManager._sharepoint_lock:
                    self._save_sharepoint_tokens(token_data, creds.get("refresh_token"))
                self.logger.info("SharePoint token refreshed successfully")
                self.monitor.end_operation(operation_id, success=True)
                return True
            else:
                error_msg = f"SharePoint token refresh failed: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                self.monitor.end_operation(operation_id, success=False, error=error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Error refreshing SharePoint token: {e}"
            self.logger.error(error_msg)
            # Reset the refresh attempt time on error so we can try again later
            with TokenRefreshManager._sharepoint_lock:
                TokenRefreshManager._token_refresh_times.pop(service_key, None)
            self.monitor.end_operation(operation_id, success=False, error=error_msg)
            return False
    
    def refresh_google_drive_token(self) -> bool:
        """Thread-safe Google Drive token refresh"""
        service_key = "google_drive_refresh"
        
        # Start monitoring the operation
        operation_id = self.monitor.start_operation("refresh", "google_drive", {
            "thread_id": threading.current_thread().ident,
            "service_key": service_key
        })
        
        try:
            # Check if another thread is already refreshing this token
            with TokenRefreshManager._google_drive_lock:
                # Check if we recently attempted a refresh (avoid rapid retries)
                last_attempt = TokenRefreshManager._token_refresh_times.get(service_key, 0)
                if time.time() - last_attempt < 60:  # Don't retry within 60 seconds
                    self.logger.info("Google Drive token refresh attempted too recently, skipping")
                    self.monitor.end_operation(operation_id, success=False, error="Rate limited")
                    return False
                
                # Mark that we're attempting a refresh
                TokenRefreshManager._token_refresh_times[service_key] = time.time()
                
                # Double-check if token is still expired after acquiring lock
                if not self._token_needs_refresh("google_drive"):
                    self.logger.info("Google Drive token no longer needs refresh (refreshed by another thread)")
                    self.monitor.end_operation(operation_id, success=True)
                    return True
            
            self.logger.info("Starting Google Drive token refresh")
            # Get credentials with lock protection
            with self._instance_lock:
                creds = self.cloud_config.get_user_credentials("google_drive")
                if not creds or not creds.get("refresh_token"):
                    self.logger.warning("No Google Drive refresh token available")
                    return False
            
            # Google OAuth token endpoint
            token_url = "https://oauth2.googleapis.com/token"
            
            # Load OAuth credentials from environment variables
            from config.oauth_config import OAuthConfig
            oauth_config = OAuthConfig()
            google_creds = oauth_config.get_google_credentials()
            
            if not google_creds['client_id'] or not google_creds['client_secret']:
                print("Google OAuth credentials not found in environment variables")
                return False
            
            client_id = google_creds['client_id']
            client_secret = google_creds['client_secret']
            
            # Prepare refresh token request
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"]
            }
            
            response = requests.post(token_url, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                with TokenRefreshManager._google_drive_lock:
                    self._save_google_drive_tokens(token_data, creds.get("refresh_token"))
                self.logger.info("Google Drive token refreshed successfully")
                self.monitor.end_operation(operation_id, success=True)
                return True
            else:
                error_msg = f"Google Drive token refresh failed: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                self.monitor.end_operation(operation_id, success=False, error=error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Error refreshing Google Drive token: {e}"
            self.logger.error(error_msg)
            # Reset the refresh attempt time on error so we can try again later
            with TokenRefreshManager._google_drive_lock:
                TokenRefreshManager._token_refresh_times.pop(service_key, None)
            self.monitor.end_operation(operation_id, success=False, error=error_msg)
            return False
    
    def check_and_refresh_tokens(self) -> Dict[str, bool]:
        """Thread-safe token expiration check and refresh"""
        results = {
            "sharepoint_refreshed": False,
            "google_drive_refreshed": False
        }
        
        # Use threading to refresh tokens in parallel, but with proper synchronization
        refresh_threads = []
        
        # Check SharePoint token
        if self._token_needs_refresh("sharepoint"):
            def refresh_sp():
                results["sharepoint_refreshed"] = self.refresh_sharepoint_token()
            
            sp_thread = threading.Thread(target=refresh_sp, name="SharePointRefresh")
            refresh_threads.append(sp_thread)
            sp_thread.start()
        
        # Check Google Drive token
        if self._token_needs_refresh("google_drive"):
            def refresh_gd():
                results["google_drive_refreshed"] = self.refresh_google_drive_token()
            
            gd_thread = threading.Thread(target=refresh_gd, name="GoogleDriveRefresh")
            refresh_threads.append(gd_thread)
            gd_thread.start()
        
        # Wait for all refresh operations to complete with timeout
        for thread in refresh_threads:
            thread.join(timeout=self._refresh_timeout)
            if thread.is_alive():
                self.logger.warning(f"Token refresh thread {thread.name} timed out")
        
        return results
    
    def _token_needs_refresh(self, service: str, buffer_minutes: int = 10) -> bool:
        """Thread-safe check if token needs refresh (expires within buffer time)"""
        operation_id = self.monitor.start_operation("validate", service, {
            "buffer_minutes": buffer_minutes
        })
        
        try:
            with self._instance_lock:
                creds = self.cloud_config.get_user_credentials(service)
                if not creds or not creds.get("expires_at"):
                    self.monitor.end_operation(operation_id, success=True)
                    return False
                
                try:
                    expires_at = datetime.fromisoformat(creds["expires_at"].replace('Z', '+00:00'))
                    buffer_time = timedelta(minutes=buffer_minutes)
                    needs_refresh = datetime.now(timezone.utc) + buffer_time >= expires_at
                    
                    if needs_refresh:
                        self.logger.info(f"{service} token expires at {expires_at}, needs refresh")
                    
                    self.monitor.end_operation(operation_id, success=True)
                    return needs_refresh
                except (ValueError, KeyError) as e:
                    error_msg = f"Error checking {service} token expiration: {e}"
                    self.logger.warning(error_msg)
                    self.monitor.end_operation(operation_id, success=False, error=error_msg)
                    return False
        except Exception as e:
            self.monitor.end_operation(operation_id, success=False, error=str(e))
            raise
    
    def _save_sharepoint_tokens(self, token_data: Dict[str, Any], existing_refresh_token: str = None):
        """Thread-safe save of refreshed SharePoint tokens"""
        expires_in = token_data.get('expires_in', 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        sharepoint_creds = {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token', existing_refresh_token),
            'expires_at': expires_at.isoformat(),
            'token_type': 'Bearer',
            'scope': token_data.get('scope', ''),
            'authenticated_at': datetime.now(timezone.utc).isoformat(),
            'refreshed_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Atomic update of user config
        with self._instance_lock:
            user_config = self.cloud_config.load_user_config()
            user_config['sharepoint'] = sharepoint_creds
            self.cloud_config.save_user_config(user_config)
            self.logger.info(f"SharePoint tokens saved, expires at {expires_at}")
    
    def _save_google_drive_tokens(self, token_data: Dict[str, Any], existing_refresh_token: str = None):
        """Thread-safe save of refreshed Google Drive tokens"""
        expires_in = token_data.get('expires_in', 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        google_creds = {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token', existing_refresh_token),
            'expires_at': expires_at.isoformat(),
            'token_type': 'Bearer',
            'scope': token_data.get('scope', 'https://www.googleapis.com/auth/drive.file'),
            'authenticated_at': datetime.now(timezone.utc).isoformat(),
            'refreshed_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Atomic update of user config
        with self._instance_lock:
            user_config = self.cloud_config.load_user_config()
            user_config['google_drive'] = google_creds
            self.cloud_config.save_user_config(user_config)
            self.logger.info(f"Google Drive tokens saved, expires at {expires_at}")
    
    def get_token_status(self, service: str) -> Dict[str, Any]:
        """Thread-safe get detailed token status information"""
        with self._instance_lock:
            creds = self.cloud_config.get_user_credentials(service)
            if not creds:
                return {"status": "not_authenticated", "message": "No credentials found"}
            
            if not creds.get("access_token"):
                return {"status": "invalid", "message": "No access token"}
            
            expires_at = creds.get("expires_at")
            if not expires_at:
                return {"status": "unknown", "message": "No expiration info"}
            
            try:
                exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                
                if now >= exp_time:
                    return {"status": "expired", "message": "Token has expired", "expired_at": exp_time}
                
                time_left = exp_time - now
                if time_left.total_seconds() < 600:  # Less than 10 minutes
                    return {
                        "status": "expiring_soon", 
                        "message": f"Expires in {int(time_left.total_seconds() // 60)} minutes",
                        "expires_at": exp_time,
                        "time_left_seconds": time_left.total_seconds()
                    }
                
                return {
                    "status": "valid", 
                    "message": f"Valid for {int(time_left.total_seconds() // 3600)}h {int((time_left.total_seconds() % 3600) // 60)}m",
                    "expires_at": exp_time,
                    "time_left_seconds": time_left.total_seconds()
                }
                
            except ValueError:
                return {"status": "invalid", "message": "Invalid expiration format"}
    
    def is_token_valid(self, service: str) -> bool:
        """Thread-safe check if token is currently valid"""
        status = self.get_token_status(service)
        return status["status"] in ["valid", "expiring_soon"]
    
    def ensure_valid_token(self, service: str) -> bool:
        """Ensure token is valid, refresh if needed. Returns True if token is valid."""
        if self.is_token_valid(service):
            return True
        
        # Token needs refresh
        if service == "sharepoint":
            return self.refresh_sharepoint_token()
        elif service == "google_drive":
            return self.refresh_google_drive_token()
        else:
            self.logger.error(f"Unknown service: {service}")
            return False
    
    @classmethod
    def reset_refresh_timers(cls):
        """Reset all refresh attempt timers (useful for testing)"""
        with cls._sharepoint_lock, cls._google_drive_lock:
            cls._token_refresh_times.clear()