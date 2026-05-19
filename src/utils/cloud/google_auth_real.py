#!/usr/bin/env python3
"""Google Drive authentication with real credentials - works like normal apps!"""

import webbrowser
import socket
import json
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

class AuthHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback"""
    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = '''
            <html>
            <head>
                <title>Success!</title>
                <style>
                    body { 
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        text-align: center; 
                        padding: 50px;
                        background: #f0f0f0;
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        max-width: 500px;
                        margin: 0 auto;
                    }
                    .success { 
                        color: #0F9D58; 
                        font-size: 48px;
                        margin-bottom: 20px;
                    }
                    h1 { 
                        color: #333; 
                        font-size: 24px;
                        margin: 20px 0;
                    }
                    p { 
                        color: #666; 
                        font-size: 16px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success">✅</div>
                    <h1>Successfully connected to Google Drive!</h1>
                    <p>You can close this window and return to Document Manager.</p>
                    <p style="font-size: 14px; color: #999;">This window will close automatically in 3 seconds...</p>
                </div>
                <script>setTimeout(() => window.close(), 3000);</script>
            </body>
            </html>
            '''
            self.wfile.write(html.encode())
        else:
            self.send_response(400)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logs

class GoogleAuthReal:
    """Google authentication with environment-based credentials"""
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        
        # Load OAuth credentials from environment variables
        from config.oauth_config import OAuthConfig
        oauth_config = OAuthConfig()
        google_creds = oauth_config.get_google_credentials()
        
        if not google_creds['client_id'] or not google_creds['client_secret']:
            raise ValueError(
                "Google OAuth credentials not found in environment variables. "
                "Please copy .env.template to .env and add your credentials."
            )
        
        self.client_id = google_creds['client_id']
        self.client_secret = google_creds['client_secret']
        self.redirect_port = self._find_free_port()
        
    def _find_free_port(self):
        """Find a free port"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    def authenticate(self) -> bool:
        """Authenticate with Google - just like any normal app!"""
        try:
            print("\n🔐 Connecting to Google Drive...")
            print("This works just like logging into any app!")
            
            # Build OAuth URL
            redirect_uri = f"http://localhost:{self.redirect_port}"
            auth_url = (
                "https://accounts.google.com/o/oauth2/v2/auth?"
                f"client_id={self.client_id}&"
                f"redirect_uri={redirect_uri}&"
                "response_type=code&"
                "scope=https://www.googleapis.com/auth/drive.file&"
                "access_type=offline&"
                "prompt=consent"
            )
            
            # Start local server
            server = HTTPServer(('localhost', self.redirect_port), AuthHandler)
            server.auth_code = None
            server.timeout = 120
            
            server_thread = threading.Thread(target=server.handle_request)
            server_thread.daemon = True
            server_thread.start()
            
            # Open browser
            print("📱 Opening browser for Google login...")
            webbrowser.open(auth_url)
            
            print("⏳ Waiting for you to login with Google...")
            print("   (The browser will redirect back automatically)")
            
            # Wait for auth
            server_thread.join(timeout=120)
            server.server_close()
            
            if server.auth_code:
                print("🔄 Getting access tokens...")
                
                # Exchange code for token
                import requests
                response = requests.post(
                    'https://oauth2.googleapis.com/token',
                    data={
                        'code': server.auth_code,
                        'client_id': self.client_id,
                        'client_secret': self.client_secret,
                        'redirect_uri': redirect_uri,
                        'grant_type': 'authorization_code'
                    }
                )
                
                if response.status_code == 200:
                    tokens = response.json()
                    self._save_tokens(tokens)
                    print("✅ Successfully connected to Google Drive!")
                    print("📁 Documents will now sync automatically when approved!")
                    return True
                else:
                    print(f"❌ Failed to get tokens: {response.text}")
                    return False
            else:
                print("❌ Login was cancelled or timed out")
                return False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def _save_tokens(self, tokens):
        """Save tokens"""
        expires_in = tokens.get('expires_in', 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        google_creds = {
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token', ''),
            'expires_at': expires_at.isoformat(),
            'token_type': 'Bearer',
            'scope': 'https://www.googleapis.com/auth/drive.file',
            'authenticated_at': datetime.now(timezone.utc).isoformat()
        }
        
        user_config = self.cloud_config.load_user_config()
        user_config['google_drive'] = google_creds
        self.cloud_config.save_user_config(user_config)
        
    def check_status(self):
        """Check if authenticated"""
        creds = self.cloud_config.get_user_credentials('google_drive')
        
        if not creds or not creds.get('access_token'):
            return False, "Not authenticated"
            
        expires_at = creds.get('expires_at', '')
        if expires_at:
            try:
                exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) < exp_time:
                    time_left = exp_time - datetime.now(timezone.utc)
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    return True, f"Authenticated ({hours}h {minutes}m left)"
                else:
                    return False, "Token expired"
            except Exception as e:
                from utils.error_logger import logger
                from utils.user_notifications import notify_user_of_network_error
                
                logger.error(f"Google token validation failed", e)
                notify_user_of_network_error(
                    "Google Drive",
                    "Error al validar autenticación con Google Drive. Las funciones de nube no estarán disponibles."
                )
                return False, "Invalid token"
        else:
            return False, "No expiration info"