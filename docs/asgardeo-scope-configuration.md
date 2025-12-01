# Asgardeo Scope Configuration for Token Exchange

## The Issue

When using RFC 8693 Token Exchange with Asgardeo's Trusted Token Issuer, scopes are:
- ✅ Requested in the token exchange request
- ❌ **Silently ignored** if not properly configured
- ❌ **NOT included in the JWT access token's `scope` claim**

**Root Cause:** Asgardeo treats custom scopes (like `vaccination:read`) as part of an **API Resource**. You cannot just request arbitrary strings as scopes - they must be:
1. Defined in an API Resource
2. Authorized for the application
3. Assigned to the user via RBAC roles

## Solution: Complete Asgardeo Configuration

### Step 1: Create the API Resource (Define the Scopes)

Asgardeo requires custom scopes to be defined inside an API Resource.

1. Log in to the **Asgardeo Console**
2. Go to **API Authorization** (left sidebar)
3. Click **+ New API Resource**
4. Fill in the details:
   - **Identifier**: Use a URI format (e.g., `https://pet-clinic.example.com/api`)
   - **Display Name**: e.g., "Pet Clinic API"
5. Once created, go to the **Scopes** tab inside that resource
6. Add your scopes:
   - `vaccination:read`
   - `vaccination:write`
   - `appointments:read`
   - `appointments:write`

### Step 2: Authorize the Orchestrator Application

Your Orchestrator application must be explicitly allowed to request these scopes.

1. Go to **Applications** and select your **Orchestrator app** (Client ID: `6GcGVxi3GxDzmAFf756MwGzmuz8a`)
2. Go to the **API Authorization** tab
3. Click **Authorize API Resource**
4. Select the "Pet Clinic API" (created in Step 1)
5. **Select the specific scopes** (`vaccination:read`, `appointments:read`) and click **Update**

> ⚠️ **Important**: If you miss this step, the app requests the scope but Asgardeo silently ignores it!

### Step 3: Authorize the Agent Applications

Each agent application also needs to be authorized for the API Resource.

1. Go to **Applications** → **Pet Vaccination Agent** app (Client ID: `V5fehG024xohBqIuHzYWP7c59CEa`)
2. Go to **API Authorization** tab
3. Authorize the "Pet Clinic API" with scope `vaccination:read`

4. Repeat for **Pet Appointments Agent** app (Client ID: `GBuclOn0Oi68n8JF66f1Cq0WSrsa`)
5. Authorize with scope `appointments:read`

### Step 4: Assign Permissions to Users (RBAC)

Even if the App is allowed to request the scope, the **User** logging in must have permission to grant it.

1. Go to **User Management** → **Roles**
2. Click **+ New Role**
3. Name it (e.g., `PetOwner` or `ClinicUser`)
4. In the permissions setup:
   - Select the **API Resource** you created in Step 1
   - Select the scopes (`vaccination:read`, `appointments:read`) to assign to this role
5. Finish creating the role
6. Go to **Users**, select your user, and **assign the role** to them

### Step 5: Update Code to Use Full Scope Identifier

When requesting scopes that belong to an API Resource, use the **full identifier format**:

```
# Instead of:
scope="openid vaccination:read appointments:read"

# Use (with your API Resource identifier):
scope="openid https://pet-clinic.example.com/api/vaccination:read https://pet-clinic.example.com/api/appointments:read"
```

Update the following files:
- `orchestrator/browser_auth.py` - Authorization URL scope
- `orchestrator/token_exchange.py` - Token exchange scope
- `.env` - Scope configuration

## Alternative: Audience-Based Validation (Current Fallback)

If you don't need scopes in the JWT claims, the current implementation validates tokens using the **audience (`aud`) claim** instead. This is secure because:
- Each agent has a unique client ID
- Token exchange produces tokens with the agent's client ID as audience
- Only tokens intended for a specific agent will pass validation

This approach works **without** the API Resource configuration above.

## Configuration Checklist

Before running the system with scope validation, verify:

- [ ] API Resource created with identifier (e.g., `https://pet-clinic.example.com/api`)
- [ ] Scopes added to API Resource (`vaccination:read`, `appointments:read`)
- [ ] Orchestrator app authorized for API Resource with all scopes
- [ ] Vaccination Agent app authorized for `vaccination:read` scope
- [ ] Appointments Agent app authorized for `appointments:read` scope
- [ ] User role created with API Resource permissions
- [ ] User assigned to the role
- [ ] `.env` updated with `API_RESOURCE_IDENTIFIER`
- [ ] Code uses full scope format: `{identifier}/{scope}`

## Advanced Option: Pre-Issue Access Token Action

Asgardeo supports **Service Extensions** that can modify tokens before they're issued:

1. Go to **Service Extensions** → **Pre-Issue Access Token**
2. Create an action that adds custom claims based on the token exchange context
3. The action can add the `scope` claim based on the requested scopes

```javascript
// Example Pre-Issue Access Token Action
exports.main = async (context) => {
  const requestedScope = context.tokenRequest.scope;
  
  if (requestedScope) {
    context.accessToken.claims.scope = requestedScope;
  }
  
  return context;
};
```

## Current Implementation Details

### Token Exchange Request

```python
exchange_data = {
    'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
    'subject_token': master_token,
    'subject_token_type': 'urn:ietf:params:oauth:token-type:jwt',
    'requested_token_type': 'urn:ietf:params:oauth:token-type:access_token',
    'scope': 'vaccination:read'  # Requested but not in JWT claims
}
```

### Validation Approach

The middleware validates:
1. ✅ JWT Signature (via JWKS)
2. ✅ Token Expiration
3. ✅ Issuer (`iss` claim)
4. ✅ **Audience** (`aud` claim) - Token must be for this agent

```python
payload = jwt.decode(
    token,
    rsa_key,
    algorithms=['RS256'],
    issuer=self.issuer,
    audience=self.agent_id,  # Key validation!
    options={
        'verify_aud': True,  # Ensures token is for this agent
    }
)
```

## Security Considerations

### Why Audience Validation is Sufficient

1. **Token Uniqueness**: Each token exchange produces a token with a specific agent's client ID as audience
2. **Can't Reuse Tokens**: A token for the Vaccination Agent won't work for the Appointments Agent
3. **User Context Preserved**: The `sub` claim still contains the original user's identity
4. **Delegation Chain**: The `act` claim (if present) tracks the delegation chain

### When You Need Scope Validation

Add scope validation if you need:
- Fine-grained permissions within an agent (e.g., read vs write)
- Multiple permission levels for different operations
- Compliance requirements that mandate scope checking

## Testing

To verify the current configuration works:

```bash
# Start agents
python vaccination/__main__.py
python appoinments/__main__.py

# Run orchestrator
cd orchestrator
python agent.py
```

The output should show:
- ✅ Token exchange successful
- ✅ Audience matches agent's client ID
- ℹ️ Scope shows "NOT SET" (expected with current Asgardeo config)
- ✅ Agents respond successfully

## References

- [Asgardeo Token Exchange](https://wso2.com/asgardeo/docs/guides/authentication/configure-token-exchange/)
- [API Resources](https://wso2.com/asgardeo/docs/guides/authorization/api-authorization/api-authorization/)
- [Pre-Issue Access Token Action](https://wso2.com/asgardeo/docs/guides/service-extensions/pre-flow-extensions/pre-issue-access-token-action/)
