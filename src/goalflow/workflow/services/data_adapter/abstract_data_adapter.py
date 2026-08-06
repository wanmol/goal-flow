from typing import Generator
from abc import abstractmethod, ABC
from goalflow.api.base_types import ChatCompletionBlockingResponse


class AbstractDataAdapter(ABC):
    """Abstract data adapter.

    A data adapter serializes goalflow's internal messages into whatever wire
    format the client expects. Two distinct paths:

    - ``generate``: streaming — transform a generator of SSE lines into the
      target streaming format.
    - ``execute``: blocking — transform a single blocking response into a dict.
    """

    @abstractmethod
    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        """流式消息转换。"""
        ...

    @abstractmethod
    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        """非流式消息转换。"""
        ...
