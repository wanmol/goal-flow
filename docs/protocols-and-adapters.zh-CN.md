[English](protocols-and-adapters.md) | **简体中文**

# 协议与数据适配器

本框架将**引擎产出什么**（一串语义事件流）与**如何在传输层序列化**（面向客户端的协议）解耦。传输格式通过 `DataAdapter` 可插拔。默认目标是 Dify 协议；内置了一个 OpenAI 兼容适配器；你也可以实现自己的适配器。

## 适配器所处的位置

```
BaseWorkflow.stream()  ──►  StreamProcessor  ──►  semantic events  ──►  DataAdapter  ──►  SSE / JSON
                                          (src/goalflow/workflow/stream/types.py)   (protocol layer)
```

生成服务产出与协议无关的生命周期数据块和语义事件（`NodeRunStreamChunkEvent`、`NodeRunSucceededEvent`、`NodeRunInterruptEvent`、`NodeRunControlEvent`、`ProxyStreamDataChunk`）。适配器是最后一环，负责将这些事件转换成客户端期望的字节流。

## 抽象层

`AbstractDataAdapter`（[`abstract_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/abstract_data_adapter.py)）：

```python
class AbstractDataAdapter(ABC):

    @abstractmethod
    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        """Streaming: transform the engine's chunk stream into wire frames."""

    @abstractmethod
    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        """Blocking: transform a single response into the wire shape."""
```

契约是**两个名称不同的抽象方法**:`generate`(流式)和 `execute`(阻塞)。子类必须两个都实现才能被实例化 —— `src/goalflow/app.py` 在流式模式下调用 `.generate()`,在阻塞模式下调用 `.execute()`。

## 默认：Dify 协议

系统默认的交互协议是 Dify 的协议。chatflow 端点（`/v1/chat-messages`）以及数据块结构（带有 `chunk_id` / `type` / `data` / `timestamp` 的 `StreamChunk`，以及 `workflow_started` / `node_finished` / `text_chunk` 等生命周期事件）都遵循 Dify 的约定，因此现有的 Dify 客户端只需极少改动即可与本服务端通信。

由于 goalflow 的内部流式/阻塞格式本身**就是** Dify 协议,`DifyDataAdapter`([`dify_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/dify_data_adapter.py))是一个 identity/透传实现:`generate` 原样逐条输出引擎的数据块,`execute` 把阻塞响应返回为 dict。它的存在是为了让每个受支持的协议都由一个具体适配器来表示,统一可发现。

## 内置的替代方案：OpenAI 兼容

`OpenAIDataAdapter`（[`openai_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/openai_data_adapter.py)）将相同的引擎输出适配为 OpenAI Chat Completions 结构。它支撑着 `POST /v1/chat/completions` 端点（为满足 LLM 应用备案/合规要求而添加），因此凡是使用 OpenAI API 的工具都能驱动你的工作流。它实现了：

- `generate(generator)` —— 流式：发出 `chat.completion.chunk` 帧。
- `execute(data)` —— 阻塞：发出一个 `chat.completion` 对象。

## 编写自定义适配器

要支持一种新协议：

1. 在 `src/goalflow/workflow/services/data_adapter/` 下创建一个继承 `AbstractDataAdapter` 的类。
2. 实现用于流式的 `generate(self, generator)` 和用于阻塞的 `execute(self, data)`（与 `OpenAIDataAdapter` 使用的具体约定保持一致）。
3. 将每个语义事件/生命周期数据块映射到你的目标帧格式。参考 `OpenAIDataAdapter` 了解引擎数据块是如何被消费的。
4. 将其接入端点。在 `src/goalflow/app.py` 中，适配器被实例化并套用在生成服务的输出之上；将你的端点指向你的适配器而非 `OpenAIDataAdapter`（或按请求进行选择）。

由于适配器只看到中立的事件流，添加一种协议时你永远无需触碰引擎、节点或图。

## 按部署选择协议

- **Dify 客户端** → 使用原生 chatflow 端点（默认）。
- **OpenAI-API 客户端** → 使用 `/v1/chat/completions`（OpenAI 适配器）。
- **你自己的客户端/网关** → 实现一个适配器并在新端点上暴露它。

端点列表见 [api-reference.md](api-reference.md)，语义事件的含义见 [streaming-and-hitl.md](streaming-and-hitl.md)。
