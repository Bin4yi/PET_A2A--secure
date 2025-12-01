# ============================================================================
# PET VACCINATION AGENT EXECUTOR - A2A PROTOCOL HANDLER
# ============================================================================
# This file handles the A2A (Agent-to-Agent) protocol communication.
# It receives incoming requests, calls the agent logic, and sends responses.
# Think of this as the "protocol adapter" between A2A and your agent logic.
# ============================================================================

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError

# Import the business logic (the "brain" of the agent)
from agent_with_token import PetVaccinationAgentWithToken as PetVaccinationAgent

class PetVaccinationAgentExecutor(AgentExecutor):
    """
    Executor that handles A2A protocol for the Pet Vaccination Agent.
    
    This class:
    - Receives incoming A2A message requests
    - Extracts the query from the request
    - Calls the agent logic to get an answer
    - Sends the response back via A2A protocol
    - Manages task lifecycle (created → in-progress → completed)
    """

    def __init__(self):
        """Initialize the executor with the agent logic."""
        # Create an instance of the vaccination agent (contains the business logic)
        self.agent = PetVaccinationAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Main execution method - called when an A2A message arrives.
        
        Flow:
        1. Validate the incoming request
        2. Extract the user's query
        3. Create/get a task for tracking
        4. Call agent logic to get response
        5. Send response back via A2A protocol
        
        Args:
            context: Contains the incoming message and metadata
            event_queue: Queue for sending responses back to caller
        """
        # ====================================================================
        # STEP 1: Validate Request
        # ====================================================================
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        # ====================================================================
        # STEP 2: Extract Query from Request
        # ====================================================================
        # Get the user's actual question (e.g., "What vaccines do dogs need?")
        query = context.get_user_input()
        task = context.current_task
        
        # ====================================================================
        # STEP 3: Create Task for Tracking
        # ====================================================================
        # Tasks track the lifecycle of a request (created → completed/failed)
        # If no task exists, create a new one
        if not task:
            task = new_task(context.message) # type: ignore
            await event_queue.enqueue_event(task)
        
        # Create updater for sending status updates and responses
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            # ================================================================
            # STEP 4: Get Response from Agent Logic
            # ================================================================
            # Call the agent's stream() method to get the answer
            async for item in self.agent.stream(query, task.context_id):
                # ============================================================
                # STEP 5: Send Response Back via A2A Protocol
                # ============================================================
                # Mark task as completed and send the response
                # final=True automatically completes the task
                await updater.update_status(
                    TaskState.completed,           # Task is done
                    new_agent_text_message(        # Create A2A message
                        item['content'],           # The actual answer
                        task.context_id,
                        task.id,
                    ),
                    final=True  # IMPORTANT: Marks task as complete (don't call updater.complete() after!)
                )
                
                # ============================================================
                # STEP 6: Add Artifact (Optional)
                # ============================================================
                # Artifacts are additional data/metadata attached to response
                # Useful for debugging or providing structured data
                await updater.add_artifact(
                    [Part(root=TextPart(text=item['content']))],
                    name='vaccination_schedule',
                )
                
                # Only process first response (since we have single-shot answers)
                break

        except Exception as e:
            # If anything goes wrong, send back an A2A error
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """
        Validate incoming request before processing.
        
        Returns:
            True if request is invalid, False if valid
            
        Note: Currently accepts all requests. You could add validation like:
        - Check if message is text-based
        - Check if user is authenticated
        - Rate limiting checks
        """
        return False  # All requests are valid

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """
        Handle cancellation requests.
        
        Called when a user wants to cancel an in-progress request.
        Simple agents like ours don't need cancellation support since
        responses are instant (no long-running operations).
        """
        pass  # No cancellation support needed