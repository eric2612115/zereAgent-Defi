# src/server/enhanced_server.py

import asyncio
import logging
import os
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, List
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.server.multi_client_handler import MultiClientManager
from src.server.mongodb_client import MongoDBClient
from src.cli import ZerePyCLI

from backend.dex_api_client.wallet_service_client import WalletServiceClient
from backend.dex_api_client.okx_web3_client import OkxWeb3Client
from backend.dex_api_client.third_client import ThirdPartyClient
from backend.dex_api_client.cave_client import CaveClient
from backend.dex_api_client.public_data import get_binance_tickers

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("enhanced_server")


# Message structure helper
class MessageStructure:
    @staticmethod
    def format_ai_response(content: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(uuid4()),
            "sender": "ai",
            "text": content.get("recommendation", ""),
            "message_type": content.get("message_type", "normal"),
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def format_error(error_text: str) -> Dict[str, Any]:
        return {
            "id": str(uuid4()),
            "sender": "system",
            "text": error_text,
            "message_type": "error",
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def format_status(status_text: str) -> Dict[str, Any]:
        return {
            "id": str(uuid4()),
            "sender": "system",
            "text": status_text,
            "message_type": "status",
            "timestamp": datetime.now().isoformat()
        }


# Define FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database client
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "zerepy_db")
    db_client = MongoDBClient(mongodb_url, database_name)

    # Initialize DB indexes
    await db_client.initialize_indexes()

    # Initialize API clients
    okx_client = OkxWeb3Client(
        project_id=os.getenv("OKX_WEB3_PROJECT_ID"),
        api_key=os.getenv("OKX_WEB3_PROJECT_KEY"),
        api_secret=os.getenv("OKX_WEB3_PROJECT_SECRET"),
        api_passphrase=os.getenv("OKX_WEB3_PROJECT_PASSWRD"),
    )
    third_party_client = ThirdPartyClient()
    cave_client = CaveClient(os.getenv("CAVE_API_KEY"))
    wallet_service_client = WalletServiceClient()

    # Initialize clients
    logger.info("Initializing OkxWeb3Client...")
    await okx_client.initialize()
    logger.info("OkxWeb3Client initialized.")

    logger.info("Initializing ThirdPartyClient...")
    await third_party_client.initialize()
    logger.info("ThirdPartyClient initialized.")

    try:
        logger.info("Initializing CaveClient...")
        await cave_client.initialize()
        logger.info("CaveClient initialized.")
    except Exception as e:
        logger.error(f"Error initializing CaveClient: {e}")

    # Store clients in app state
    app.state.db_client = db_client
    app.state.okx_client = okx_client
    app.state.third_party_client = third_party_client
    app.state.cave_client = cave_client
    app.state.wallet_service_client = wallet_service_client

    # Create connection manager
    app.state.connection_manager = MultiClientManager()

    logger.info("Server initialized successfully")

    yield  # This is where the app runs

    # Cleanup (if needed)
    logger.info("Server shutting down")


class EnhancedZerePyServer:
    def __init__(self, mongodb_url: str, database_name: str):
        # Initialize FastAPI app with lifespan
        self.app = FastAPI(title="ZerePy AI Trading Assistant", lifespan=lifespan)

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # In production, restrict to specific origins
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Set up routes
        self.setup_routes()

    def setup_routes(self):
        @self.app.websocket("/ws/{wallet_address}")
        async def websocket_endpoint(websocket: WebSocket, wallet_address: str):
            """WebSocket endpoint for client connections"""
            wallet_address = wallet_address.lower()  # Normalize wallet address

            # Get connection manager from app state
            connection_manager = self.app.state.connection_manager
            db_client = self.app.state.db_client

            # Connect client
            connection_info = await connection_manager.connect(wallet_address, websocket)

            # Get or create user
            user = await db_client.get_user(wallet_address)
            if not user:
                user = await db_client.create_user(wallet_address)

            # Create a dedicated agent for this user if not exists
            if not connection_manager.get_agent_for_user(wallet_address):
                cli = ZerePyCLI()
                # Load default agent
                cli._load_default_agent()
                connection_manager.set_agent_for_user(wallet_address, cli.agent)

            # Send welcome message
            welcome_message = MessageStructure.format_ai_response({
                "recommendation": "Welcome to ZerePy AI Trading Assistant! How can I help you today?"
            })
            await db_client.save_message(wallet_address, welcome_message)
            await connection_manager.send_message(wallet_address, welcome_message)

            try:
                # Message handling loop
                while True:
                    # Receive message from client
                    data = await websocket.receive_text()

                    try:
                        # Parse message data
                        message_data = json.loads(data)

                        # Save user message
                        if "query" in message_data:
                            query = message_data["query"]
                            user_message = {
                                "id": str(uuid4()),
                                "sender": "user",
                                "text": query,
                                "message_type": "normal",
                                "timestamp": datetime.now().isoformat()
                            }
                            await db_client.save_message(wallet_address, user_message)

                        # Let connection manager handle the message
                        await connection_manager.handle_client_message(wallet_address, message_data)

                    except json.JSONDecodeError:
                        await connection_manager.send_message(
                            wallet_address,
                            MessageStructure.format_error("Invalid message format. Expected JSON.")
                        )

            except WebSocketDisconnect:
                # Handle client disconnection
                connection_manager.disconnect(wallet_address)

            except Exception as e:
                logger.exception(f"Unexpected error in WebSocket connection: {e}")
                await connection_manager.send_message(
                    wallet_address,
                    MessageStructure.format_error(f"An unexpected error occurred: {str(e)}")
                )
                connection_manager.disconnect(wallet_address)

        @self.app.get("/api/user/{wallet_address}")
        async def get_user_info(wallet_address: str):
            """Get user information API endpoint"""
            wallet_address = wallet_address.lower()
            user = await self.app.state.db_client.get_user(wallet_address)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return user

        @self.app.get("/api/conversation/{wallet_address}")
        async def get_conversation(wallet_address: str):
            """Get conversation history API endpoint"""
            wallet_address = wallet_address.lower()
            history = await self.app.state.db_client.get_conversation_history(wallet_address)
            return {"messages": history}

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

        # Add more API routes here...
        @self.app.get("/api/get-cave-news")
        async def get_cave_news():
            """Get news from Cave API"""
            cave_client = self.app.state.cave_client
            res = cave_client.process_news_data(await cave_client.fetch_news_data())
            return res

        @self.app.get("/api/user-status")
        async def check_user_status(wallet_address: str):
            """檢查用戶狀態API端點"""
            wallet_address = wallet_address.lower()
            user = await self.app.state.db_client.get_user(wallet_address)
            if not user:
                return {"has_agent": False, "multisig_address": None}
            return {
                "has_agent": user.get("has_agent", False),
                "multisig_address": user.get("multisig_address")
            }

        # 2. Agent相關端點
        @self.app.post("/api/create-agent")
        async def create_agent_endpoint(data: dict):
            """創建新Agent API端點"""
            wallet_address = data.get("wallet_address")
            if not wallet_address:
                raise HTTPException(status_code=400, detail="wallet_address is required")

            wallet_address = wallet_address.lower()
            user = await self.app.state.db_client.get_user(wallet_address)

            if not user:
                user = await self.app.state.db_client.create_user(wallet_address)

            # 檢查用戶是否已有Agent
            if user.get("has_agent"):
                return {
                    "success": True,
                    "message": "Agent already exists",
                    "agent_id": user.get("agent_id")
                }

            # 創建Agent
            agent_id = str(uuid.uuid4())
            await self.app.state.db_client.db.users.update_one(
                {"wallet_address": wallet_address},
                {"$set": {
                    "agent_id": agent_id,
                    "has_agent": True,
                    "created_at": datetime.utcnow(),
                    "last_active": datetime.utcnow()
                }}
            )

            return {
                "success": True,
                "message": "Agent created successfully",
                "agent_id": agent_id
            }

        # @self.app.post("/api/agent")
        # async def create_agent_alt(wallet_address: str):
        #     """創建Agent的另一個端點 (兼容舊版)"""
        #     if not wallet_address:
        #         raise HTTPException(status_code=400, detail="wallet_address is required")
        #
        #     wallet_address = wallet_address.lower()
        #     user = await self.app.state.db_client.get_user(wallet_address)
        #
        #     if not user:
        #         await self.app.state.db_client.create_user(wallet_address)
        #
        #     await self.app.state.db_client.db.users.update_one(
        #         {"wallet_address": wallet_address},
        #         {"$set": {"has_agent": True}}
        #     )
        #
        #     return {"success": True, "message": "Agent created successfully."}

        @self.app.get("/api/agent-status/{wallet_address}")
        async def get_agent_status(wallet_address: str):
            """獲取Agent狀態API端點"""
            wallet_address = wallet_address.lower()
            user = await self.app.state.db_client.get_user(wallet_address)

            if user:
                return {
                    "has_agent": user.get("has_agent", False),
                    "multisig_address": user.get("multisig_address"),
                }
            else:
                return {"has_agent": False, "multisig_address": None}

        # 3. 錢包和交易相關端點
        @self.app.post("/api/wallet-register")
        async def wallet_register(data: dict):
            """註冊錢包地址"""
            wallet_address = data.get("ownerAddress")
            if not wallet_address:
                raise HTTPException(status_code=400, detail="ownerAddress is required")

            wallet_address = wallet_address.lower()

            try:
                # 嘗試使用錢包服務創建多簽錢包
                multisig_address = await self.app.state.wallet_service_client.create_multi_sig_wallet(
                    wallet_address)

                # 更新用戶記錄
                await self.app.state.db_client.db.users.update_one(
                    {"wallet_address": wallet_address},
                    {"$set": {"multisig_address": multisig_address}},
                    upsert=True
                )

                return {"success": True, "message": "Wallet registered successfully."}
            except Exception as e:
                logger.error(f"Error registering wallet: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to register wallet: {str(e)}")

        @self.app.post("/api/deploy-multisig-wallet")
        async def deploy_multisig_wallet(wallet_address: str, chain_id: int = 1):
            """部署多簽錢包"""
            wallet_address = wallet_address.lower()

            # 檢查用戶是否存在
            user = await self.app.state.db_client.get_user(wallet_address)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # 檢查用戶是否已有多簽錢包
            if user.get("multisig_address"):
                raise HTTPException(status_code=400, detail="Multisig wallet already deployed for this user")

            try:
                # 嘗試部署多簽錢包
                multisig_address = await self.app.state.wallet_service_client.create_multi_sig_wallet(
                    owner_address=wallet_address,
                    chain_id=chain_id
                )

                # 更新用戶記錄
                await self.app.state.db_client.db.users.update_one(
                    {"wallet_address": wallet_address},
                    {"$set": {"multisig_address": multisig_address}}
                )

                return {
                    "success": True,
                    "message": "Multisig wallet deployed successfully",
                    "multisig_address": multisig_address,
                }
            except Exception as e:
                logger.error(f"Error deploying multisig wallet: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to deploy multisig wallet: {str(e)}")

        @self.app.post("/api/get-multisig-wallets")
        async def get_multisig_wallets(wallet_address: str):
            """獲取用戶的多簽錢包"""
            wallet_address = wallet_address.lower()

            # 檢查用戶是否存在
            user = await self.app.state.db_client.get_user(wallet_address)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # 檢查用戶是否有多簽錢包
            multisig_address = user.get("multisig_address")
            if not multisig_address:
                raise HTTPException(status_code=404, detail="Multisig wallet not deployed for this user")

            return {"multisig_address": multisig_address}

        # 4. 資產和餘額相關端點
        @self.app.post("/api/total-balance")
        async def get_total_balance(data: dict):
            """獲取總餘額"""
            wallet_address = data.get("wallet_address")
            chain_id_list = data.get("chain_id_list")

            if not wallet_address:
                raise HTTPException(status_code=400, detail="wallet_address is required")

            try:
                return await self.app.state.okx_client.get_total_value_by_address(
                    wallet_address,
                    chain_id_list
                )
            except Exception as e:
                logger.error(f"Error getting total balance: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get total balance: {str(e)}")

        @self.app.post("/api/total-balance-detail")
        async def get_total_balance_detail(data: dict):
            """獲取詳細餘額信息"""
            wallet_address = data.get("wallet_address")
            chain_id_list = data.get("chain_id_list")

            if not wallet_address:
                raise HTTPException(status_code=400, detail="wallet_address is required")

            try:
                result = await self.app.state.okx_client.get_all_token_balances_by_address(
                    wallet_address,
                    chain_id_list,
                    filter_risk_tokens=True
                )

                if not result['data']:
                    return []

                return await self.app.state.okx_client.process_token_data(result)
            except Exception as e:
                logger.error(f"Error getting balance details: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get balance details: {str(e)}")

        @self.app.post("/api/wallet-transaction-history")
        async def get_wallet_transaction_history(data: dict):
            """獲取錢包交易歷史"""
            wallet_address = data.get("wallet_address")
            chain_id_list = data.get("chain_id_list")

            if not wallet_address:
                raise HTTPException(status_code=400, detail="wallet_address is required")

            try:
                result = await self.app.state.okx_client.get_transactions_by_address(
                    wallet_address,
                    chain_id_list
                )

                if not result['data']:
                    return []

                return await self.app.state.okx_client.process_transaction_data(result, wallet_address)
            except Exception as e:
                logger.error(f"Error getting transaction history: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get transaction history: {str(e)}")

        # 5. 消息相關端點
        @self.app.get("/api/messages")
        async def get_user_messages(wallet_address: str, show_history: bool = False):
            """獲取用戶消息"""
            wallet_address = wallet_address.lower()

            # 獲取對話歷史
            conversation = await self.app.state.db_client.db.conversations.find_one(
                {"wallet_address": wallet_address})

            if conversation and "messages" in conversation:
                messages = conversation["messages"]

                if show_history:
                    # 返回所有非"thinking"類型的消息
                    return {"messages": [msg for msg in messages if msg.get("message_type") != "thinking"]}
                else:
                    # 只返回最近的一條normal類型消息
                    for msg in reversed(messages):
                        if msg.get("message_type") == "normal":
                            return {"messages": [msg]}
                    return {"messages": []}

            return {"messages": []}

        @self.app.get("/api/public-data/tickers")
        async def get_tickers():
            """獲取行情數據"""
            try:
                tickers = await get_binance_tickers(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
                return {"tickers": tickers}
            except Exception as e:
                logger.error(f"Error fetching tickers: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch tickers: {str(e)}")
    async def process_user_message(self, wallet_address: str, query: str):
        """Process a user message and generate a response"""
        # Get services from app state
        connection_manager = self.app.state.connection_manager
        db_client = self.app.state.db_client

        # Mark agent as busy
        connection_manager.set_agent_busy(wallet_address, True)

        try:
            # Get user's agent
            agent = connection_manager.get_agent_for_user(wallet_address)
            if not agent:
                await connection_manager.send_message(
                    wallet_address,
                    MessageStructure.format_error("No agent available for this user.")
                )
                return

            # Send thinking status
            thinking_message = MessageStructure.format_status("Thinking...")
            await connection_manager.send_message(wallet_address, thinking_message)

            # Get conversation history for context
            history = await db_client.get_conversation_history(wallet_address)

            # Format history as context for the agent
            context = ""
            for msg in history[-5:]:  # Use last 5 messages for context
                if msg["sender"] == "user":
                    context += f"User: {msg['text']}\n"
                elif msg["sender"] == "ai":
                    context += f"Assistant: {msg['text']}\n"

            # Generate response using agent's LLM
            response = agent.prompt_llm(
                prompt=query,
                system_prompt=agent._construct_system_prompt() + f"\nConversation history:\n{context}"
            )

            # Format and send response
            ai_response = MessageStructure.format_ai_response({
                "recommendation": response
            })

            await db_client.save_message(wallet_address, ai_response)
            await connection_manager.send_message(wallet_address, ai_response)

        except Exception as e:
            logger.exception(f"Error processing message: {e}")

            # Send error message to client
            error_message = MessageStructure.format_error(f"Sorry, I encountered an error: {str(e)}")
            await db_client.save_message(wallet_address, error_message)
            await connection_manager.send_message(wallet_address, error_message)

        finally:
            # Mark agent as not busy
            connection_manager.set_agent_busy(wallet_address, False)


def create_enhanced_server():
    # Get MongoDB connection details from environment variables
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "zerepy_db")

    # Create and return server instance
    server = EnhancedZerePyServer(mongodb_url, database_name)
    return server.app