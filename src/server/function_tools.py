# src/server/function_tools.py

from typing import Dict, Any, List
import json
import logging
from src.action_handler import action_registry, execute_action
from src.custom_actions.tools_registry import get_all_tools

logger = logging.getLogger("function_tools")


def get_tool_schemas() -> List[Dict[str, Any]]:
    """
    Convert registered tools to Anthropic function schemas.

    Returns:
        List[Dict[str, Any]]: List of function schemas
    """
    tools_info = get_all_tools()
    function_schemas = []

    for tool_name, tool_info in tools_info.items():
        # Skip internal tools
        if tool_name.startswith("_"):
            continue

        # Create parameter schema
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }

        for param in tool_info.get("parameters", []):
            param_name = param.get("name")
            if param_name == "kwargs":  # Skip **kwargs
                continue

            # Convert parameter type to JSON schema type
            param_type = param.get("type", "any")
            if param_type in ["str", "string"]:
                json_type = "string"
            elif param_type in ["int", "integer"]:
                json_type = "integer"
            elif param_type in ["float", "number"]:
                json_type = "number"
            elif param_type in ["bool", "boolean"]:
                json_type = "boolean"
            elif param_type in ["dict", "object"]:
                json_type = "object"
            elif param_type in ["list", "array"]:
                json_type = "array"
            else:
                json_type = "string"  # Default to string

            # Add parameter to schema
            parameters["properties"][param_name] = {
                "type": json_type,
                "description": f"Parameter: {param_name}"
            }

            # Add to required list if needed
            if param.get("required", False):
                parameters["required"].append(param_name)

        # Create function schema
        function_schema = {
            "name": tool_name,
            "description": tool_info.get("description", ""),
            "parameters": parameters
        }

        function_schemas.append(function_schema)

    return function_schemas


def execute_tool_from_function_call(agent, tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool from a function call.

    Args:
        agent: The agent instance
        tool_call: Function call from Anthropic API

    Returns:
        Dict[str, Any]: Result of tool execution
    """
    try:
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})

        logger.info(f"Executing tool {tool_name} with arguments {arguments}")

        if tool_name not in action_registry:
            return {
                "success": False,
                "error": f"Tool {tool_name} not found in registry"
            }

        # Execute the tool
        result = execute_action(agent, tool_name, **arguments)

        return {
            "success": True,
            "tool": tool_name,
            "arguments": arguments,
            "result": result
        }

    except Exception as e:
        logger.error(f"Error executing tool {tool_call.get('name', 'unknown')}: {str(e)}")
        return {
            "success": False,
            "tool": tool_call.get("name", "unknown"),
            "arguments": tool_call.get("arguments", {}),
            "error": str(e)
        }