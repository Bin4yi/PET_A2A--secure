# Multi-Agent A2A Authentication Flow

## Overview

This document describes the secure authentication flow for the Multi-Agent A2A system using Asgardeo OAuth 2.0 Token Exchange (RFC 8693) with Trusted Token Issuer.

### Key Security Features

1. **Single Sign-On**: User authenticates once via browser
2. **Token Exchange**: Master token is exchanged for agent-specific tokens
3. **Audience Binding**: Each agent receives a token with its own client ID as audience
4. **No Browser Interrupts**: Agent communication happens without additional user interaction

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    
    participant User
    participant Browser
    participant Orchestrator
    participant Asgardeo
    participant VaccinationAgent as Vaccination Agent
    participant AppointmentsAgent as Appointments Agent

    %% ===== PHASE 1: User Authentication (Single Login) =====
    rect rgb(230, 245, 255)
        Note over User, Asgardeo: Phase 1: User Authentication (Single Browser Login)
        
        User->>Orchestrator: Start Request
        Orchestrator->>Browser: Open Authorization URL (PKCE)
        Browser->>Asgardeo: GET /authorize
        Asgardeo->>Browser: Login Page
        User->>Browser: Enter Credentials
        Browser->>Asgardeo: Submit Credentials
        Asgardeo->>Browser: Redirect with Auth Code
        Browser->>Orchestrator: Callback with Auth Code
        Orchestrator->>Asgardeo: POST /token (code + PKCE verifier)
        Asgardeo-->>Orchestrator: Master Access Token
        Note over Orchestrator: Master Token:<br/>aud: Orchestrator ID<br/>sub: User ID
    end

    %% ===== PHASE 2: Agent Discovery =====
    rect rgb(255, 245, 230)
        Note over Orchestrator, AppointmentsAgent: Phase 2: Agent Discovery (Public Endpoints)
        
        Orchestrator->>VaccinationAgent: GET /.well-known/agent-card.json
        VaccinationAgent-->>Orchestrator: Agent Card (name, skills, app_id)
        Orchestrator->>AppointmentsAgent: GET /.well-known/agent-card.json
        AppointmentsAgent-->>Orchestrator: Agent Card (name, skills, app_id)
    end

    %% ===== PHASE 3: LLM Processing =====
    rect rgb(245, 255, 230)
        Note over User, Orchestrator: Phase 3: LLM Request Processing
        
        User->>Orchestrator: "Check dog vaccines & Dr. Smith availability"
        Orchestrator->>Orchestrator: LLM analyzes request
        Note over Orchestrator: LLM decides to call:<br/>1. Vaccination Agent<br/>2. Appointments Agent
    end

    %% ===== PHASE 4: Token Exchange for Vaccination Agent =====
    rect rgb(255, 230, 245)
        Note over Orchestrator, Asgardeo: Phase 4: RFC 8693 Token Exchange (Vaccination)
        
        Orchestrator->>Asgardeo: POST /token (client_credentials)<br/>client_id: Vaccination App ID
        Asgardeo-->>Orchestrator: Actor Token (for auth)
        
        Orchestrator->>Asgardeo: POST /token (token-exchange)<br/>grant_type: token-exchange<br/>subject_token: Master Token<br/>subject_token_type: jwt<br/>scope: vaccination:read<br/>Auth: Basic (Vaccination credentials)
        Asgardeo-->>Orchestrator: ✓ Delegated Token<br/>aud: Vaccination Agent ID
    end

    %% ===== PHASE 5: Call Vaccination Agent =====
    rect rgb(230, 255, 245)
        Note over Orchestrator, VaccinationAgent: Phase 5: Secure Agent Communication (Vaccination)
        
        Orchestrator->>VaccinationAgent: POST /message<br/>Authorization: Bearer <delegated_token>
        
        Note over VaccinationAgent: JWT Validation:<br/>1. Verify signature (JWKS)<br/>2. Check expiration<br/>3. Verify issuer<br/>4. Verify audience = this agent
        
        VaccinationAgent->>Asgardeo: GET /jwks (cached)
        Asgardeo-->>VaccinationAgent: Public Keys
        
        VaccinationAgent->>VaccinationAgent: ✓ Token Valid<br/>✓ Audience Matches
        VaccinationAgent-->>Orchestrator: Vaccination Schedule Response
    end

    %% ===== PHASE 6: Token Exchange for Appointments Agent =====
    rect rgb(255, 230, 245)
        Note over Orchestrator, Asgardeo: Phase 6: RFC 8693 Token Exchange (Appointments)
        
        Orchestrator->>Asgardeo: POST /token (client_credentials)<br/>client_id: Appointments App ID
        Asgardeo-->>Orchestrator: Actor Token (for auth)
        
        Orchestrator->>Asgardeo: POST /token (token-exchange)<br/>grant_type: token-exchange<br/>subject_token: Master Token<br/>subject_token_type: jwt<br/>scope: appointments:read<br/>Auth: Basic (Appointments credentials)
        Asgardeo-->>Orchestrator: ✓ Delegated Token<br/>aud: Appointments Agent ID
    end

    %% ===== PHASE 7: Call Appointments Agent =====
    rect rgb(230, 255, 245)
        Note over Orchestrator, AppointmentsAgent: Phase 7: Secure Agent Communication (Appointments)
        
        Orchestrator->>AppointmentsAgent: POST /message<br/>Authorization: Bearer <delegated_token>
        
        Note over AppointmentsAgent: JWT Validation:<br/>1. Verify signature (JWKS)<br/>2. Check expiration<br/>3. Verify issuer<br/>4. Verify audience = this agent
        
        AppointmentsAgent-->>Orchestrator: Dr. Smith Availability Response
    end

    %% ===== PHASE 8: Response Synthesis =====
    rect rgb(245, 245, 255)
        Note over User, Orchestrator: Phase 8: Response Synthesis
        
        Orchestrator->>Orchestrator: LLM combines responses
        Orchestrator-->>User: Combined Answer:<br/>Dog vaccines + Dr. Smith availability
    end
```

## Token Flow Details

### Master Token (from browser auth)
```
{
  "aud": "6GcGVxi3GxDzmAFf756MwGzmuz8a",  // Orchestrator's client ID
  "sub": "67f171c3-e65a-4131-ab64-ebc0d7962504",  // User ID
  "iss": "https://api.asgardeo.io/t/pasansanjiiwa/oauth2/token"
}
```

### Delegated Token (after exchange for Vaccination Agent)
```
{
  "aud": "V5fehG024xohBqIuHzYWP7c59CEa",  // Vaccination Agent's client ID
  "sub": "67f171c3-e65a-4131-ab64-ebc0d7962504",  // Same User ID
  "iss": "https://api.asgardeo.io/t/pasansanjiiwa/oauth2/token"
}
```

### Delegated Token (after exchange for Appointments Agent)
```
{
  "aud": "GBuclOn0Oi68n8JF66f1Cq0WSrsa",  // Appointments Agent's client ID
  "sub": "67f171c3-e65a-4131-ab64-ebc0d7962504",  // Same User ID
  "iss": "https://api.asgardeo.io/t/pasansanjiiwa/oauth2/token"
}
```

## Security Guarantees

| Security Property | Implementation |
|------------------|----------------|
| User Identity | Preserved via `sub` claim in all tokens |
| Agent Authorization | Each token has unique `aud` matching agent's client ID |
| Token Integrity | Signature verified using Asgardeo JWKS |
| Token Freshness | Expiration (`exp`) checked on every request |
| Issuer Validation | Only tokens from Asgardeo org are accepted |

## Asgardeo Configuration

### Required Setup

1. **Trusted Token Issuer**: Configure your Asgardeo organization as a trusted token issuer for itself
2. **Applications**: Create separate applications for Orchestrator and each Agent
3. **API Resources**: Define scopes (`vaccination:read`, `appointments:read`)
4. **Scope Assignment**: Assign appropriate scopes to each application

### Token Exchange Request
```http
POST /oauth2/token HTTP/1.1
Host: api.asgardeo.io
Authorization: Basic <base64(agent_client_id:agent_client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<master_token>
&subject_token_type=urn:ietf:params:oauth:token-type:jwt
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
&scope=vaccination:read
```

### Key Point
The `subject_token_type` must be `jwt` (not `access_token`) for Asgardeo's Trusted Token Issuer flow to work.
