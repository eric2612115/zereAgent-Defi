# your_project_root/src/custom_actions/my_tools.py
import logging
import os
from dotenv import load_dotenv
from src.action_handler import register_action

logger = logging.getLogger("custom_actions.my_tools")

# --- Example 1:  Check Wallet Balance (Generic - could be on any chain) ---

@register_action("check-wallet-balance")
def check_wallet_balance(agent, **kwargs):
    """Checks the balance of a wallet.

    Args:
        agent: The agent instance.
        kwargs:  Expected to contain:
            chain (str): The blockchain to check (e.g., "ethereum", "solana", "base").
            token_address (str, optional): The token address to check.  If None, checks native token balance.
    """
    try:
        chain = kwargs.get("chain")
        token_address = kwargs.get("token_address")

        if not chain:
            logger.error("No chain specified for balance check.")
            return "Error: No chain specified."  # Return error message

        if chain not in agent.connection_manager.connections:
            logger.error(f"No connection configured for chain: {chain}")
            return f"Error: No connection for chain '{chain}'."

        connection = agent.connection_manager.connections[chain]

        # Assuming your EVMConnection, SolanaConnection, etc. have a get_balance method.
        #  Adapt this to your *actual* connection methods!
        balance_result = connection.get_balance(token_address=token_address) # Adapt to actual connection methods.

        if isinstance(balance_result, dict) and "balance" in balance_result: # Example return from a connection
            # If token address isn't given, it's the base currency
            if not token_address:
                token = "Base currency"
            else:
                token = token_address

            return f"Balance on {chain} ({token}): {balance_result['balance']}" # Create an easy to read output for the llm.
        else:
            logger.error(f"Unexpected balance result format: {balance_result}")
            return f"Error: Could not retrieve balance for {chain}."


    except Exception as e:
        logger.exception(f"Error checking balance: {e}")
        return f"Error: An unexpected error occurred: {e}"

# --- Example 2:  Add to Whitelist ---

@register_action("add-to-whitelist")
def add_to_whitelist(agent, **kwargs):
    """Adds an address to the agent's whitelist.

    Args:
        agent:  The agent instance.
        kwargs: Expected to contain:
            address (str): The address to add.
    """
    try:
        address = kwargs.get("address")
        if not address:
            logger.error("No address provided for whitelisting.")
            return "Error: No address provided."

        # VERY IMPORTANT:  You need a way to store the whitelist *persistently*.
        # A simple way is to add it to the agent's config.
        # A more robust way is to use a database (like you're using MongoDB for articles).

        # Example using agent config (simplest for now):
        if "whitelist" not in agent.config:
            agent.config["whitelist"] = []

        if address in agent.config["whitelist"]:
            return f"Address {address} is already in the whitelist."

        agent.config["whitelist"].append(address)
        # You would also need to save the updated agent config here!
        #  This depends on how you manage agent configurations.
        agent.save_config() #  <---  IMPORTANT!  Add a save_config() method to your Agent class

        return f"Address {address} added to the whitelist."

    except Exception as e:
        logger.exception(f"Error adding to whitelist: {e}")
        return f"Error: An unexpected error occurred: {e}"
# --- Example 3:  Swap Tokens (Generic - could be on any chain) ---

@register_action("swap-tokens")
def swap_tokens(agent, **kwargs):
    """Swaps tokens.  This is a more complex example.

    Args:
        agent: The agent instance
        kwargs: Expected to contain:
            chain (str):  The blockchain to use (e.g., "ethereum", "base", "solana")
            token_in (str): The token to sell.
            token_out (str): The token to buy.
            amount (float): The amount of token_in to sell.
            slippage (float, optional):  The acceptable slippage (default 0.5).
    """
    try:
        chain = kwargs.get("chain")
        token_in = kwargs.get("token_in")
        token_out = kwargs.get("token_out")
        amount = kwargs.get("amount")
        slippage = kwargs.get("slippage", 0.5)  # Default slippage

        if not chain or not token_in or not token_out or amount is None:
            logger.error("Missing required parameters for swap.")
            return "Error: Missing required parameters (chain, token_in, token_out, amount)."

        if chain not in agent.connection_manager.connections:
            return f"Error: No connection configured for chain: {chain}."
        # Get correct connection
        connection = agent.connection_manager.connections[chain]
        # Do swap with the correct connection, make sure that the connection has a swap method.
        result = connection.swap(token_in=token_in, token_out=token_out, amount=amount, slippage=slippage)
        return result
    except Exception as e:
        logger.exception(f"Error swapping tokens: {e}")
        return f"Error: An unexpected error occurred: {e}"