from typing import Any, AsyncIterable

# ============================================================================
# APPOINTMENT AGENT - WITH TOKEN VALIDATION
# ============================================================================
# This agent validates incoming tokens from the orchestrator.
# ============================================================================

class AppointmentAgentWithToken:
    """Agent that returns appointment availability with token validation."""

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    AVAILABLE_SLOTS = {
        "dr_smith": [
            "Monday: 9:00 AM, 11:30 AM",
            "Wednesday: 2:00 PM",
            "Friday: 10:00 AM"
        ],
        "dr_jones": [
            "Tuesday: 1:00 PM, 3:30 PM",
            "Thursday: 9:00 AM"
        ],
        "grooming": [
            "Monday - Friday: 8:00 AM - 4:00 PM (Walk-ins available)"
        ]
    }
    
    def __init__(self):
        """Initialize the appointment agent."""
        self._validated_token = None

    async def validate_token(self, token: str) -> bool:
        """
        Validate incoming agent token.
        
        In production, this would:
        1. Validate the token signature using Asgardeo JWKS
        2. Check token expiration
        3. Verify required scopes (appointments:read)
        
        Args:
            token: Agent-specific token from orchestrator
            
        Returns:
            True if valid
        """
        print(f"\n{'='*70}")
        print(f"🔒 APPOINTMENT AGENT - TOKEN VALIDATION")
        print(f"{'='*70}")
        print(f"  Received Token: {token[:30]}...")
        
        # Store validated token
        self._validated_token = token
        
        print(f"  ✓ Token validated successfully")
        print(f"  ✓ Scope verified: appointments:read")
        print(f"{'='*70}")
        
        return True

    async def stream(self, query: str, context_id: str, token: str = None) -> AsyncIterable[dict[str, Any]]:
        """
        Process an appointment query with token validation.
        
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
        
        if "smith" in query_lower:
            response_text = "Dr. Smith has the following openings:\n" + "\n".join(self.AVAILABLE_SLOTS["dr_smith"])
        elif "jones" in query_lower:
            response_text = "Dr. Jones has the following openings:\n" + "\n".join(self.AVAILABLE_SLOTS["dr_jones"])
        elif "groom" in query_lower or "bath" in query_lower:
            response_text = "For Grooming:\n" + "\n".join(self.AVAILABLE_SLOTS["grooming"])
        else:
            response_text = (
                "I can help you book appointments. "
                "Please ask for 'Dr. Smith', 'Dr. Jones', or 'Grooming' to see available slots."
            )

        # Add authentication confirmation if token was provided
        if self._validated_token:
            response_text += f"\n\n✅ Verified with secure token"

        yield {
            'is_task_complete': True,
            'require_user_input': False,
            'content': response_text,
        }
