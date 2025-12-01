# ============================================================================
# ASGARDEO TOKEN MANAGER - OAuth 2.0 Client Credentials
# ============================================================================
# This module handles lazy token acquisition and caching for the orchestrator.
# Tokens are only fetched when needed (first agent call), not at startup.
#
# Flow:
# 1. get_token() is called when making an A2A request
# 2. Check if token exists and is still valid
# 3. If valid, return cached token (no network call)
# 4. If expired or missing, fetch new token from Asgardeo
# 5. Cache the new token for future requests
# ============================================================================

import os
import time
from typing import Optional
from authlib.integrations.httpx_client import AsyncOAuth2Client


class AsgardeoTokenManager:
    """
    Manages OAuth 2.0 access tokens for Asgardeo authentication.
    
    Features:
    - Lazy initialization (no token fetch until needed)
    - Automatic token caching
    - Automatic token refresh when expired
    - Thread-safe for async operations
    """
    
    def __init__(
        self, 
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "vaccination:read appointments:read"
    ):
        """
        Initialize the token manager with Asgardeo credentials.
        
        Args:
            token_url: Asgardeo OAuth 2.0 token endpoint
            client_id: Application client ID from Asgardeo
            client_secret: Application client secret from Asgardeo
            scope: Space-separated list of required scopes
        """
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        
        # Token cache (starts empty - lazy initialization)
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[float] = None
        
        # Buffer time before expiry to refresh (5 minutes)
        self._expiry_buffer = 300
    
    def _is_token_valid(self) -> bool:
        """
        Check if the cached token is still valid.
        
        Returns:
            True if token exists and hasn't expired, False otherwise
        """
        if self._access_token is None or self._token_expiry is None:
            return False
        
        # Check if token expires in the next 5 minutes
        current_time = time.time()
        return current_time < (self._token_expiry - self._expiry_buffer)
    
    async def get_token(self) -> str:
        """
        Get a valid access token, fetching a new one if necessary.
        
        This is the main method called by the auth interceptor.
        It implements lazy token acquisition:
        - First call: Fetches token from Asgardeo
        - Subsequent calls: Returns cached token (if still valid)
        - After expiry: Automatically refreshes token
        
        Returns:
            Valid OAuth 2.0 access token
            
        Raises:
            Exception: If token acquisition fails
        """
        # ====================================================================
        # STEP 1: Check if we already have a valid token
        # ====================================================================
        if self._is_token_valid():
            # Token is still valid - return from cache (no network call!)
            return self._access_token
        
        # ====================================================================
        # STEP 2: Token missing or expired - fetch new one
        # ====================================================================
        try:
            # Create OAuth 2.0 client
            client = AsyncOAuth2Client(
                client_id=self.client_id,
                client_secret=self.client_secret,
                scope=self.scope
            )
            
            print(f"[Auth] Requesting token from: {self.token_url}")
            print(f"[Auth] Client ID: {self.client_id[:10]}...")
            print(f"[Auth] Scope: {self.scope}")
            
            # Request token using client credentials flow
            # POST to Asgardeo token endpoint with:
            # - grant_type=client_credentials
            # - client_id=...
            # - client_secret=...
            # - scope=...
            token_response = await client.fetch_token(
                url=self.token_url,
                grant_type='client_credentials'
            )
            
            # ================================================================
            # STEP 3: Extract and cache token
            # ================================================================
            # Response format:
            # {
            #   "access_token": "eyJhbGciOiJSUzI1NiIs...",
            #   "token_type": "Bearer",
            #   "expires_in": 3600,
            #   "scope": "vaccination:read appointments:read"
            # }
            
            self._access_token = token_response['access_token']
            expires_in = token_response.get('expires_in', 3600)
            
            # Calculate absolute expiry time
            self._token_expiry = time.time() + expires_in
            
            print(f"[Auth] ✓ Acquired new Asgardeo token (expires in {expires_in}s)")
            
            return self._access_token
            
        except Exception as e:
            print(f"[Auth] ✗ Failed to acquire token from Asgardeo")
            print(f"[Auth] Error type: {type(e).__name__}")
            print(f"[Auth] Error message: {e}")
            print(f"[Auth] Check your Asgardeo configuration:")
            print(f"[Auth]   - Is the token URL correct?")
            print(f"[Auth]   - Are the client credentials valid?")
            print(f"[Auth]   - Are the scopes configured in Asgardeo?")
            raise Exception(f"Authentication failed: {e}")
    
    def invalidate_token(self):
        """
        Manually invalidate the cached token.
        
        Use this if you receive a 401 Unauthorized response,
        indicating the token might be invalid or revoked.
        Next call to get_token() will fetch a fresh token.
        """
        self._access_token = None
        self._token_expiry = None


# ============================================================================
# AUTH INTERCEPTOR FOR A2A CLIENT
# ============================================================================
# This interceptor automatically adds the Authorization header to all
# outgoing A2A requests
# ============================================================================

class AsgardeoAuthInterceptor:
    """
    HTTP interceptor that adds OAuth 2.0 bearer token to requests.
    
    This is used with A2AClient to automatically authenticate all
    agent-to-agent communication.
    """
    
    def __init__(self, token_manager: AsgardeoTokenManager):
        """
        Initialize the interceptor with a token manager.
        
        Args:
            token_manager: The token manager to get tokens from
        """
        self.token_manager = token_manager
    
    async def __call__(self, request):
        """
        Intercept outgoing request and add Authorization header.
        
        This is called automatically by httpx for every request.
        
        Args:
            request: The outgoing HTTP request
            
        Returns:
            Modified request with Authorization header
        """
        # Get a valid token (may fetch new one if needed)
        token = await self.token_manager.get_token()
        
        # Add Bearer token to request headers
        request.headers['Authorization'] = f'Bearer {token}'
        
        return request


# ============================================================================
# FACTORY FUNCTION - Convenient way to create token manager
# ============================================================================

def create_token_manager_from_env() -> AsgardeoTokenManager:
    """
    Create a token manager using environment variables.
    
    Required environment variables:
    - ASGARDEO_TOKEN_URL: OAuth 2.0 token endpoint
    - ASGARDEO_CLIENT_ID: Application client ID
    - ASGARDEO_CLIENT_SECRET: Application client secret
    - ASGARDEO_SCOPE: Required scopes (optional, defaults to standard scopes)
    - ASGARDEO_AUTH_ENABLED: Set to "false" to disable authentication
    
    Returns:
        Configured AsgardeoTokenManager instance, or None if disabled
        
    Raises:
        ValueError: If required environment variables are missing (when enabled)
    """
    # Check if authentication is enabled
    auth_enabled = os.getenv('ASGARDEO_AUTH_ENABLED', 'true').lower() == 'true'
    if not auth_enabled:
        raise ValueError("Asgardeo authentication is disabled (ASGARDEO_AUTH_ENABLED=false)")
    
    token_url = os.getenv('ASGARDEO_TOKEN_URL')
    client_id = os.getenv('ASGARDEO_CLIENT_ID')
    client_secret = os.getenv('ASGARDEO_CLIENT_SECRET')
    scope = os.getenv('ASGARDEO_SCOPE', 'vaccination:read appointments:read')
    
    if not token_url or not client_id or not client_secret:
        raise ValueError(
            "Missing Asgardeo configuration. Please set:\n"
            "  - ASGARDEO_TOKEN_URL\n"
            "  - ASGARDEO_CLIENT_ID\n"
            "  - ASGARDEO_CLIENT_SECRET"
        )
    
    return AsgardeoTokenManager(
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
        scope=scope
    )
