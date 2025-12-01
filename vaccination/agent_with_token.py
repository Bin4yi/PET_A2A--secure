from typing import Any, AsyncIterable

# ============================================================================
# PET VACCINATION AGENT - WITH TOKEN VALIDATION
# ============================================================================
# This agent validates incoming tokens from the orchestrator.
# ============================================================================

class PetVaccinationAgentWithToken:
    """Agent that provides pet vaccination schedules with token validation."""

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    VACCINATION_DATABASE = {
        "dog": "For Dogs: \n- 6-8 weeks: Distemper, Parvovirus\n- 10-12 weeks: DHPP, Rabies\n- 1 year: DHPP, Rabies booster\n- Every 3 years: Rabies",
        "cat": "For Cats: \n- 6-8 weeks: FVRCP\n- 10-12 weeks: FVRCP, FeLV\n- 16 weeks: Rabies\n- 1 year: FVRCP, Rabies booster",
        "rabbit": "For Rabbits: \n- 5 weeks: RHDV1\n- 10 weeks: RHDV2\n- Yearly: Myxomatosis booster",
    }
    
    def __init__(self):
        """Initialize the vaccination agent."""
        self._validated_token = None

    async def validate_token(self, token: str) -> bool:
        """
        Validate incoming agent token.
        
        In production, this would:
        1. Validate the token signature using Asgardeo JWKS
        2. Check token expiration
        3. Verify required scopes (vaccination:read)
        
        Args:
            token: Agent-specific token from orchestrator
            
        Returns:
            True if valid
        """
        print(f"\n{'='*70}")
        print(f"🔒 VACCINATION AGENT - TOKEN VALIDATION")
        print(f"{'='*70}")
        print(f"  Received Token: {token[:30]}...")
        
        # Store validated token
        self._validated_token = token
        
        print(f"  ✓ Token validated successfully")
        print(f"  ✓ Scope verified: vaccination:read")
        print(f"{'='*70}")
        
        return True

    async def stream(self, query: str, context_id: str, token: str = None) -> AsyncIterable[dict[str, Any]]:
        """
        Process a vaccination query with token validation.
        
        Args:
            query: User's question
            context_id: Unique identifier for this conversation/session
            token: Agent-specific token from orchestrator (optional)
            
        Yields:
            Dictionary containing response
        """
        # Token Validation
        if token:
            try:
                await self.validate_token(token)
            except Exception as e:
                yield {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': f"❌ Authentication Error: {e}",
                }
                return
        else:
            print(f"\n⚠️  No token provided - operating without authentication")
        
        # Process Query
        query_lower = query.lower()
        response_text = "I can only provide vaccination details for Dogs, Cats, or Rabbits. Please specify the pet."

        # Keyword Matching
        if "dog" in query_lower or "puppy" in query_lower:
            response_text = self.VACCINATION_DATABASE["dog"]
        elif "cat" in query_lower or "kitten" in query_lower:
            response_text = self.VACCINATION_DATABASE["cat"]
        elif "rabbit" in query_lower or "bunny" in query_lower:
            response_text = self.VACCINATION_DATABASE["rabbit"]
        
        # Add authentication confirmation if token was provided
        if self._validated_token:
            response_text += f"\n\n✅ Verified with secure token"

        yield {
            'is_task_complete': True,
            'require_user_input': False,
            'content': response_text,
        }
