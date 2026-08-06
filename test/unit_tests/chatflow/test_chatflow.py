import os
import sys
import uuid
from datetime import datetime

from goalflow.app import WorkflowInput, WorkflowOutput
from generated.workflow import GeneratedWorkflow_1755073385417
from goalflow.state import BaseState
from goalflow.tool.dify_transformer import WorkflowCodeGenerator
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

class TestChatflow:

    def generate(self):
        test_file_dir = os.path.dirname(os.path.abspath(__file__))
        generator = WorkflowCodeGenerator(f"{test_file_dir}{os.sep}" + "start_llm_end.yml")
        generator.generate()

    def prepare_initial_state(self,workflow_input: WorkflowInput) -> BaseState:
        """Prepare initial state from input."""
        workflow_run_id = str(uuid.uuid4())

        # Convert input to state format
        initial_state = {
            "sys_query": workflow_input.query,
            "sys_user_id": workflow_input.user,
            "sys_app_id": workflow_input.sys_app_id,
            "sys_workflow_id": workflow_input.sys_workflow_id,
            "sys_workflow_run_id": workflow_run_id,
            "sys_conversation_id": workflow_input.conversation_id,
            "sys_files": workflow_input.sys_files,
            "input_variables": workflow_input.inputs
        }

        return initial_state

    def test1(self):
        workflow_run_id = str(uuid.uuid4())
        workflow_input = WorkflowInput(
            query="你好",  # 必填
            user="test_user",  # 必填
            conversation_id="1",
            sys_workflow_id="test_app",
            response_mode="stream" ,
            sys_app_id="11" ,
            sys_files=[],
            inputs={},
        )

        workflow = GeneratedWorkflow_1755073385417()

        start_time = datetime.utcnow()
        initial_state = self.prepare_initial_state(workflow_input=workflow_input)
        initial_state["sys_workflow_run_id"] = workflow_run_id
        result_state = workflow.stream(initial_state)

        execution_time = (datetime.utcnow() - start_time).total_seconds()
        print(execution_time)

        return WorkflowOutput(
            success=True,
            workflow_run_id=workflow_run_id,
            result=dict(result_state),
            execution_time=execution_time
        )

if __name__ == '__main__':
    chat_flow = TestChatflow()
    # chat_flow.generate()
    chat_flow.test1()