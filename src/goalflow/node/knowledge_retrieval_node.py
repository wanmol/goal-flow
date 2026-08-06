from goalflow.node import BaseNode, NodeOutput
from goalflow.state import GenericState
from goalflow.tool.utils import VariableResolver
import time
from langgraph.types import Command

#@deprecated   
class KnowledgeRetrievalNode(BaseNode):
    def __init__(
        self,
        **kwargs
    ):
        super().__init__(**kwargs)
        

    def call(self, state: GenericState) -> NodeOutput:
        
        output = {"content":"","title":"","url":""}
        result = [output]
        
        update =  VariableResolver.format_output(
            node_id = self.id,
            outputs={"result":result}
        )
        
        return Command(
            update=update,
            goto=self.next_node_ids
        )