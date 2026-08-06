import os
import sys
from langgraph.constants import START, END
from langgraph.graph import StateGraph

# 添加项目根目录到路径 (从 unit_tests -> test -> project_root)
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from goalflow.node.doc_extractor_node import DocExtractorNode


from goalflow.workflow_types import (
    File,
    FileType,
    FileTransferMethod,
    HttpRequestBodyConfig,
    HttpRequestBodyConfigItem,
    HttpNodeAuthorizationConfig,
    HttpNodeApiKeyConfig,
    HttpNodeRetryConfig,
    HttpNodeTimeoutConfig,
)
from goalflow.node import HttpRequestNode
from goalflow.state import GenericState, BaseState


class TestDocExtractorNode:
    """DocumentExtractor节点的单元测试"""

    def setUp(self):
        """测试前的设置"""
        self.id = "test_doc_extractor_node"
        self.variable_selector = ["sys", "files"]
        self.next_node_ids = ["next_node_1"]

        # 创建测试状态
        self.test_state = {
            "sys_query": "test query",
            "sys_dialogue_count": 1,
            "sys_conversation_id": "conv_123",
            "sys_user_id": "user_123",
            "sys_files": [
                {
                    type: "document",
                    "transfer_method": "remote_url",  # 使用字符串字面量
                    # "remote_url": "https://assets.wanlabai.com/industry_assistant/20250912/3e77db703bd02fd016ddaf921b419d41.pdf",
                    # "remote_url": "https://assets.wanlabai.com/industry_assistant/20250912/1663f9c6eb0fa0b20aec39005ea53794.docx",
                    # "remote_url": "https://assets.wanlabai.com/industry_assistant/20250912/b64fc4e4853f5d55a63fd84a15847317.doc",
                    "remote_url": "https://assets.wanlabai.com/industry_assistant/20250912/c2b4db6482fde7fb43a675fe5e7c8d96.xlsx",
                    # "remote_url":"https://assets.wanlabai.com/industry_assistant/20250912/743dab9885d493830dafe37b4c714298.xls"
                    # "remote_url":"https://assets.wanlabai.com/industry_assistant/20250912/74e66cc2e6a80bae8b144d1e10aee027.txt",
                    # "remote_url": "https://assets.wanlabai.com/industry_assistant/20250925/64a4d6f27a8253c1a8945c178036bb75.pdf",
                }
            ],
            "sys_app_id": "app_123",
            "sys_workflow_id": "wf_123",
            "sys_workflow_run_id": "run_123",
            "node_id": self.id,  # 修复：使用 self.id 而不是 self.node_id
            "source_handle": "source",
            "step": 1,
            "outputs": {},
            "input_variables": {},
            "output_variables": {},
            "conversation_variables": {},
            "environment_variables": {},
        }

    def _create_mock_file(
        self,
        file_type: FileType = FileType.DOCUMENT,
        transfer_method: FileTransferMethod = "remote_url",
        remote_url: str = "http://example.com/test.pdf",
    ) -> File:
        """创建模拟文件对象"""
        file = File(
            type=file_type, transfer_method=transfer_method, remote_url=remote_url
        )
        return file

    def test_document_extractor_node(self):
        """测试单个文件成功提取文本的情况"""
        # 调用setUp方法初始化属性
        self.setUp()

        # 准备测试数据
        mock_file = self._create_mock_file()
        extracted_text = "这是从PDF文件中提取的文本内容"

        # 执行测试
        result = DocExtractorNode(
            id=self.id,
            is_array_file=True,
            next_node_ids=self.next_node_ids,
            variable_selector=self.variable_selector,
            desc="",
            selected=False,
            title="文档提取器",
            type="document-extractor",
        ).call(self.test_state)

        print(result)


if __name__ == "__main__":
    TestDocExtractorNode().test_document_extractor_node()
