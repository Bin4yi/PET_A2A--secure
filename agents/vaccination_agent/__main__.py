# ============================================================================
# PET VACCINATION AGENT - HTTP SERVER ENTRY POINT
# ============================================================================
# This file starts the HTTP server that exposes the vaccination agent via
# the A2A (Agent-to-Agent) protocol.
#
# What it does:
# 1. Loads configuration from config.json
# 2. Creates an "Agent Card" (public metadata about this agent)
# 3. Sets up HTTP request handlers
# 4. Starts an HTTP server on configured host/port
# 5. Automatically exposes /.well-known/agent-card.json endpoint
# ============================================================================

import sys
import os
import json
import logging
from dotenv import load_dotenv

# Load .env file from project root FIRST
current_dir = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    env_path = os.path.join(current_dir, '..', '..', '.env')
    env_path = os.path.abspath(env_path)
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ Loaded .env from: {env_path}")
        break
    current_dir = os.path.dirname(current_dir)

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
from agent import PetVaccinationAgent
from executor import PetVaccinationAgentExecutor

# Import authentication middleware
from middleware import create_jwt_middleware_from_env

def load_config():
    """Load configuration from config.json"""
    # Look for config.json in parent directories
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Try to find config.json (go up to root)
    for _ in range(5):  # Search up to 5 levels
        config_path = os.path.join(current_dir, '..', '..', 'config.json')
        config_path = os.path.abspath(config_path)
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Find vaccination_agent config
                for agent in config.get('agents', []):
                    if agent.get('name') == 'vaccination_agent':
                        return agent, config
                raise Exception("vaccination_agent not found in config.json")
        
        current_dir = os.path.dirname(current_dir)
    
    raise Exception("config.json not found")

def main():
    """Start the Pet Vaccination Agent HTTP server."""
    
    try:
        # Load configuration
        agent_config, global_config = load_config()
        
        # Setup logging
        log_level = agent_config.get('logging', {}).get('level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format=global_config.get('global', {}).get('log_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logger = logging.getLogger(__name__)
        
        # Server configuration from config.json
        host = agent_config.get('host', 'localhost')
        port = agent_config.get('port', 10005)
        agent_id = agent_config.get('application_id')
        required_scope = agent_config.get('required_scope', 'vaccination:read')
        description = agent_config.get('description', 'Pet Vaccination Assistant')
        
        logger.info(f"Loading Pet Vaccination Agent")
        logger.info(f"LLM Model: {agent_config.get('llm', {}).get('model', 'N/A')}")
        logger.info(f"Server: http://{host}:{port}")
        
        # ====================================================================
        # STEP 1: Define Agent Capabilities
        # ====================================================================
        capabilities = AgentCapabilities(
            streaming=True,
            pushNotifications=False
        )

        # ====================================================================
        # STEP 2: Define Agent Skills
        # ====================================================================
        skill = AgentSkill(
            id="get_pet_vaccination_schedule",
            name="Get Pet Vaccination Schedule",
            description="Provides AI-powered vaccination information for dogs, cats, and rabbits using LLM.",
            tags=["pets", "health", "vaccination", "veterinary", "AI"],
            examples=[
                "What vaccines does my dog need?",
                "Cat vaccination schedule",
                "Do rabbits need shots?",
                "When should I vaccinate my puppy?"
            ],
        )

        # ====================================================================
        # STEP 3: Create the Agent Card
        # ====================================================================
        agent_card = AgentCard(
            name="Pet Vaccination Assistant",
            description=description,
            url=f"http://{host}:{port}/",
            version="2.0.0",
            defaultInputModes=PetVaccinationAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=PetVaccinationAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
            metadata={
                "asgardeo": {
                    "application_id": agent_id,
                    "required_scope": required_scope,
                    "issuer": global_config.get('asgardeo', {}).get('issuer', '')
                },
                "llm": agent_config.get('llm', {})
            }
        )

        # ====================================================================
        # STEP 4: Setup Request Handler
        # ====================================================================
        httpx_client = httpx.AsyncClient()
        
        request_handler = DefaultRequestHandler(
            agent_executor=PetVaccinationAgentExecutor(agent_config),
            task_store=InMemoryTaskStore(),
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        # ====================================================================
        # STEP 5: Create A2A Application
        # ====================================================================
        server = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler
        )

        # ====================================================================
        # STEP 6: Add JWT Authentication Middleware
        # ====================================================================
        app = server.build()
        
        # Create and add middleware to the app
        jwt_middleware = create_jwt_middleware_from_env(
            app=app, 
            required_scope=required_scope,
            agent_id=agent_id
        )
        # Important: The middleware wraps the app and must be used for serving
        app = jwt_middleware
        logger.info(f"JWT authentication middleware configured")

        # ====================================================================
        # STEP 7: Start the HTTP Server
        # ====================================================================
        logger.info(f"🚀 Starting Pet Vaccination Agent on http://{host}:{port}")
        uvicorn.run(app, host=host, port=port, log_level=log_level.lower())

    except Exception as e:
        print(f"Error during server startup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
