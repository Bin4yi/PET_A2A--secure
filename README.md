# 🐾 Pet Care Multi-Agent System with Asgardeo Authentication

A multi-agent orchestration system for pet care services, featuring secure OAuth 2.0 token exchange via Asgardeo, AI agents, and intelligent request routing.

## 🌟 Overview

This project demonstrates a production-ready multi-agent architecture where:
- **Orchestrator Agent** intelligently routes user requests to specialized agents using GPT-4o
- **Vaccination Agent** provides AI-powered pet vaccination information using GPT-4o-mini
- **Appointments Agent** manages veterinary appointment scheduling using GPT-3.5-turbo
- **Asgardeo OAuth 2.0** secures all inter-agent communication with token exchange (RFC 8693)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         User                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Orchestrator Agent (GPT-4o)                     │
│  - User Authentication (Browser OAuth)                       │
│  - Intelligent Request Routing                               │
│  - Token Exchange (RFC 8693)                                 │
│  - Response Synthesis                                        │
└───────────┬─────────────────────────┬───────────────────────┘
            │                         │
            ▼                         ▼
┌───────────────────────┐   ┌───────────────────────┐
│ Vaccination Agent     │   │ Appointments Agent    │
│ (GPT-4o-mini)         │   │ (GPT-3.5-turbo)      │
│ - JWT Validation      │   │ - JWT Validation      │
│ - LLM Processing      │   │ - LLM Processing      │
│ Port: 10005           │   │ Port: 10006           │
└───────────────────────┘   └───────────────────────┘
```

## 📁 Project Structure

```
PET_A2A-secure/
├── config.json                 # Central configuration for all agents
├── .env                        # Environment variables (secrets)
├── README.md                   # This file
│
├── agents/                     # All agent implementations
│   ├── orchestrator_agent/     # Main orchestrator
│   │   ├── agent.py           # Orchestrator logic with LLM
│   │   ├── browser_auth.py    # User authentication (OAuth PKCE)
│   │   ├── token_exchange.py  # RFC 8693 token exchange
│   │   ├── auth.py            # Authentication utilities
│   │   └── requirements.txt
│   │
│   ├── vaccination_agent/      # Pet vaccination service
│   │   ├── agent.py           # LLM-powered vaccination agent
│   │   ├── executor.py        # A2A protocol handler
│   │   ├── middleware.py      # JWT validation middleware
│   │   ├── __main__.py        # Server entry point
│   │   └── requirements.txt
│   │
│   └── appointments_agent/     # Appointment scheduling service
│       ├── agent.py           # LLM-powered appointments agent
│       ├── executor.py        # A2A protocol handler
│       ├── middleware.py      # JWT validation middleware
│       ├── __main__.py        # Server entry point
│       └── requirements.txt
│
└── docs/                       # Documentation
    ├── asgardeo-scope-configuration.md
    └── sequence-diagram.md
```

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.12+**
- **Asgardeo Account** ([Sign up free](https://asgardeo.io/))
- **OpenAI API Key** ([Get one here](https://platform.openai.com/api-keys))

### 2. Installation

```powershell
# Clone the repository
git clone <repository-url>
cd PET_A2A-secure

# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows PowerShell

# Install dependencies for all agents
pip install -r agents/orchestrator_agent/requirements.txt
pip install -r agents/vaccination_agent/requirements.txt
pip install -r agents/appointments_agent/requirements.txt
```

### 3. Configure Asgardeo

#### Create Applications in Asgardeo Console:

1. **Orchestrator Application** (Standard Web Application)
   - Protocol: OAuth 2.0 / OpenID Connect
   - Allowed Grant Types: Authorization Code, Token Exchange
   - Callback URL: `http://localhost:8080/callback`
   - Note the Client ID and Secret

2. **Vaccination Agent Application** (M2M Application)
   - Protocol: OAuth 2.0
   - Allowed Grant Types: Client Credentials, Token Exchange
   - Note the Client ID and Secret

3. **Appointments Agent Application** (M2M Application)
   - Protocol: OAuth 2.0
   - Allowed Grant Types: Client Credentials, Token Exchange
   - Note the Client ID and Secret

#### Create API Resource:

1. Go to **API Resources** → **New API Resource**
2. Identifier: `https://api.petclinic.com`
3. Add Scopes:
   - `vaccination:read` - Access vaccination information
   - `appointments:read` - Access appointment scheduling

#### Configure Trusted Token Issuer:

1. Go to **Connections** → **Trusted Token Issuer** → **New Trusted Token Issuer**
2. Name: "Asgardeo Self"
3. Issuer: `https://api.asgardeo.io/t/<your-org>/oauth2/token`
4. Alias: `https://api.asgardeo.io/t/<your-org>/oauth2/token`
5. JWKS Endpoint: `https://api.asgardeo.io/t/<your-org>/oauth2/jwks`
6. **Account Linking**:
   - Primary Lookup Attribute: `sub`
   - Secondary Lookup Attribute: `email` (optional)

### 4. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
# Asgardeo Configuration
ASGARDEO_TOKEN_URL=https://api.asgardeo.io/t/<your-org>/oauth2/token
ASGARDEO_AUTHORIZE_URL=https://api.asgardeo.io/t/<your-org>/oauth2/authorize
ASGARDEO_JWKS_URL=https://api.asgardeo.io/t/<your-org>/oauth2/jwks
ASGARDEO_ISSUER=https://api.asgardeo.io/t/<your-org>

# Orchestrator Application
ASGARDEO_CLIENT_ID=<orchestrator-client-id>
ASGARDEO_CLIENT_SECRET=<orchestrator-client-secret>

# Vaccination Agent
VACCINATION_APP_ID=<vaccination-client-id>
VACCINATION_APP_SECRET=<vaccination-client-secret>
VACCINATION_REQUIRED_SCOPE=vaccination:read

# Appointments Agent
APPOINTMENTS_APP_ID=<appointments-client-id>
APPOINTMENTS_APP_SECRET=<appointments-client-secret>
APPOINTMENTS_REQUIRED_SCOPE=appointments:read

# API Resource
API_RESOURCE_IDENTIFIER=https://api.petclinic.com

# OpenAI
OPENAI_API_KEY=<your-openai-api-key>

# Enable/Disable Authentication
ASGARDEO_AUTH_ENABLED=true
```

### 5. Update config.json

The `config.json` file contains centralized configuration for all agents. Update the `application_id` fields with your Asgardeo client IDs.

### 6. Run the System

Open **three terminal windows**:

**Terminal 1 - Vaccination Agent:**
```powershell
cd agents/vaccination_agent
python __main__.py
```

**Terminal 2 - Appointments Agent:**
```powershell
cd agents/appointments_agent
python __main__.py
```

**Terminal 3 - Orchestrator:**
```powershell
cd agents/orchestrator_agent
python agent.py
```

The orchestrator will:
1. Open your browser for authentication
2. Discover available agents
3. Process your query using GPT-4o
4. Route requests to appropriate agents
5. Synthesize and return the final response

## 🔐 Security Features

### OAuth 2.0 Token Exchange (RFC 8693)
- **User Authentication**: Browser-based login with PKCE flow
- **Token Delegation**: Master token exchanged for agent-specific tokens
- **Audience Isolation**: Each agent validates its unique audience claim
- **Scope Validation**: Server-side scope verification via Trusted Token Issuer

### JWT Validation
- **Signature Verification**: Using Asgardeo's JWKS endpoint
- **Expiration Checks**: Automatic token expiry validation
- **Audience Matching**: Agent ID verification
- **Issuer Validation**: Ensures tokens from trusted Asgardeo org

### Security Best Practices
- ✅ No shared secrets between agents
- ✅ Principle of least privilege (minimal scopes)
- ✅ Token-based authentication for all agent communication
- ✅ Centralized identity management via Asgardeo

## ⚙️ Configuration Options

### Agent Configuration (config.json)

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Unique agent identifier | `"vaccination_agent"` |
| `type` | Agent type (`orchestrator` or `service`) | `"service"` |
| `enabled` | Enable/disable agent | `true` |
| `host` | Server host | `"localhost"` |
| `port` | Server port | `10005` |
| `application_id` | Asgardeo client ID | `"abc123..."` |
| `required_scope` | Required OAuth scope | `"vaccination:read"` |
| `llm.model` | OpenAI model name | `"gpt-4o-mini"` |
| `llm.temperature` | LLM creativity (0-1) | `0.5` |
| `logging.level` | Log level | `"INFO"` |

### Logging Levels

Set log levels in `config.json` to control verbosity:
- `"DEBUG"` - Detailed debugging information
- `"INFO"` - General informational messages (default)
- `"WARNING"` - Warning messages only
- `"ERROR"` - Error messages only
- `"CRITICAL"` - Critical errors only

### LLM Model Selection

Each agent can use a different LLM model:
- **Orchestrator**: `gpt-4o` - Best for complex reasoning and routing
- **Vaccination Agent**: `gpt-4o-mini` - Cost-effective for specialized tasks
- **Appointments Agent**: `gpt-3.5-turbo` - Fast responses for simple queries

## 🧪 Testing

### Test Individual Agents:

**Vaccination Agent:**
```powershell
cd agents/vaccination_agent
python __main__.py
```
Visit: `http://localhost:10005/.well-known/agent-card.json`

**Appointments Agent:**
```powershell
cd agents/appointments_agent
python __main__.py
```
Visit: `http://localhost:10006/.well-known/agent-card.json`

## 📝 Example Usage

```
User Query: "I need to check vaccination requirements for my dog, 
            and then check if Dr. Smith is free for an appointment."

Orchestrator (GPT-4o):
  ├─ Analyzes query (identifies two sub-tasks)
  ├─ Calls Vaccination Agent with "dog vaccination requirements"
  │   └─ Returns: Vaccination schedule for dogs
  ├─ Calls Appointments Agent with "Dr. Smith availability"
  │   └─ Returns: Dr. Smith's available slots
  └─ Synthesizes: Complete response combining both answers
```

## 🐛 Troubleshooting

### Token Exchange Fails
**Error:** `"Configured lookup attributes not found in the subject token"`

**Solution:** 
1. Verify Trusted Token Issuer configuration
2. Set Primary Lookup Attribute to `sub`
3. Ensure user has logged in successfully

### Agent Not Discovered
**Error:** `Agent not found` or `Connection refused`

**Solution:**
1. Check agent is running on correct port
2. Verify `config.json` has correct host/port
3. Check firewall settings

### LLM Not Responding
**Error:** `OpenAI API error` or `LLM service not available`

**Solution:**
1. Verify `OPENAI_API_KEY` in `.env`
2. Check OpenAI API quota/billing
3. Verify internet connection

### Authentication Disabled
**Warning:** `Authentication disabled`

**Cause:** Missing Asgardeo configuration in `.env`

**Solution:** Set all required `ASGARDEO_*` environment variables

## 📚 Documentation

- [Asgardeo Scope Configuration](docs/asgardeo-scope-configuration.md)
- [Sequence Diagram](docs/sequence-diagram.md)
- [OAuth 2.0 Token Exchange (RFC 8693)](https://datatracker.ietf.org/doc/html/rfc8693)
- [Asgardeo Documentation](https://wso2.com/asgardeo/docs/)

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

**Built with ❤️ for secure, intelligent multi-agent systems**
