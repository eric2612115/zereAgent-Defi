# src/connections/anthropic_connection.py

import logging
import os
import json
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv, set_key
from anthropic import Anthropic, NotFoundError
from src.connections.base_connection import BaseConnection, Action, ActionParameter
from src.action_handler import action_registry, execute_action

logger = logging.getLogger("connections.enhanced_anthropic_connection")


class AnthropicConnectionError(Exception):
    """Base exception for Anthropic connection errors"""
    pass


class AnthropicConfigurationError(AnthropicConnectionError):
    """Raised when there are configuration/credential issues"""
    pass


class AnthropicAPIError(AnthropicConnectionError):
    """Raised when Anthropic API requests fail"""
    pass


class AnthropicConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._client = None
        self._function_schemas = None  # Cache for function schemas

    @property
    def is_llm_provider(self) -> bool:
        return True

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Anthropic configuration from JSON"""
        required_fields = ["model"]
        missing_fields = [field for field in required_fields if field not in config]

        if missing_fields:
            raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")

        if not isinstance(config["model"], str):
            raise ValueError("model must be a string")

        return config

    def register_actions(self) -> None:
        """Register available Anthropic actions"""
        self.actions = {
            "generate-text": Action(
                name="generate-text",
                parameters=[
                    ActionParameter("prompt", True, str, "The input prompt for text generation"),
                    ActionParameter("system_prompt", True, str, "System prompt to guide the model"),
                    ActionParameter("model", False, str, "Model to use for generation")
                ],
                description="Generate text using Anthropic models"
            ),
            "generate-text-with-tools": Action(
                name="generate-text-with-tools",
                parameters=[
                    ActionParameter("prompt", True, str, "The input prompt for text generation"),
                    ActionParameter("system_prompt", True, str, "System prompt to guide the model"),
                    ActionParameter("model", False, str, "Model to use for generation"),
                    ActionParameter("temperature", False, float, "Temperature for generation (0-1)"),
                    ActionParameter("max_tokens", False, int, "Maximum tokens to generate")
                ],
                description="Generate text using Anthropic models with tool-using capabilities"
            ),
            "check-model": Action(
                name="check-model",
                parameters=[
                    ActionParameter("model", True, str, "Model name to check availability")
                ],
                description="Check if a specific model is available"
            ),
            "list-models": Action(
                name="list-models",
                parameters=[],
                description="List all available Anthropic models"
            )
        }

    def _get_client(self) -> Anthropic:
        """Get or create Anthropic client"""
        if not self._client:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise AnthropicConfigurationError("Anthropic API key not found in environment")
            self._client = Anthropic(api_key=api_key)
        return self._client

    def _get_function_schemas(self) -> List[Dict[str, Any]]:
        """
        Convert registered tools to Anthropic function schemas.

        Returns:
            List[Dict[str, Any]]: List of function schemas
        """
        # Return cached schemas if available
        if self._function_schemas is not None:
            return self._function_schemas

        function_schemas = []

        for tool_name, tool_func in action_registry.items():
            # Skip internal tools or tools without docstrings
            if tool_name.startswith("_") or not tool_func.__doc__:
                continue

            # Get the function's docstring
            doc = tool_func.__doc__.strip()

            # Extract parameter info from docstring
            param_lines = []
            description = doc.split("\n")[0]  # First line is the description

            # Look for parameter documentation in the docstring
            if "Args:" in doc:
                param_section = doc.split("Args:")[1]
                if "Returns:" in param_section:
                    param_section = param_section.split("Returns:")[0]

                param_lines = [line.strip() for line in param_section.strip().split("\n") if line.strip()]

            # Create parameter schema
            parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }

            # Parse parameter information from docstring
            for line in param_lines:
                if ":" not in line:
                    continue

                parts = line.split(":", 1)
                param_name = parts[0].strip()

                # Skip the agent parameter
                if param_name == "agent":
                    continue

                param_desc = parts[1].strip()

                # Determine if parameter is required
                is_required = "optional" not in param_desc.lower()

                # Determine parameter type
                param_type = "string"  # Default type
                if "int" in param_desc.lower():
                    param_type = "integer"
                elif "float" in param_desc.lower() or "number" in param_desc.lower():
                    param_type = "number"
                elif "bool" in param_desc.lower():
                    param_type = "boolean"
                elif "dict" in param_desc.lower() or "object" in param_desc.lower():
                    param_type = "object"
                elif "list" in param_desc.lower() or "array" in param_desc.lower():
                    param_type = "array"

                # Add parameter to schema
                parameters["properties"][param_name] = {
                    "type": param_type,
                    "description": param_desc
                }

                # Add to required list if needed
                if is_required:
                    parameters["required"].append(param_name)

            # Create function schema
            function_schema = {
                "name": tool_name,
                "description": description,
                "parameters": parameters
            }

            function_schemas.append(function_schema)

        # Cache the schemas
        self._function_schemas = function_schemas
        logger.info(f"Generated {len(function_schemas)} function schemas for tools")

        return function_schemas

    def configure(self) -> bool:
        """Sets up Anthropic API authentication"""
        logger.info("\n🤖 ANTHROPIC API SETUP")

        if self.is_configured():
            logger.info("\nAnthropic API is already configured.")
            response = input("Do you want to reconfigure? (y/n): ")
            if response.lower() != 'y':
                return True

        logger.info("\n📝 To get your Anthropic API credentials:")
        logger.info("1. Go to https://console.anthropic.com/settings/keys")
        logger.info("2. Create a new API key.")

        api_key = input("\nEnter your Anthropic API key: ")

        try:
            if not os.path.exists('.env'):
                with open('.env', 'w') as f:
                    f.write('')

            set_key('.env', 'ANTHROPIC_API_KEY', api_key)

            # Validate the API key
            client = Anthropic(api_key=api_key)
            client.models.list()

            logger.info("\n✅ Anthropic API configuration successfully saved!")
            logger.info("Your API key has been stored in the .env file.")
            return True

        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return False

    def is_configured(self, verbose=False) -> bool:
        """Check if Anthropic API key is configured and valid"""
        try:
            load_dotenv()
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                return False

            client = Anthropic(api_key=api_key)
            client.models.list()
            return True

        except Exception as e:
            if verbose:
                logger.debug(f"Configuration check failed: {e}")
            return False

    def generate_text(self, prompt: str, system_prompt: str, model: str = None, **kwargs) -> str:
        """Generate text using Anthropic models"""
        try:
            client = self._get_client()

            # Use configured model if none provided
            if not model:
                model = self.config["model"]

            message = client.messages.create(
                model=model,
                max_tokens=1000,
                temperature=0,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            return message.content[0].text

        except Exception as e:
            raise AnthropicAPIError(f"Text generation failed: {e}")

    def _execute_tool_from_function_call(self, agent, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool from a function call.

        Args:
            agent: The agent instance to execute the tool with
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

    def generate_text_with_tools(self, prompt: str, system_prompt: str, model: str = None,
                                 temperature: float = 0.2, max_tokens: int = 2000, **kwargs) -> str:
        """
        Generate text using Anthropic models with tool-using capabilities.

        This method allows Claude to decide when to use tools, execute them, and
        use the results to generate a response.

        Args:
            prompt: The input prompt for text generation
            system_prompt: System prompt to guide the model
            model: Model to use for generation (defaults to configured model)
            temperature: Temperature for generation (0-1)
            max_tokens: Maximum tokens to generate

        Returns:
            str: Generated text with tool usage integrated
        """
        try:
            client = self._get_client()

            # Use configured model if none provided
            if not model:
                model = self.config["model"]

            # Get function schemas for tools
            function_schemas = self._get_function_schemas()
            logger.info(f"Using {len(function_schemas)} function schemas")

            # Make the API call with function calling
            try:
                # First call: Let Claude decide whether to use tools
                message = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    tools=function_schemas
                )

                logger.info(f"Got initial response from Claude (length: {len(message.content)})")

                # Handle function calls if present
                tool_results = []
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    logger.info(f"Claude is using {len(message.tool_calls)} tools")

                    # Process each tool call
                    for tool_call in message.tool_calls:
                        logger.info(f"Executing tool call: {tool_call.name}")

                        # Parse input JSON
                        tool_input = tool_call.input
                        if isinstance(tool_input, str):
                            try:
                                tool_input = json.loads(tool_input)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse tool input as JSON: {tool_input}")
                                tool_input = {}

                        # Execute the tool (using the agent from kwargs)
                        agent = kwargs.get('agent')
                        if not agent:
                            raise ValueError("Agent must be provided in kwargs for tool execution")

                        result = self._execute_tool_from_function_call(agent, {
                            "name": tool_call.name,
                            "arguments": tool_input
                        })

                        tool_results.append(result)
                        logger.info(f"Tool execution {'succeeded' if result['success'] else 'failed'}")

                    # If tools were executed, make a second call to Claude with the results
                    if tool_results:
                        # Format tool results for the second call
                        tool_results_text = "\n\n".join([
                            f"Tool: {result['tool']}\n" +
                            f"Arguments: {json.dumps(result['arguments'], indent=2)}\n" +
                            (f"Result: {result['result']}" if result['success'] else f"Error: {result['error']}")
                            for result in tool_results
                        ])

                        logger.info("Making second call to Claude with tool results")

                        # Make the second call
                        second_message = client.messages.create(
                            model=model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system=system_prompt,
                            messages=[
                                {
                                    "role": "user",
                                    "content": prompt
                                },
                                {
                                    "role": "assistant",
                                    "content": "I'll help you with that request. Let me use some tools to get the information."
                                },
                                {
                                    "role": "user",
                                    "content": f"Here are the results of the tools you used:\n\n{tool_results_text}\n\nNow, please provide a final, comprehensive response based on these results. Focus on answering my original query clearly and directly."
                                }
                            ]
                        )

                        # Use the final result
                        final_text = "\n".join([part.text for part in second_message.content if hasattr(part, 'text')])
                        return final_text
                    else:
                        # No successful tool executions, use the original response
                        return "\n".join([part.text for part in message.content if hasattr(part, 'text')])
                else:
                    # No tool calls, use the original response
                    logger.info("Claude did not use any tools for this request")
                    return "\n".join([part.text for part in message.content if hasattr(part, 'text')])

            except Exception as e:
                logger.error(f"Error from Anthropic API: {e}")
                raise AnthropicAPIError(f"Text generation with tools failed: {e}")

        except Exception as e:
            logger.error(f"Text generation with tools failed: {e}")
            raise AnthropicAPIError(f"Text generation with tools failed: {e}")

    def check_model(self, model: str, **kwargs) -> bool:
        """Check if a specific model is available"""
        try:
            client = self._get_client()
            try:
                client.models.retrieve(model_id=model)
                return True
            except NotFoundError:
                logging.error("Model not found.")
                return False
            except Exception as e:
                raise AnthropicAPIError(f"Model check failed: {e}")

        except Exception as e:
            raise AnthropicAPIError(f"Model check failed: {e}")

    def list_models(self, **kwargs) -> None:
        """List all available Anthropic models"""
        try:
            client = self._get_client()
            response = client.models.list().data
            model_ids = [model.id for model in response]

            logger.info("\nCLAUDE MODELS:")
            for i, model in enumerate(model_ids):
                logger.info(f"{i + 1}. {model}")

            return model_ids

        except Exception as e:
            raise AnthropicAPIError(f"Listing models failed: {e}")

    def perform_action(self, action_name: str, kwargs) -> Any:
        """Execute an Anthropic action with validation"""
        if action_name not in self.actions:
            raise KeyError(f"Unknown action: {action_name}")

        action = self.actions[action_name]
        errors = action.validate_params(kwargs)
        if errors:
            raise ValueError(f"Invalid parameters: {', '.join(errors)}")

        # Call the appropriate method based on action name
        method_name = action_name.replace('-', '_')
        method = getattr(self, method_name)
        return method(**kwargs)