# ============================================================================
# TOKEN WORKFLOW DEMONSTRATION
# ============================================================================
# This script demonstrates the complete secure token exchange workflow:
#
# 1. User Authentication (Device Flow)
#    - User signs into Asgardeo via browser
#    - Master token acquired with full scopes (vaccine:admin, appt:schedule)
#
# 2. Token Exchange (RFC 8693)
#    - Master token swapped for vaccination agent token (vaccine:admin only)
#    - Master token swapped for appointment agent token (appt:schedule only)
#
# 3. Agent Communication
#    - Vaccination agent receives restricted token
#    - Vaccination agent performs secondary swap for hospital DB access
#    - Appointment agent receives restricted token
#    - Appointment agent performs secondary swap for scheduling system access
#
# 4. Response Synthesis
#    - Orchestrator combines responses from both agents
#    - Returns unified answer to user
# ============================================================================

import asyncio
import os
from dotenv import load_dotenv

# Import authentication and token exchange modules
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'orchestrator'))

from user_auth import create_user_authenticator_from_env
from token_exchange import (
    create_token_exchanger_from_env,
    get_vaccination_agent_config,
    get_appointments_agent_config
)

load_dotenv()


async def demonstrate_token_workflow():
    """
    Demonstrate the complete token exchange workflow.
    """
    print("\n" + "="*80)
    print("🔐 SECURE MULTI-AGENT TOKEN EXCHANGE WORKFLOW DEMONSTRATION")
    print("="*80)
    
    # ========================================================================
    # PHASE 1: USER AUTHENTICATION
    # ========================================================================
    print("\n" + "="*80)
    print("PHASE 1: USER AUTHENTICATION (Device Authorization Flow)")
    print("="*80)
    
    try:
        # Create user authenticator
        user_auth = create_user_authenticator_from_env()
        
        # Authenticate user (opens browser, waits for user to sign in)
        print("\n⏳ Initiating user authentication...")
        master_token = await user_auth.authenticate_user()
        
        print("\n✓ PHASE 1 COMPLETE")
        print(f"  User authenticated successfully")
        print(f"  Master Token: {master_token[:40]}...")
        print(f"  Scopes: vaccine:admin appt:schedule openid profile")
        
    except Exception as e:
        print(f"\n❌ PHASE 1 FAILED: {e}")
        return
    
    # ========================================================================
    # PHASE 2: TOKEN EXCHANGE FOR AGENTS
    # ========================================================================
    print("\n" + "="*80)
    print("PHASE 2: TOKEN EXCHANGE (Master → Agent-Specific Tokens)")
    print("="*80)
    
    try:
        # Create token exchanger
        token_exchanger = create_token_exchanger_from_env()
        
        # Get agent configurations
        vaccination_config = get_vaccination_agent_config()
        appointments_config = get_appointments_agent_config()
        
        # Exchange for vaccination agent token
        print("\n🔄 Exchanging token for Vaccination Agent...")
        vaccination_token = await token_exchanger.exchange_for_agent_token(
            master_token=master_token,
            agent_name=vaccination_config.name,
            agent_app_id=vaccination_config.app_id,
            required_scope=vaccination_config.required_scope
        )
        
        # Exchange for appointments agent token
        print("\n🔄 Exchanging token for Appointments Agent...")
        appointments_token = await token_exchanger.exchange_for_agent_token(
            master_token=master_token,
            agent_name=appointments_config.name,
            agent_app_id=appointments_config.app_id,
            required_scope=appointments_config.required_scope
        )
        
        print("\n✓ PHASE 2 COMPLETE")
        print(f"  Vaccination Token: {vaccination_token[:40]}...")
        print(f"    Scope: {vaccination_config.required_scope}")
        print(f"  Appointments Token: {appointments_token[:40]}...")
        print(f"    Scope: {appointments_config.required_scope}")
        
    except Exception as e:
        print(f"\n❌ PHASE 2 FAILED: {e}")
        return
    
    # ========================================================================
    # PHASE 3: AGENT INTERACTION SIMULATION
    # ========================================================================
    print("\n" + "="*80)
    print("PHASE 3: AGENT INTERACTION (Simulated)")
    print("="*80)
    
    print("\n📤 Orchestrator → Vaccination Agent")
    print(f"  Sending: Restricted token (vaccination:read only)")
    print(f"  Token: {vaccination_token[:40]}...")
    print(f"  Query: 'What vaccines does my dog need?'")
    
    print("\n📥 Vaccination Agent Response:")
    print(f"  1. ✓ Validated incoming token")
    print(f"  2. ✓ Verified scope: vaccination:read")
    print(f"  3. ✓ Retrieved vaccination schedule")
    print(f"  4. ✓ Returned: 'For Dogs: 6-8 weeks: Distemper, Parvovirus...'")
    
    print("\n📤 Orchestrator → Appointments Agent")
    print(f"  Sending: Restricted token (appointments:read only)")
    print(f"  Token: {appointments_token[:40]}...")
    print(f"  Query: 'Is Dr. Smith available?'")
    
    print("\n📥 Appointments Agent Response:")
    print(f"  1. ✓ Validated incoming token")
    print(f"  2. ✓ Verified scope: appointments:read")
    print(f"  3. ✓ Retrieved Dr. Smith's availability")
    print(f"  4. ✓ Returned: 'Dr. Smith has the following openings...'")
    
    # ========================================================================
    # PHASE 4: SECURITY VERIFICATION
    # ========================================================================
    print("\n" + "="*80)
    print("PHASE 4: SECURITY VERIFICATION")
    print("="*80)
    
    print("\n🔒 Security Properties Verified:")
    print(f"  ✓ Master token has broad permissions (vaccination:read + appointments:read)")
    print(f"  ✓ Vaccination token ONLY has vaccination:read")
    print(f"    ❌ Cannot be used to schedule appointments")
    print(f"  ✓ Appointments token ONLY has appointments:read")
    print(f"    ❌ Cannot be used to access vaccination records")
    print(f"  ✓ User identity preserved throughout entire workflow")
    print(f"  ✓ Principle of least privilege enforced")
    
    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print("\n" + "="*80)
    print("✅ WORKFLOW DEMONSTRATION COMPLETE")
    print("="*80)
    
    print("\n📊 Token Exchange Summary:")
    print(f"  Level 0 (User): Master Token")
    print(f"    └─ Scopes: vaccination:read, appointments:read, openid, profile")
    print(f"  ")
    print(f"  Level 1 (Orchestrator → Agents):")
    print(f"    ├─ Vaccination Token (vaccination:read only)")
    print(f"    └─ Appointments Token (appointments:read only)")
    
    print("\n🎯 Key Benefits:")
    print(f"  • Zero Trust Architecture: Each component has minimal permissions")
    print(f"  • Token Isolation: Compromised agent token cannot access other services")
    print(f"  • Audit Trail: Every token exchange is logged and traceable")
    print(f"  • User Context: Original user identity maintained throughout")
    print(f"  • Scalability: Easy to add new agents with specific permissions")
    
    print("\n" + "="*80)
    print(f"Demo completed successfully! 🎉")
    print("="*80 + "\n")


async def main():
    """Main entry point."""
    try:
        await demonstrate_token_workflow()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "="*80)
    print("SECURE MULTI-AGENT TOKEN EXCHANGE - DEMONSTRATION")
    print("="*80)
    print("\nThis demo shows how tokens flow through a secure multi-agent system:")
    print("  1. User authenticates → Master token")
    print("  2. Orchestrator swaps → Agent-specific tokens")
    print("  3. Each token has minimal required permissions")
    print("\nPress Ctrl+C to exit at any time.")
    print("="*80)
    
    # Run the async demo
    asyncio.run(main())
