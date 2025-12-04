# ============================================================================
# ASGARDEO JWT VALIDATION MIDDLEWARE - Agent Security
# ============================================================================
# This middleware validates OAuth 2.0 JWT tokens from Asgardeo for incoming
# A2A requests. It ensures only authenticated orchestrators can communicate
# with this agent.
#
# Security Flow:
# 1. Extract Authorization header from incoming request
# 2. Validate JWT signature using Asgardeo's public keys (JWKS)
# 3. Check token expiration
# 4. Verify audience matches this agent's client ID
# 5. Allow or reject request based on validation
# ============================================================================

import os
import time
from typing import Optional, Dict
import requests
from jose import jwt, JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class AsgardeoJWTMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that validates Asgardeo JWT tokens.
    
    This middleware intercepts all incoming HTTP requests and validates
    the OAuth 2.0 bearer token before allowing the request to proceed.
    
    Validates standard JWT tokens from Asgardeo with:
    - Signature verification (JWKS)
    - Expiration check
    - Issuer verification
    - Audience verification (token must be for this agent)
    """
    
    def __init__(
        self,
        app,
        jwks_url: str,
        issuer: str,
        required_scope: str,
        agent_id: str = None,
        api_resource_identifier: str = None,
        enabled: bool = True
    ):
        """
        Initialize the JWT validation middleware.
        
        Args:
            app: The Starlette application
            jwks_url: URL to fetch Asgardeo's public keys (JWKS endpoint)
            issuer: Expected token issuer (Asgardeo org URL)
            required_scope: Scope required to access this agent (for documentation)
            agent_id: This agent's application ID (for audience validation)
            api_resource_identifier: API Resource identifier (alternative audience)
            enabled: Whether authentication is enabled (for development)
        """
        super().__init__(app)
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.required_scope = required_scope
        self.agent_id = agent_id or os.getenv('APPOINTMENTS_APP_ID', '')
        self.api_resource_identifier = api_resource_identifier or os.getenv('API_RESOURCE_IDENTIFIER', '')
        self.enabled = enabled
        
        # Build list of valid audiences (agent ID and/or API Resource)
        self.valid_audiences = []
        if self.agent_id:
            self.valid_audiences.append(self.agent_id)
        if self.api_resource_identifier:
            self.valid_audiences.append(self.api_resource_identifier)
        
        # JWKS cache (public keys from Asgardeo)
        self._jwks_cache: Optional[Dict] = None
        self._jwks_cache_time: Optional[float] = None
        self._jwks_cache_duration = 86400  # 24 hours
        
        # Paths that don't require authentication
        self._public_paths = [
            '/.well-known/agent-card.json',  # Agent card is public
            '/health',  # Health check endpoint
        ]
    
    def _is_public_path(self, path: str) -> bool:
        """Check if the request path is public (doesn't require auth)."""
        return any(path.startswith(public_path) for public_path in self._public_paths)
    
    def _get_jwks(self) -> Dict:
        """
        Fetch JWKS (public keys) from Asgardeo.
        
        Caches keys for 24 hours to avoid excessive network calls.
        
        Returns:
            JWKS dictionary containing public keys
        """
        current_time = time.time()
        
        # Check if cache is still valid
        if (self._jwks_cache is not None and 
            self._jwks_cache_time is not None and
            current_time - self._jwks_cache_time < self._jwks_cache_duration):
            return self._jwks_cache
        
        # Cache expired or empty - fetch new keys
        try:
            response = requests.get(self.jwks_url, timeout=5)
            response.raise_for_status()
            
            self._jwks_cache = response.json()
            self._jwks_cache_time = current_time
            
            print(f"[Auth] Fetched JWKS from Asgardeo ({len(self._jwks_cache.get('keys', []))} keys)")
            
            return self._jwks_cache
            
        except Exception as e:
            print(f"[Auth] Failed to fetch JWKS: {e}")
            # If fetch fails but we have cached keys, use them
            if self._jwks_cache:
                print("[Auth] Using cached JWKS despite fetch failure")
                return self._jwks_cache
            raise
    
    def _validate_token(self, token: str) -> Dict:
        """
        Validate JWT token and return decoded payload.
        
        Args:
            token: The JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            JWTError: If token is invalid
        """
        try:
            # ================================================================
            # STEP 1: Get JWKS (public keys)
            # ================================================================
            jwks = self._get_jwks()
            
            # ================================================================
            # STEP 2: Decode JWT header to get key ID
            # ================================================================
            unverified_header = jwt.get_unverified_header(token)
            key_id = unverified_header.get('kid')
            
            # ================================================================
            # STEP 3: Find matching public key
            # ================================================================
            rsa_key = None
            for key in jwks['keys']:
                if key['kid'] == key_id:
                    rsa_key = {
                        'kty': key['kty'],
                        'kid': key['kid'],
                        'use': key['use'],
                        'n': key['n'],
                        'e': key['e']
                    }
                    break
            
            if not rsa_key:
                raise JWTError(f"Public key not found for kid: {key_id}")
            
            # ================================================================
            # STEP 4: Verify signature and decode payload
            # ================================================================
            # This validates:
            # - Signature is valid (token not tampered with)
            # - Token is not expired
            # - Issuer matches expected value
            # Note: We'll validate audience manually since we accept multiple valid audiences
            
            # First decode without verification to see the issuer
            unverified_payload = jwt.get_unverified_claims(token)
            token_issuer = unverified_payload.get('iss', 'MISSING')
            
            print(f"[Auth] Token issuer: {token_issuer}")
            print(f"[Auth] Expected issuer: {self.issuer}")
            
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=['RS256'],
                issuer=self.issuer,
                options={
                    'verify_signature': True,
                    'verify_exp': True,
                    'verify_iss': True,
                    'verify_aud': False,  # We'll validate audience manually
                }
            )
            
            # ================================================================
            # STEP 5: Manually validate audience (support multiple valid audiences)
            # ================================================================
            token_audience = payload.get('aud')
            if self.valid_audiences and token_audience not in self.valid_audiences:
                raise JWTError(f"Invalid audience. Expected one of {self.valid_audiences}, got {token_audience}")
            
            return payload
            
        except JWTError as e:
            raise JWTError(f"Token validation failed: {str(e)}")
    
    async def dispatch(self, request: Request, call_next):
        """
        Intercept incoming request and validate authentication.
        
        This is called for every incoming HTTP request.
        
        Args:
            request: The incoming HTTP request
            call_next: Function to call next middleware or endpoint
            
        Returns:
            HTTP response (either from endpoint or error response)
        """
        # ====================================================================
        # STEP 1: Check if authentication is enabled
        # ====================================================================
        if not self.enabled:
            # Auth disabled (development mode) - allow all requests
            return await call_next(request)
        
        # ====================================================================
        # STEP 2: Check if path is public
        # ====================================================================
        if self._is_public_path(request.url.path):
            # Public endpoint - no auth required
            return await call_next(request)
        
        # ====================================================================
        # STEP 3: Extract Authorization header
        # ====================================================================
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "error_description": "Missing authentication token"
                }
            )
        
        # ====================================================================
        # STEP 4: Extract token from "Bearer <token>" format
        # ====================================================================
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return JSONResponse(
                status_code=401,
                content={
                    "error": "invalid_request",
                    "error_description": "Invalid Authorization header format. Expected: Bearer <token>"
                }
            )
        
        token = parts[1]
        
        # ====================================================================
        # STEP 5: Validate token
        # ====================================================================
        try:
            payload = self._validate_token(token)
            
            # Token valid - attach payload to request state for later use
            request.state.token_payload = payload
            request.state.client_id = payload.get('client_id')
            
            # Log successful authentication
            aud = payload.get('aud', 'unknown')
            sub = payload.get('sub', 'unknown')
            scope = payload.get('scope', 'NOT IN TOKEN')
            print(f"[Auth] ✓ Token validated successfully")
            print(f"[Auth]   - Audience: {aud} (matches agent ID)")
            print(f"[Auth]   - Subject: {sub}")
            print(f"[Auth]   - Scope in JWT: {scope}")
            if scope == 'NOT IN TOKEN':
                print(f"[Auth]   ℹ️  Note: Scope not in JWT claims - using audience-based security")
            
            # Allow request to proceed to agent logic
            return await call_next(request)
            
        except JWTError as e:
            print(f"[Auth] ❌ Token validation failed: {str(e)}")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "invalid_token",
                    "error_description": str(e)
                }
            )
        except Exception as e:
            # Unexpected error during validation
            print(f"[Auth] Unexpected error during token validation: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "server_error",
                    "error_description": "Token validation failed due to server error"
                }
            )


# ============================================================================
# FACTORY FUNCTION - Create middleware from environment variables
# ============================================================================

def create_jwt_middleware_from_env(app, required_scope: str, agent_id: str = None):
    """
    Create JWT validation middleware using environment variables.
    
    Required environment variables:
    - ASGARDEO_JWKS_URL: URL to fetch public keys
    - ASGARDEO_ISSUER: Expected token issuer
    - ASGARDEO_AUTH_ENABLED: "true" or "false" (optional, defaults to true)
    - APPOINTMENTS_APP_ID: This agent's application ID
    
    Args:
        app: The Starlette application
        required_scope: The scope required to access this agent (for documentation)
        agent_id: This agent's application ID (optional, can be set via env var)
        
    Returns:
        Configured AsgardeoJWTMiddleware instance
    """
    jwks_url = os.getenv('ASGARDEO_JWKS_URL')
    issuer = os.getenv('ASGARDEO_ISSUER')
    enabled = os.getenv('ASGARDEO_AUTH_ENABLED', 'true').lower() == 'true'
    agent_id = agent_id or os.getenv('APPOINTMENTS_APP_ID', '')
    
    if not jwks_url or not issuer:
        print("[Auth] Warning: Asgardeo configuration missing. Authentication disabled.")
        print("[Auth] Set ASGARDEO_JWKS_URL and ASGARDEO_ISSUER to enable authentication.")
        enabled = False
    
    return AsgardeoJWTMiddleware(
        app=app,
        jwks_url=jwks_url or '',
        issuer=issuer or '',
        required_scope=required_scope,
        agent_id=agent_id,
        enabled=enabled
    )
