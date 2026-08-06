from goalflow.node import BaseNode
from goalflow.constants import WfNodeType
from goalflow.workflow_types import NodeVarConfig

class EndStreamGenerateRoute:
    """
    EndStreamGenerateRoute entity
    """
    
    end_dependencies: dict[str, list[str]] 
    
    end_stream_variable_selector_mapping: dict[str, list[list[str]]] 
    
    def __init__(self, * ,end_dependencies: dict[str, list[str]], end_stream_variable_selector_mapping: dict[str, list[list[str]]]):
        self.end_dependencies = end_dependencies
        self.end_stream_variable_selector_mapping = end_stream_variable_selector_mapping
        
        
class NormalEndStreamOutRouter:
    @classmethod
    def init(
        cls,
        node_id_object_mapping: dict[str, BaseNode],
        reverse_edge_mapping: dict[str, list["GraphEdge"]],  # type: ignore[name-defined]
    ) -> EndStreamGenerateRoute:
        """
        Get end generate routes.
        :return:
        """
        end_stream_variable_selectors_mapping: dict[str, list[list[str]]] = {}
        for end_node_id, node in node_id_object_mapping.items():
            if node.type != WfNodeType.END.value:
                continue

            # get generate route for stream output
            stream_variable_selectors = cls.extract_stream_variable_selector_from_node_data(node_id_object_mapping, node)
            end_stream_variable_selectors_mapping[end_node_id] = stream_variable_selectors

        # fetch end dependencies
        end_node_ids = list(end_stream_variable_selectors_mapping.keys())
        end_dependencies = cls._fetch_ends_dependencies(
            end_node_ids=end_node_ids,
            reverse_edge_mapping=reverse_edge_mapping,
            node_id_config_mapping=node_id_object_mapping,
        )

        return EndStreamGenerateRoute(
            end_stream_variable_selector_mapping=end_stream_variable_selectors_mapping,
            end_dependencies=end_dependencies,
        )
        
    
    @classmethod
    def extract_stream_variable_selector_from_node_data(
        cls, node_id_config_mapping: dict[str, BaseNode], node_data: "EndNode"
    ) -> list[list[str]]:
        """
        Extract stream variable selector from node data
        :param node_id_config_mapping: node id config mapping
        :param node_data: node data object
        :return:
        """
        variable_selectors : list[NodeVarConfig] = node_data.outputs

        value_selectors = []
        for variable_selector in variable_selectors:
            if not variable_selector.value_selector:
                continue

            node_id = variable_selector.value_selector[0]
            if node_id != "sys" and node_id in node_id_config_mapping:
                node = node_id_config_mapping[node_id]
                node_type = node.type
                if (
                    variable_selector.value_selector not in value_selectors
                    and node_type == WfNodeType.LLM.value
                    and variable_selector.value_selector[1] == "text"
                ):
                    value_selectors.append(list(variable_selector.value_selector))

        return value_selectors
    
    
    @classmethod
    def _fetch_ends_dependencies(
        cls,
        end_node_ids: list[str],
        reverse_edge_mapping: dict[str, list["GraphEdge"]],  # type: ignore[name-defined]
        node_id_config_mapping: dict[str, dict],
    ) -> dict[str, list[str]]:
        """
        Fetch end dependencies
        :param end_node_ids: end node ids
        :param reverse_edge_mapping: reverse edge mapping
        :param node_id_config_mapping: node id config mapping
        :return:
        """
        end_dependencies: dict[str, list[str]] = {}
        for end_node_id in end_node_ids:
            if end_dependencies.get(end_node_id) is None:
                end_dependencies[end_node_id] = []

            cls._recursive_fetch_end_dependencies(
                current_node_id=end_node_id,
                end_node_id=end_node_id,
                node_id_config_mapping=node_id_config_mapping,
                reverse_edge_mapping=reverse_edge_mapping,
                end_dependencies=end_dependencies,
            )

        return end_dependencies

    @classmethod
    def _recursive_fetch_end_dependencies(
        cls,
        current_node_id: str,
        end_node_id: str,
        node_id_config_mapping: dict[str, BaseNode],
        reverse_edge_mapping: dict[str, list["GraphEdge"]],  # type: ignore[name-defined]
        end_dependencies: dict[str, list[str]],
    ) -> None:
        """
        Recursive fetch end dependencies
        :param current_node_id: current node id
        :param end_node_id: end node id
        :param node_id_config_mapping: node id config mapping
        :param reverse_edge_mapping: reverse edge mapping
        :param end_dependencies: end dependencies
        :return:
        """
        reverse_edges = reverse_edge_mapping.get(current_node_id, [])
        for edge in reverse_edges:
            source_node_id = edge.source
            if source_node_id not in node_id_config_mapping:
                continue
            source_node_type = node_id_config_mapping[source_node_id].type
            if source_node_type in {
                WfNodeType.IF_ELSE.value,
                WfNodeType.QUESTION_CLASSIFIER.value,
            }:
                end_dependencies[end_node_id].append(edge)
            else:
                cls._recursive_fetch_end_dependencies(
                    current_node_id=source_node_id,
                    end_node_id=end_node_id,
                    node_id_config_mapping=node_id_config_mapping,
                    reverse_edge_mapping=reverse_edge_mapping,
                    end_dependencies=end_dependencies,
                )
    
    

        

