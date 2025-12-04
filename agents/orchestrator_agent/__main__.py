"""
Orchestrator Entry Point
Starts the orchestrator agent that handles user authentication and routes requests.

Implements OAuth Extension for AI Agents (IETF draft) for secure agent delegation.
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def start():
    """Main entry point for the orchestrator."""
    from agent import main as run_orchestrator
    
    logger.info("Starting Orchestrator Agent...")
    logger.info("This orchestrator will:")
    logger.info("  1. Open browser for you to login to Asgardeo")
    logger.info("  2. Use OAuth Extension for AI Agents to delegate tokens")
    logger.info("  3. Route your requests to vaccination and appointments agents")
    logger.info("")
    logger.info("Make sure vaccination and appointments agents are running!")
    logger.info("")
    
    try:
        await run_orchestrator()
    except KeyboardInterrupt:
        logger.info("Orchestrator stopped by user")
    except Exception as e:
        logger.error(f"Error running orchestrator: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(start())
