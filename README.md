# Secure Multi-Agent Token Exchange Workflow

This project demonstrates OAuth 2.0 Token Exchange (RFC 8693) with Asgardeo for secure agent-to-agent communication.

## Architecture

```
User → Signs into Asgardeo → Master Token (vaccination:read + appointments:read)
         ↓
Orchestrator (holds Master Token)
         ↓
Token Exchange: Master Token → Agent-Specific Token
         ↓
    ┌────────────────────┬────────────────────┐
    ↓                    ↓                    ↓
Vaccination Agent   Appointments Agent
(vaccination:read)  (appointments:read)
```

## Asgardeo Applications

You need **3 applications** in Asgardeo:

### 1. Orchestrator Application
- **Grant Types:** Device Authorization, Client Credentials, Token Exchange
- **Scopes:** `vaccination:read appointments:read openid profile`

### 2. Vaccination Agent Application  
- **Grant Types:** Token Exchange
- **Scopes:** `vaccination:read`

### 3. Appointments Agent Application
- **Grant Types:** Token Exchange
- **Scopes:** `appointments:read`

## Setup

1. **Configure Asgardeo applications** (see above)

2. **Update `.env`** with your credentials:
```bash
ASGARDEO_CLIENT_ID=<orchestrator_client_id>
ASGARDEO_CLIENT_SECRET=<orchestrator_client_secret>
VACCINATION_APP_ID=<vaccination_client_id>
APPOINTMENTS_APP_ID=<appointments_client_id>
```

3. **Update `agents_config.json`** with application IDs

4. **Install dependencies:**
```powershell
pip install -r requirements.txt
```

## Running the System

### Option 1: Demo (Recommended)
```powershell
python test_token_workflow.py
```

### Option 2: Full System
```powershell
# Terminal 1
cd vaccination
python __main__.py

# Terminal 2  
cd appoinments
python __main__.py

# Terminal 3
cd orchestrator
python agent.py
```

## How It Works

1. **User Authentication:**
   - User signs into Asgardeo via browser (Device Flow)
   - Orchestrator receives Master Token with full scopes

2. **Token Exchange:**
   - When calling Vaccination Agent: Master Token → Vaccination Token (vaccination:read only)
   - When calling Appointments Agent: Master Token → Appointments Token (appointments:read only)

3. **Agent Communication:**
   - Orchestrator sends restricted token to each agent
   - Agents validate tokens and respond
   - Orchestrator synthesizes responses

## Security Benefits

- ✅ **Least Privilege:** Each agent only gets the permissions it needs
- ✅ **Token Isolation:** Vaccination token cannot access appointments
- ✅ **Zero Trust:** Every request requires a valid token
- ✅ **Audit Trail:** All token exchanges are logged

## Key Files

- `orchestrator/user_auth.py` - User authentication via Device Flow
- `orchestrator/token_exchange.py` - RFC 8693 token exchange
- `orchestrator/agent.py` - Main orchestrator with GPT-4 routing
- `vaccination/agent_with_token.py` - Token-aware vaccination agent
- `appoinments/agent_with_token.py` - Token-aware appointments agent
- `test_token_workflow.py` - Complete workflow demonstration
- `setup_check.py` - Verify your configuration

## Troubleshooting

**Token exchange fails:**
- Verify application IDs in `.env` match Asgardeo console
- Ensure Token Exchange grant is enabled for all 3 applications

**User authentication timeout:**
- Complete sign-in within 5 minutes
- Check ASGARDEO_DEVICE_AUTHORIZE_URL is correct

**Agents not responding:**
- Ensure agents are running on ports 10005 and 10006
- Check middleware JWT validation settings

## License

MIT
