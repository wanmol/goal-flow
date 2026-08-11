from typing import Optional
from collections import defaultdict
from goalflow.dify_parser.dify_types import (
    DifyGraphEdge,
    DifyGraphNode,
    ConversationVar,
    DifyWfFeatures
)

class DifyAppNode:
    description: str
    icon: str
    icon_background: str
    mode: str
    name: str
    use_icon_as_answer_icon: str

class DifyDependencyConfig:
    current_identifier: str
    type : str = "marketplace"
    value: dict
        
    
class DifyDependenciesNode:
    dependencies: list[DifyDependencyConfig]
    
class DifyWorkflow:
    """
    Dify workflow definition
    """
    __slots__ = [
        "nodes", 
        "conversation_variables", 
        "features",
        "environment_variables",
        "node_map",
        "edges",
        #extra, below are graph detail data
        "_edge_source_target_map",
        "_edge_target_source_map",
        "start_node_id",
        "parent_children_node_map",
        "parent_child_start_node_map"
    ]
    
    conversation_variables: list[ConversationVar]
    features: list[DifyWfFeatures]
    nodes: list[DifyGraphNode]
    edges: list[DifyGraphEdge]
    environment_variables: list
    start_node_id: str
    
    def add_node(self, node : DifyGraphNode):
        if self.nodes is None:
            self.nodes = []
        self.nodes.append(node)
        
    def get_node(self, node_id : str) -> Optional[DifyGraphNode]:
        if self.node_map is None:
            return None
        return self.node_map.get(node_id, None)
    
    @property
    def all_nodes(self) -> Optional[list[DifyGraphNode]]:
        return self.nodes
    
    def add_edge(self, edge : DifyGraphEdge):
        if not hasattr(self , "edges"):
            self.edges = []
        
        self.edges.append(edge)
    
    @property
    def all_edges(self) -> Optional[list[DifyGraphEdge]]:
        return self.edges
    
    @property
    def start_node(self) -> Optional[DifyGraphNode]:
        if self.start_node_id is None:
            return None
        return self.get_node(self.start_node_id)
    
    @property
    def edge_target_source_map(self) -> dict[str, list[DifyGraphEdge]]:
        return self._edge_target_source_map

    @property
    def edge_source_target_map(self) -> dict[str, list[DifyGraphEdge]]:
        return self._edge_source_target_map
    
    def get_next_node_ids(self, node_id : str) -> list[str]:
        if node_id not in self.edge_source_target_map:
            return []
        
        return [edge.target for edge in self.edge_source_target_map[node_id]]

    
    def get_subgraph_node_ids(self, parent_id : str) -> list[str]:
        if parent_id not in self.parent_children_node_map:
            raise ValueError(f"subgraph {parent_id} not found")
        
        return self.parent_children_node_map[parent_id]
    
    def get_subgraph_start_node_id(self, parent_id : str) -> str:
        if parent_id not in self.parent_children_node_map:
            raise ValueError(f"subgraph {parent_id} not found")
        
        return self.parent_child_start_node_map[parent_id]
        
    def init_graph_data(self):
        self.node_map : dict[str, DifyGraphNode] = {}
        self.parent_children_node_map : dict[str, list[str]] = defaultdict(list)
        self.parent_child_start_node_map : dict[str, str] = {}
        self.start_node_id : str = None

        for node in self.nodes:
            if node.data is not None and node.data.type == "start":
                if self.start_node_id is not None:
                    raise ValueError("multi start not supported")
                self.start_node_id = node.id
            
            if node.parentId is not None:
                self.parent_children_node_map[node.parentId].append(node.id)
                
                if node.data is not None and node.data.type.endswith("start"):
                    self.parent_child_start_node_map[node.parentId] = node.id
                    
            self.node_map[node.id] = node
        
        if self.start_node_id is None:
            raise ValueError("start node not found")
         
        for parent_id, _ in self.parent_children_node_map.items():
            if parent_id not in self.parent_child_start_node_map:
                raise ValueError(f"subgraph {parent_id} start node not found")
            
        self._edge_source_target_map : dict[str, list[DifyGraphEdge]] = defaultdict(list)
        self._edge_target_source_map : dict[str, list[DifyGraphEdge]] = defaultdict(list)
        for edge in self.edges:
            self._edge_source_target_map[edge.source].append(edge)
            self._edge_target_source_map[edge.target].append(edge)


class DifyDslDefinition:
    app : DifyAppNode
    dependencies : DifyDependenciesNode
    kind : str
    version: str
    workflow: DifyWorkflow