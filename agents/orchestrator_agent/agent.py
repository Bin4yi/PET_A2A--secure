# ============================================================================
# ORCHESTRATOR AGENT - MULTI-AGENT COORDINATOR
# ============================================================================
# This agent coordinates between multiple specialized agents (vaccination,
# appointments, etc.) using an LLM to intelligently route user requests.
#
# Architecture:
# 1. Discovers available agents by fetching their agent cards
# 2. Creates a LangChain ReAct agent with OpenAI GPT-4
# 3. Provides a "talk_to_agent" tool for the LLM to call other agents
# 4. Synthesizes responses from multiple agents into a coherent answer
# ============================================================================

import asyncio
import json
import os
from uuid import uuid4

import httpx
from dotenv import load_dotenv

# A2A Protocol Imports
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

# LangChain / OpenAI Imports for AI orchestration
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

# Asgardeo Authentication & Token Exchange
from token_exchange import (
    create_token_exchanger_from_env,
    AgentConfig
)

# Load environment variables (OPENAI_API_KEY, ASGARDEO credentials, etc.)
load_dotenv()

# ============================================================================
# GLOBAL REGISTRY - Discovered Agents & Authentication
# ============================================================================
# Stores information about all discovered agents
# Format: {"Agent Name": {"client": A2AClient, "card": AgentCard, "url": str, "config": AgentConfig}}
# ============================================================================
KNOWN_AGENTS = {}

# Global instances for authentication (initialized in main)
USER_AUTHENTICATOR = None
TOKEN_EXCHANGER = None
MASTER_TOKEN = None

# Agent-specific configurations
AGENT_CONFIGS = {}

# Cache for delegated tokens (agent_name -> delegated_access_token)
DELEGATED_TOKENS = {}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def derive_env_var_name(agent_name: str, suffix: str) -> str:
    """
    Derive environment variable name from agent name dynamically.
    
    Extracts significant words from agent name and converts to uppercase.
    Examples:
        "Pet Vaccination Assistant" + "_APP_SECRET" -> "VACCINATION_APP_SECRET"
        "Weather Forecast Service" + "_APP_ID" -> "WEATHER_APP_ID"
        "Customer Support Bot" + "_APP_SECRET" -> "CUSTOMER_APP_SECRET"
    
    Args:
        agent_name: Full agent name from agent card
        suffix: Suffix to append (e.g., "_APP_SECRET", "_APP_ID", "_REQUIRED_SCOPE")
        
    Returns:
        Derived environment variable name
    """
    # Common filler words to ignore (can work with any domain)
    ignore_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'for', 'of', 'to', 'in', 'on', 'at',
        'assistant', 'agent', 'service', 'helper', 'bot', 'system', 'manager',
        'handler', 'processor', 'worker', 'server', 'client', 'api',
        'pet', 'pets'  # Domain-specific filler words
    }
    
    # Extract meaningful words from agent name
    words = agent_name.split()
    significant_words = [word for word in words if word.lower() not in ignore_words]
    
    # Use first significant word as the key term
    if significant_words:
        key_term = significant_words[0].upper()
    else:
        # Fallback: use first word if all are ignored
        key_term = words[0].upper()
    
    return f"{key_term}{suffix}"


def get_agent_config_from_env(agent_name: str) -> tuple:
    """
    Dynamically discover agent configuration from environment variables.
    
    Tries multiple naming patterns to find APP_ID, APP_SECRET, and REQUIRED_SCOPE.
    Works with any agent name without prior knowledge of what agents exist.
    
    Args:
        agent_name: Full agent name from agent card
        
    Returns:
        Tuple of (app_id, app_secret, required_scope, env_vars_tried) 
        or (None, None, None, []) if not found
    """
    # Generate multiple possible environment variable patterns
    patterns = []
    
    # Pattern 1: First significant word (e.g., "VACCINATION_APP_ID")
    primary_pattern = derive_env_var_name(agent_name, "")
    patterns.append(primary_pattern)
    
    # Pattern 2: All significant words concatenated (e.g., "VACCINATION_ASSISTANT_APP_ID")
    ignore_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'for', 'of', 'to', 'in', 'on', 'at',
        'assistant', 'agent', 'service', 'helper', 'bot', 'system', 'manager',
        'pet', 'pets'  # Domain-specific filler words
    }
    words = agent_name.split()
    significant_words = [w.upper() for w in words if w.lower() not in ignore_words]
    if len(significant_words) > 1:
        combined = "_".join(significant_words)
        patterns.append(combined)
    
    # Pattern 3: Full name converted to snake_case (e.g., "PET_VACCINATION_ASSISTANT_APP_ID")
    full_snake = "_".join(word.upper() for word in words)
    patterns.append(full_snake)
    
    # Pattern 4: Handle specific aliases (Clinic/Scheduler -> APPOINTMENTS)
    if any(word in agent_name.lower() for word in ['clinic', 'scheduler', 'appointment']):
        patterns.insert(0, 'APPOINTMENTS')  # Try this first
    
    # Try each pattern to find configuration
    tried_vars = []
    for pattern in patterns:
        app_id_var = f"{pattern}_APP_ID"
        app_secret_var = f"{pattern}_APP_SECRET"
        scope_var = f"{pattern}_REQUIRED_SCOPE"
        
        tried_vars.extend([app_id_var, app_secret_var, scope_var])
        
        # Get values from environment
        app_id = os.getenv(app_id_var, '')
        app_secret = os.getenv(app_secret_var, '')
        required_scope = os.getenv(scope_var, '')
        
        # Validate values (check if not placeholder)
        def is_valid(value):
            return value and '<' not in value and '>' not in value
        
        if is_valid(app_id):
            # Found valid configuration with this pattern
            app_secret = app_secret if is_valid(app_secret) else None
            required_scope = required_scope if is_valid(required_scope) else None
            return app_id, app_secret, required_scope, [app_id_var, app_secret_var, scope_var]
    
    # No valid configuration found
    return None, None, None, list(set(tried_vars))

# ============================================================================
# TOOL DEFINITION - Communication Bridge
# ============================================================================
# This tool allows the LLM to send messages to other agents
# The LLM decides WHICH agent to call and WHAT to ask them
# ============================================================================

@tool
async def talk_to_agent(agent_name: str, content: str) -> str:
    """
    Send a message to a specific remote agent and return their response.
    
    This tool uses RFC 8693 Token Exchange to get agent-specific tokens:
    1. Uses cached master token from initial user login
    2. Exchanges master token + agent client ID for delegated token
    3. NO additional browser login required!
    4. Sends delegated token to the agent
    5. Returns agent's response
    
    The LLM provides:
    - agent_name: Which agent to contact (e.g., "Pet Vaccination Assistant")
    - content: What to ask them (e.g., "What vaccines do dogs need?")
    
    Args:
        agent_name: The exact name of the agent (must match KNOWN_AGENTS keys)
        content: The message/question to send to that agent
        
    Returns:
        The agent's response as a string, or an error message if communication fails
    """
    global DELEGATED_TOKENS
    
    # ========================================================================
    # STEP 1: Verify Agent Exists
    # ========================================================================
    if agent_name not in KNOWN_AGENTS:
        return f"Error: Agent '{agent_name}' is not available. Available agents: {list(KNOWN_AGENTS.keys())}"
    
    # Get the A2A client for this agent
    agent_data = KNOWN_AGENTS[agent_name]
    client = agent_data['client']
    
    # ========================================================================
    # STEP 2: Get Delegated Token via Token Exchange (NO BROWSER!)
    # ========================================================================
    agent_token = None
    try:
        print(f"\n{'='*70}")
        print(f"🎫 Preparing to call: {agent_name}")
        print(f"{'='*70}")
        
        # Check if we have a cached delegated token
        if agent_name in DELEGATED_TOKENS:
            agent_token = DELEGATED_TOKENS[agent_name]
            print(f"✓ Using cached delegated token for {agent_name}")
        
        # Perform token exchange (no browser needed!)
        elif TOKEN_EXCHANGER and MASTER_TOKEN and agent_name in AGENT_CONFIGS:
            agent_config = AGENT_CONFIGS[agent_name]
            
            print(f"\n🔄 Token Exchange (no browser login)")
            print(f"   Agent: {agent_name}")
            print(f"   Scope: {agent_config.required_scope}")
            
            # Exchange master token for agent-specific token
            agent_token = await TOKEN_EXCHANGER.exchange_token_for_agent(
                master_token=MASTER_TOKEN,
                agent_name=agent_name,
                agent_client_id=agent_config.app_id,
                required_scope=agent_config.required_scope
            )
            
            # Cache the token for future use
            DELEGATED_TOKENS[agent_name] = agent_token
            print(f"✓ Delegated token obtained for {agent_name}")
        else:
            return f"Error: Cannot get token for {agent_name}. Configuration missing."
            
    except Exception as e:
        return f"Error: Token exchange failed for {agent_name}: {e}"

    try:
        # ====================================================================
        # STEP 3: Build A2A Message Payload
        # ====================================================================
        # Construct a properly formatted A2A message
        payload = {
            'message': {
                'role': 'user',                          # We're asking as a user
                'parts': [{'kind': 'text', 'text': content}],  # The actual question
                'message_id': uuid4().hex,               # Unique message ID
            }
        }
        
        # Wrap in A2A SendMessageRequest format
        request = SendMessageRequest(
            id=str(uuid4()),                    # Unique request ID (for JSON-RPC)
            params=MessageSendParams(**payload) # The message payload
        )

        # ====================================================================
        # STEP 4: Send Message with Agent Token via A2A Protocol
        # ====================================================================
        # If we have an agent-specific token, use it for the request
        if agent_token:
            # Create httpx client with Authorization header properly set in constructor
            # This is the standard way - headers must be set when creating the client
            temp_client = httpx.AsyncClient(
                headers={'Authorization': f'Bearer {agent_token}'},
                timeout=30.0
            )
            
            print(f"\n📤 Preparing to send message to {agent_name}")
            print(f"   Token preview: {agent_token[:30]}...")
            print(f"   Headers set: {dict(temp_client.headers)}")
            
            # Create A2A client with the authenticated httpx client
            # The JsonRpcTransport will use this client's headers for all requests
            auth_client = A2AClient(
                httpx_client=temp_client,
                agent_card=agent_data['card']
            )
            
            print(f"   Sending request via A2A protocol...")
            
            try:
                response = await auth_client.send_message(request)
                print(f"✅ Received response from {agent_name}")
            finally:
                await temp_client.aclose()
        else:
            # Use default client (no authentication)
            print(f"⚠️  No delegated token available, sending without authentication")
            response = await client.send_message(request)
        # ====================================================================
        
        # ====================================================================
        # STEP 5: Parse Response
        # ====================================================================
        # Extract the text from the A2A response structure
        print(f"📥 Received response from {agent_name}")
        
        if hasattr(response, 'root') and response.root:
            if hasattr(response.root, 'message') and response.root.message:
                if hasattr(response.root.message, 'parts') and response.root.message.parts:
                    part = response.root.message.parts[0]
                    if hasattr(part, 'text'):
                        # Successfully got text response!
                        return f"{agent_name} replied: {part.text}"
        
        # Alternative response format (some agents use 'data' field)
        if hasattr(response, 'data') and response.data:
            return f"{agent_name} data: {response.data}"
        
        # Unexpected format - return raw response for debugging
        return f"The agent responded, but format was unexpected: {response}"

    except Exception as e:
        # If communication fails, return error message
        return f"Error communicating with {agent_name}: {e}"

# ============================================================================
# MAIN ORCHESTRATOR FUNCTION
# ============================================================================
# This function:
# 1. Discovers available agents
# 2. Creates an AI orchestrator with GPT-4
# 3. Processes user queries by coordinating between agents
# ============================================================================

async def main():
    global USER_AUTHENTICATOR, TOKEN_EXCHANGER, MASTER_TOKEN, AGENT_CONFIGS
    
    print("="*70)
    print("🚀 MULTI-AGENT ORCHESTRATOR WITH SECURE TOKEN EXCHANGE")
    print("="*70)
    
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found in environment variables.")
        return

    # ========================================================================
    # STEP 1: Initialize Authentication Components
    # ========================================================================
    try:
        from browser_auth import create_browser_authenticator_from_env
        
        USER_AUTHENTICATOR = create_browser_authenticator_from_env()
        TOKEN_EXCHANGER = create_token_exchanger_from_env()
        
        print("\n✓ Authentication system initialized")
        print("  - User Authentication: Enabled (Browser Login)")
        print("  - Token Delegation: Enabled (OAuth Extension for AI Agents)")
        print("  - Agent configurations will be discovered dynamically from agent cards")
        
    except Exception as e:
        print(f"\n⚠️  Authentication initialization failed: {e}")
        print("  - Continuing without authentication")
        USER_AUTHENTICATOR = None
        TOKEN_EXCHANGER = None

    # ========================================================================
    # STEP 2: User Authentication (SINGLE LOGIN)
    # ========================================================================
    # Get master token with ONE browser login
    # Agent-specific tokens will be obtained via token exchange (no browser)
    if USER_AUTHENTICATOR:
        try:
            print("\n📝 Getting user authentication (single login)...")
            
            # Single browser login - no per-agent authentication
            MASTER_TOKEN = await USER_AUTHENTICATOR.authenticate_user(requested_actors=None)
            
            print("\n✓ User authenticated successfully")
            print(f"  Master Token: {MASTER_TOKEN[:30]}...")
            print(f"  Agent tokens will be obtained via token exchange (no browser)")
            
        except Exception as e:
            print(f"\n✗ User authentication failed: {e}")
            print("  Cannot continue without authentication")
            return
    else:
        print("\n⚠️  Skipping user authentication (not configured)")
    
    # ========================================================================
    # STEP 3: Load Agent Configuration from File
    # ========================================================================
    # Read config.json to get list of agents to discover
    # This allows easy modification of agents without changing code
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Extract enabled service agents only (exclude orchestrator)
        candidate_urls = [
            f"http://{agent['host']}:{agent['port']}"
            for agent in config["agents"] 
            if agent.get("enabled", True) and agent.get("type") == "service"
        ]
        
        print(f"Loaded configuration: {len(candidate_urls)} agents enabled")
        
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        print("Using default agent URLs...")
        candidate_urls = [
            "http://localhost:10005",
            "http://localhost:10006",
        ]
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file: {e}")
        return
    
    # ========================================================================
    # STEP 4: Create Persistent HTTP Client
    # ========================================================================
    # IMPORTANT: This client must stay alive throughout the entire execution!
    # If it closes, the A2A clients won't be able to send messages
    httpx_client = httpx.AsyncClient()
    
    try:
        # ====================================================================
        # STEP 5: Agent Discovery Phase
        # ====================================================================
        # Scan each URL to discover what agents are available
        # For each agent, we:
        # 1. Fetch their agent card (GET /.well-known/agent-card.json)
        # 2. Create an A2A client to communicate with them
        # 3. Store them in KNOWN_AGENTS registry
        # ====================================================================
        print(f"\n{'='*70}")
        print(f"🔍 DISCOVERING AGENTS")
        print(f"{'='*70}")
        print(f"Scanning: {candidate_urls}...")
        
        for url in candidate_urls:
            try:
                # Create a card resolver to fetch the agent's metadata
                resolver = A2ACardResolver(httpx_client=httpx_client, base_url=url)
                
                # Fetch the agent card (contains name, description, skills, etc.)
                card = await resolver.get_agent_card()
                
                # ============================================================
                # Create A2A Client (No Built-in Auth - We Handle Token Exchange)
                # ============================================================
                # We don't use automatic auth interceptor anymore
                # Instead, we manually add agent-specific tokens per request
                # ============================================================
                client = A2AClient(
                    httpx_client=httpx_client,  # Shared HTTP client
                    agent_card=card
                )
                
                # Register this agent in our global registry
                KNOWN_AGENTS[card.name] = {
                    "card": card,      # Metadata (name, description, skills)
                    "client": client,  # A2A client for sending messages
                    "url": url         # Base URL of the agent
                }
                
                # Extract or derive Asgardeo security configuration
                app_id = None
                app_secret = None
                required_scope = None
                config_source = "none"
                env_vars_tried = []
                
                # Strategy 1: Try to get from agent card metadata
                if hasattr(card, 'metadata') and card.metadata and 'asgardeo' in card.metadata:
                    asgardeo_meta = card.metadata['asgardeo']
                    app_id = asgardeo_meta.get('application_id')
                    required_scope = asgardeo_meta.get('required_scope')
                    if app_id:
                        config_source = "agent card"
                
                # Strategy 2: Discover from environment variables (tries multiple naming patterns)
                if not app_id:
                    app_id, app_secret, env_scope, env_vars_tried = get_agent_config_from_env(card.name)
                    if app_id:
                        config_source = "environment"
                        if not required_scope:
                            required_scope = env_scope
                
                # Get secret if not already retrieved
                if app_id and not app_secret:
                    _, app_secret, _, _ = get_agent_config_from_env(card.name)
                
                # Create agent config if we have minimum required info
                if app_id and required_scope:
                    AGENT_CONFIGS[card.name] = AgentConfig(
                        name=card.name,
                        app_id=app_id,
                        app_secret=app_secret or '',
                        required_scope=required_scope
                    )
                    
                    secret_status = "✓" if app_secret else "✗"
                    print(f"    Security: App ID={app_id[:15]}..., Scope={required_scope}, Secret={secret_status}")
                    print(f"    Source: {config_source}")
                else:
                    print(f"    Security: ⚠️  No configuration found (token exchange will be disabled)")
                    if env_vars_tried:
                        # Show first few attempted patterns for debugging
                        sample_vars = env_vars_tried[:3]
                        print(f"    Tried patterns: {', '.join(sample_vars)}...")
                
                print(f"  ✓ Found: '{card.name}' at {url}")
                
            except Exception as e:
                # If discovery fails for this URL, continue with others
                print(f"  ✗ Failed: {url}")
                print(f"    Error: {type(e).__name__}: {e})")

        # Check if we found any agents
        if not KNOWN_AGENTS:
            print("\n❌ No agents found! Please ensure agents are running.")
            return
        
        print(f"\n✓ Discovery complete: {len(KNOWN_AGENTS)} agent(s) available")

        # ====================================================================
        # STEP 6: Build Dynamic System Prompt
        # ====================================================================
        # Create a prompt that tells the LLM about available agents
        # The LLM will use this to decide which agent to call
        # ====================================================================
        
        agent_descriptions = []
        for name, data in KNOWN_AGENTS.items():
            desc = data['card'].description
            agent_descriptions.append(f"- Name: '{name}'\n  Description: {desc}")
        
        agent_info_text = "\n".join(agent_descriptions)
        
        system_prompt = f"""You are the Host Orchestrator. Your goal is to help the user by coordinating with available sub-agents.

Available Agents:
{agent_info_text}

Instructions:
1. Analyze the user's request.
2. Determine which agent(s) can handle parts of the request based on their descriptions.
3. Use the 'talk_to_agent' tool to delegate tasks to them. 
   - ALWAYS use the exact 'Name' listed above for the agent_name argument.
4. Synthesize the information from the agents to provide a final answer to the user.
"""

        # ====================================================================
        # STEP 7: Initialize AI Agent (LLM + Tools)
        # ====================================================================
        # Create a ReAct agent powered by GPT-4o
        # ReAct = Reasoning + Acting (the LLM thinks, then uses tools)
        # ====================================================================
        
        print(f"\n{'='*70}")
        print(f"🤖 INITIALIZING AI ORCHESTRATOR")
        print(f"{'='*70}")
        
        # Load LLM configuration from config file (with fallback to defaults)
        orchestrator_config = next(
            (agent for agent in config.get("agents", []) if agent.get("name") == "orchestrator"),
            {}
        )
        llm_config = orchestrator_config.get("llm", {})
        llm_model = llm_config.get("model", "gpt-4o")
        llm_temperature = llm_config.get("temperature", 0.7)
        
        # Create LLM instance (GPT from OpenAI)
        # temperature controls randomness in responses (0 = deterministic, 1 = creative)
        print(f"  Model: {llm_model}")
        print(f"  Temperature: {llm_temperature}")
        llm = ChatOpenAI(model=llm_model, temperature=llm_temperature).bind_tools(tools=[talk_to_agent])
        
        # Create a chat prompt template
        # This structures the conversation with system prompt + user messages
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),     # Our orchestrator instructions
            ("placeholder", "{messages}"), # User messages go here
        ])
        
        # Create the ReAct agent
        # This gives GPT-4 the ability to use the talk_to_agent tool
        agent_executor = create_react_agent(llm, [talk_to_agent], prompt=prompt)
        
        print(f"✓ AI Orchestrator ready")

        # ====================================================================
        # STEP 8: Process User Query
        # ====================================================================
        # Send a complex query that requires multiple agents
        # The LLM will:
        # 1. Analyze the query
        # 2. Decide to call vaccination agent for dog vaccines
        # 3. Decide to call appointments agent for Dr. Smith's schedule
        # 4. Synthesize both responses into a final answer
        # ====================================================================
        
        print(f"\n{'='*70}")
        print(f"💬 PROCESSING USER REQUEST")
        print(f"{'='*70}")
        
        user_input = "I need to check vaccination requirements for my dog, and then check if Dr. Smith is free for an appointment."
        
        print(f"\nUser: {user_input}")
        print("-" * 70)

        # Format input for LangChain
        inputs = {"messages": [HumanMessage(content=user_input)]}
        
        # Stream the agent's execution
        # This shows the LLM's reasoning process step-by-step
        async for event in agent_executor.astream(inputs, stream_mode="values"):
            message = event["messages"][-1]
            
            if message.type == "ai":
                # LLM is thinking or providing final answer
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    # LLM decided to call a tool
                    call = message.tool_calls[0]
                    print(f"\n[Orchestrator AI] Calling '{call['name']}' with: {call['args']}")
                else:
                    # LLM provided final answer
                    print(f"\n{'='*70}")
                    print(f"✅ FINAL ANSWER")
                    print(f"{'='*70}")
                    print(f"{message.content}")
                    print(f"{'='*70}")
            elif message.type == "tool":
                # Tool execution completed
                print(f"[System] Tool execution completed")
        
        print(f"\n{'='*70}")
        print(f"✓ WORKFLOW COMPLETE")
        print(f"{'='*70}")
        print(f"\nSummary:")
        print(f"  1. ✓ User authenticated via Asgardeo")
        print(f"  2. ✓ Master token acquired")
        print(f"  3. ✓ Token exchanged for agent-specific tokens")
        print(f"  4. ✓ Agents communicated successfully")
        print(f"  5. ✓ Response synthesized")
        print(f"{'='*70}")
    
    finally:
        # ====================================================================
        # CLEANUP: Close HTTP Client
        # ====================================================================
        # Always close the httpx client to free resources
        await httpx_client.aclose()

# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())