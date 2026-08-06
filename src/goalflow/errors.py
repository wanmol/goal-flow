"""
Custom exceptions for the goalflow workflow system.
"""


class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class NodeExecutionError(WorkflowError):
    """Exception raised when a node fails to execute."""
    
    def __init__(self, node_id: str, node_type: str, message: str):
        self.node_id = node_id
        self.node_type = node_type
        super().__init__(f"Node {node_id} ({node_type}) failed: {message}")


class VariableResolutionError(WorkflowError):
    """Exception raised when variable resolution fails."""
    
    def __init__(self, variable_name: str, message: str):
        self.variable_name = variable_name
        super().__init__(f"Variable '{variable_name}' resolution failed: {message}")


class InvalidConfigurationError(WorkflowError):
    """Exception raised when configuration is invalid."""
    pass


class LLMError(WorkflowError):
    """Exception raised when LLM processing fails."""
    pass


class StateValidationError(WorkflowError):
    """Exception raised when state validation fails."""
    pass


class DifyParsingError(WorkflowError):
    """Exception raised when Dify DSL parsing fails."""
    pass


class TemplateError(WorkflowError):
    """Exception raised when template processing fails."""
    pass


class SkillError(WorkflowError):
    """Base exception for skill system errors."""
    pass


class SkillParseError(SkillError):
    """Exception raised when skill file parsing fails."""

    def __init__(self, file_path: str, message: str):
        self.file_path = file_path
        super().__init__(f"Failed to parse skill '{file_path}': {message}")


class SkillMatchError(SkillError):
    """Exception raised when skill matching fails."""
    pass
