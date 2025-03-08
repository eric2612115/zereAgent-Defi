import asyncio
import logging
import os
import hmac
import base64
import json
from pprint import pprint

import aiohttp
from dotenv import load_dotenv, find_dotenv
from datetime import datetime

from typing import Optional


class ThirdPartyClient:
    BASE_URL = "https://hexa-guard-backend.onrender.com"

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ThirdPartyClient...")
        self.session = None
        self.logger.info("ThirdPartyClient initialized.")

    async def initialize(self):
        """Asynchronously initialize ClientSession"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self.logger.info("ThirdPartyClient session initialized.")

    async def close(self):
        """Close ClientSession"""
        if self.session:
            await self.session.close()
            self.session = None
            self.logger.info("ThirdPartyClient session closed.")

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Send GET request"""
        if self.session is None:
            await self.initialize()

        url = f"{self.BASE_URL}/{path}"
        try:
            async with self.session.get(url, params=params) as response:
                return await response.json()
        except Exception as e:
            self.logger.error(f"Error in GET request: {e}")
            return {"error": str(e)}

    async def _post_request(self, path: str, data: dict) -> dict:
        """Send POST request"""
        if self.session is None:
            await self.initialize()

        url = f"{self.BASE_URL}/{path}"
        try:
            async with self.session.post(url, json=data) as response:
                return await response.json()
        except Exception as e:
            self.logger.error(f"Error in POST request: {e}")
            return {"error": str(e)}

    async def get_security(self, original_token: str, target_token: str, chain: str, amount: str):
        """Get text security with structured data like:
                {
          "original_token": "string",
          "target_token": "string",
          "chain": "string",
          "amount": "string"
        }"""
        try:
            # If structured data is provided, use it as the primary input
            # Otherwise, fall back to the legacy text input
            data = {
                "original_token": original_token,
                "target_token": target_token,
                "chain": chain,
                "amount": amount
            }
            return await self._post_request("get-security", data)
        except Exception as e:
            self.logger.error(f"Error getting security: {e}")
            return {"error": str(e), "message": "Failed to get security information"}

    async def get_top5_tokens(self):
        return await self._get("top5_tokens")


async def main():
    client = ThirdPartyClient()
    await client.initialize()
    # result = await client.get_security("Give me KAITO security on BASE")
    # pprint(result)

    print(await client.get_top5_tokens())


if __name__ == "__main__":
    load_dotenv(find_dotenv())
    asyncio.run(main())
