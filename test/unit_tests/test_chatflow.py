import json
import os
import uuid
from contextlib import asynccontextmanager
from time import sleep
from typing import Optional, List, Any
import sys
import requests
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
#import main
from storage.mysql.database import Database
from goalflow.workflow.generated.workflow_industry import WorkflowIndustry


class ConversationService:
    url: str

    def __init__(self, *, url: str, api_key: str) -> None:
        self.url = url
        self.api_key = api_key

    # 是否还有下一页

    def get_conversations(self, *, user_id: str, last_id: str, limit: str = 100, conversations=[]) -> list:
        """
        查询全部的 会话记录
        """
        conversation_url = f"{self.url}/conversations?user={user_id}&limit={limit}&sort_by=-created_at"
        if last_id:
            conversation_url += f"&last_id={last_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.get(conversation_url, headers=headers)
        if response.status_code == 200:
            response_json = response.json()
            if response_json is not None:
                last_id = response_json["data"][-1]["id"]
                for data in response_json["data"]:
                    conversations.append(data)
            _has_more = False  # response_json["has_more"]
            if _has_more:
                self.get_conversations(user_id=user_id, last_id=last_id, limit=limit, conversations=conversations)

        return conversations


class MessageService:
    url: str

    def __init__(self, *, url: str, api_key: str) -> None:
        self.url = url
        self.api_key = api_key

    def get_message_by_conversation_id(self, *, conversation_id: str, user_id: str) -> dict:
        """
        通过会话id 查询会话记录
        """
        # 'localhost:9999/messages/8d3a6e35-cde7-4064-8076-6dc87ac28d04'

        local_url = f"{self.url}/messages/{conversation_id}"
        response = requests.get(local_url)
        return response.json()


@staticmethod
def get_state(*,
              query: str,
              user_id: str,
              app_id: str = "",
              workflow_id: str,
              conversation_id: str,
              sys_files: Optional[List[Any]] = None,
              inputs: dict = None,
              ):
    workflow_run_id = str(uuid.uuid4())

    # Convert input to state format
    return {
        "sys_query": query,
        "sys_user_id": user_id,
        "sys_app_id": app_id,
        "sys_workflow_id": workflow_id,
        "sys_workflow_run_id": workflow_run_id,
        "sys_conversation_id": conversation_id,
        "sys_files": sys_files,
        "input_variables": inputs
    }


if __name__ == '__main__':
    api_key = "app-Zm82FvsICMd016qoGvdn2XL6"
    conversation_service = ConversationService(
        url="http://172.26.124.23/v1",
        api_key=api_key
    )

    conversations = conversation_service.get_conversations(user_id="ai", last_id=None, limit=1)

    message_service = MessageService(
        url="http://192.168.40.230:9999",
        api_key=api_key
    )
    for conversation in conversations:
        conversation_id = conversation["id"]
        messages = message_service.get_message_by_conversation_id(conversation_id=conversation_id,
                                                                  user_id="ai")
        if messages and len(messages["data"]) > 0:
            for message in messages["data"]:
                inputs = {
                    "query": message["query"],
                    "conversation_id": conversation_id,
                    "user": "ai",
                    "response_mode": "stream",
                    "sys_app_id": "aira-workflow",
                    "sys_workflow_id": "1745215322322",
                    "sys_files": [],
                    "inputs": json.loads(message["inputs"]),

                }
                response = requests.post(f"http://localhost:8000/v1/chat-messages", json=inputs, stream=True,
                                         headers={"Accept": "text/event-stream"})
                print(response)
                # print(response.json())
                print("**" * 64)

                # wf = WorkflowIndustry()
                # wf.bind_subworkflows()
                # # wf.execute(
                # #     initial_state=state
                # # )
                # stream_iterator = wf.stream(
                #     initial_state=state,
                #     stream_mode="messages"
                # )
                for chunk in response:
                    print(chunk)  # 实时输出每个数据块
