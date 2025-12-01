# ============================================================================
# USER AUTHENTICATION - Device Authorization Flow
# ============================================================================
# This module handles user authentication using OAuth 2.0 Device Authorization
# Grant (RFC 8628). This flow is ideal for CLI/agent applications where users
# authenticate via a web browser.
#
# Flow:
# 1. Application requests a device code from Asgardeo
# 2. User is shown a URL and user code
# 3. User visits URL in browser and enters code
# 4. User signs in with Asgardeo credentials
# 5. Application polls for token until user completes sign-in
# 6. Master access token is returned with full scopes (vaccine:admin, appt:schedule)
# ============================================================================

import os
import time
import webbrowser
from typing import Dict, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()


class UserAuthenticator:
    """
    Handles user authentication via OAuth 2.0 Device Authorization Grant.
    
    This allows users to authenticate via a web browser while the application
    waits for the authentication to complete.
    """
    
    def __init__(
        self,
        device_authorize_url: str,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "vaccination:read appointments:read openid profile"
    ):
        """
        Initialize the user authenticator.
        
        Args:
            device_authorize_url: Asgardeo device authorization endpoint
            token_url: Asgardeo token endpoint
            client_id: Orchestrator application client ID
            client_secret: Orchestrator application client secret
            scope: Requested scopes (full permissions for orchestrator)
        """
        self.device_authorize_url = device_authorize_url
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        
        # Master token cache (user's full-scope token)
        self._master_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[float] = None
        self._user_info: Optional[Dict] = None
    
    async def initiate_device_flow(self) -> Dict:
        """
        Step 1: Request device and user codes from Asgardeo.
        
        Returns:
            Dictionary containing:
            - device_code: Code for polling
            - user_code: Code for user to enter
            - verification_uri: URL where user authenticates
            - verification_uri_complete: URL with code pre-filled
            - expires_in: How long codes are valid
            - interval: Polling interval in seconds
        """
        print("\n" + "="*70)
        print("🔐 INITIATING USER AUTHENTICATION")
        print("="*70)
        
        async with httpx.AsyncClient() as client:
            try:
                # For Asgardeo, try without Basic Auth first
                print(f"\n🔍 Attempting device flow without Basic Auth...")
                
                response = await client.post(
                    self.device_authorize_url,
                    data={
                        'client_id': self.client_id,
                        'scope': self.scope
                    },
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded'
                    }
                )
                
                print(f"\n📥 Response Status: {response.status_code}")
                
                if response.status_code == 401 or response.status_code == 400:
                    # Try with Basic Auth
                    print(f"🔍 Retrying with Basic Authentication...")
                    credentials = f"{self.client_id}:{self.client_secret}"
                    encoded_credentials = base64.b64encode(credentials.encode()).decode()
                    
                    response = await client.post(
                        self.device_authorize_url,
                        data={
                            'client_id': self.client_id,
                            'scope': self.scope
                        },
                        headers={
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Authorization': f'Basic {encoded_credentials}'
                        }
                    )
                    
                    print(f"📥 Response Status (with auth): {response.status_code}")
                
                if response.status_code != 200:
                    print(f"📥 Response Body: {response.text[:500]}")
                
                response.raise_for_status()
                
                device_data = response.json()
                
                print(f"\n✓ Device code obtained")
                print(f"  User Code: {device_data.get('user_code', 'N/A')}")
                print(f"  Expires in: {device_data.get('expires_in', 0)} seconds")
                
                return device_data
                
            except Exception as e:
                print(f"\n✗ Failed to initiate device flow")
                print(f"  Error: {e}")
                raise
    
    async def prompt_user_to_authenticate(self, device_data: Dict) -> None:
        """
        Step 2: Display authentication instructions to user and open browser.
        
        Args:
            device_data: Response from initiate_device_flow()
        """
        verification_uri = device_data.get('verification_uri')
        user_code = device_data.get('user_code')
        verification_uri_complete = device_data.get('verification_uri_complete')
        
        print("\n" + "="*70)
        print("👤 USER AUTHENTICATION REQUIRED")
        print("="*70)
        print("\nPlease complete the following steps:")
        print(f"\n  1. Visit: {verification_uri}")
        print(f"  2. Enter code: {user_code}")
        print(f"  3. Sign in with your Asgardeo credentials")
        print(f"\n  (A browser window will open automatically)")
        print("="*70)
        
        # Try to open browser automatically
        try:
            if verification_uri_complete:
                webbrowser.open(verification_uri_complete)
            else:
                webbrowser.open(verification_uri)
        except Exception as e:
            print(f"\n⚠️  Could not open browser automatically: {e}")
            print("  Please open the URL manually.")
    
    async def poll_for_token(
        self,
        device_code: str,
        interval: int = 5,
        timeout: int = 300
    ) -> Dict:
        """
        Step 3: Poll Asgardeo for token until user completes authentication.
        
        Args:
            device_code: Device code from initiate_device_flow()
            interval: Polling interval in seconds
            timeout: Max time to wait for user authentication
            
        Returns:
            Token response containing:
            - access_token: Master access token with full scopes
            - refresh_token: Token to refresh access token
            - expires_in: Token lifetime in seconds
            - scope: Granted scopes
            - id_token: User identity token (if openid scope)
        """
        print("\n⏳ Waiting for user to complete authentication...")
        
        start_time = time.time()
        async with httpx.AsyncClient() as client:
            while True:
                # Check timeout
                if time.time() - start_time > timeout:
                    raise TimeoutError("User authentication timeout - please try again")
                
                try:
                    response = await client.post(
                        self.token_url,
                        data={
                            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                            'device_code': device_code,
                            'client_id': self.client_id,
                            'client_secret': self.client_secret
                        },
                        headers={'Content-Type': 'application/x-www-form-urlencoded'}
                    )
                    
                    # Success - user authenticated!
                    if response.status_code == 200:
                        token_data = response.json()
                        print("\n✓ User successfully authenticated!")
                        print(f"  Granted scopes: {token_data.get('scope', 'N/A')}")
                        return token_data
                    
                    # Check for specific error codes
                    error_data = response.json()
                    error_code = error_data.get('error')
                    
                    if error_code == 'authorization_pending':
                        # User hasn't completed authentication yet - keep polling
                        print(".", end="", flush=True)
                        await asyncio.sleep(interval)
                        continue
                    
                    elif error_code == 'slow_down':
                        # We're polling too fast - increase interval
                        interval += 5
                        print(f"\n⚠️  Slowing down polling (new interval: {interval}s)")
                        await asyncio.sleep(interval)
                        continue
                    
                    elif error_code in ['expired_token', 'access_denied']:
                        # Authentication failed or expired
                        raise Exception(f"Authentication failed: {error_code}")
                    
                    else:
                        # Unknown error
                        raise Exception(f"Token polling error: {error_data}")
                
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400:
                        # Continue polling on 400 errors (normal for pending auth)
                        print(".", end="", flush=True)
                        await asyncio.sleep(interval)
                    else:
                        raise
    
    async def authenticate_user(self) -> str:
        """
        Complete user authentication flow and return master access token.
        
        This is the main method to call. It orchestrates the entire flow:
        1. Request device code
        2. Prompt user to authenticate
        3. Poll for token
        4. Cache and return master token
        
        Returns:
            Master access token with full scopes (vaccine:admin, appt:schedule)
        """
        # Check if we already have a valid token
        if self._master_token and self._token_expiry:
            if time.time() < self._token_expiry - 300:  # 5 min buffer
                print("\n✓ Using cached master token")
                return self._master_token
        
        # Initiate device flow
        device_data = await self.initiate_device_flow()
        
        # Prompt user
        await self.prompt_user_to_authenticate(device_data)
        
        # Poll for token
        token_data = await self.poll_for_token(
            device_code=device_data['device_code'],
            interval=device_data.get('interval', 5)
        )
        
        # Cache token
        self._master_token = token_data['access_token']
        self._refresh_token = token_data.get('refresh_token')
        self._token_expiry = time.time() + token_data.get('expires_in', 3600)
        
        print("\n" + "="*70)
        print("✓ MASTER TOKEN ACQUIRED")
        print("="*70)
        print(f"  Token Type: Bearer")
        print(f"  Scopes: {token_data.get('scope', 'N/A')}")
        print(f"  Valid for: {token_data.get('expires_in', 0)} seconds")
        print("="*70)
        
        return self._master_token
    
    async def refresh_master_token(self) -> str:
        """
        Refresh the master token using refresh token.
        
        Returns:
            New master access token
        """
        if not self._refresh_token:
            raise Exception("No refresh token available - please re-authenticate")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': self._refresh_token,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            
            token_data = response.json()
            
            # Update cache
            self._master_token = token_data['access_token']
            self._refresh_token = token_data.get('refresh_token', self._refresh_token)
            self._token_expiry = time.time() + token_data.get('expires_in', 3600)
            
            print("\n✓ Master token refreshed")
            return self._master_token
    
    def get_cached_token(self) -> Optional[str]:
        """Get cached master token without making network calls."""
        if self._master_token and self._token_expiry:
            if time.time() < self._token_expiry - 300:
                return self._master_token
        return None


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_user_authenticator_from_env() -> UserAuthenticator:
    """
    Create a user authenticator from environment variables.
    
    Required environment variables:
    - ASGARDEO_DEVICE_AUTHORIZE_URL
    - ASGARDEO_TOKEN_URL
    - ASGARDEO_CLIENT_ID
    - ASGARDEO_CLIENT_SECRET
    
    Returns:
        Configured UserAuthenticator instance
    """
    device_authorize_url = os.getenv('ASGARDEO_DEVICE_AUTHORIZE_URL')
    token_url = os.getenv('ASGARDEO_TOKEN_URL')
    client_id = os.getenv('ASGARDEO_CLIENT_ID')
    client_secret = os.getenv('ASGARDEO_CLIENT_SECRET')
    
    if not all([device_authorize_url, token_url, client_id, client_secret]):
        raise ValueError(
            "Missing user authentication configuration. Please set:\n"
            "  - ASGARDEO_DEVICE_AUTHORIZE_URL\n"
            "  - ASGARDEO_TOKEN_URL\n"
            "  - ASGARDEO_CLIENT_ID\n"
            "  - ASGARDEO_CLIENT_SECRET"
        )
    
    return UserAuthenticator(
        device_authorize_url=device_authorize_url,
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret
    )


# Fix missing import
import asyncio
