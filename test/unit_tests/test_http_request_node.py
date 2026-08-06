from langgraph.constants import START, END
from langgraph.graph import StateGraph

from goalflow.workflow_types import HttpRequestBodyConfig, HttpRequestBodyConfigItem, HttpNodeAuthorizationConfig, \
    HttpNodeApiKeyConfig, HttpNodeRetryConfig, HttpNodeTimeoutConfig
from goalflow.node import HttpRequestNode
from goalflow.state import GenericState, BaseState
from test.integration_tests.simple_demo import DeepSeekClient


def start_node(state: GenericState):
    print("执行 开始节点")
    return {
        "sys_query": state["sys_query"],
        "input_variables": {"sys_query": state["sys_query"]},
    }


class HttpRequestNodeTest:
    """
    http request node test
    """

    def __init__(self):
        print("🧪 HttpRequestNodeTest 测试初始化")

    def test_get(self):
        """
        测试 get 请求
        """

        body = HttpRequestBodyConfig()
        body.data = [HttpRequestBodyConfigItem(
            id="key-value-994",
            key="",
            type="text",
            value="{\"user_id\": \"{{#sys.query#}}\" ,\"user_name\": \"张三\"}",
        )]
        body.type = "json"

        try:
            builder = StateGraph(BaseState)
            builder.add_node("node_start", start_node)
            http_request_node = HttpRequestNode(
                # 'desc', 'selected', 'title', and 'type'
                desc="http request node",
                selected=False,
                title="http request node",
                type="http-request",
                url="http://172.26.124.23:8080/api/qcc/simple?apiName=FuzzySearch/GetList&companyName={{#sys_query#}}",
                method="get",
                headers={},
                body={
                    "data": [],
                    "type": "x-www-form-urlencoded"
                },
                authorization={
                    "config": {
                        "api_key": "str",
                        "header": "str",
                        "type": "str",
                    },
                    "type": "no-auth",  # "api-key"
                },
                params={},
                ssl_verify=False,
                retry_config={
                    "max_retries": 10,
                    "retry_enabled": True,
                    "retry_interval": 1000
                },
                timeout_config={
                    "retry_interval": 40000,
                    "max_read_timeout": 20000,
                    "max_write_timeout": 10000
                },
                variables=[]
            )
            builder.add_node("node_http_request", http_request_node)

            builder.add_edge(START, "node_start")
            builder.add_edge("node_start", "node_http_request")
            builder.add_edge("node_http_request", END)
            graph = builder.compile()
            graph.invoke({
                "sys_query": "阳光保险集团",
                "sys.dialogue_count": "你好",
            })
            return True
        except Exception as e:
            print(f"❌ 测试执行异常: {e}")
            return False

    def test_post(self):
        """
        测试 post 请求
        """

        body = HttpRequestBodyConfig()
        body.data = [HttpRequestBodyConfigItem(
            id="key-value-994",
            key="",
            type="text",
            value="{\"user_id\": \"{{#sys.query#}}\" ,\"user_name\": \"张三\"}",
        )]
        body.type = "json"

        authorization_config = HttpNodeApiKeyConfig()
        authorization_config.api_key = "str"
        authorization_config.header = "str"
        authorization_config.type = "bearer"

        authorization = HttpNodeAuthorizationConfig(
            config=authorization_config,
            type="api-key",
        )

        retry_config = HttpNodeRetryConfig(
            max_retries=3,
            retry_enabled=True,
            retry_interval=100
        )

        timeout_config = HttpNodeTimeoutConfig(
            max_connect_timeout=10000,
            max_read_timeout=8000,
            max_write_timeout=1000
        )

        try:
            builder = StateGraph(BaseState)
            builder.add_node("node_start", start_node)
            http_request_node = HttpRequestNode(
                desc="",
                selected=False,
                title="获取额外数据-mk",
                type="http-request",
                url="http://172.26.124.2:8120/indus_mk",
                method="post",
                headers={},
                body=body,
                authorization=authorization,
                params={},
                ssl_verify=False,
                retry_config=retry_config,
                timeout_config=timeout_config,
                variables=[]
            )
            builder.add_node("node_http_request", http_request_node)

            builder.add_edge(START, "node_start")
            builder.add_edge("node_start", "node_http_request")
            builder.add_edge("node_http_request", END)
            graph = builder.compile()
            graph.invoke({
                "sys_query": "阳光保险集团",
                "sys.dialogue_count": "你好",
            })
            return True
        except Exception as e:
            print(f"❌ 测试执行异常: {e}")
            return False

    def test_put(self):
        """
        测试 put 请求
        """
        pass

    def test_patch(self):
        """
        测试 patch 请求
        """
        pass

    def test_delete(self):
        """
        测试 delete 请求
        """
        pass

    def test_head(self):
        """
        测试 head 请求
        """
        pass

    def test_options(self):
        """
        测试 options 请求
        """
        pass

    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始运行 HttpRequestNodeTest 测试套件")
        print("=" * 60)

        tests = [
            self.test_get,
            self.test_post,
            # self.test_put,
            # self.test_patch,
            # self.test_delete,
            # self.test_head,
            # self.test_options,
        ]

        passed = 0
        failed = 0

        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ 测试执行异常: {e}")
                failed += 1

        print("\n" + "=" * 60)
        print(f"📊 测试结果汇总:")
        print(f"✅ 通过: {passed}")
        print(f"❌ 失败: {failed}")
        print(f"📈 成功率: {passed / (passed + failed) * 100:.1f}%")

        if failed == 0:
            print("🎉 所有测试都通过了！")
        else:
            print("⚠️ 有测试失败，请检查上述输出")

        return failed == 0


def main():
    """主函数"""
    print("🧪 Http Request Node 执行测试")
    print("=" * 60)

    tester = HttpRequestNodeTest()
    success = tester.run_all_tests()

    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()
