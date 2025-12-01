# ============================================================================
# PET VACCINATION AGENT - HTTP SERVER ENTRY POINT
# ============================================================================
# This file starts the HTTP server that exposes the vaccination agent via
# the A2A (Agent-to-Agent) protocol.
#
# What it does:
# 1. Creates an "Agent Card" (public metadata about this agent)
# 2. Sets up HTTP request handlers
# 3. Starts an HTTP server on port 10005
# 4. Automatically exposes /.well-known/agent-card.json endpoint
# ============================================================================

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

# Import the agent logic and executor
from agent_with_token import PetVaccinationAgentWithToken as PetVaccinationAgent
from executor import PetVaccinationAgentExecutor

# Import authentication middleware
from middleware import create_jwt_middleware_from_env

def main():
    """Start the Pet Vaccination Agent HTTP server."""
    
    # Server configuration
    host = "localhost"
    port = 10005  # Unique port for this agent

    try:
        # ====================================================================
        # STEP 1: Define Agent Capabilities
        # ====================================================================
        # Capabilities describe what features this agent supports
        capabilities = AgentCapabilities(
            streaming=True,           # Can stream responses chunk-by-chunk
            pushNotifications=False   # No push notifications support
        )

        # ====================================================================
        # STEP 2: Define Agent Skills
        # ====================================================================
        # Skills describe what tasks this agent can perform
        # This metadata helps other agents/orchestrators decide when to use us
        skill = AgentSkill(
            id="get_pet_vaccination_schedule",
            name="Get Pet Vaccination Schedule",
            description="Provides hardcoded vaccination details for dogs, cats, and rabbits.",
            tags=["pets", "health", "vaccination", "veterinary"],
            examples=[
                "What vaccines does my dog need?",
                "Cat vaccination schedule",
                "Do rabbits need shots?"
            ],
        )

        # ====================================================================
        # STEP 3: Create the Agent Card (Public Identity)
        # ====================================================================
        # The Agent Card is like a business card - it tells other agents:
        # - Who we are (name)
        # - What we do (description)
        # - How to reach us (url)
        # - What we're capable of (skills, capabilities)
        #
        # This card is automatically served at: /.well-known/agent-card.json
        # Includes security metadata for Asgardeo token exchange
        agent_card = AgentCard(
            name="Pet Vaccination Assistant",
            description="A helpful agent that provides standard vaccination schedules for common pets.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=PetVaccinationAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=PetVaccinationAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
            # Security metadata for Asgardeo
            metadata={
                "asgardeo": {
                    "application_id": os.getenv('VACCINATION_APP_ID', '<vaccination_client_id>'),
                    "required_scope": "vaccination:read",
                    "issuer": os.getenv('ASGARDEO_ISSUER', 'https://api.asgardeo.io/t/pasansanjiiwa')
                }
            }
        )

        # ====================================================================
        # STEP 4: Setup Request Handler
        # ====================================================================
        # The request handler connects incoming HTTP requests to our executor
        httpx_client = httpx.AsyncClient()
        
        request_handler = DefaultRequestHandler(
            agent_executor=PetVaccinationAgentExecutor(),  # Connect the executor (the "brain")
            task_store=InMemoryTaskStore(),                # Store for tracking tasks
            push_config_store=InMemoryPushNotificationConfigStore(),  # (Not used, but required)
        )

        # ====================================================================
        # STEP 5: Create A2A Application
        # ====================================================================
        # This creates a Starlette web application that:
        # - Serves the agent card at /.well-known/agent-card.json
        # - Handles incoming A2A messages at / (POST requests)
        # - Follows the A2A protocol specification
        server = A2AStarletteApplication(
            agent_card=agent_card,      # Our public identity
            http_handler=request_handler # Handles incoming requests
        )

        # ====================================================================
        # STEP 5.5: Add JWT Authentication Middleware
        # ====================================================================
        # Add middleware to validate JWT tokens from orchestrator
        # This ensures only authenticated requests can access the agent
        # Public paths (/.well-known/agent-card.json) are exempted
        # Build the app first to get the underlying Starlette application
        app = server.build()
        
        # Create and add JWT middleware with the required scope
        agent_id = os.getenv('VACCINATION_APP_ID', 'V5fehG024xohBqIuHzYWP7c59CEa')
        jwt_middleware = create_jwt_middleware_from_env(
            app=app, 
            required_scope="vaccination:read",
            agent_id=agent_id
        )
        print(f"JWT authentication middleware configured for agent {agent_id[:10]}...")

        # ====================================================================
        # STEP 6: Start the HTTP Server
        # ====================================================================
        # Run the server using Uvicorn (ASGI server)
        print(f"Starting Pet Vaccination Agent on http://{host}:{port}")
        uvicorn.run(app, host=host, port=port)

    except Exception as e:
        print(f"Error during server startup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()