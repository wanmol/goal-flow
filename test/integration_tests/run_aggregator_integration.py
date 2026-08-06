#!/usr/bin/env python3
"""
AggregatorNode 集成测试运行器
提供简单的命令行接口来运行 AggregatorNode 集成测试

这个集成测试展示基于 LangGraph 的完整工作流：
Start -> [Code Node, Text Code Node] -> AggregatorNode -> Answer
"""

import sys
import os

def main():
    """主函数"""
    print("=" * 60)
    print("🌟 AggregatorNode 集成测试运行器")
    print("=" * 60)
    
    # 解析命令行参数
    mode = "all"  # 默认运行所有测试
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    
    # 导入测试模块
    try:
        from aggregator_node_integration_test import AggregatorNodeIntegrationTest
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保在正确的目录下运行此脚本")
        print("建议从项目根目录运行: python test/integration_tests/run_aggregator_integration.py")
        exit(1)
    
    # 创建测试实例
    tester = AggregatorNodeIntegrationTest()
    
    # 根据模式运行测试
    if mode == "all":
        print("🧪 运行所有 AggregatorNode 集成测试")
        success = tester.run_all_tests()
    elif mode == "non_grouped" or mode == "1":
        print("🧪 运行非分组聚合测试")
        success = tester.test_non_grouped_aggregation()
    elif mode == "grouped" or mode == "2":
        print("🧪 运行分组聚合测试")
        success = tester.test_grouped_aggregation()
    elif mode == "fallback" or mode == "3":
        print("🧪 运行兜底聚合测试")
        success = tester.test_fallback_aggregation()
    else:
        print(f"❌ 未知的测试模式: {mode}")
        print("可用模式:")
        print("  all        - 运行所有测试")
        print("  non_grouped - 运行非分组聚合测试")
        print("  grouped    - 运行分组聚合测试") 
        print("  fallback   - 运行兜底聚合测试")
        print("  1          - 等同于 non_grouped")
        print("  2          - 等同于 grouped")
        print("  3          - 等同于 fallback")
        exit(1)
    
    # 输出最终结果
    if success:
        print("\n🎉 测试执行成功！")
        exit(0)
    else:
        print("\n💥 测试执行失败！")
        exit(1)


if __name__ == "__main__":
    main()
