from pydantic import BaseModel, Field
from enum import Enum
from typing import Sequence
from goalflow.constants import WfNodeType,ErrorStrategy
from goalflow.workflow.stream.variable_template_parser import VariableTemplateParser
from goalflow.workflow.stream.prompt_template_parser import PromptTemplateParser
from goalflow.node import BaseNode
from typing import TypedDict


class GenerateRouteChunk(BaseModel):
    """
    Generate Route Chunk.
    """

    class ChunkType(Enum):
        VAR = "var"
        TEXT = "text"

    type: ChunkType = Field(..., description="generate route chunk type")


class VarGenerateRouteChunk(GenerateRouteChunk):
    """
    Var Generate Route Chunk.
    """

    type: GenerateRouteChunk.ChunkType = GenerateRouteChunk.ChunkType.VAR
    """generate route chunk type"""
    value_selector: Sequence[str] = Field(..., description="value selector")


class TextGenerateRouteChunk(GenerateRouteChunk):
    """
    Text Generate Route Chunk.
    """

    type: GenerateRouteChunk.ChunkType = GenerateRouteChunk.ChunkType.TEXT
    """generate route chunk type"""
    text: str = Field(..., description="text")



class AnswerStreamGenerateRoute:
    """
    AnswerStreamGenerateRoute entity
    """

    answer_dependencies: dict[str, list] 
    answer_gen_route_chunks: dict[str, list[GenerateRouteChunk]] 
    
    def __init__(self, * ,answer_dependencies: dict[str, list], answer_gen_route_chunks: dict[str, list[GenerateRouteChunk]]):
        self.answer_dependencies = answer_dependencies
        self.answer_gen_route_chunks = answer_gen_route_chunks


class AnswerEndStreamOutRouter:
    @classmethod
    def init(
        cls,
        node_id_object_mapping: dict[str, BaseNode],
        reverse_edge_mapping: dict[str, list["GraphEdge"]],  # type: ignore[name-defined]
    ) -> AnswerStreamGenerateRoute:
        """
        Get stream generate routes.
        :return:
        """
        # parse stream output node value selectors of answer nodes
        answer_generate_route: dict[str, list[GenerateRouteChunk]] = {}
        for answer_node_id, node in node_id_object_mapping.items():
            if node.type != WfNodeType.ANSWER.value:
                continue

            # get generate route for stream output
            generate_route = cls.extract_generate_route_from_node_data(node)
            answer_generate_route[answer_node_id] = generate_route

        # fetch answer dependencies
        answer_node_ids = list(answer_generate_route.keys())
        answer_dependencies = cls._fetch_answers_dependencies(
            answer_node_ids=answer_node_ids,
            reverse_edge_mapping=reverse_edge_mapping,
            node_id_config_mapping=node_id_object_mapping,
        )

        return AnswerStreamGenerateRoute(
            answer_gen_route_chunks=answer_generate_route, 
            answer_dependencies=answer_dependencies
        )

    @classmethod
    def extract_generate_route_from_node_data(cls, node_data: "AnswerNode") -> list[GenerateRouteChunk]:
        """
        Extract generate route from node data
        :param node_data: node data object
        :return:
        """
        variable_template_parser = VariableTemplateParser(template=node_data.answer)
        variable_selectors = variable_template_parser.extract_variable_selectors()

        value_selector_mapping = {
            variable_selector.variable: variable_selector.value_selector for variable_selector in variable_selectors
        }

        variable_keys = list(value_selector_mapping.keys())

        # format answer template
        template_parser = PromptTemplateParser(template=node_data.answer, with_variable_tmpl=True)
        template_variable_keys = template_parser.variable_keys

        # Take the intersection of variable_keys and template_variable_keys
        variable_keys = list(set(variable_keys) & set(template_variable_keys))

        template = node_data.answer
        for var in variable_keys:
            template = template.replace(f"{{{{{var}}}}}", f"Ω{{{{{var}}}}}Ω")

        generate_routes: list[GenerateRouteChunk] = []
        for part in template.split("Ω"):
            if part:
                if cls._is_variable(part, variable_keys):
                    var_key = part.replace("Ω", "").replace("{{", "").replace("}}", "")
                    value_selector = value_selector_mapping[var_key]
                    generate_routes.append(VarGenerateRouteChunk(value_selector=value_selector))
                else:
                    generate_routes.append(TextGenerateRouteChunk(text=part))

        return generate_routes

    #@classmethod
    #def _extract_generate_route_selectors(cls, config: dict) -> list[GenerateRouteChunk]:
    #    """
    #    Extract generate route selectors
    #    :param config: node config
    #    :return:
    #    """
    #    node_data = AnswerNodeData(**config.get("data", {}))
    #    return cls.extract_generate_route_from_node_data(node_data)

    @classmethod
    def _is_variable(cls, part, variable_keys):
        cleaned_part = part.replace("{{", "").replace("}}", "")
        return part.startswith("{{") and cleaned_part in variable_keys

    @classmethod
    def _fetch_answers_dependencies(
        cls,
        answer_node_ids: list[str],
        reverse_edge_mapping: dict[str, list["GraphEdge"]],  # type: ignore[name-defined]
        node_id_config_mapping: dict[str, BaseNode],
    ) -> dict[str, list[str]]:
        """
        Fetch answer dependencies
        :param answer_node_ids: answer node ids
        :param reverse_edge_mapping: reverse edge mapping
        :param node_id_config_mapping: node id config mapping
        :return:
        """
        answer_dependencies: dict[str, list[str]] = {}
        for answer_node_id in answer_node_ids:
            if answer_dependencies.get(answer_node_id) is None:
                answer_dependencies[answer_node_id] = []

            cls._recursive_fetch_answer_dependencies(
                current_node_id=answer_node_id,
                answer_node_id=answer_node_id,
                node_id_config_mapping=node_id_config_mapping,
                reverse_edge_mapping=reverse_edge_mapping,
                answer_dependencies=answer_dependencies,
            )

        return answer_dependencies

    @classmethod
    def _recursive_fetch_answer_dependencies(
        cls,
        current_node_id: str,
        answer_node_id: str,
        node_id_config_mapping: dict[str, BaseNode],
        reverse_edge_mapping: dict[str, list["GraphEdge"]],  # type: ignore[name-defined]
        answer_dependencies: dict[str, list[str]],
    ) -> None:
        """
        Recursive fetch answer dependencies
        :param current_node_id: current node id
        :param answer_node_id: answer node id
        :param node_id_config_mapping: node id config mapping
        :param reverse_edge_mapping: reverse edge mapping
        :param answer_dependencies: answer dependencies
        :return:
        """
        reverse_edges = reverse_edge_mapping.get(current_node_id, [])
        for edge in reverse_edges:
            source_node_id = edge.source
            if source_node_id not in node_id_config_mapping:
                continue
            source_node_type = node_id_config_mapping[source_node_id].type
            source_node_data = node_id_config_mapping[source_node_id]
            if (
                source_node_type
                in {
                    WfNodeType.ANSWER.value,
                    WfNodeType.IF_ELSE.value,
                    WfNodeType.QUESTION_CLASSIFIER.value
                }
                or source_node_data.error_strategy == ErrorStrategy.FAIL_BRANCH
            ):
                answer_dependencies[answer_node_id].append(edge)
            else:
                cls._recursive_fetch_answer_dependencies(
                    current_node_id=source_node_id,
                    answer_node_id=answer_node_id,
                    node_id_config_mapping=node_id_config_mapping,
                    reverse_edge_mapping=reverse_edge_mapping,
                    answer_dependencies=answer_dependencies,
                )
                

