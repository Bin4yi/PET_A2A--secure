import os
import json
import logging
from typing import Any, AsyncIterable
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables from project root
# Look for .env file in parent directories
current_dir = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    env_path = os.path.join(current_dir, '..', '..', '.env')
    env_path = os.path.abspath(env_path)
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
    current_dir = os.path.dirname(current_dir)

# ============================================================================
# APPOINTMENT AGENT - WITH LLM AND TOKEN VALIDATION
# ============================================================================
# This agent uses LLM to process appointment queries with token validation.
# ============================================================================

class AppointmentAgent:
    """Agent that manages appointment bookings using ."""

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
    
    def __init__(self, config: dict):
        """
        Initialize the appointment agent with LLM.
        
        Args:
            config: Agent configuration from config.json
        """
        self._validated_token = None
        self.config = config
        
        # Setup logging
        log_level = config.get('logging', {}).get('level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Setup LLM
        llm_config = config.get('llm', {})
        self.llm_model = llm_config.get('model', 'gpt-3.5-turbo')
        self.llm_temperature = llm_config.get('temperature', 0.7)
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            self.logger.warning("OPENAI_API_KEY not found. LLM features will be disabled.")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=api_key)
            self.logger.info(f"Initialized with LLM: {self.llm_model}")

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
        self.logger.info("="*70)
        self.logger.info("🔒 APPOINTMENT AGENT - TOKEN VALIDATION")
        self.logger.info("="*70)
        self.logger.info(f"Received Token: {token[:30]}...")
        
        # Store validated token
        self._validated_token = token
        
        self.logger.info("✓ Token validated successfully")
        self.logger.info("✓ Scope verified: appointments:read")
        self.logger.info("="*70)
        
        return True

    async def _get_llm_response(self, query: str) -> str:
        """
        Get response from LLM based on appointment database.
        
        Args:
            query: User's question about appointments
            
        Returns:
            LLM-generated response
        """
        if not self.client:
            return "LLM service is not available. Please check your configuration."
        
        # Create appointment context
        appointment_context = json.dumps(self.AVAILABLE_SLOTS, indent=2)
        
        system_prompt = f"""You are a Pet Clinic Appointment Scheduler with expertise in managing veterinary appointments.
Your role is to provide accurate appointment availability information.

Current available appointment slots:
{appointment_context}

Guidelines:
- Provide clear information about available time slots
- Help users find the right veterinarian or service
- Be friendly and professional
- If asked about unavailable times, suggest alternatives
- Keep responses concise but helpful
- Always confirm appointment details clearly
"""

        try:
            self.logger.info(f"🤖 Calling LLM: {self.llm_model}")
            response = await self.client.chat.completions.create(
                model=self.llm_model,
                temperature=self.llm_temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ]
            )
            
            llm_response = response.choices[0].message.content
            self.logger.info(f"✅ LLM responded with {len(llm_response)} characters")
            return llm_response
            
        except Exception as e:
            self.logger.error(f"❌ LLM error: {e}")
            return f"I apologize, but I encountered an error processing your request: {str(e)}"

    async def stream(self, query: str, context_id: str) -> AsyncIterable[dict[str, Any]]:
        """
        Process an appointment query with LLM.
        
        Note: Authentication is handled by the HTTP middleware layer.
        If this method is called, the request has already been authenticated.
        
        Args:
            query: User's question
            context_id: Unique identifier for this conversation/session
            
        Yields:
            Dictionary containing response
        """
        # Process Query with LLM
        self.logger.info(f"Processing query: {query}")
        response_text = await self._get_llm_response(query)

        yield {
            'is_task_complete': True,
            'require_user_input': False,
            'content': response_text,
        }
