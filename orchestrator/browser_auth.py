"""
Browser-based Authentication using Authorization Code Flow with PKCE
This opens a browser for the user to sign in via Asgardeo

Implements OAuth Extension for AI Agents (IETF draft) per Asgardeo documentation:
- requested_actor parameter in authorize URL
- Actor token in Authorization header during code exchange
- Results in delegated JWT for agent to act on behalf of user
"""

import base64
import hashlib
import secrets
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse
from typing import Optional, List, Tuple
import httpx


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to receive the OAuth callback."""
    
    authorization_code: Optional[str] = None
    error: Optional[str] = None
    error_description: Optional[str] = None
    
    def do_GET(self):
        """Handle the OAuth callback request."""
        try:
            query = parse_qs(urlparse(self.path).query)
            
            # Check for error response from Asgardeo
            if 'error' in query:
                CallbackHandler.error = query['error'][0]
                CallbackHandler.error_description = query.get('error_description', ['Unknown error'])[0]
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                error_msg = f"""
                    <html>
                    <body>
                        <h1>Authentication Error</h1>
                        <p><strong>Error:</strong> {CallbackHandler.error}</p>
                        <p><strong>Description:</strong> {CallbackHandler.error_description}</p>
                        <p>Please close this window and check the console for details.</p>
                    </body>
                    </html>
                """
                self.wfile.write(error_msg.encode())
                return
            
            if 'code' in query:
                CallbackHandler.authorization_code = query['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"""
                    <html>
                    <body>
                        <h1>Authentication Successful!</h1>
                        <p>You can close this window and return to the application.</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                """)
            else:
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Error: No authorization code received</h1></body></html>")
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f"<html><body><h1>Server Error: {e}</h1></body></html>".encode())
    
    def log_message(self, format, *args):
        """Suppress server logs."""
        pass


class BrowserAuthenticator:
    """
    Handles user authentication via browser using Authorization Code Flow with PKCE.
    
    Implements OAuth Extension for AI Agents (IETF draft) per Asgardeo documentation:
    1. Include requested_actor in authorize URL (identifies which agent will act on behalf of user)
    2. Get actor_token for the agent separately (client credentials)
    3. Exchange authorization code with actor_token in Authorization header
    4. Receive delegated JWT that encapsulates user-agent relationship
    """
    
    def __init__(
        self,
        authorize_url: str,
        token_url: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:8080/callback",
        scope: str = "openid profile vaccination:read appointments:read",
        api_resource_identifier: str = None
    ):
        self.authorize_url = authorize_url
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scope = scope or "openid profile vaccination:read appointments:read"
        self.api_resource_identifier = api_resource_identifier
        
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
    
    def _generate_pkce_pair(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        return code_verifier, code_challenge
    
    async def authenticate_user_with_delegation(
        self,
        actor_client_id: str,
        actor_client_secret: str,
        requested_scope: str
    ) -> str:
        """
        Authenticate user with OAuth Extension for AI Agents.
        
        This implements the full Asgardeo AI Agent delegation flow:
        1. Get actor_token for the agent (client credentials)
        2. Redirect user to authorize with requested_actor parameter
        3. Exchange auth code with actor_token in Authorization header
        4. Return delegated token
        
        Args:
            actor_client_id: The AI agent's client ID (requested_actor)
            actor_client_secret: The AI agent's client secret
            requested_scope: Scope to request for this delegation
            
        Returns:
            Delegated access token for agent to act on behalf of user
        """
        print("\n" + "="*70)
        print("🔐 OAUTH EXTENSION FOR AI AGENTS - DELEGATION FLOW")
        print("="*70)
        
        # Step 1: Get actor_token for the agent
        print(f"\n📍 Step 1: Obtaining actor_token for agent {actor_client_id[:15]}...")
        actor_token = await self._get_actor_token(actor_client_id, actor_client_secret, requested_scope)
        print(f"  ✓ Actor token obtained: {actor_token[:30]}...")
        
        # Step 2: Get authorization code with requested_actor
        print(f"\n📍 Step 2: User authentication with requested_actor...")
        auth_code, code_verifier = await self._get_authorization_code_with_actor(
            actor_client_id, 
            requested_scope
        )
        print(f"  ✓ Authorization code received")
        
        # Step 3: Exchange code with actor_token in Authorization header
        print(f"\n📍 Step 3: Exchanging code with actor_token...")
        delegated_token = await self._exchange_code_with_actor_token(
            auth_code,
            code_verifier,
            actor_token,
            requested_scope
        )
        
        print(f"\n✓ Delegated token obtained!")
        print(f"  Token: {delegated_token[:30]}...")
        print("="*70)
        
        return delegated_token
    
    async def _get_actor_token(self, client_id: str, client_secret: str, scope: str) -> str:
        """Get actor_token for an agent using client credentials with JWT assertion."""
        import jwt
        import time
        
        async with httpx.AsyncClient() as client:
            # Create JWT assertion
            # For Asgardeo, the aud should be the token issuer (without /token endpoint)
            now = int(time.time())
            token_issuer = self.token_url.replace('/token', '')
            
            jwt_payload = {
                'iss': client_id,
                'sub': client_id,
                'aud': token_issuer,  # Use issuer URL, not token endpoint
                'exp': now + 300,  # 5 minutes expiration
                'iat': now,
                'jti': secrets.token_urlsafe(16)
            }
            
            client_assertion = jwt.encode(jwt_payload, client_secret, algorithm='HS256')
            
            # Ensure scope includes openid
            scopes = set(scope.split())
            # scopes.add('openid')
            combined_scope = ' '.join(scopes)
            
            response = await client.post(
                self.token_url,
                data={
                    'grant_type': 'client_credentials',
                    'scope': combined_scope,
                    'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
                    'client_assertion': client_assertion
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get actor token: {response.text}")
            
            return response.json()['access_token']
    
    async def _get_authorization_code_with_actor(
        self,
        requested_actor: str,
        scope: str
    ) -> Tuple[str, str]:
        """
        Get authorization code with requested_actor parameter.
        
        Per Asgardeo docs: Include requested_actor in authorize URL
        """
        code_verifier, code_challenge = self._generate_pkce_pair()
        state = secrets.token_urlsafe(16)
        
        # Build authorization URL WITH requested_actor
        auth_params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': scope,
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'requested_actor': requested_actor,  # Key parameter for AI agent delegation!
        }
        
        # Add resource parameter if API Resource identifier is configured
        if self.api_resource_identifier:
            auth_params['resource'] = self.api_resource_identifier
        
        auth_url = f"{self.authorize_url}?{urlencode(auth_params)}"
        
        print(f"\n🌐 Opening browser for authentication...")
        print(f"   requested_actor: {requested_actor}")
        print(f"   scope: {scope}")
        
        # Open browser
        webbrowser.open(auth_url)
        
        # Start local server to receive callback
        print(f"\n⏳ Waiting for user consent...")
        
        # Reset callback handler
        CallbackHandler.authorization_code = None
        
        server = HTTPServer(('localhost', 8080), CallbackHandler)
        server.timeout = 300
        server.handle_request()
        
        if not CallbackHandler.authorization_code:
            raise Exception("Failed to receive authorization code")
        
        return CallbackHandler.authorization_code, code_verifier
    
    async def _exchange_code_with_actor_token(
        self,
        auth_code: str,
        code_verifier: str,
        actor_token: str,
        scope: str
    ) -> str:
        """
        Exchange authorization code WITH actor_token to get delegated token.
        
        Per Asgardeo AI Agent Authentication:
        When requested_actor is used in authorization, the actor_token MUST be 
        provided in the code exchange request (not a separate token exchange).
        """
        async with httpx.AsyncClient() as client:
            print(f"\n🔍 Exchanging auth code with actor_token...")
            
            credentials = f"{self.client_id}:{self.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            # Include actor_token in the code exchange request
            code_exchange_data = {
                'grant_type': 'authorization_code',
                'code': auth_code,
                'redirect_uri': self.redirect_uri,
                'code_verifier': code_verifier,
                'actor_token': actor_token,
                'actor_token_type': 'urn:ietf:params:oauth:token-type:access_token'
            }
            
            # Add resource parameter if API Resource identifier is configured
            if self.api_resource_identifier:
                code_exchange_data['resource'] = self.api_resource_identifier
            
            print(f"  grant_type: authorization_code")
            print(f"  actor_token: <provided>")
            print(f"  actor_token_type: access_token")
            
            response = await client.post(
                self.token_url,
                data=code_exchange_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': f'Basic {encoded_credentials}'
                }
            )
            
            print(f"\n  📥 Response Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"  📥 Response Body: {response.text}")
                raise Exception(f"Failed to exchange code: {response.text}")
            
            token_response = response.json()
            delegated_token = token_response['access_token']
            
            print(f"  ✓ Delegated token obtained: {delegated_token[:30]}...")
            
            return delegated_token
    
    async def authenticate_user(self, requested_actors: Optional[List[str]] = None) -> str:
        """
        User authentication with optional delegation to AI agents.
        
        If requested_actors is provided, includes them in the authorization request
        so the resulting token has delegation claims for those agents.
        
        Args:
            requested_actors: List of agent client IDs to request delegation for
            
        Returns:
            Access token string (with delegation claims if requested_actors provided)
        """
        print("\n" + "="*70)
        print("🔐 INITIATING USER AUTHENTICATION (BROWSER)")
        print("="*70)
        
        # Generate PKCE parameters
        code_verifier, code_challenge = self._generate_pkce_pair()
        state = secrets.token_urlsafe(16)
        
        # Build authorization URL
        auth_params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'resource': self.api_resource_identifier
        }
        
        # Add resource parameter if API Resource identifier is configured
        if self.api_resource_identifier:
            auth_params['resource'] = self.api_resource_identifier
        
        # Add requested_actor for delegation (can be multiple)
        if requested_actors:
            # Asgardeo accepts multiple requested_actor values
            for actor in requested_actors:
                auth_params['requested_actor'] = actor  # Will be last one if multiple
            print(f"\n📍 Requesting delegation for agents: {requested_actors}")
        
        auth_url = f"{self.authorize_url}?{urlencode(auth_params)}"
        
        # If multiple actors, add them manually (urlencode doesn't handle duplicates well)
        if requested_actors and len(requested_actors) > 1:
            actor_params = '&'.join([f'requested_actor={actor}' for actor in requested_actors])
            auth_url = f"{self.authorize_url}?{urlencode({k:v for k,v in auth_params.items() if k != 'requested_actor'})}&{actor_params}"
        
        print(f"\n🌐 Opening browser for authentication...")
        print(f"   If browser doesn't open, visit: {auth_url}")
        
        # Open browser
        webbrowser.open(auth_url)
        
        # Start local server to receive callback
        print(f"\n⏳ Waiting for authentication callback on {self.redirect_uri}")
        print(f"   Please sign in via the browser...")
        
        # Reset callback handler
        CallbackHandler.authorization_code = None
        CallbackHandler.error = None
        CallbackHandler.error_description = None
        
        # Start local server to receive callback
        try:
            server = HTTPServer(('localhost', 8080), CallbackHandler)
            server.timeout = 300
            print(f"   Server started on port 8080...")
        except OSError as e:
            if "Address already in use" in str(e) or "10048" in str(e):
                print(f"\n⚠️  Port 8080 is already in use. Trying port 8081...")
                server = HTTPServer(('localhost', 8081), CallbackHandler)
                server.timeout = 300
                # Note: You may need to update redirect_uri in Asgardeo to include 8081
            else:
                raise
        
        server.handle_request()
        
        # Check for errors from Asgardeo
        if CallbackHandler.error:
            raise Exception(f"Asgardeo error: {CallbackHandler.error} - {CallbackHandler.error_description}")
        
        if not CallbackHandler.authorization_code:
            raise Exception("Failed to receive authorization code")
        
        print(f"\n✓ Authorization code received")
        
        # Exchange code for token (standard flow - Basic Auth)
        async with httpx.AsyncClient() as client:
            credentials = f"{self.client_id}:{self.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            token_data = {
                'grant_type': 'authorization_code',
                'code': CallbackHandler.authorization_code,
                'redirect_uri': self.redirect_uri,
                'code_verifier': code_verifier,
                'resource': self.api_resource_identifier,
            }
            
            # Add resource parameter if API Resource identifier is configured
            if self.api_resource_identifier:
                token_data['resource'] = self.api_resource_identifier
            
            response = await client.post(
                self.token_url,
                data=token_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': f'Basic {encoded_credentials}'
                }
            )
            
            if response.status_code != 200:
                print(f"\n✗ Token exchange failed")
                print(f"  Status: {response.status_code}")
                print(f"  Response: {response.text}")
                raise Exception(f"Failed to exchange code for token: {response.text}")
            
            token_response = response.json()
            self._access_token = token_response['access_token']
            self._refresh_token = token_response.get('refresh_token')
            
            print(f"\n✓ Access token obtained")
            print(f"  Token: {self._access_token[:30]}...")
            print(f"  Expires in: {token_response.get('expires_in', 'unknown')} seconds")
            print("="*70)
            
            return self._access_token


def create_browser_authenticator_from_env():
    """Create BrowserAuthenticator from environment variables."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    return BrowserAuthenticator(
        authorize_url=os.getenv('ASGARDEO_AUTHORIZE_URL'),
        token_url=os.getenv('ASGARDEO_TOKEN_URL'),
        client_id=os.getenv('ASGARDEO_CLIENT_ID'),
        client_secret=os.getenv('ASGARDEO_CLIENT_SECRET'),
        redirect_uri='http://localhost:8080/callback',
        scope=os.getenv('ASGARDEO_SCOPE', 'openid profile vaccination:read appointments:read'),
        api_resource_identifier=os.getenv('API_RESOURCE_IDENTIFIER')
    )
