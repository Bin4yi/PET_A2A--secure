import logging
import sys
import os

import httpx
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

# Import the new logic
from agent_with_token import AppointmentAgentWithToken as AppointmentAgent
from executor import AppointmentAgentExecutor

# Import authentication middleware
from middleware import create_jwt_middleware_from_env

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Starts the Pet Appointment Agent server."""
    host = "localhost"
    port = 10006  # Different port from vaccination agent

    try:
        # 1. Define Capabilities
        capabilities = AgentCapabilities(streaming=True, pushNotifications=False)

        # 2. Define Skills
        skill = AgentSkill(
            id="check_appointment_slots",
            name="Check Appointment Availability",
            description="Checks hardcoded availability for Dr. Smith, Dr. Jones, or Grooming.",
            tags=["scheduling", "vet", "appointments"],
            examples=[
                "Is Dr. Smith free?",
                "Grooming hours",
                "When can I see Dr. Jones?"
            ],
        )

        # 3. Create the Agent Card
        agent_card = AgentCard(
            name="Pet Clinic Scheduler",
            description="Agent for checking veterinary appointment slots.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=AppointmentAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=AppointmentAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
            # Security metadata for Asgardeo
            metadata={
                "asgardeo": {
                    "application_id": os.getenv('APPOINTMENTS_APP_ID', '<appointments_client_id>'),
                    "required_scope": "appointments:read",
                    "issuer": os.getenv('ASGARDEO_ISSUER', 'https://api.asgardeo.io/t/pasansanjiiwa')
                }
            }
        )

        # 4. Setup Server
        httpx_client = httpx.AsyncClient()
        
        request_handler = DefaultRequestHandler(
            agent_executor=AppointmentAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, 
            http_handler=request_handler
        )

        # Build the app first to get the underlying Starlette application
        app = server.build()
        
        # Add JWT authentication middleware
        # This ensures only authenticated requests from the orchestrator can access the agent
        agent_id = os.getenv('APPOINTMENTS_APP_ID', 'GBuclOn0Oi68n8JF66f1Cq0WSrsa')
        jwt_middleware = create_jwt_middleware_from_env(
            app=app, 
            required_scope="appointments:read",
            agent_id=agent_id
        )
        logger.info(f"JWT authentication middleware configured for agent {agent_id[:10]}...")

        logger.info(f"Starting Appointment Agent on http://{host}:{port}")
        uvicorn.run(app, host=host, port=port)

    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()