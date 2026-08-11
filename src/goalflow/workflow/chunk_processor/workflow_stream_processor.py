import logging
from collections.abc import Generator
from langgraph.types import StreamMode
from langchain_core.messages import AIMessageChunk 
from goalflow.workflow.stream.types import (
    NodeRunSucceededEvent,
    StreamEventChunk,
    NodeRunStreamChunkEvent,
    LANGGRAPH_STREAM_MODE_UPDATES,
    LANGGRAPH_STREAM_MODE_MESSAGES
)
from goalflow.node import BaseNode
from goalflow.workflow.base_workflow import BaseWorkflow
from goalflow.state import GenericState
from typing import Generic,Dict,Any
from goalflow.constants import (
    WfNodeType,
    ErrorStrategy,
    THINK_START_TAG,
    THINK_END_TAG,
    THINKING_CONTENT_KEY
)
from goalflow.tool.utils import VariableResolver


class WorkflowStreamProcessor(Generic[GenericState]):
    def __init__(
        self, 
        workflow: BaseWorkflow[GenericState]
    ) -> None:
        self.workflow = workflow

        self.end_stream_generate_routes = self.workflow.end_stream_generate_routes
        
        self.route_position = {}
        for end_node_id, _ in self.end_stream_generate_routes.end_stream_variable_selector_mapping.items():
            self.route_position[end_node_id] = 0
        
        '''
        当前运行工作流能够立即流式输出到客户端涉及到的end_node_id
        :key 正在运行的节点id
        :value 通过当前节点肯定能够到达的end节点id（比如当前节点和end节点之间没有分支节点或者分支节点运行结果确定是到end节点的分支）
        '''
        self.curr_node_end_node_id_map: dict[str, list[str]] = {}
        
        self.has_output = False
        self.output_node_ids: set[str] = set()
        self.rest_node_ids = [node.id for node in self.workflow.nodes]

    def process(self, generator: Generator[Dict, None, None]) -> Generator[StreamEventChunk, None, None]:
        # save the output of each node
        runtime_state = {}
        for stream_mode,event_data in generator:
            #print(stream_mode,event_data)
            #if isinstance(event, NodeRunStartedEvent):
            #    if event.route_node_state.node_id == self.graph.root_node_id and not self.rest_node_ids:
            #        self.reset()
           
            #    yield event
            has_thinking:bool = False
            thinking_end:bool = False

            if stream_mode == LANGGRAPH_STREAM_MODE_MESSAGES:
                message_chunk , metadata = event_data
                message_chunk : AIMessageChunk = message_chunk
                metadata: dict = metadata

                response_metadata = message_chunk.response_metadata
                
                node_id = metadata["langgraph_node"]
                node : BaseNode = self.workflow.get_node(node_id)
                
                if node_id in self.curr_node_end_node_id_map:
                    stream_out_end_node_ids = self.curr_node_end_node_id_map[
                        node_id
                    ]
                else:
                    #this must be an llm node (only llm nodes have stream_mode=StreamMode.MESSAGES)
                    local_runtime_state = {"node_id":node_id,"source_handle":"source"}
                    
                    stream_out_end_node_ids = self._get_stream_out_end_node_ids(local_runtime_state)
                    
                    self.curr_node_end_node_id_map[node_id] = (
                        stream_out_end_node_ids
                    )

                if stream_out_end_node_ids:
                    content = (
                        message_chunk.content 
                        or message_chunk.additional_kwargs.get(THINKING_CONTENT_KEY,"") 
                    )

                    if (has_thinking == False 
                        and message_chunk.additional_kwargs 
                        and THINKING_CONTENT_KEY in message_chunk.additional_kwargs
                    ):
                        if message_chunk.additional_kwargs[THINKING_CONTENT_KEY] != "":
                            has_thinking = True
                            content = THINK_START_TAG + message_chunk.additional_kwargs[THINKING_CONTENT_KEY]

                    if (has_thinking == True 
                        and thinking_end == False 
                        and message_chunk.content != ""
                    ):
                        thinking_end = True
                        content = THINK_END_TAG + content

                    is_finish_msg = response_metadata.get("finish_reason","") == "stop"
                    
                    if is_finish_msg:
                        token_usage = response_metadata.get("token_usage",{})
                        usage = {}
                        metadata = {"usage":usage}
                        prompt_tokens = token_usage.get("input_tokens",0)
                        completion_tokens = token_usage.get("output_tokens",0)
                        total_tokens = token_usage.get("total_tokens",0)
                        usage["prompt_tokens"] = prompt_tokens
                        usage["completion_tokens"] = completion_tokens
                        usage["total_tokens"] = total_tokens
                        
                        event = NodeRunStreamChunkEvent(
                            node_id=node_id,
                            node_type=node.type,
                            node_data=node.to_json(),
                            chunk_content=content,
                            metadata=metadata
                        )
                    else:
                        event = NodeRunStreamChunkEvent(
                            node_id=node_id,
                            node_type=node.type,
                            node_data=node.to_json(),
                            chunk_content=content
                        )                        
                    
                    #event = NodeRunStreamChunkEvent(
                    #    node_id=node_id,
                    #    node_type=node.type,
                    #    node_data=node.to_json(),
                    #    chunk_content=content,
                    #)
                    
                    #if the end node is configured with multiple sources, the output of each source is separated by a newline
                    if self.has_output and node_id not in self.output_node_ids:
                        event.chunk_content = "\n" + event.chunk_content
                    self.output_node_ids.add(event.node_id)
                    self.has_output = True
                    
                    yield event
            elif stream_mode == LANGGRAPH_STREAM_MODE_UPDATES:
                node_id = next(iter(list(event_data.keys())))
                
                event_data = event_data[node_id]
                
                if event_data is None:
                    event_data = {"node_id":node_id}

                event_data = event_data.copy() 
                self._merge_runtime_state(runtime_state,event_data)
                #runtime_state = event_data["node_runtime_state"]
                
                #node_id = runtime_state["node_id"]

                node : BaseNode = self.workflow.get_node(node_id)
                
                # workflow end output content
                if node.type == WfNodeType.END:
                    event_data = event_data["outputs"]

                event = NodeRunSucceededEvent(
                    node_id=node_id,
                    node_type=node.type,
                    node_data=node.to_json(),
                    outputs=event_data,
                )
                
                yield event
                
                if event.node_id in self.curr_node_end_node_id_map:
                    # update self.route_position after all stream event finished
                    for end_node_id in self.curr_node_end_node_id_map[event.node_id]:
                        self.route_position[end_node_id] += 1

                    del self.curr_node_end_node_id_map[event.node_id]

                # remove unreachable nodes
                #self._remove_unreachable_nodes(event)

                # generate stream outputs
                yield from self._generate_stream_outputs_when_node_finished(runtime_state)
            else:
                raise ValueError(f"stream mode {stream_mode} not supported")

    def _merge_runtime_state(self, runtime_state: dict, update_data: dict):
        if update_data is None:
            return
        runtime_state["input_variables"] = runtime_state.get("input_variables", {})
        runtime_state["output_variables"] = runtime_state.get("output_variables", {})
        runtime_state["conversation_variables"] = runtime_state.get("conversation_variables", {})
        
        for key,value in update_data.items():
            if key in ("input_variables","output_variables","conversation_variables"):
                runtime_state[key].update(value)
            else:
                runtime_state[key] = value
        
        if "source_handle" not in update_data:
            update_data["source_handle"] = "source"

    def _generate_stream_outputs_when_node_finished(
        self, 
        runtime_state: dict[str,any]
    ) -> Generator[Any, None, None]:
        """
        Generate stream outputs.
        :param event: node run succeeded event
        :return:
        """
        node_id = runtime_state.get("node_id")
        node = self.workflow.get_node(node_id)
        
        for end_node_id, position in self.route_position.items():
            # all depends on end node id not in rest node ids
            if node.id != end_node_id and (
                end_node_id not in self.rest_node_ids
                or not all(
                    edge.source not in self.rest_node_ids
                    for edge in self.end_stream_generate_routes.end_dependencies[end_node_id]
                )
            ):
                continue
            
            route_position = self.route_position[end_node_id]

            position = 0
            value_selectors = []
            for current_value_selectors in self.end_stream_generate_routes.end_stream_variable_selector_mapping[end_node_id]:
                if position >= route_position:
                    value_selectors.append(current_value_selectors)

                position += 1

            for value_selector in value_selectors:
                if not value_selector:
                    continue

                value = VariableResolver.resolve_value_selector(value_selector, runtime_state)

                if value is None:
                    break

                if value:
                    current_node_id = value_selector[0]
                    if self.has_output and current_node_id not in self.output_node_ids:
                        value = "\n" + value

                    self.output_node_ids.add(current_node_id)
                    self.has_output = True
                    yield NodeRunStreamChunkEvent(
                        node_id=node.id,
                        node_type=node.type,
                        node_data=node,
                        chunk_content=value,
                    )

                self.route_position[end_node_id] += 1
            
            self._remove_dependencies(end_node_id, runtime_state)
        
        if node.id in self.rest_node_ids:
            self.rest_node_ids.remove(node.id)

            

    def _get_stream_out_end_node_ids(self, runtime_state: dict[str,any]) -> list[str]:
        """
        Is stream out support
        :param event: queue text chunk event
        :return:
        """
        node_id = runtime_state.get("node_id")
        node = self.workflow.get_node(node_id)
        end_dependencies = self.end_stream_generate_routes.end_dependencies

        stream_out_end_node_ids = []
        for end_node_id, route_position in self.route_position.items():
            if end_node_id not in self.rest_node_ids:
                continue
            
            self._remove_dependencies(end_node_id, runtime_state)

            # all depends on end node id not in rest node ids
            if all(dep_id not in self.rest_node_ids for dep_id in end_dependencies[end_node_id]):
                if route_position >= len(self.end_stream_generate_routes.end_stream_variable_selector_mapping[end_node_id]):
                    continue

                position = 0
                value_selector = None
                for current_value_selectors in self.end_stream_generate_routes.end_stream_variable_selector_mapping[end_node_id]:
                    if position == route_position:
                        value_selector = current_value_selectors
                        break

                    position += 1

                if not value_selector:
                    continue

                # check whether the chunk node id is before the current node id or equal to the current node id
                # for now do not consider multi-parameter nodes (as an llm node it is always text, as other nodes it needs to wait for the node to finish executing and return a result, so there is no need to compare the selector, only the node id needs to be compared)
                if value_selector[0] != node.id:
                    continue

                stream_out_end_node_ids.append(end_node_id)

        return stream_out_end_node_ids
    
    
    def _remove_dependencies(self, end_node_id: str, runtime_state: dict[str,any]):
        """
        Remove dependencies of node.
        :param node_id: node id
        :return:
        """
        end_dependencies = self.end_stream_generate_routes.end_dependencies
        node_id = runtime_state.get("node_id")
        node = self.workflow.get_node(node_id)
        
        # TODO  the sub-flow's messages are captured in the main flow, the cause needs to be investigated
        if node is None:
            return
        
        source_handle = runtime_state.get("source_handle") or ""
        # Remove current node id from answer dependencies to support stream output if it is a success branch
        edge_mapping = self.workflow.edge_source_target_map.get(node.id)
        is_branch_node = (
            node.type
            in {
                WfNodeType.IF_ELSE,
                WfNodeType.QUESTION_CLASSIFIER,
            }
            or node.error_strategy == ErrorStrategy.FAIL_BRANCH
        )
        success_edge = (
            next(
                (
                    edge
                    for edge in edge_mapping
                    if edge.source_handle 
                    and edge.source_handle == source_handle
                ),
                None,
            )
            if edge_mapping
            else None
        ) if is_branch_node else None

        if any(
            success_edge and success_edge.source == edge.source
            and source_handle == edge.source_handle
            for edge in end_dependencies[end_node_id]
        ):                
            end_dependencies[end_node_id] = [
                edge for edge in end_dependencies[end_node_id] if edge.source != node_id
            ]
