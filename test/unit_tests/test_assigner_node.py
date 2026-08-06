"""
AssignerNode 测试用例
测试 AssignerNode 的变量赋值和操作功能
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到路径
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from goalflow.workflow_types import VariableOperationItem, DefaultValue
from goalflow.node.assigner_node import AssignerNode
from goalflow.state import BaseState, GenericState
from goalflow.constants import WfNodeType, ErrorStrategy, AssignerInputType, AssignerOperation
from goalflow.service.workflow_conversation_variables_service import (
    WorkflowConversationVariablesService,
)
from goalflow.model.wf_conv_variable import WorkflowConversationVariables


class TestAssignerNode(unittest.TestCase):
    """AssignerNode 测试类"""

    def setUp(self):
        """每个测试前的设置"""
        print("🧪 AssignerNode 测试初始化")

        # Mock Redis和数据库连接
        self.redis_patcher = patch("cache.redis_manager.RedisClusterManager")
        self.db_patcher = patch("db.database.Database")

        self.mock_redis = self.redis_patcher.start()
        self.mock_db = self.db_patcher.start()

        # 配置Mock返回值
        self.mock_redis.is_enabled.return_value = True
        self.mock_db.health_check.return_value = True

    def tearDown(self):
        """每个测试后的清理"""
        self.redis_patcher.stop()
        self.db_patcher.stop()

    def create_test_state(self, **kwargs) -> GenericState:
        """创建测试用的状态对象"""
        default_state = {
            "sys_query": "测试查询",
            "sys_conversation_id": "test_conv_1234",
            "sys_user_id": "test_user",
            "sys_app_id": "test_app",
            "sys_workflow_id": "test_workflow",
            "sys_workflow_run_id": "test_run",
            "node_id": "test_node",
            "source_handle": "source",
            "step": 0,
            "outputs": {},
            "input_variables": {},
            "output_variables": {},
            "conversation_variables": {"a": "aaa", "b": "bbbb"},
            "environment_variables": {},
        }
        default_state.update(kwargs)
        return default_state

    def create_variable_operation_item(
        self,
        variable_selector: list[str],
        operation: AssignerOperation,
        input_type: AssignerInputType,
        value: any,
    ) -> VariableOperationItem:
        """创建变量操作项"""
        item = VariableOperationItem()
        item.variable_selector = variable_selector
        item.operation = operation
        item.input_type = input_type
        item.value = value
        return item

    def test_constant_assignment_overwrite(self):
        """测试常量赋值 - 覆写操作"""
        print("🔧 测试常量赋值 - 覆写操作")

        # 创建变量操作项
        assignment = self.create_variable_operation_item(
            variable_selector=["output", "test_var"],
            operation=AssignerOperation.OVER_WRITE,
            input_type=AssignerInputType.CONSTANT,
            value="测试值",
        )

        # 创建 AssignerNode
        assigner = AssignerNode(
            assignments=[assignment],
            id="test_assigner",
            desc="测试赋值节点",
            selected=True,
            title="测试赋值节点",
            type="assigner",
        )

        # 创建测试状态
        state = self.create_test_state()

        # 执行节点
        result = assigner.call(state)

        # 验证结果
        self.assertIsInstance(result, Command, "返回结果应该是 Command 对象")
        self.assertIn(
            "output_variables", result.update, "应该包含 output_variables 更新"
        )
        self.assertIn(
            "output_test_var", result.update["output_variables"], "应该包含目标变量"
        )
        self.assertEqual(
            result.update["output_variables"]["output_test_var"],
            "测试值",
            "变量值应该正确",
        )

        print("✅ 常量赋值 - 覆写操作测试通过")

    @patch.object(WorkflowConversationVariablesService, "get_by_conversation_id")
    @patch.object(WorkflowConversationVariablesService, "create")
    def test_conversation_variable_assignment(self, mock_create, mock_get):
        """测试会话变量赋值"""
        print("🔧 测试会话变量赋值")

        # Mock 数据库操作
        mock_get.return_value = None  # 模拟没有现有会话变量
        mock_create.return_value = True

        # 创建变量操作项
        assignment = self.create_variable_operation_item(
            variable_selector=["conversation", "user_name"],
            operation=AssignerOperation.OVER_WRITE,
            input_type=AssignerInputType.CONSTANT,
            value="张三",
        )

        # 创建 AssignerNode
        assigner = AssignerNode(
            assignments=[assignment],
            id="test_assigner",
            desc="测试赋值节点",
            selected=True,
            title="测试赋值节点",
            type="assigner",
        )

        # 创建测试状态
        state = self.create_test_state()

        # 执行节点
        result = assigner.call(state)

        # 验证结果
        self.assertIsInstance(result, Command, "返回结果应该是 Command 对象")
        self.assertIn(
            "conversation_variables",
            result.update,
            "应该包含 conversation_variables 更新",
        )
        self.assertIn(
            "conversation_user_name",
            result.update["conversation_variables"],
            "应该包含目标变量",
        )
        self.assertEqual(
            result.update["conversation_variables"]["conversation_user_name"],
            "张三",
            "变量值应该正确",
        )

        # 验证数据库操作被调用
        mock_get.assert_called_once_with(conversation_id="test_conv_1234")
        mock_create.assert_called_once()

        print("✅ 会话变量赋值测试通过")

    # ... 其他测试方法保持不变 ...


def main():
    """主函数"""
    print("🧪 AssignerNode 执行测试")
    print("=" * 60)

    # 使用unittest的测试运行器
    unittest.main(verbosity=2)


if __name__ == "__main__":
    main()
