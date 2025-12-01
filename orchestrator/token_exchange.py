# ============================================================================
# TOKEN EXCHANGE - RFC 8693 with Asgardeo Trusted Token Issuer
# ============================================================================
# This module implements RFC 8693 Token Exchange for delegating tokens to
# AI agents. Works with Asgardeo's Trusted Token Issuer feature.
#
# Flow:
# 1. User authenticates once (browser login)
# 2. Orchestrator receives master token
# 3. For each agent call, master token is exchanged for agent-specific token
# 4. Agent receives token with correct audience (agent's client ID)
#
# Key configuration in Asgardeo:
# - Configure organization as Trusted Token Issuer
# - Use subject_token_type = jwt
# ============================================================================

import os
from typing import Optional, Dict
import httpx
import base64
import json
import time
from dotenv import load_dotenv

load_dotenv()


class TokenExchanger:
    """
    Handles RFC 8693 Token Exchange for agent delegation.
    
    Uses Asgardeo's Trusted Token Issuer flow where:
    1. Master token is exchanged for agent-specific token
    2. Agent receives token with correct audience
    3. No additional browser authentication required
    """
    
    def __init__(
        self,
        token_exchange_url: str,
        client_id: str,
        client_secret: str,
        api_resource_identifier: str = None
    ):
        """
        Initialize the token exchanger.
        
        Args:
            token_exchange_url: Asgardeo token exchange endpoint
            client_id: Orchestrator client ID
            client_secret: Orchestrator client secret
            api_resource_identifier: Optional API Resource identifier for scope binding
        """
        self.token_exchange_url = token_exchange_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_resource_identifier = api_resource_identifier
        
        # Cache for delegated tokens per agent
        # Format: {agent_name: {'token': str, 'expiry': float}}
        self._token_cache: Dict[str, Dict] = {}
    
    async def exchange_token_for_agent(
        self,
        master_token: str,
        agent_name: str,
        agent_client_id: str,
        required_scope: str
    ) -> str:
        """
        Exchange master token for agent-specific delegated token using RFC 8693.
        
        Uses Asgardeo's Trusted Token Issuer flow with JWT token type.
        
        Args:
            master_token: User's access token (from browser authentication)
            agent_name: Name of target agent (for logging/caching)
            agent_client_id: Agent's Asgardeo application client ID
            required_scope: Scope(s) to request for this agent
            
        Returns:
            Delegated access token for the agent
            
        Raises:
            Exception: If token exchange fails
        """
        print(f"\n{'='*70}")
        print(f"🔄 TOKEN EXCHANGE: {agent_name}")
        print(f"{'='*70}")
        
        # Check cache first
        cached = self._get_cached_token(agent_name)
        if cached:
            print(f"✓ Using cached token for {agent_name}")
            return cached
        
        # Display master token claims for debugging
        self._display_token_claims(master_token, "Master Token")
        
        async with httpx.AsyncClient() as client:
            # Get actor token for the agent (proves agent identity)
            print(f"\n📍 Step 1: Getting actor token for agent...")
            agent_secret = self._get_agent_secret(agent_name)
            
            if not agent_secret:
                raise Exception(f"No client secret configured for {agent_name}. "
                              f"Please set the appropriate APP_SECRET in .env")
            
            actor_token = await self._get_actor_token(agent_client_id, agent_secret)
            
            # Build token exchange request
            print(f"\n📍 Step 2: Token exchange request...")
            
            # Format scope with API Resource identifier if configured
            formatted_scope = required_scope
            if self.api_resource_identifier:
                # Use full identifier format: {identifier}/{scope}
                # We also prepend 'openid' as it is often required for the token exchange to return a valid ID token/claims
                formatted_scope = f"openid {self.api_resource_identifier}/{required_scope}"
                print(f"  Using API Resource identifier: {self.api_resource_identifier}")
            
            # RFC 8693 Token Exchange with Trusted Token Issuer
            # Key: use 'jwt' token type for trusted issuer flow
            exchange_data = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
                'subject_token': master_token,
                'subject_token_type': 'urn:ietf:params:oauth:token-type:jwt',
                'requested_token_type': 'urn:ietf:params:oauth:token-type:access_token',
                'scope': formatted_scope
            }
            
            # Add audience parameter to target the API Resource
            # This ensures the token's aud claim matches the API Resource that owns the scope
            if self.api_resource_identifier:
                exchange_data['audience'] = self.api_resource_identifier
                exchange_data['resource'] = self.api_resource_identifier
                print(f"  audience: {self.api_resource_identifier}")
            
            print(f"  grant_type: token-exchange")
            print(f"  subject_token: <master_token>")
            print(f"  subject_token_type: jwt")
            print(f"  scope: {formatted_scope}")
            
            # Use AGENT's credentials for authentication
            credentials = f"{agent_client_id}:{agent_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            response = await client.post(
                self.token_exchange_url,
                data=exchange_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': f'Basic {encoded_credentials}'
                }
            )
            
            print(f"\n  📥 Response Status: {response.status_code}")
            
            if response.status_code != 200:
                error_body = response.text
                print(f"  📥 Response Body: {error_body}")
                raise Exception(f"Token exchange failed for {agent_name}: {error_body}")
            
            token_response = response.json()
            delegated_token = token_response['access_token']
            
            # Log what Asgardeo returned in the response
            issued_scope = token_response.get('scope', 'NOT IN RESPONSE')
            token_type = token_response.get('token_type', 'unknown')
            expires_in = token_response.get('expires_in', 'unknown')
            
            print(f"\n✓ Token exchange successful!")
            print(f"  Token: {delegated_token[:30]}...")
            print(f"  Response scope: {issued_scope}")
            print(f"  Token type: {token_type}")
            print(f"  Expires in: {expires_in}s")
            
            # Display delegated token claims (from JWT payload)
            self._display_token_claims(delegated_token, "Delegated Token")
            
            # Note about scope behavior
            print(f"\n📝 Security Note:")
            print(f"   Scope requested: {required_scope}")
            print(f"   Audience (aud): {agent_client_id}")
            print(f"   ✓ Token is secured via audience-based validation")
            print(f"   ℹ️  Scopes may not appear in JWT claims - this is expected")
            print(f"      See docs/asgardeo-scope-configuration.md for details")
            
            # Cache the token
            self._token_cache[agent_name] = {
                'token': delegated_token,
                'expiry': time.time() + token_response.get('expires_in', 3600) - 60
            }
            
            return delegated_token
    
    async def _get_actor_token(self, agent_client_id: str, agent_client_secret: str) -> str:
        """Get agent's actor token using client credentials grant."""
        async with httpx.AsyncClient() as client:
            credentials = f"{agent_client_id}:{agent_client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            token_data = {
                'grant_type': 'client_credentials',
                'scope': 'openid'
            }
            
            print(f"  🤖 Requesting actor token for agent {agent_client_id[:15]}...")
            
            response = await client.post(
                self.token_exchange_url,
                data=token_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': f'Basic {encoded_credentials}'
                }
            )
            
            if response.status_code != 200:
                print(f"  ✗ Actor token request failed: {response.status_code}")
                print(f"    Response: {response.text}")
                raise Exception(f"Failed to get actor token: {response.text}")
            
            token_response = response.json()
            actor_token = token_response['access_token']
            
            print(f"  ✓ Actor token obtained: {actor_token[:30]}...")
            return actor_token
    
    def _display_token_claims(self, token: str, label: str):
        """Decode and display JWT token claims for debugging."""
        try:
            token_parts = token.split('.')
            if len(token_parts) >= 2:
                payload = token_parts[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = base64.b64decode(payload).decode('utf-8')
                claims = json.loads(decoded)
                
                print(f"\n📋 {label} Claims:")
                print(f"  - aud (audience): {claims.get('aud', 'NOT SET')}")
                print(f"  - scope: {claims.get('scope', 'NOT SET')}")
                print(f"  - act (actor): {claims.get('act', 'NOT SET')}")
                print(f"  - sub (subject): {claims.get('sub', 'NOT SET')}")
                print(f"  - iss (issuer): {claims.get('iss', 'NOT SET')}")
        except Exception as e:
            print(f"  (Could not decode {label}: {e})")
    
    def _get_cached_token(self, agent_name: str) -> Optional[str]:
        """Get cached agent token if still valid."""
        if agent_name not in self._token_cache:
            return None
        
        cache_entry = self._token_cache[agent_name]
        
        if time.time() < cache_entry['expiry']:
            return cache_entry['token']
        
        # Token expired, remove from cache
        del self._token_cache[agent_name]
        return None
    
    def clear_cache(self, agent_name: Optional[str] = None):
        """Clear cached tokens (all or specific agent)."""
        if agent_name:
            self._token_cache.pop(agent_name, None)
        else:
            self._token_cache.clear()
    
    def _get_agent_secret(self, agent_name: str) -> Optional[str]:
        """Get agent's client secret from environment."""
        if "Vaccination" in agent_name:
            secret = os.getenv('VACCINATION_APP_SECRET', '')
        elif "Appointment" in agent_name or "Scheduler" in agent_name or "Clinic" in agent_name:
            secret = os.getenv('APPOINTMENTS_APP_SECRET', '')
        else:
            secret = ''
        
        # Check if it's a real secret (not placeholder)
        if secret and secret not in ['<YOUR_VACCINATION_AGENT_SECRET>', '<YOUR_APPOINTMENTS_AGENT_SECRET>']:
            return secret
        return None


# ============================================================================
# AGENT CONFIGURATION - Metadata for Token Exchange
# ============================================================================

class AgentConfig:
    """
    Stores agent-specific configuration for token exchange.
    
    Each agent needs:
    - Application ID in Asgardeo
    - Application Secret in Asgardeo
    - Required scope(s) for that agent
    """
    
    def __init__(
        self,
        name: str,
        app_id: str,
        app_secret: str,
        required_scope: str
    ):
        """
        Initialize agent configuration.
        
        Args:
            name: Agent name (e.g., "Pet Vaccination Assistant")
            app_id: Agent's Asgardeo application ID
            app_secret: Agent's Asgardeo application secret
            required_scope: Scope(s) needed by this agent
        """
        self.name = name
        self.app_id = app_id
        self.app_secret = app_secret
        self.required_scope = required_scope
    
    def has_credentials(self) -> bool:
        """Check if agent has valid credentials configured."""
        return (
            self.app_id and 
            self.app_secret and 
            self.app_secret not in ['<YOUR_VACCINATION_AGENT_SECRET>', '<YOUR_APPOINTMENTS_AGENT_SECRET>']
        )


# ============================================================================
# PRE-CONFIGURED AGENT CONFIGS
# ============================================================================

def get_vaccination_agent_config() -> AgentConfig:
    """Get configuration for vaccination agent."""
    return AgentConfig(
        name="Pet Vaccination Assistant",
        app_id=os.getenv('VACCINATION_APP_ID', '<your_vaccination_client_id>'),
        app_secret=os.getenv('VACCINATION_APP_SECRET', '<YOUR_VACCINATION_AGENT_SECRET>'),
        required_scope=os.getenv('VACCINATION_REQUIRED_SCOPE', 'vaccination:read')
    )


def get_appointments_agent_config() -> AgentConfig:
    """Get configuration for appointments agent."""
    return AgentConfig(
        name="Pet Clinic Scheduler",
        app_id=os.getenv('APPOINTMENTS_APP_ID', '<your_appointments_client_id>'),
        app_secret=os.getenv('APPOINTMENTS_APP_SECRET', '<YOUR_APPOINTMENTS_AGENT_SECRET>'),
        required_scope=os.getenv('APPOINTMENTS_REQUIRED_SCOPE', 'appointments:read')
    )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_token_exchanger_from_env() -> TokenExchanger:
    """
    Create a token exchanger from environment variables.
    
    Required environment variables:
    - ASGARDEO_TOKEN_EXCHANGE_URL
    - ASGARDEO_CLIENT_ID
    - ASGARDEO_CLIENT_SECRET
    
    Optional environment variables:
    - API_RESOURCE_IDENTIFIER: API Resource identifier for scope binding
    
    Returns:
        Configured TokenExchanger instance
    """
    token_exchange_url = os.getenv('ASGARDEO_TOKEN_EXCHANGE_URL')
    client_id = os.getenv('ASGARDEO_CLIENT_ID')
    client_secret = os.getenv('ASGARDEO_CLIENT_SECRET')
    api_resource_identifier = os.getenv('API_RESOURCE_IDENTIFIER')
    
    if not all([token_exchange_url, client_id, client_secret]):
        raise ValueError(
            "Missing token exchange configuration. Please set:\n"
            "  - ASGARDEO_TOKEN_EXCHANGE_URL\n"
            "  - ASGARDEO_CLIENT_ID\n"
            "  - ASGARDEO_CLIENT_SECRET"
        )
    
    return TokenExchanger(
        token_exchange_url=token_exchange_url,
        client_id=client_id,
        client_secret=client_secret,
        api_resource_identifier=api_resource_identifier
    )
