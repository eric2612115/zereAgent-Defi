import logging
import os
from typing import Dict, Any
from dotenv import load_dotenv, set_key
from google import genai
from src.connections.base_connection import BaseConnection, Action, ActionParameter

logger = logging.getLogger("connections.gemini_connection")

class GeminiConnectionError(Exception):
    """Base exception for Gemini connection errors"""
    pass

class GeminiConfigurationError(GeminiConnectionError):
    """Raised when there are configuration/credential issues"""
    pass

class GeminiAPIError(GeminiConnectionError):
    """Raised when Gemini API requests fail"""
    pass

class GeminiConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._client = None

    @property
    def is_llm_provider(self) -> bool:
        return True

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Gemini configuration from JSON"""
        required_fields = ["model"]
        missing_fields = [field for field in required_fields if field not in config]

        if missing_fields:
            raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")

        if not isinstance(config["model"], str):
            raise ValueError("model must be a string")

        return config

    def register_actions(self) -> None:
        """Register available Gemini actions"""
        self.actions = {
            "generate-text": Action(
                name="generate-text",
                parameters=[
                    ActionParameter("prompt", True, str, "The input prompt for text generation"),
                    ActionParameter("system_prompt", False, str, "System prompt to guide the model"), # System prompt is optional with Gemini, adjust as needed.
                    ActionParameter("model", False, str, "Model to use for generation")
                ],
                description="Generate text using Gemini models"
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
                description="List all available Gemini models"
            )
        }

    def _get_client(self) -> genai.Client:
        """Get or create Gemini client"""
        if not self._client:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise GeminiConfigurationError("Gemini API key not found in environment")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def configure(self) -> bool:
        """Sets up Gemini API authentication"""
        logger.info("\n🤖 GEMINI API SETUP")

        if self.is_configured():
            logger.info("\nGemini API is already configured.")
            response = input("Do you want to reconfigure? (y/n): ")
            if response.lower() != 'y':
                return True

        logger.info("\n📝 To get your Gemini API credentials:")
        logger.info("1. Go to https://makersuite.google.com/app/apikey")
        logger.info("2. Create a new API key.")

        api_key = input("\nEnter your Gemini API key: ")

        try:
            if not os.path.exists('.env'):
                with open('.env', 'w') as f:
                    f.write('')

            set_key('.env', 'GEMINI_API_KEY', api_key)

            # Validate the API key
            client = self._get_client()
            # Using list_models() for a lightweight check
            for model in client.list_models():
                break # Just need to make one request
            # client.models.list() # this would have worked, but now it needs to be called on a client instance

            logger.info("\n✅ Gemini API configuration successfully saved!")
            logger.info("Your API key has been stored in the .env file.")
            return True

        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return False

    def is_configured(self, verbose=False) -> bool:
        """Check if Gemini API key is configured and valid"""
        try:
            load_dotenv()
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                return False

            client = self._get_client()
            # Minimal check - just try to list models
            for model in client.list_models():
                break # Just need to make one request
            # client.models.list()
            return True

        except Exception as e:
            if verbose:
                logger.debug(f"Configuration check failed: {e}")
            return False

    def generate_text(self, prompt: str, system_prompt: str = None, model: str = None, **kwargs) -> str:
        """Generate text using Gemini models"""
        try:
            client = self._get_client()

            # Use configured model if none provided
            if not model:
                model = self.config["model"]

            contents = [{"role": "user", "parts": [prompt]}]
            if system_prompt:
                # Prepend system prompt to content.  Gemini 1.5 Pro has a system instruction.
                # https://ai.google.dev/docs/prompt_best_practices#system-instructions
                contents = [{"role": "user", "parts": [system_prompt]}, {"role": "model", "parts": ["OK"]}, {"role": "user", "parts":[prompt]}]
             # Using client.models.generate_content (not client.chat.send_message) because this is a single turn
            response = client.models.generate_content(
                model=model,
                contents=contents,
                # Use safety_settings if you want to control content filtering.
                # safety_settings=[
                #     {
                #         "category": "HARM_CATEGORY_HARASSMENT",
                #         "threshold": "BLOCK_MEDIUM_AND_ABOVE",
                #     }
                # ],
                # Adjust generation_config as needed (temperature, top_p, etc.)
                generation_config = {
                    "temperature": 0,
                    "max_output_tokens": 1000
                }
            )

            return response.text

        except Exception as e:
            raise GeminiAPIError(f"Text generation failed: {e}")

    def check_model(self, model: str, **kwargs) -> bool:
        """Check if a specific model is available"""
        try:
            client = self._get_client()
            try:
                #  client.models.get is the new method instead of retrieve.
                client.models.get(model_name=model)
                return True
            except Exception as e:
                #  check exception message to see if its a model not found.
                if "was not found" in str(e):
                    logger.error("Model not found.")
                    return False
                else: # Other error.
                    raise GeminiAPIError(f"Model check failed: {e}")

        except Exception as e:
            raise GeminiAPIError(f"Model check failed: {e}")

    def list_models(self, **kwargs) -> None:
        """List all available Gemini models"""
        try:
            client = self._get_client()
            # Changed to client.list_models
            response = client.list_models()
            logger.info("\nGEMINI MODELS:")
            # Iterating since response is now a generator.
            for i, model in enumerate(response):
                logger.info(f"{i+1}. {model.name}")  #  access the name

        except Exception as e:
            raise GeminiAPIError(f"Listing models failed: {e}")
    def perform_action(self, action_name: str, kwargs) -> Any:
        """Execute a Gemini action with validation"""
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