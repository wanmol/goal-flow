#!/usr/bin/env python3
"""
演示运行脚本 - 提供交互式和批量测试两种模式
"""

import sys
import os
# 添加项目根目录到路径 (从 integration_tests -> test -> project_root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from simple_demo import SimpleDemoWorkflow

# DeepSeek API Key - 从环境变量读取
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


def interactive_mode(use_deepseek=True):
    """交互式模式 - 允许用户输入问题"""
    print("🚀 进入交互式模式")
    if use_deepseek:
        print("🤖 使用DeepSeek AI模型")
    else:
        print("🎭 使用模拟回复")
    print("输入 'quit', 'exit' 或 'q' 退出\n")
    
    workflow = SimpleDemoWorkflow(
        deepseek_api_key=DEEPSEEK_API_KEY if use_deepseek else None,
        use_mock_llm=not use_deepseek
    )
    
    while True:
        try:
            user_input = input("👤 请输入您的问题: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q', '退出']:
                print("👋 再见！")
                break
                
            if not user_input:
                print("⚠️  请输入有效问题")
                continue
                
            print(f"\n🤖 处理中...")
            result = workflow.execute(user_input)
            final_answer = result.get("output_variables", {}).get("final_answer", "无回答")
            
            print(f"\n✨ AI回答: {final_answer}\n")
            print("-" * 60)
            
        except KeyboardInterrupt:
            print("\n👋 用户中断，再见！")
            break
        except Exception as e:
            print(f"❌ 执行出错: {e}")


def batch_test_mode(use_deepseek=True):
    """批量测试模式 - 运行预设的测试用例"""
    print("🧪 批量测试模式")
    if use_deepseek:
        print("🤖 使用DeepSeek AI模型")
    else:
        print("🎭 使用模拟回复")
    
    workflow = SimpleDemoWorkflow(
        deepseek_api_key=DEEPSEEK_API_KEY if use_deepseek else None,
        use_mock_llm=not use_deepseek
    )
    
    test_cases = [
        {
            "query": "你好，请问你是谁？",
            "description": "基础问候测试"
        },
        {
            "query": "今天天气怎么样？",
            "description": "天气查询测试"  
        },
        {
            "query": "请解释一下人工智能",
            "description": "知识问答测试"
        },
        {
            "query": "1+1等于几？",
            "description": "数学计算测试"
        },
        {
            "query": "帮我写一首诗",
            "description": "创作能力测试"
        }
    ]
    
    success_count = 0
    total_count = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 测试用例 {i}/{total_count}: {test_case['description']}")
        print(f"🔍 问题: {test_case['query']}")
        
        try:
            result = workflow.execute(test_case['query'])
            final_answer = result.get("output_variables", {}).get("final_answer", "无回答")
            print(f"✅ 成功! 回答: {final_answer}")
            success_count += 1
        except Exception as e:
            print(f"❌ 失败: {e}")
        
        print("-" * 80)
    
    print(f"\n📊 测试结果: {success_count}/{total_count} 成功")
    if success_count == total_count:
        print("🎉 所有测试都通过了！")
    else:
        print(f"⚠️  有 {total_count - success_count} 个测试失败")


def quick_test(use_deepseek=True):
    """快速测试 - 运行一个简单的验证"""
    print("⚡ 快速测试模式")
    if use_deepseek:
        print("🤖 使用DeepSeek AI模型")
    else:
        print("🎭 使用模拟回复")
    
    try:
        workflow = SimpleDemoWorkflow(
            deepseek_api_key=DEEPSEEK_API_KEY if use_deepseek else None,
            use_mock_llm=not use_deepseek
        )
        result = workflow.execute("你好")
        final_answer = result.get("output_variables", {}).get("final_answer", "")
        
        if final_answer:
            print("✅ 工作流运行正常！")
            print(f"测试回答: {final_answer}")
            return True
        else:
            print("❌ 工作流运行异常：没有获得回答")
            return False
            
    except Exception as e:
        print(f"❌ 工作流运行失败: {e}")
        return False


def show_help():
    """显示帮助信息"""
    help_text = """
🔧 Aira 工作流演示运行器

用法: python run_demo.py [模式] [选项]

模式选项:
  interactive  交互式模式 - 允许用户输入问题 (默认)
  batch        批量测试模式 - 运行预设测试用例
  quick        快速测试模式 - 运行单个验证测试
  help         显示此帮助信息

选项:
  --mock       使用模拟LLM回复而不是DeepSeek API

示例:
  python run_demo.py                    # 使用DeepSeek API的交互模式
  python run_demo.py interactive        # 使用DeepSeek API的交互模式
  python run_demo.py interactive --mock # 使用模拟回复的交互模式
  python run_demo.py batch             # 使用DeepSeek API的批量测试
  python run_demo.py quick --mock      # 使用模拟回复的快速测试

📝 说明:
这个演示展示了一个简单的 Start -> LLM -> Answer 工作流。
默认使用DeepSeek API进行真实的AI对话，也可以使用 --mock 选项进行模拟测试。

🔑 API密钥:
DeepSeek API密钥已内置在代码中，实际生产环境中应从环境变量读取。
    """
    print(help_text)


def main():
    """主函数"""
    print("=" * 60)
    print("🌟 Aira 工作流演示系统")
    print("=" * 60)
    
    # 解析命令行参数
    mode = "interactive"  # 默认模式
    use_deepseek = True   # 默认使用DeepSeek API
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    
    # 检查是否有--mock选项
    if "--mock" in sys.argv:
        use_deepseek = False
    
    # 根据模式执行相应功能
    if mode in ["interactive", "i"]:
        interactive_mode(use_deepseek)
    elif mode in ["batch", "b"]:
        batch_test_mode(use_deepseek)
    elif mode in ["quick", "q"]:
        quick_test(use_deepseek)
    elif mode in ["help", "h", "--help", "-h"]:
        show_help()
    else:
        print(f"❌ 未知模式: {mode}")
        print("💡 使用 'python run_demo.py help' 查看帮助")
        sys.exit(1)


if __name__ == "__main__":
    main()
