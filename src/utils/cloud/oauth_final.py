"""Final OAuth implementation with proper client IDs"""

import json
import webbrowser
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import http.server
import socketserver
from urllib.parse import parse_qs, urlparse

# Check for libraries without printing warnings
HAS_MSAL = False
HAS_GOOGLE_AUTH = False

try:
    from msal import PublicClientApplication
    HAS_MSAL = True
except ImportError:
    pass

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    HAS_GOOGLE_AUTH = True
except ImportError:
    pass


class FinalOAuthManager:
    """Final OAuth manager with working configurations"""
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        
    def authenticate_sharepoint(self) -> bool:
        """Authenticate with SharePoint using authorization code flow (like Google Drive)"""
        try:
            print("\n=== SharePoint/OneDrive Authentication ===")
            
            # Use the new MicrosoftAuthReal class for consistent OAuth flow
            from utils.microsoft_auth_real import MicrosoftAuthReal
            
            microsoft_auth = MicrosoftAuthReal(self.cloud_config)
            return microsoft_auth.authenticate()
                
        except Exception as e:
            print(f"✗ SharePoint authentication error: {e}")
            return False
    
    def authenticate_google_drive(self) -> bool:
        """Authenticate with Google Drive using installed app flow"""
        if not HAS_GOOGLE_AUTH:
            print("\n=== Google Drive Authentication ===")
            print("Google auth libraries are required for Drive authentication.")
            print("Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2")
            return False
        
        try:
            print("\n=== Google Drive Authentication ===")
            
            # Load Google credentials from environment
            from config.oauth_config import OAuthConfig
            oauth_config = OAuthConfig()
            google_creds = oauth_config.get_google_credentials()
            
            if not google_creds['client_id'] or not google_creds['client_secret']:
                print("Google OAuth credentials not found in environment variables")
                print("Please check your .env file contains GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
                return False
            
            # Use client configuration from environment
            client_config = {
                "installed": {
                    "client_id": google_creds['client_id'],
                    "client_secret": google_creds['client_secret'],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
                }
            }
            
            # Create flow with out-of-band redirect
            flow = Flow.from_client_config(
                client_config,
                scopes=['https://www.googleapis.com/auth/drive.file'],
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            
            # Get authorization URL
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                prompt='consent'
            )
            
            print("\n" + "="*60)
            print("Opening browser for Google authentication...")
            print("\nAfter authorizing, you'll see an authorization code.")
            print("Copy and paste that code below.")
            print("="*60)
            
            # Open browser
            webbrowser.open(auth_url)
            
            # Get authorization code from user
            auth_code = input("\nEnter authorization code: ").strip()
            
            if auth_code:
                # Exchange code for tokens
                flow.fetch_token(code=auth_code)
                
                # Save credentials
                self._save_google_tokens(flow.credentials)
                print("✓ Google Drive authentication successful!")
                return True
            else:
                print("✗ No authorization code provided")
                return False
                
        except Exception as e:
            print(f"✗ Google Drive authentication error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _save_sharepoint_tokens(self, token_result: Dict[str, Any]):
        """Save SharePoint tokens to user config"""
        # Calculate expiration time
        expires_in = token_result.get('expires_in', 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        # Prepare credentials
        sharepoint_creds = {
            'access_token': token_result['access_token'],
            'refresh_token': token_result.get('refresh_token', ''),
            'expires_at': expires_at.isoformat(),
            'token_type': 'Bearer',
            'scope': token_result.get('scope', ''),
            'authenticated_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Load existing config
        user_config = self.cloud_config.load_user_config()
        user_config['sharepoint'] = sharepoint_creds
        
        # Save updated config
        self.cloud_config.save_user_config(user_config)
        print(f"✓ Tokens saved to: {self.cloud_config.user_config_path}")
    
    def _save_google_tokens(self, credentials):
        """Save Google Drive tokens to user config"""
        google_creds = {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token or '',
            'expires_at': credentials.expiry.isoformat() if credentials.expiry else '',
            'token_type': 'Bearer',
            'scope': ' '.join(credentials.scopes) if hasattr(credentials, 'scopes') else '',
            'authenticated_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Load existing config
        user_config = self.cloud_config.load_user_config()
        user_config['google_drive'] = google_creds
        
        # Save updated config
        self.cloud_config.save_user_config(user_config)
        print(f"✓ Tokens saved to: {self.cloud_config.user_config_path}")
    
    def check_authentication_status(self):
        """Check and display current authentication status"""
        print("\n=== Authentication Status ===")
        
        # Check SharePoint
        sp_creds = self.cloud_config.get_user_credentials('sharepoint')
        if sp_creds and sp_creds.get('access_token'):
            expires_at = sp_creds.get('expires_at', '')
            if expires_at:
                try:
                    exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) < exp_time:
                        time_left = exp_time - datetime.now(timezone.utc)
                        print(f"✓ SharePoint: Authenticated (expires in {time_left})")
                    else:
                        print("✗ SharePoint: Token expired")
                except:
                    print("✗ SharePoint: Invalid token")
            else:
                print("✗ SharePoint: No expiration info")
        else:
            print("✗ SharePoint: Not authenticated")
        
        # Check Google Drive
        gd_creds = self.cloud_config.get_user_credentials('google_drive')
        if gd_creds and gd_creds.get('access_token'):
            expires_at = gd_creds.get('expires_at', '')
            if expires_at:
                try:
                    exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) < exp_time:
                        time_left = exp_time - datetime.now(timezone.utc)
                        print(f"✓ Google Drive: Authenticated (expires in {time_left})")
                    else:
                        print("✗ Google Drive: Token expired")
                except:
                    print("✗ Google Drive: Invalid token")
            else:
                print("✗ Google Drive: No expiration info")
        else:
            print("✗ Google Drive: Not authenticated")