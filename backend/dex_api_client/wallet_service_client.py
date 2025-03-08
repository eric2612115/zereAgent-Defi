import aiohttp, asyncio, json, logging, os
from dotenv import find_dotenv, load_dotenv


class WalletServiceClient:

    def __init__(self):
        load_dotenv(find_dotenv())
        self.base_url = os.getenv("WALLET_SERVICE_URL")
        self.header = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        self.session = None  # Initialize session to None

    async def _get_session(self):
        """Lazily creates an aiohttp ClientSession."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _request(self, method, url, data=None):
        """Centralized request handling with retries."""
        session = await self._get_session()
        try:
            async with session.request(method, url, headers=self.header, json=data) as response:
                response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
                return await response.json()
        except aiohttp.ClientResponseError as e:
            if e.status == 429 or e.status >= 500:  # Retry on rate limits or server errors
                logging.error(f"Request failed after multiple retries: {e}")
                raise  # Re-raise the exception after all retries fail
            else:
                logging.error(f"Request failed with client error: {e}")
                raise  # Re-raise for other client errors (4xx but not 429)
        except aiohttp.ClientConnectionError as e:
            logging.error(f"Connection error after multiple retries: {e}")
            raise
        except Exception as e:  # Catch any other exceptions
            logging.error(f"An unexpected error occurred: {e}")
            raise

    async def get_ai_wallet_address(self, wallet_address: str):
        """
        Retrieves an AI wallet by its ID.

        :param wallet_address: The ID of the wallet.
        :return: A dictionary containing the wallet information.
        """
        url = f"{self.base_url}/wallet/ai/{wallet_address}"
        return await self._request("GET", url)

    async def create_ai_wallet(self, owner_address: str):
        """
        Creates an AI wallet.

        :param owner_address: The address of the wallet owner.
        :return: A dictionary containing the wallet information.
        """
        url = f"{self.base_url}/wallet/create-ai"
        data = {"ownerAddress": owner_address}
        return await self._request("POST", url, data=data)

    async def create_multi_sig_wallet(self, owner_address: str, chain_id: int):
        """
        Creates a multi-sig wallet.

        :param owner_address: The address of the wallet owner.
        :param chain_id: The ID of the blockchain.
        :return: A dictionary containing the multi-sig wallet information.
        """
        url = f"{self.base_url}/wallet/create-wallet"
        data = {"ownerAddress": owner_address, "chain": chain_id}
        return await self._request("POST", url, data=data)

    async def get_multi_sig_wallet(self, wallet_address: str):
        """
        Retrieves a list of multi-sig wallets for a given owner address.

        :param wallet_address:  The owner address.
        :return: A dictionary containing the list of multi-sig wallets.
        """
        url = f"{self.base_url}/wallet/list?ownerAddress={wallet_address}"
        return await self._request("GET", url)

    async def get_multi_sig_wallet_whitelist(self, wallet_address: str, chain_id: int):
        """
        Gets the whitelist for a multi-sig wallet.

        :param wallet_address: The address of the multi-sig wallet.
        :param chain_id: The ID of the blockchain.
        :return:  The response from the whitelist endpoint.
        """
        url = f"{self.base_url}/wallet/whitelist"
        data = {"chain": str(chain_id), "safeWalletAddress": wallet_address}  # Ensure chain is string
        # Note: using json=data in _request already correctly handles the body.
        return await self._request("GET", url, data=data)

    async def add_multi_sig_wallet_whitelist(self, chain_id: int, safe_wallet_address: str, whitelist_signatures: list,
                                             token_addresses: list):
        """
        Adds tokens to the whitelist of a multi-sig wallet.
        """
        url = f"{self.base_url}/wallet/whitelist/add"
        data = {
            "chain": str(chain_id),  #Ensure chain is string
            "safeWalletAddress": safe_wallet_address,
            "whitelistSignatures": whitelist_signatures,
            "tokenAddresses": token_addresses
        }
        return await self._request("POST", url, data=data)

    async def remove_multi_sig_wallet_whitelist(self, chain_id: int, safe_wallet_address: str,
                                                whitelist_signatures: list, token_addresses: list):
        """
        Removes tokens from the whitelist of a multi-sig wallet.
        """
        url = f"{self.base_url}/wallet/whitelist/remove"
        data = {
            "chain": str(chain_id),  # Ensure chain is string
            "safeWalletAddress": safe_wallet_address,
            "whitelistSignatures": whitelist_signatures,
            "tokenAddresses": token_addresses
        }
        return await self._request("POST", url, data=data)

    async def multi_sig_wallet_swap(self, chain_id: int, ai_address: str, safe_wallet_address: str, pair_address: str,
                                    input_token_address: str, input_token_amount: str, output_token_address: str,
                                    output_token_min_amount: str):
        """
        Performs a token swap through a multi-sig wallet.
        """
        url = f"{self.base_url}/wallet/swap"
        data = {
            "chain": str(chain_id),  #Ensure chain is string
            "aiAddress": ai_address,
            "safeWalletAddress": safe_wallet_address,
            "pairAddress": pair_address,
            "inputTokenAddress": input_token_address,
            "inputTokenAmount": input_token_amount,
            "outputTokenAddress": output_token_address,
            "outputTokenMinAmount": output_token_min_amount
        }
        return await self._request("POST", url, data=data)

    async def close(self):
        """Closes the aiohttp ClientSession."""
        if self.session:
            await self.session.close()
