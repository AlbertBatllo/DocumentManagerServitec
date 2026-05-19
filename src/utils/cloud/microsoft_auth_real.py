#!/usr/bin/env python3
"""Microsoft SharePoint authentication with real credentials - works like normal apps!"""

import webbrowser
import socket
import json
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import requests

class MicrosoftAuthHandler(BaseHTTPRequestHandler):
    """Handle Microsoft OAuth callback"""
    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.server.state = params.get('state', [''])[0]
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
                        color: #0078d4; 
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
                    <h1>Successfully connected to SharePoint!</h1>
                    <p>You can close this window and return to Document Manager.</p>
                    <p style="font-size: 14px; color: #999;">This window will close automatically in 3 seconds...</p>
                </div>
                <script>setTimeout(() => window.close(), 3000);</script>
            </body>
            </html>
            '''
            self.wfile.write(html.encode())
        elif 'error' in params:
            self.server.auth_error = params['error'][0]
            self.server.error_description = params.get('error_description', [''])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error_html = f'''
            <html>
            <head>
                <title>Authentication Error</title>
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        text-align: center; 
                        padding: 50px;
                        background: #f0f0f0;
                    }}
                    .container {{
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        max-width: 500px;
                        margin: 0 auto;
                    }}
                    .error {{ 
                        color: #d13438; 
                        font-size: 48px;
                        margin-bottom: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error">❌</div>
                    <h1>Authentication Failed</h1>
                    <p>Error: {params.get('error', ['Unknown'])[0]}</p>
                    <p>{params.get('error_description', [''])[0]}</p>
                </div>
            </body>
            </html>
            '''
            self.wfile.write(error_html.encode())
        else:
            self.send_response(400)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logs

class MicrosoftAuthReal:
    """Microsoft SharePoint authentication with environment-based credentials"""
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        
        # Load OAuth credentials from environment
        from config.oauth_config import OAuthConfig
        oauth_config = OAuthConfig()
        microsoft_creds = oauth_config.get_microsoft_credentials()
        
        client_id = microsoft_creds.get('client_id', '')
        client_secret = microsoft_creds.get('client_secret', '')
        
        if not client_id or not client_secret:
            raise ValueError(
                "Microsoft OAuth credentials not found in environment variables. "
                "Please check your .env file contains MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET."
            )
        
        self.client_id = client_id
        self.client_secret = client_secret
        # Use a fixed port that we'll configure in Azure
        self.redirect_port = 8080
        
    def _find_free_port(self):
        """Find a free port"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    def _find_available_port(self, preferred_ports):
        """Find an available port from a list of preferred ports"""
        for port in preferred_ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                continue
        
        # If none of the preferred ports work, fall back to any available port
        return self._find_free_port()
    
    def authenticate(self) -> bool:
        """Authenticate with Microsoft SharePoint - just like any normal app!"""
        try:
            print("\n🔐 Connecting to SharePoint/OneDrive...")
            print("This works just like logging into any app!")
            
            # Build OAuth URL - using 'organizations' instead of 'common' for single-tenant apps
            redirect_uri = f"http://localhost:{self.redirect_port}/microsoft/callback"
            auth_url = (
                "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?"
                f"client_id={self.client_id}&"
                f"redirect_uri={redirect_uri}&"
                "response_type=code&"
                "response_mode=query&"
                "scope=Files.ReadWrite.All+offline_access&"
                "state=auth_session"
            )
            
            # Start local server
            server = HTTPServer(('localhost', self.redirect_port), MicrosoftAuthHandler)
            server.auth_code = None
            server.auth_error = None
            server.error_description = None
            server.state = None
            server.timeout = 120
            
            server_thread = threading.Thread(target=server.handle_request)
            server_thread.daemon = True
            server_thread.start()
            
            # Open browser
            print("📱 Opening browser for Microsoft login...")
            webbrowser.open(auth_url)
            
            print("⏳ Waiting for you to login with Microsoft...")
            print("   (The browser will redirect back automatically)")
            
            # Wait for auth
            server_thread.join(timeout=120)
            server.server_close()
            
            # Check for errors first
            if server.auth_error:
                print(f"❌ Authentication error: {server.auth_error}")
                if server.error_description:
                    print(f"   Description: {server.error_description}")
                return False
            
            if server.auth_code:
                print("🔄 Getting access tokens...")
                
                # Exchange code for token
                token_data = {
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': server.auth_code,
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code',
                    'scope': 'Files.ReadWrite.All offline_access'
                }
                
                response = requests.post(
                    'https://login.microsoftonline.com/organizations/oauth2/v2.0/token',
                    data=token_data
                )
                
                if response.status_code == 200:
                    tokens = response.json()
                    self._save_tokens(tokens)
                    print("✅ Successfully connected to SharePoint/OneDrive!")
                    print("📁 Documents will now sync automatically when approved!")
                    return True
                else:
                    print(f"❌ Failed to get tokens: {response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"   Error: {error_data.get('error', 'Unknown error')}")
                        print(f"   Description: {error_data.get('error_description', '')}")
                    except Exception as e:
                        from utils.error_logger import logger
                        logger.warning(f"Failed to parse error response from Microsoft auth", {"error": str(e), "response_text": response.text})
                        print(f"   Response: {response.text}")
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
        
        sharepoint_creds = {
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token', ''),
            'expires_at': expires_at.isoformat(),
            'token_type': 'Bearer',
            'scope': tokens.get('scope', 'Files.ReadWrite.All offline_access'),
            'authenticated_at': datetime.now(timezone.utc).isoformat()
        }
        
        user_config = self.cloud_config.load_user_config()
        user_config['sharepoint'] = sharepoint_creds
        self.cloud_config.save_user_config(user_config)
        
    def check_status(self):
        """Check if authenticated"""
        creds = self.cloud_config.get_user_credentials('sharepoint')
        
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
                
                logger.error(f"Microsoft token validation failed", e)
                notify_user_of_network_error(
                    "Microsoft SharePoint",
                    "Error al validar autenticación con Microsoft SharePoint. Las funciones de nube no estarán disponibles."
                )
                return False, "Invalid token"
        else:
            return False, "No expiration info"