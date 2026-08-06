#!/usr/bin/env python3
"""
CodeNode 集成测试运行器
提供简单的命令行接口来运行 CodeNode 集成测试

这是唯一的 CodeNode 集成测试，展示基于 LangGraph 的完整工作流：
Start -> CodeNode -> Answer
"""

import sys
import os

def main():
    """主函数"""
    print("=" * 60)
    print("🌟 CodeNode 集成测试运行器")
    print("=" * 60)
    
    # 解析命令行参数
    mode = "all"  # 默认运行所有测试
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    
    # 导入测试模块
    try:
        from code_node_integration_test import CodeNodeIntegrationTest
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保在正确的目录下运行此脚本")
        sys.exit(1)
    
    tester = CodeNodeIntegrationTest()
    
    # 根据模式执行测试
    if mode == "all":
        print("🧪 运行所有 CodeNode 集成测试")
        success = tester.run_all_tests()
    elif mode == "sum":
        print("🧪 运行求和操作测试")
        success = tester.test_sum_operation()
    elif mode == "analyze":
        print("🧪 运行数据分析测试")
        success = tester.test_analyze_operation()
    elif mode == "error":
        print("🧪 运行错误处理测试")
        success = tester.test_error_handling()
    elif mode == "string":
        print("🧪 运行字符串输入测试")
        success = tester.test_string_input()
    elif mode == "help":
        show_help()
        sys.exit(0)
    else:
        print(f"❌ 未知模式: {mode}")
        print("💡 使用 'python run_code_integration.py help' 查看帮助")
        sys.exit(1)
    
    if success:
        print("\n🎉 测试执行完成！")
        sys.exit(0)
    else:
        print("\n❌ 测试执行失败！")
        sys.exit(1)


def show_help():
    """显示帮助信息"""
    help_text = """
🔧 CodeNode 集成测试运行器

用法: python run_code_integration.py [模式]

模式选项:
  all      运行所有集成测试 (默认)
  sum      运行求和操作测试
  analyze  运行数据分析测试
  error    运行错误处理测试
  string   运行字符串输入测试
  help     显示此帮助信息

示例:
  python run_code_integration.py           # 运行所有测试
  python run_code_integration.py sum       # 只运行求和测试
  python run_code_integration.py analyze   # 只运行分析测试

📝 说明:
这个集成测试展示了基于 LangGraph 的完整工作流：
Start -> CodeNode -> Answer

测试涵盖:
- 数学运算 (求和、平均值、最值)
- 数据分析 (统计信息)
- 错误处理 (无效输入)
- 输入格式 (JSON字符串)

🔍 工作流结构:
1. Start 节点: 接收数字列表和操作类型
2. Code 节点: 执行动态 Python 代码进行数据处理
3. Answer 节点: 格式化并输出最终结果
    """
    print(help_text)


if __name__ == "__main__":
    main()
