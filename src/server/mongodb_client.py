# src/server/mongodb_client.py

import motor.motor_asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
from uuid import uuid4

logger = logging.getLogger("mongodb_client")


class MongoDBClient:
    """MongoDB client for persisting user conversations and wallet data"""

    def __init__(self, mongodb_url: str, database_name: str):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(mongodb_url)
        self.db = self.client[database_name]

    async def initialize_indexes(self):
        """Create necessary database indexes"""
        try:
            await self.db.users.create_index("wallet_address", unique=True)
            await self.db.conversations.create_index("wallet_address")
            await self.db.multisig_whitelists.create_index("multisig_address")
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating database indexes: {e}")

    async def get_user(self, wallet_address: str) -> Optional[Dict[str, Any]]:
        """Get a user by wallet address"""
        return await self.db.users.find_one({"wallet_address": wallet_address})

    async def create_user(self, wallet_address: str) -> Dict[str, Any]:
        """Create a new user"""
        user = {
            "wallet_address": wallet_address,
            "created_at": datetime.now(),
            "has_agent": False,
            "multisig_address": None
        }
        await self.db.users.insert_one(user)
        return user

    async def save_message(self, wallet_address: str, message: Dict[str, Any]):
        """Save a message to the conversation history"""
        # Ensure message has required fields
        if "id" not in message:
            message["id"] = str(uuid4())
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()

        result = await self.db.conversations.update_one(
            {"wallet_address": wallet_address},
            {"$push": {"messages": message}},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    async def get_conversation_history(self, wallet_address: str) -> List[Dict[str, Any]]:
        """Get conversation history for a user"""
        conversation = await self.db.conversations.find_one({"wallet_address": wallet_address})
        return conversation.get("messages", []) if conversation else []