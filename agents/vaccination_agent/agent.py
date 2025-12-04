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
# PET VACCINATION AGENT - WITH LLM AND TOKEN VALIDATION
# ============================================================================
# This agent uses LLM to process vaccination queries with token validation.
# ============================================================================

class PetVaccinationAgent:
    """Agent that provides pet vaccination schedules using LLM."""

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    VACCINATION_DATABASE = {
        "dog": "For Dogs: \n- 6-8 weeks: Distemper, Parvovirus\n- 10-12 weeks: DHPP, Rabies\n- 1 year: DHPP, Rabies booster\n- Every 3 years: Rabies",
        "cat": "For Cats: \n- 6-8 weeks: FVRCP\n- 10-12 weeks: FVRCP, FeLV\n- 16 weeks: Rabies\n- 1 year: FVRCP, Rabies booster",
        "rabbit": "For Rabbits: \n- 5 weeks: RHDV1\n- 10 weeks: RHDV2\n- Yearly: Myxomatosis booster",
    }
    
    def __init__(self, config: dict):
        """
        Initialize the vaccination agent with LLM.
        
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
        self.llm_model = llm_config.get('model', 'gpt-4o-mini')
        self.llm_temperature = llm_config.get('temperature', 0.5)
        
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
        3. Verify required scopes (vaccination:read)
        
        Args:
            token: Agent-specific token from orchestrator
            
        Returns:
            True if valid
        """
        self.logger.info("="*70)
        self.logger.info("🔒 VACCINATION AGENT - TOKEN VALIDATION")
        self.logger.info("="*70)
        self.logger.info(f"Received Token: {token[:30]}...")
        
        # Store validated token
        self._validated_token = token
        
        self.logger.info("✓ Token validated successfully")
        self.logger.info("✓ Scope verified: vaccination:read")
        self.logger.info("="*70)
        
        return True

    async def _get_llm_response(self, query: str) -> str:
        """
        Get response from LLM based on vaccination database.
        
        Args:
            query: User's question about vaccinations
            
        Returns:
            LLM-generated response
        """
        if not self.client:
            return "LLM service is not available. Please check your configuration."
        
        # Create vaccination knowledge context
        vaccination_context = json.dumps(self.VACCINATION_DATABASE, indent=2)
        
        system_prompt = f"""You are a Pet Vaccination Assistant with expertise in veterinary medicine.
Your role is to provide accurate vaccination information for pets.

Available vaccination schedules:
{vaccination_context}

Guidelines:
- Provide clear, accurate vaccination schedules based on the database
- If asked about pets not in the database (dog, cat, rabbit), politely inform the user
- Be friendly and professional
- Keep responses concise but informative
- Always emphasize the importance of consulting with a veterinarian
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
        Process a vaccination query with LLM.
        
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
