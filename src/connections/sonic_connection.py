import logging
import os
import requests
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv, set_key
from web3 import Web3
from web3.middleware import geth_poa_middleware
from src.constants.abi import ERC20_ABI
from src.connections.base_connection import BaseConnection, Action, ActionParameter
from src.constants.networks import SONIC_NETWORKS

logger = logging.getLogger("connections.sonic_connection")


class SonicConnectionError(Exception):
    """Base exception for Sonic connection errors"""
    pass

class SonicConnection(BaseConnection):

    def __init__(self, config: Dict[str, Any]):
        logger.info("Initializing Sonic connection...")
        self._web3 = None

        # Get network configuration from .env
        self.rpc_url = os.getenv("SONIC_RPC_URL")
        if not self.rpc_url:
            raise ValueError("SONIC_RPC_URL environment variable not set.")

        super().__init__(config) # config 還是要正確
        self._initialize_web3()
        self.ERC20_ABI = ERC20_ABI
        self.NATIVE_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        self.aggregator_api = "https://aggregator-api.kyberswap.com/sonic/api/v1" #先保留 之後可能還是會用到

    def _get_explorer_link(self, tx_hash: str) -> str:
        """Generate block explorer link for transaction"""
        # return f"{self.explorer}/tx/{tx_hash}" #不再需要
        #  根據您的 Sonic 測試網/主網設定修改
        return f"https://scan.sonic.network/tx/{tx_hash}" # 假設是這個

    def _initialize_web3(self):
        """Initialize Web3 connection"""
        if not self._web3:
            self._web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            # Sonic is a POA chain
            self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)
            if not self._web3.is_connected():
                raise SonicConnectionError("Failed to connect to Sonic network")

            try:
                chain_id = self._web3.eth.chain_id
                logger.info(f"Connected to network with chain ID: {chain_id}")
            except Exception as e:
                logger.warning(f"Could not get chain ID: {e}")

    @property
    def is_llm_provider(self) -> bool:
        return False

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # 簡化 config 驗證，因為我們現在直接從 .env 讀取
        return config

    def get_token_by_ticker(self, ticker: str) -> Optional[str]:
        """Get token address by ticker symbol (using an external API, since we don't have chain info)."""
        try:
            if ticker.lower() in ["s", "S"]: # 如果是查詢原生代幣
                return "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

            response = requests.get(
                f"https://api.dexscreener.com/latest/dex/search?q={ticker}"
            )
            response.raise_for_status()

            data = response.json()
            if not data.get('pairs'):
                return None

            sonic_pairs = [
                pair for pair in data["pairs"] if pair.get("chainId") == "sonic"  # Use "sonic"
            ]
            sonic_pairs.sort(key=lambda x: x.get("fdv", 0), reverse=True) #依照fdv排序

            sonic_pairs = [
                pair
                for pair in sonic_pairs
                if pair.get("baseToken", {}).get("symbol", "").lower() == ticker.lower()
            ]

            if sonic_pairs:
                return sonic_pairs[0].get("baseToken", {}).get("address")
            return None

        except Exception as error:
            logger.error(f"Error fetching token address: {str(error)}")
            return None

    def register_actions(self) -> None:
        self.actions = {
            "get-token-by-ticker": Action(
                name="get-token-by-ticker",
                parameters=[
                    ActionParameter("ticker", True, str, "Token ticker symbol to look up")
                ],
                description="Get token address by ticker symbol"
            ),
            "get-balance": Action(
                name="get-balance",
                parameters=[
                    ActionParameter("address", False, str, "Address to check balance for"),
                    ActionParameter("token_address", False, str, "Optional token address")
                ],
                description="Get $S or token balance"
            ),
            "transfer": Action(
                name="transfer",
                parameters=[
                    ActionParameter("to_address", True, str, "Recipient address"),
                    ActionParameter("amount", True, float, "Amount to transfer"),
                    ActionParameter("token_address", False, str, "Optional token address")
                ],
                description="Send $S or tokens"
            ),
            "swap": Action(
                name="swap",
                parameters=[
                    ActionParameter("token_in", True, str, "Input token address"),
                    ActionParameter("token_out", True, str, "Output token address"),
                    ActionParameter("amount", True, float, "Amount to swap"),
                    ActionParameter("slippage", False, float, "Max slippage percentage")
                ],
                description="Swap tokens"
            )
        }

    def configure(self) -> bool:
        # 現在設定只需要檢查 SONIC_RPC_URL
        logger.info("\n🔷 SONIC CHAIN SETUP")
        if self.is_configured():
            logger.info("Sonic connection is already configured.")
            return True

        # 如果需要，可以在這裡提示使用者輸入 SONIC_RPC_URL，並將其儲存到 .env
        # 但通常 RPC URL 應該在環境變數中預先設定好

        return True # 如果不需要使用者輸入，直接返回 True


    def is_configured(self, verbose: bool = False) -> bool:
        try:
            load_dotenv()
            if not os.getenv('SONIC_RPC_URL'): # 檢查環境變數
                if verbose:
                    logger.error("Missing SONIC_RPC_URL in environment variables")
                return False

            if not self._web3.is_connected():
                if verbose:
                    logger.error("Not connected to Sonic network")
                return False
            return True

        except Exception as e:
            if verbose:
                logger.error(f"Configuration check failed: {e}")
            return False

    def get_balance(self, address: Optional[str] = None, token_address: Optional[str] = None) -> float:
        """Get balance for an address or the configured wallet."""
        try:

            if not address:
                raise "address is needed"  # 應該要給 address

            if token_address:  # ERC-20 token
                token_address = Web3.to_checksum_address(token_address)
                contract = self._web3.eth.contract(address=token_address, abi=self.ERC20_ABI)
                balance_wei = contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
                decimals = contract.functions.decimals().call()
                balance = balance_wei / (10 ** decimals)
            else:  # Native token ($S)
                balance_wei = self._web3.eth.get_balance(Web3.to_checksum_address(address))
                balance = self._web3.from_wei(balance_wei, 'ether')

            return float(balance)

        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            raise

    def transfer(self, to_address: str, amount: float, token_address: Optional[str] = None) -> str:
        """Transfer $S or tokens to an address"""
        try:
            private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)
            chain_id = self._web3.eth.chain_id
            
            if token_address:
                contract = self._web3.eth.contract(
                    address=Web3.to_checksum_address(token_address),
                    abi=self.ERC20_ABI
                )
                decimals = contract.functions.decimals().call()
                amount_raw = int(amount * (10 ** decimals))
                
                tx = contract.functions.transfer(
                    Web3.to_checksum_address(to_address),
                    amount_raw
                ).build_transaction({
                    'from': account.address,
                    'nonce': self._web3.eth.get_transaction_count(account.address),
                    'gasPrice': self._web3.eth.gas_price,
                    'chainId': chain_id
                })
            else:
                tx = {
                    'nonce': self._web3.eth.get_transaction_count(account.address),
                    'to': Web3.to_checksum_address(to_address),
                    'value': self._web3.to_wei(amount, 'ether'),
                    'gas': 21000,
                    'gasPrice': self._web3.eth.gas_price,
                    'chainId': chain_id
                }

            signed = account.sign_transaction(tx)
            tx_hash = self._web3.eth.send_raw_transaction(signed.rawTransaction)

            # Log and return explorer link immediately
            tx_link = self._get_explorer_link(tx_hash.hex())
            return f"⛓️ Transfer transaction sent: {tx_link}"

        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            raise

    def _get_swap_route(self, token_in: str, token_out: str, amount_in: float) -> Dict:
        """Get the best swap route from Kyberswap API"""
        try:
            # Handle native token address
            
            # Convert amount to raw value
            if token_in.lower() == self.NATIVE_TOKEN.lower():
                amount_raw = self._web3.to_wei(amount_in, 'ether')
            else:
                token_contract = self._web3.eth.contract(
                    address=Web3.to_checksum_address(token_in),
                    abi=self.ERC20_ABI
                )
                decimals = token_contract.functions.decimals().call()
                amount_raw = int(amount_in * (10 ** decimals))
            
            # Set up API request
            url = f"{self.aggregator_api}/routes"
            headers = {"x-client-id": "ZerePyBot"}
            params = {
                "tokenIn": token_in,
                "tokenOut": token_out,
                "amountIn": str(amount_raw),
                "gasInclude": "true"
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("code") != 0:
                raise SonicConnectionError(f"API error: {data.get('message')}")
                
            return data["data"]
                
        except Exception as e:
            logger.error(f"Failed to get swap route: {e}")
            raise

    def _get_encoded_swap_data(self, route_summary: Dict, slippage: float = 0.5) -> str:
        """Get encoded swap data from Kyberswap API"""
        try:
            private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)
            
            url = f"{self.aggregator_api}/route/build"
            headers = {"x-client-id": "zerepy"}
            
            payload = {
                "routeSummary": route_summary,
                "sender": account.address,
                "recipient": account.address,
                "slippageTolerance": int(slippage * 100),  # Convert to bps
                "deadline": int(time.time() + 1200),  # 20 minutes
                "source": "ZerePyBot"
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            if data.get("code") != 0:
                raise SonicConnectionError(f"API error: {data.get('message')}")
                
            return data["data"]["data"]
                
        except Exception as e:
            logger.error(f"Failed to encode swap data: {e}")
            raise
    
    def _handle_token_approval(self, token_address: str, spender_address: str, amount: int) -> None:
        """Handle token approval for spender"""
        try:
            private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)
            
            token_contract = self._web3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )
            
            # Check current allowance
            current_allowance = token_contract.functions.allowance(
                account.address,
                spender_address
            ).call()
            
            if current_allowance < amount:
                approve_tx = token_contract.functions.approve(
                    spender_address,
                    amount
                ).build_transaction({
                    'from': account.address,
                    'nonce': self._web3.eth.get_transaction_count(account.address),
                    'gasPrice': self._web3.eth.gas_price,
                    'chainId': self._web3.eth.chain_id
                })
                
                signed_approve = account.sign_transaction(approve_tx)
                tx_hash = self._web3.eth.send_raw_transaction(signed_approve.rawTransaction)
                logger.info(f"Approval transaction sent: {self._get_explorer_link(tx_hash.hex())}")
                
                # Wait for approval to be mined
                self._web3.eth.wait_for_transaction_receipt(tx_hash)
                
        except Exception as e:
            logger.error(f"Approval failed: {e}")
            raise

    def swap(self, token_in: str, token_out: str, amount: float, slippage: float = 0.5) -> str:
        """Execute a token swap using the KyberSwap router"""
        try:
            private_key = os.getenv('SONIC_PRIVATE_KEY')
            account = self._web3.eth.account.from_key(private_key)

            # Check token balance before proceeding
            current_balance = self.get_balance(
                address=account.address,
                token_address=None if token_in.lower() == self.NATIVE_TOKEN.lower() else token_in
            )
            
            if current_balance < amount:
                raise ValueError(f"Insufficient balance. Required: {amount}, Available: {current_balance}")
                
            # Get optimal swap route
            route_data = self._get_swap_route(token_in, token_out, amount)
            
            # Get encoded swap data
            encoded_data = self._get_encoded_swap_data(route_data["routeSummary"], slippage)
            
            # Get router address from route data
            router_address = route_data["routerAddress"]
            
            # Handle token approval if not using native token
            if token_in.lower() != self.NATIVE_TOKEN.lower():
                if token_in.lower() == "0x039e2fb66102314ce7b64ce5ce3e5183bc94ad38".lower():  # $S token
                    amount_raw = self._web3.to_wei(amount, 'ether')
                else:
                    token_contract = self._web3.eth.contract(
                        address=Web3.to_checksum_address(token_in),
                        abi=self.ERC20_ABI
                    )
                    decimals = token_contract.functions.decimals().call()
                    amount_raw = int(amount * (10 ** decimals))
                self._handle_token_approval(token_in, router_address, amount_raw)
            
            # Prepare transaction
            tx = {
                'from': account.address,
                'to': Web3.to_checksum_address(router_address),
                'data': encoded_data,
                'nonce': self._web3.eth.get_transaction_count(account.address),
                'gasPrice': self._web3.eth.gas_price,
                'chainId': self._web3.eth.chain_id,
                'value': self._web3.to_wei(amount, 'ether') if token_in.lower() == self.NATIVE_TOKEN.lower() else 0
            }
            
            # Estimate gas
            try:
                tx['gas'] = self._web3.eth.estimate_gas(tx)
            except Exception as e:
                logger.warning(f"Gas estimation failed: {e}, using default gas limit")
                tx['gas'] = 500000  # Default gas limit
            
            # Sign and send transaction
            signed_tx = account.sign_transaction(tx)
            tx_hash = self._web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Log and return explorer link immediately
            tx_link = self._get_explorer_link(tx_hash.hex())
            return f"🔄 Swap transaction sent: {tx_link}"
                
        except Exception as e:
            logger.error(f"Swap failed: {e}")
            raise
    def perform_action(self, action_name: str, kwargs) -> Any:
        """Execute a Sonic action with validation"""
        if action_name not in self.actions:
            raise KeyError(f"Unknown action: {action_name}")

        load_dotenv()
        
        if not self.is_configured(verbose=True):
            raise SonicConnectionError("Sonic is not properly configured")

        action = self.actions[action_name]
        errors = action.validate_params(kwargs)
        if errors:
            raise ValueError(f"Invalid parameters: {', '.join(errors)}")

        method_name = action_name.replace('-', '_')
        method = getattr(self, method_name)
        return method(**kwargs)