# src/custom_actions/api_tools.py

import logging
import requests
import json
from src.action_handler import register_action

logger = logging.getLogger("custom_actions.api_tools")


# --- Balance and Token Information Tools ---

local_api_url = "http://localhost:8000/api"

@register_action("get-wallet-balance")
def get_wallet_balance(agent, **kwargs):
    """Get the wallet balance for a given address and chain"""
    wallet_address = kwargs.get("wallet_address")
    chain_id = kwargs.get("chain_id", "1")  # Default to Ethereum

    if not wallet_address:
        return "Error: wallet_address is required"

    try:
        # Make API call to your backend
        response = requests.post(
            f"{local_api_url}/total-balance",
            json={"wallet_address": wallet_address, "chain_id_list": [chain_id]}
        )
        response.raise_for_status()

        balance_data = response.json()
        return balance_data
    except Exception as e:
        logger.exception(f"Error getting wallet balance: {e}")
        return f"Error: {str(e)}"


@register_action("get-token-balances")
def get_token_balances(agent, **kwargs):
    """Get detailed token balances for a wallet address"""
    wallet_address = kwargs.get("wallet_address")
    chain_id_list = kwargs.get("chain_id_list", ["1", "56", "137", "8453"])  # Default to common chains

    if not wallet_address:
        return "Error: wallet_address is required"

    try:
        # Make API call to your backend
        response = requests.post(
            f"{local_api_url}/total-balance-detail",
            json={"wallet_address": wallet_address, "chain_id_list": chain_id_list}
        )
        response.raise_for_status()

        token_data = response.json()
        return token_data
    except Exception as e:
        logger.exception(f"Error getting token balances: {e}")
        return f"Error: {str(e)}"


# --- News and Market Information Tools ---

@register_action("get-crypto-news")
def get_crypto_news(agent, **kwargs):
    """Get the latest crypto news"""
    try:
        # Make API call to your backend
        response = requests.get(f"{local_api_url}/get-cave-news")
        response.raise_for_status()

        news_data = response.json()

        # Format the news for better readability
        formatted_news = []
        for news_item in news_data:
            formatted_news.append({
                "title": news_item.get("title"),
                "summary": news_item.get("summary"),
                "source": news_item.get("source"),
                "date": news_item.get("date")
            })

        return formatted_news
    except Exception as e:
        logger.exception(f"Error getting crypto news: {e}")
        return f"Error: {str(e)}"


@register_action("get-ticker-data")
def get_ticker_data(agent, **kwargs):
    """Get ticker data for cryptocurrency pairs"""
    try:
        # Make API call to your backend
        response = requests.get(f"{local_api_url}/public-data/tickers")
        response.raise_for_status()

        ticker_data = response.json()
        return ticker_data
    except Exception as e:
        logger.exception(f"Error getting ticker data: {e}")
        return f"Error: {str(e)}"


# --- Multisig Wallet Tools ---

@register_action("create-multisig-wallet")
def create_multisig_wallet(agent, **kwargs):
    """Create a multisig wallet for a user"""
    wallet_address = kwargs.get("wallet_address")
    chain_id = kwargs.get("chain_id", 421614)  # Default to Arbitrum Sepolia

    if not wallet_address:
        return "Error: wallet_address is required"

    try:
        # Make API call to your backend
        response = requests.post(
            f"{local_api_url}/deploy-multisig-wallet?wallet_address={wallet_address}&chain_id={chain_id}"
        )
        response.raise_for_status()

        result = response.json()
        return result
    except Exception as e:
        logger.exception(f"Error creating multisig wallet: {e}")
        return f"Error: {str(e)}"


@register_action("get-multisig-info")
def get_multisig_info(agent, **kwargs):
    """Get information about a user's multisig wallet"""
    wallet_address = kwargs.get("wallet_address")

    if not wallet_address:
        return "Error: wallet_address is required"

    try:
        # Make API call to your backend
        response = requests.get(f"{local_api_url}/get-multisig-wallets?wallet_address={wallet_address}")

        # If status code is 404, it means the user doesn't have a multisig wallet
        if response.status_code == 404:
            return {"has_multisig": False, "message": "No multisig wallet found for this user"}

        response.raise_for_status()
        result = response.json()

        # Add has_multisig flag for easier checking
        result["has_multisig"] = "multisig_address" in result and result["multisig_address"] is not None

        return result
    except Exception as e:
        logger.exception(f"Error getting multisig info: {e}")
        return f"Error: {str(e)}"