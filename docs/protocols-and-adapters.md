**English** | [简体中文](protocols-and-adapters.zh-CN.md)

# Protocols & Data Adapters

The framework separates **what the engine produces** (a stream of semantic events) from **how it's serialized on the wire** (the client-facing protocol). The wire format is pluggable via a `DataAdapter`. The default target is the Dify protocol; an OpenAI-compatible adapter ships in the box; you can implement your own.

## Where adapters sit

```
BaseWorkflow.stream()  ──►  StreamProcessor  ──►  semantic events  ──►  DataAdapter  ──►  SSE / JSON
                                          (src/goalflow/workflow/stream/types.py)   (protocol layer)
```

The generate service produces protocol-neutral lifecycle chunks and semantic events (`NodeRunStreamChunkEvent`, `NodeRunSucceededEvent`, `NodeRunInterruptEvent`, `NodeRunControlEvent`, `ProxyStreamDataChunk`). The adapter is the last hop that turns those into whatever bytes the client expects.

## The abstraction

`AbstractDataAdapter` ([`abstract_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/abstract_data_adapter.py)):

```python
class AbstractDataAdapter(ABC):

    @abstractmethod
    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        """Streaming: transform the engine's chunk stream into wire frames."""

    @abstractmethod
    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        """Blocking: transform a single response into the wire shape."""
```

The contract is **two distinctly named abstract methods**: `generate` (streaming) and `execute` (blocking). A subclass must implement both to be instantiable — `src/goalflow/app.py` calls `.generate()` for streaming mode and `.execute()` for blocking mode.

## The default: Dify protocol

The system's default interaction protocol is Dify's. The chatflow endpoints (`/v1/chat-messages`) and the chunk shapes (`StreamChunk` with `chunk_id` / `type` / `data` / `timestamp`, and the `workflow_started` / `node_finished` / `text_chunk` lifecycle events) follow Dify's conventions, so existing Dify clients can talk to this server with minimal change.

Because goalflow's internal streaming/blocking format already *is* the Dify protocol, the `DifyDataAdapter` ([`dify_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/dify_data_adapter.py)) is an identity/passthrough implementation: `generate` yields the engine's chunks unchanged and `execute` returns the blocking response as a dict. It exists so every supported protocol is represented by a concrete adapter and is uniformly discoverable.

## The included alternative: OpenAI-compatible

`OpenAIDataAdapter` ([`openai_data_adapter.py`](../src/goalflow/workflow/services/data_adapter/openai_data_adapter.py)) adapts the same engine output to the OpenAI Chat Completions shape. It backs the `POST /v1/chat/completions` endpoint (added for LLM-application filing/compliance requirements), so tools that speak the OpenAI API can drive your workflows. It implements:

- `generate(generator)` — streaming: emits `chat.completion.chunk` frames.
- `execute(data)` — blocking: emits a `chat.completion` object.

## Writing a custom adapter

To support a new protocol:

1. Create a class extending `AbstractDataAdapter` under `src/goalflow/workflow/services/data_adapter/`.
2. Implement `generate(self, generator)` for streaming and `execute(self, data)` for blocking (matching the concrete convention used by `OpenAIDataAdapter`).
3. Map each semantic event/lifecycle chunk to your target frame format. Reference `OpenAIDataAdapter` for how the engine's chunks are consumed.
4. Wire it into the endpoint. In `src/goalflow/app.py`, the adapter is instantiated and applied around the generate service's output; point your endpoint at your adapter instead of `OpenAIDataAdapter` (or select it per-request).

Because the adapter only sees the neutral event stream, you never touch the engine, the nodes, or the graph to add a protocol.

## Choosing the protocol per deployment

- **Dify clients** → use the native chatflow endpoints (default).
- **OpenAI-API clients** → use `/v1/chat/completions` (OpenAI adapter).
- **Your own client/gateway** → implement an adapter and expose it on a new endpoint.

See [api-reference.md](api-reference.md) for the endpoint list and [streaming-and-hitl.md](streaming-and-hitl.md) for what the semantic events mean.
