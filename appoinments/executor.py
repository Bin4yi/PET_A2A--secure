import logging

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

# Import the NEW appointment agent logic
from agent_with_token import AppointmentAgentWithToken as AppointmentAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AppointmentAgentExecutor(AgentExecutor):
    """Executor for the Pet Appointment Agent."""

    def __init__(self):
        self.agent = AppointmentAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task
        
        # Create a new task if needed
        if not task:
            task = new_task(context.message) # type: ignore
            await event_queue.enqueue_event(task)
        
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            async for item in self.agent.stream(query, task.context_id):
                # Send the answer
                await updater.update_status(
                    TaskState.completed,
                    new_agent_text_message(
                        item['content'],
                        task.context_id,
                        task.id,
                    ),
                    final=True
                )
                
                # Create an artifact for the appointment details
                await updater.add_artifact(
                    [Part(root=TextPart(text=item['content']))],
                    name='available_slots',
                )
                # Task is already completed with final=True above
                break

        except Exception as e:
            logger.error(f'An error occurred: {e}')
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        return False

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        pass