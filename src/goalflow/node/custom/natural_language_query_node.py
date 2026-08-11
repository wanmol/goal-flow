from goalflow.node.base import BaseNode,NodeOutput
from goalflow.tool.utils import VariableResolver
from langgraph.types import Command
from goalflow.constants import WfNodeType,VariableEntityType
from goalflow.state import BaseState,GenericState
from langchain_core.language_models.chat_models import (
    BaseChatModel,
)
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, START, MessagesState, StateGraph
from langchain.messages import AIMessage

from typing import List


from goalflow.config import get_logger

logger = get_logger(__name__)

# Query the database using natural language and return the result; the following is adapted from the official example
class NaturalLanguageQueryNode(BaseNode):
    """
    @see https://docs.langchain.com/oss/python/langgraph/sql-agent
    
    we implement a simple ReAct-agent setup, with dedicated nodes for specific tool-calls. 
    We will use the same [state] as the pre-built agent.
    1. Select an LLM
    
    2. Configure the database
    
    3. Add tools for database interactions
    
    4. Define application steps
        We construct dedicated nodes for the following steps:
        Listing DB tables
        Calling the “get schema” tool
        Generating a query
        Checking the query
        
      Putting these steps in dedicated nodes lets us (1) force tool-calls when needed, and (2) customize the prompts associated with each step.
   
    5. Implement the agent
       We can now assemble these steps into a workflow using the Graph API. We define a conditional edge at the query 
       generation step that will route to the query checker if a query is generated, or end if there are no tool calls 
       present, such that the LLM has delivered a response to the query.
       
    """
    
    # read only
    __node_type = WfNodeType.NL_DB_QUERY
    
    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type
    
    def __init__(
        self, 
        *, 
        query_selector: List[str],
        model: BaseChatModel, 
        db:SQLDatabase,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.query_selector = query_selector
        self.model = model
        self.db = db
        
    def call(self, state: GenericState) -> NodeOutput:
        toolkit = SQLDatabaseToolkit(db=self.db, llm=self.model)
        tools = toolkit.get_tools()
        
        get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
        get_schema_node = ToolNode([get_schema_tool], name="get_schema")

        run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")
        run_query_node = ToolNode([run_query_tool], name="run_query")
        
        def list_tables(state: MessagesState):
            tool_call = {
                "name": "sql_db_list_tables",
                "args": {},
                "id": "abc123",
                "type": "tool_call",
            }
            tool_call_message = AIMessage(content="", tool_calls=[tool_call])

            list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")
            tool_message = list_tables_tool.invoke(tool_call)
            response = AIMessage(f"Available tables: {tool_message.content}")
            
            return {"messages": [tool_call_message, tool_message, response]}
        
        def call_get_schema(state: MessagesState):
            # Note that LangChain enforces that all models accept `tool_choice="any"`
            # as well as `tool_choice=<string name of tool>`.
            llm_with_tools = self.model.bind_tools([get_schema_tool], tool_choice="any")
            response = llm_with_tools.invoke(state["messages"])

            return {"messages": [response]}
        
        generate_query_system_prompt = """
    You are an agent designed to interact with a SQL database.
    Given an input question, create a syntactically correct {dialect} query to run,
    then look at the results of the query and return the answer. Unless the user
    specifies a specific number of examples they wish to obtain, always limit your
    query to at most {top_k} results.

    You can order the results by a relevant column to return the most interesting
    examples in the database. Never query for all the columns from a specific table,
    only ask for the relevant columns given the question.

    DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.
    """.format(
        dialect=self.db.dialect,
        top_k=5,
    )
        def generate_query(state: MessagesState):
            system_message = {
                "role": "system",
                "content": generate_query_system_prompt,
            }
            # We do not force a tool call here, to allow the model to
            # respond naturally when it obtains the solution.
            llm_with_tools = self.model.bind_tools([run_query_tool])
            response = llm_with_tools.invoke([system_message] + state["messages"])
            
            return {"messages": [response]}
        
        check_query_system_prompt = """
You are a SQL expert with a strong attention to detail.
Double check the {dialect} query for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins

If there are any of the above mistakes, rewrite the query. If there are no mistakes,
just reproduce the original query.

You will call the appropriate tool to execute the query after running this check.
""".format(dialect=self.db.dialect)

        def check_query(state: MessagesState):
            system_message = {
                "role": "system",
                "content": check_query_system_prompt,
            }
            # Generate an artificial user message to check
            tool_call = state["messages"][-1].tool_calls[0]
            user_message = {"role": "user", "content": tool_call["args"]["query"]}
            llm_with_tools = self.model.bind_tools([run_query_tool], tool_choice="any")
            response = llm_with_tools.invoke([system_message, user_message])
            response.id = state["messages"][-1].id

            return {"messages": [response]}
        
        def should_continue(state: MessagesState) -> Literal[END, "check_query"]:
            messages = state["messages"]
            last_message = messages[-1]
            if not last_message.tool_calls:
                return END
            else:
                return "check_query"
            
        builder = StateGraph(MessagesState)
        builder.add_node(list_tables)
        builder.add_node(call_get_schema)
        builder.add_node(get_schema_node, "get_schema")
        builder.add_node(generate_query)
        builder.add_node(check_query)
        builder.add_node(run_query_node, "run_query")

        builder.add_edge(START, "list_tables")
        builder.add_edge("list_tables", "call_get_schema")
        builder.add_edge("call_get_schema", "get_schema")
        builder.add_edge("get_schema", "generate_query")
        builder.add_conditional_edges(
            "generate_query",
            should_continue,
        )
        builder.add_edge("check_query", "run_query")
        builder.add_edge("run_query", "generate_query")

        agent = builder.compile()
        
        question = VariableResolver.resolve_value_selector(self.query_selector, state)
        
        try:
            data = agent.invoke({"messages": [{"role": "user", "content": question}]})
            messages = data.get("messages",[])
            message:AIMessage = messages[-1]
            content = message.content
            # data contains the entire execution process of this node (all llm and tool calls)
            logger.info("after natural language node execute", name=self.formatted_name, data=data)
            
            update = VariableResolver.format_output(node_id=self.id,outputs={"result":content})
            
            return Command(
                update=update,
                goto=self.next_node_ids
            )
        except Exception as e:
            logger.error("natural language query error", exc_info=True, node_id=self.formatted_name)
            if self.fail_branch_node_ids != None:
                return Command(
                    # this is the state update
                    update={
                        "output_variables": {f"{self.id}_error": str(e)},
                        "node_id": self.id,
                        "source_handle": "fail-branch",
                    },
                    # this is a replacement for an edge
                    goto=self.fail_branch_node_ids,
                )
            else:
                raise e