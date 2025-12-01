"""
Simple Client Credentials Authentication for Orchestrator
Uses OAuth 2.0 Client Credentials Grant instead of Device Flow
"""

import httpx
from typing import Optional
import base64


class ClientAuthenticator:
    """
    Handles client credentials flow for machine-to-machine authentication.
    This is simpler than device flow and doesn't require user interaction.
    """
    
    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str
    ):
        """
        Initialize client authenticator.
        
        Args:
            token_url: OAuth token endpoint
            client_id: Application client ID
            client_secret: Application client secret
            scope: Requested scopes
        """
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[float] = None
    
    async def get_access_token(self) -> str:
        """
        Get an access token using client credentials grant.
        
        Returns:
            Access token string
        """
        print("\n" + "="*70)
        print("🔐 AUTHENTICATING ORCHESTRATOR (CLIENT CREDENTIALS)")
        print("="*70)
        
        async with httpx.AsyncClient() as client:
            try:
                # Encode client credentials for Basic Auth
                credentials = f"{self.client_id}:{self.client_secret}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                
                print(f"\n🔍 Debug Info:")
                print(f"  Endpoint: {self.token_url}")
                print(f"  Client ID: {self.client_id}")
                print(f"  Scope: {self.scope}")
                
                response = await client.post(
                    self.token_url,
                    data={
                        'grant_type': 'client_credentials',
                        'scope': self.scope
                    },
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Authorization': f'Basic {encoded_credentials}'
                    }
                )
                
                print(f"\n📥 Response Status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"📥 Response Body: {response.text[:500]}")
                
                response.raise_for_status()
                
                token_data = response.json()
                self._access_token = token_data['access_token']
                
                print(f"\n✓ Access token obtained")
                print(f"  Token: {self._access_token[:30]}...")
                print(f"  Expires in: {token_data.get('expires_in', 'unknown')} seconds")
                
                return self._access_token
                
            except Exception as e:
                print(f"\n✗ Failed to get access token")
                print(f"  Error: {e}")
                raise


def create_client_authenticator_from_env():
    """
    Create ClientAuthenticator from environment variables.
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    return ClientAuthenticator(
        token_url=os.getenv('ASGARDEO_TOKEN_URL'),
        client_id=os.getenv('ASGARDEO_CLIENT_ID'),
        client_secret=os.getenv('ASGARDEO_CLIENT_SECRET'),
        scope=os.getenv('ASGARDEO_SCOPE', 'vaccination:read appointments:read')
    )
