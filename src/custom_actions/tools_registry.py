# src/custom_actions/tools_registry.py

import logging
import inspect
from typing import Dict, List, Any, Callable
from src.action_handler import action_registry

logger = logging.getLogger("custom_actions.tools_registry")


def get_all_tools() -> Dict[str, Dict[str, Any]]:
    """
    Get a dictionary of all registered tools with their documentation.

    Returns:
        Dict[str, Dict[str, Any]]: Dictionary of tool_name -> tool_info
    """
    tools_info = {}

    for tool_name, tool_func in action_registry.items():
        # Get the function's docstring
        doc = inspect.getdoc(tool_func) or "No documentation available"

        # Get parameter information
        signature = inspect.signature(tool_func)
        params = []

        for param_name, param in signature.parameters.items():
            # Skip the first parameter (agent)
            if param_name == "agent":
                continue

            # Get parameter default if available
            if param.default is not param.empty:
                default = param.default
            else:
                default = None

            # Get parameter type if available
            if param.annotation is not param.empty:
                param_type = str(param.annotation).replace("<class '", "").replace("'>", "")
            else:
                param_type = "any"

            params.append({
                "name": param_name,
                "type": param_type,
                "default": default,
                "required": param.default is param.empty and param_name != "kwargs"
            })

        # Store tool information
        tools_info[tool_name] = {
            "name": tool_name,
            "description": doc.split("\n")[0] if doc else "No description",
            "full_doc": doc,
            "parameters": params
        }

    return tools_info


def format_tools_for_prompt() -> str:
    """
    Format all registered tools into a string suitable for inclusion in a system prompt.

    Returns:
        str: Formatted tools documentation
    """
    tools = get_all_tools()

    if not tools:
        return "No tools available."

    formatted_output = "# Available Tools\n\n"

    # Group tools by category (assuming naming convention tool_category_action)
    categories = {}
    for tool_name, tool_info in tools.items():
        # Skip internal tools
        if tool_name.startswith("_"):
            continue

        parts = tool_name.split("_")
        if len(parts) > 1:
            category = parts[0]
        else:
            category = "general"

        if category not in categories:
            categories[category] = []

        categories[category].append(tool_info)

    # Format each category
    for category, tools_list in sorted(categories.items()):
        formatted_output += f"## {category.capitalize()} Tools\n\n"

        for tool in tools_list:
            formatted_output += f"### {tool['name']}\n"
            formatted_output += f"{tool['description']}\n\n"

            if tool['parameters']:
                formatted_output += "Parameters:\n"
                for param in tool['parameters']:
                    default_str = f" (default: {param['default']})" if param['default'] is not None else ""
                    required_str = " (required)" if param['required'] else ""
                    formatted_output += f"- {param['name']}: {param['type']}{required_str}{default_str}\n"
                formatted_output += "\n"

            # Add full documentation if it's different from the short description
            full_doc = tool.get('full_doc', '').strip()
            short_desc = tool.get('description', '').strip()

            if full_doc and full_doc != short_desc:
                # Extract everything after the first line
                doc_lines = full_doc.split('\n')
                if len(doc_lines) > 1:
                    additional_doc = '\n'.join(doc_lines[1:]).strip()
                    if additional_doc:
                        formatted_output += f"{additional_doc}\n\n"

    return formatted_output


def get_tool_info(tool_name: str) -> Dict[str, Any]:
    """
    Get information about a specific tool.

    Args:
        tool_name: The name of the tool

    Returns:
        Dict[str, Any]: Tool information or None if not found
    """
    tools = get_all_tools()
    return tools.get(tool_name)