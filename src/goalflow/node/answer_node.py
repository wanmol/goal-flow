from goalflow.node.base import BaseNode,NodeOutput
from pydantic import BaseModel
from goalflow.state import GenericState
from goalflow.workflow.stream.chatflow_stream_out_decision_route import AnswerEndStreamOutRouter,GenerateRouteChunk,VarGenerateRouteChunk,TextGenerateRouteChunk
from typing import cast
from goalflow.tool.utils import VariableResolver
from goalflow.workflow.stream.chatflow_stream_out_decision_route import AnswerEndStreamOutRouter

class AnswerNode(BaseNode):
    """
    Answer node for workflow.
    This node returns the answer of the question.
    """
    answer: str
    
    def __init__(self, *,answer : str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.answer = answer
        self.generate_routes = AnswerEndStreamOutRouter.extract_generate_route_from_node_data(self)
    
    def call(self, state: GenericState) -> NodeOutput:
        """implements protocol _StateNode"""
        
        answer = ""
        for part in self.generate_routes:
            if part.type == GenerateRouteChunk.ChunkType.VAR:
                part = cast(VarGenerateRouteChunk, part)
                value_selector = part.value_selector
                value = VariableResolver.resolve_value_selector(value_selector,state)
                if value:
                    answer += str(value)
            else:
                part = cast(TextGenerateRouteChunk, part)
                answer += part.text
        
        del state

        return VariableResolver.format_output(
            node_id=self.id,
            outputs={"answer":answer}
        )


