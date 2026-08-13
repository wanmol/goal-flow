from goalflow.workflow.stream.types import (
    NodeRunSucceededEvent,
    NodeRunInterruptEvent,
    NodeRunControlEvent,
    StreamEventChunk,
    NodeRunStreamChunkEvent,
    ProxyStreamDataChunk,
    LANGGRAPH_STREAM_MODE_UPDATES,
    LANGGRAPH_STREAM_MODE_MESSAGES,
    LANGGRAPH_STREAM_MODE_CUSTOM,
    CUSTOM_STREAM_MODE_PASSTHROUGH,
    CUSTOM_STREAM_MODE_DIRECT_OUTPUT,
    WF_NODE_CONTROL_EVENT_NAME
)
from goalflow.node import BaseNode
from goalflow.workflow.base_workflow import BaseWorkflow
from goalflow.state import GenericState
from typing import Generic,Generator,Dict,Any,cast
from langgraph.types import Interrupt
from langgraph._internal._constants import INTERRUPT
from langchain_core.messages import AIMessageChunk 
from goalflow.workflow.stream.chatflow_stream_out_decision_route import (
    VarGenerateRouteChunk,
    TextGenerateRouteChunk,
    GenerateRouteChunk,
    AnswerStreamGenerateRoute
)
from goalflow.tool.utils import VariableResolver
from goalflow.constants import (
    WfNodeType,
    ErrorStrategy,
    THINK_START_TAG,
    THINK_END_TAG,
    THINKING_CONTENT_KEY
)

from goalflow.config import get_logger

logger = get_logger(__name__)

class ChatflowStreamProcessor(Generic[GenericState]):
    def __init__(
        self, 
        workflow: BaseWorkflow[GenericState]
    ):
        self.workflow = workflow
        # record the output route config under each answer_node_id.
        # NOTE: workflow.answer_stream_generate_routes is built once in
        # BaseWorkflow.__init__ and shared by every request on this (singleton)
        # workflow instance. _remove_dependencies mutates answer_dependencies in
        # place, so we must work on a per-request copy or the first request would
        # permanently strip edges for all subsequent/concurrent requests.
        shared_routes = workflow.answer_stream_generate_routes
        self.generate_routes = AnswerStreamGenerateRoute(
            # answer_dependencies is mutated per request -> copy dict + each list
            # (the edge objects inside are only read, never mutated).
            answer_dependencies={
                node_id: list(edges)
                for node_id, edges in shared_routes.answer_dependencies.items()
            },
            # answer_gen_route_chunks is read-only here -> safe to share.
            answer_gen_route_chunks=shared_routes.answer_gen_route_chunks,
        )
        # record the position of the next route item under each answer_node_id
        # :key answer_node_id
        # :value position of the next route item to process
        self.next_route_chunk_pos_map: dict[str, int] = {}
        for answer_node_id in self.generate_routes.answer_gen_route_chunks:
            self.next_route_chunk_pos_map[answer_node_id] = 0
        
        '''
        当前运行工作流能够立即流式输出到客户端涉及到的answer_node_id
        :key 正在运行的节点id
        :value 通过当前节点肯定能够到达的answer节点id（比如当前节点和answer节点之间没有分支节点或者分支节点运行结果确定是到answer节点的分支）p
        '''
        self.curr_node_answer_node_id_map: dict[str, list[str]] = {}
        
        self.rest_node_ids = [node.id for node in self.workflow.nodes]
        
        self.source_handle_map = {}

    
 
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
            
        
    def process(
        self, 
        generator: Generator[Dict, None, None],
        use_end_stream=True
    ) -> Generator[StreamEventChunk, None, None]:
        # save reachable answer node ids
        reachable_answer_ids = set()
        # save the output of each node
        runtime_state = {}
        has_thinking:bool = False
        thinking_end:bool = False
        for stream_mode,event_data in generator:
            #print(stream_mode,event_data)
            
            # code implementation conventions:
            # 1. subgraphs cannot use the LANGGRAPH_STREAM_MODE_CUSTOM stream_mode
            # 2. the event data format of the LANGGRAPH_STREAM_MODE_CUSTOM stream_mode is (stream_mode,event_data)
            #logger.info("custom_stream_mode_event_data======",stream_mode=stream_mode,event_data=event_data)
            if stream_mode == LANGGRAPH_STREAM_MODE_CUSTOM:
                stream_mode,event_data = event_data
                
            if stream_mode not in (
                LANGGRAPH_STREAM_MODE_MESSAGES,
                LANGGRAPH_STREAM_MODE_UPDATES,
                CUSTOM_STREAM_MODE_PASSTHROUGH,
                CUSTOM_STREAM_MODE_DIRECT_OUTPUT
            ):
                raise ValueError(f"stream mode {stream_mode} not supported in subgraph")
            
            if stream_mode == LANGGRAPH_STREAM_MODE_MESSAGES:
                message_chunk , metadata = event_data
                #print(stream_mode,event_data)
                message_chunk : AIMessageChunk = message_chunk
                metadata: dict = metadata
                
                response_metadata = message_chunk.response_metadata
                
                node_id = metadata["langgraph_node"]
                node : BaseNode = self.workflow.get_node(node_id)
                
                if node_id in self.curr_node_answer_node_id_map:
                    stream_out_answer_node_ids = self.curr_node_answer_node_id_map[
                        node_id
                    ]
                else:
                    #this must be an llm node (only llm nodes have stream_mode=StreamMode.MESSAGES)
                    local_runtime_state = {"node_id":node_id,"source_handle":"source"}
                    #global_state["node_runtime_state"] = runtime_state
                    
                    stream_out_answer_node_ids = self._get_stream_out_answer_node_ids(local_runtime_state)
                    
                    self.curr_node_answer_node_id_map[node_id] = (
                        stream_out_answer_node_ids
                    )

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
                    prompt_tokens = token_usage.get("input_tokens",0) or token_usage.get("prompt_tokens",0)
                    completion_tokens = token_usage.get("output_tokens",0) or token_usage.get("completion_tokens",0)
                    total_tokens = token_usage.get("total_tokens",0) 
                    
                    usage["prompt_tokens"] = prompt_tokens
                    usage["completion_tokens"] = completion_tokens
                    usage["total_tokens"] = total_tokens
                    
                    event = NodeRunStreamChunkEvent(
                        node_id=node_id,
                        node_type=node.type if node is not None else node_id,
                        node_data=node.to_json() if node is not None else {},
                        chunk_content=content,
                        metadata=metadata
                    )
                else:
                    event = NodeRunStreamChunkEvent(
                        node_id=node_id,
                        node_type=node.type if node is not None else node_id,
                        node_data=node.to_json() if node is not None else {},
                        chunk_content=content
                    )
                    
                # agent node outputs directly
                if node_id == "agent":
                    yield event
                
                for answer_node_id in stream_out_answer_node_ids:
                    if answer_node_id not in reachable_answer_ids:
                        reachable_answer_ids.add(answer_node_id)
                        # first run through the TextGenerateRouteChunk
                        yield from self._try_generate_stream_outputs(answer_node_id, local_runtime_state,use_end_stream)
                     
                    yield event   

            elif stream_mode == LANGGRAPH_STREAM_MODE_UPDATES:
                node_id = next(iter(list(event_data.keys())))
                
                # the flow is actively interrupted (e.g. calling the langgraph.tgypes.interrput method inside a node, etc.)
                if node_id == INTERRUPT:
                    interrupt:Interrupt = cast(Interrupt,event_data[INTERRUPT][0])
                    value = interrupt.value
                    id = interrupt.id
                    yield NodeRunInterruptEvent(
                        outputs={"value":value,"id":id}
                    )
                    
                    continue
                
                # handle node-internal control events
                if node_id == WF_NODE_CONTROL_EVENT_NAME:
                    yield NodeRunControlEvent(
                        outputs=event_data[node_id]
                    )
                    
                    continue
                
                event_data = event_data[node_id]
                
                if event_data is None:
                    event_data = {"node_id":node_id}

                event_data = event_data.copy() 
                self._merge_runtime_state(runtime_state,event_data)
                #runtime_state = event_data["node_runtime_state"]
                
                if "node_id" in runtime_state and (node_id is None or node_id ==""):
                    node_id = runtime_state["node_id"]
                else:
                    runtime_state["node_id"] = node_id
                    
                source_handle = runtime_state.get("source_handle","source") 
                
                self.source_handle_map[node_id] = source_handle

                node : BaseNode = self.workflow.get_node(node_id)

                event = NodeRunSucceededEvent(
                    node_id=node_id,
                    node_type=node.type,
                    node_data=node.to_json(),
                    outputs=event_data,
                )
                
                yield event
                
                if node_id in self.curr_node_answer_node_id_map:
                    # update self.route_position after all stream event finished
                    for answer_node_id in self.curr_node_answer_node_id_map[node_id]:
                        self.next_route_chunk_pos_map[answer_node_id] += 1

                    del self.curr_node_answer_node_id_map[node_id]

                # generate stream outputs
                yield from self._generate_stream_outputs_when_node_finished(runtime_state,use_end_stream)
            #elif stream_mode == LANGGRAPH_STREAM_MODE_CUSTOM:
            #    pass
            elif stream_mode == CUSTOM_STREAM_MODE_PASSTHROUGH:
                yield ProxyStreamDataChunk(data=event_data)
            elif stream_mode == CUSTOM_STREAM_MODE_DIRECT_OUTPUT:
                # text fragment actively pushed by the node (AgentBaseNode.stream_text)
                direct_node_id = event_data.get("node_id")
                node = self.workflow.get_node(direct_node_id)
                yield NodeRunStreamChunkEvent(
                    node_id=direct_node_id,
                    node_type=node.type if node is not None else direct_node_id,
                    node_data=node.to_json() if node is not None else {},
                    chunk_content=event_data.get("text", ""),
                )
            else:
                raise ValueError(f"stream mode {stream_mode} not supported")
            
            
    def _get_stream_out_answer_node_ids(self, runtime_state: dict[str,any]) -> list[str]:

        """
        Is stream out support
        :param event: queue text chunk event
        :return:
        """
        #if not event.from_variable_selector:
        #    return []

        #stream_output_value_selector = event.from_variable_selector
        #if not stream_output_value_selector:
        #    return []
        node_id = runtime_state.get("node_id")
        #logger.info(f"get_stream_out_answer_node_ids============",node_id=node_id,runtime_state=runtime_state)
        node = self.workflow.get_node(node_id)
        if node is None:
            logger.warning(f"node not found in workflow",node_id=node_id,run_time_state=runtime_state)
            return []
        answer_dependencies = self.generate_routes.answer_dependencies
        stream_out_answer_node_ids = []
        for answer_node_id, route_position in self.next_route_chunk_pos_map.items():
            if answer_node_id not in self.rest_node_ids:
                continue
            
            self._remove_dependencies(answer_node_id, runtime_state)
                
            answer_dependencies_ids = [
                edge.source for edge in answer_dependencies.get(answer_node_id, [])
            ]
            # all depends on answer node id not in rest node ids
            if all( 
                (dep_id not in self.rest_node_ids
                    or (
                        dep_node := self.workflow.get_node(dep_id),
                        dep_node.node_level
                    )[-1] <= node.node_level
                )
                for dep_id in answer_dependencies_ids
            ):
                if route_position >= len(self.generate_routes.answer_gen_route_chunks[answer_node_id]):
                    continue

                route_chunk = self.generate_routes.answer_gen_route_chunks[answer_node_id][route_position]

                if route_chunk.type != GenerateRouteChunk.ChunkType.VAR:
                    continue

                route_chunk:VarGenerateRouteChunk = route_chunk
                value_selector = route_chunk.value_selector

                # check chunk node id is before current node id or equal to current node id
                if value_selector[0] != node.id:
                    continue

                stream_out_answer_node_ids.append(answer_node_id)

        return stream_out_answer_node_ids
    
    def _generate_stream_outputs_when_node_finished(
        self, 
        runtime_state: dict[str,any],
        use_end_stream:bool = True
    ) -> Generator[Any, None, None]:
        """
        Generate stream outputs.
        :param event: node run succeeded event
        :return:
        """
        #runtime_state = global_state.get("node_runtime_state")
        node_id = runtime_state.get("node_id")
        node = self.workflow.get_node(node_id)
        
        for answer_node_id in self.next_route_chunk_pos_map:
            # all depends on answer node id not in rest node ids
            if node.id != answer_node_id and (
                answer_node_id not in self.rest_node_ids
                or not all(
                    (edge.source not in self.rest_node_ids  or edge.source == node_id)
                    and edge.source_handle == self.source_handle_map[edge.source]
                    for edge in self.generate_routes.answer_dependencies[answer_node_id]
                )
            ):
                continue

            yield from self._try_generate_stream_outputs(answer_node_id, runtime_state,use_end_stream)
            
            self._remove_dependencies(answer_node_id, runtime_state)
        
        if node.id in self.rest_node_ids:
            self.rest_node_ids.remove(node.id)
        
        
    def _try_generate_stream_outputs(self, answer_node_id:str, runtime_state: dict[str,any],use_end_stream:True):
        """
        Try stream out.
        :param runtime_state: runtime state
        :return:
        """
        node_id = runtime_state.get("node_id")
        node = self.workflow.get_node(node_id)
        route_position = self.next_route_chunk_pos_map[answer_node_id]
        route_chunks = self.generate_routes.answer_gen_route_chunks[answer_node_id][route_position:]
        answer_node = self.workflow.get_node(answer_node_id)
        for route_chunk in route_chunks:
            if route_chunk.type == GenerateRouteChunk.ChunkType.TEXT:
                route_chunk:TextGenerateRouteChunk = route_chunk
                if use_end_stream:
                    yield NodeRunStreamChunkEvent(
                        node_id=answer_node_id,
                        node_type=answer_node.type,
                        node_data=answer_node.to_json(),
                        chunk_content=route_chunk.text,
                    )
            else:
                route_chunk:VarGenerateRouteChunk = route_chunk
                value_selector = route_chunk.value_selector
                if not value_selector:
                    break

                value = VariableResolver.resolve_value_selector(value_selector, runtime_state)

                if value is None:
                    break

                if value and use_end_stream:
                    yield NodeRunStreamChunkEvent(
                        node_id=node.id,
                        node_type=node.type,
                        node_data=node.to_json(),
                        chunk_content=value,
                    )

            self.next_route_chunk_pos_map[answer_node_id] += 1
        
    def _remove_dependencies(self, answer_node_id: str, runtime_state: dict[str,any]):
        """
        Remove dependencies of node.
        :param node_id: node id
        :return:
        """
        answer_dependencies = self.generate_routes.answer_dependencies
        node_id = runtime_state.get("node_id")
        node = self.workflow.get_node(node_id)
        source_handle = runtime_state.get("source_handle") or ""
        # Remove current node id from answer dependencies to support stream output if it is a success branch
        edge_mapping = self.workflow.edge_source_target_map.get(node.id)
        is_branch_node = (
            node.type
            in {
                WfNodeType.ANSWER.value,
                WfNodeType.IF_ELSE.value,
                WfNodeType.QUESTION_CLASSIFIER.value,
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
            for edge in answer_dependencies[answer_node_id]
        ):                
            answer_dependencies[answer_node_id] = [
                edge for edge in answer_dependencies[answer_node_id] if edge.source != node_id
            ]
    
    def _create_task_detail_event(self, node: BaseNode, research_result: dict) -> NodeRunStreamChunkEvent:
        """
        Create task detail event (streamlined version, plan A)

        Args:
            node: ResearchTeamNode
            research_result: research result of a single task

        Returns:
            stream event containing task details
        """
        # get execution_metadata
        exec_metadata = research_result.get("execution_metadata", {})

        # build task detail data (streamlined version)
        task_detail = {
            "event_type": "task_detail",
            "task_id": research_result.get("task_id"),
            "title": research_result.get("title"),
            "status": research_result.get("status"),
            "findings": research_result.get("findings", ""),  # complete research findings
            "analysis": research_result.get("analysis", ""),  # For CoderAgent
            "formatted_output": research_result.get("formatted_output", ""),  # ⚡ DeerFlow style formatted output (for real-time display)
            "references": research_result.get("references", []),  # detailed reference content list (replaces sources)
            "intermediate_steps": research_result.get("intermediate_steps", []),
            "execution_metadata": exec_metadata  # contains tools_used
        }

        # if there are code execution results (CoderAgent)
        if "code_executed" in research_result:
            task_detail["code_executed"] = research_result.get("code_executed", [])
            task_detail["execution_results"] = research_result.get("execution_results", [])

        # build user-friendly summary information
        summary_parts = [f"✅ {task_detail['title']}"]
        if task_detail.get("references"):
            refs_count = len(task_detail["references"])
            refs_by_source = {}
            for ref in task_detail["references"]:
                source = ref.get("source", "未知来源")
                refs_by_source[source] = refs_by_source.get(source, 0) + 1

            summary_parts.append(f"📚 References: {refs_count} ({', '.join(f'{k}: {v}' for k, v in refs_by_source.items())})")

        chunk_content = "\n\n🔍 " + " | ".join(summary_parts) + "\n"

        return NodeRunStreamChunkEvent(
            node_id=node.id,
            node_type=node.type,
            node_data=node.to_json(),
            chunk_content=chunk_content,
            metadata=task_detail  # place detailed data in metadata
        )


            




