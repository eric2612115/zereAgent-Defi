# enhanced_server.py
import asyncio
import json
import logging
import os
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

# Ensure tool modules are imported and registered
try:
    import src.custom_actions.phase_tools
    import src.custom_actions.trading_tools
    import src.custom_actions.api_tools
    import src.actions.my_tools
except ImportError as e:
    logging.warning(f"Could not import some tool modules: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("enhanced_server")


# Message structure helper
class MessageStructure:
    @staticmethod
    def format_message(sender: str, text: str, message_type: str = "normal") -> Dict[str, Any]:
        """
        格式化一般訊息。
        """
        return {
            "id": str(uuid4()),
            "sender": sender,
            "text": text,
            "message_type": message_type,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def format_thinking(text: str) -> Dict[str, Any]:
        """
        格式化 AI 思考中的訊息。
        """
        return MessageStructure.format_message("system", text, "thinking")

    @staticmethod
    def format_status(text: str) -> Dict[str, Any]:
        """
        格式化狀態更新訊息。
        """
        return MessageStructure.format_message("system", text, "status")

    @staticmethod
    def format_error(text: str) -> Dict[str, Any]:
        """
        格式化錯誤訊息。
        """
        return MessageStructure.format_message("system", text, "error")

    @staticmethod
    def format_ai_response(content: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化 AI 的最終回覆 (可以是文字或結構化資料)。
        重要：確保 text 字段是一個字符串。
        """
        text = content.get("recommendation", "")
        if isinstance(text, dict):
            text = json.dumps(text)  # 如果是字典，轉成JSON字符串
        return {
            "id": str(uuid4()),
            "sender": "agent",
            "text": text,
            "message_type": content.get("message_type", "normal"),
            "timestamp": datetime.now().isoformat()
        }


# Define FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    async def process_user_message(wallet_address: str, message_data: dict):
        """處理用戶消息並生成回應"""
        query = message_data.get("query", "")
        if not query:
            return "Please provide a query."

        # 獲取應用狀態中的服務
        connection_manager = app.state.connection_manager
        db_client = app.state.db_client
        cli = app.state.cli

        # 將 agent 設置為忙碌狀態
        connection_manager.set_agent_busy(wallet_address, True)

        try:
            # 獲取用戶的 agent
            agent = connection_manager.get_agent_for_user(wallet_address)
            if not agent:
                await connection_manager.send_message(
                    wallet_address,
                    MessageStructure.format_error("No agent available for this user.")
                )
                return

            # 發送思考中狀態
            thinking_message = MessageStructure.format_thinking("Thinking...")
            await connection_manager.send_message(wallet_address, thinking_message)

            # 使用 agent 的 LLM 生成回應
            try:
                # 檢查是否有 anthropic 連接
                if "anthropic" not in agent.connection_manager.connections:
                    logger.error("No anthropic connection found")
                    error_message = MessageStructure.format_error(
                        "No anthropic connection found. Please check agent configuration.")
                    await db_client.save_message(wallet_address, error_message)
                    await connection_manager.send_message(wallet_address, error_message)
                    return "Error: No anthropic connection found."

                # 獲取連接
                connection = agent.connection_manager.connections["anthropic"]

                # 檢查是否已配置
                if not connection.is_configured():
                    logger.error("Anthropic connection is not configured")
                    error_message = MessageStructure.format_error(
                        "Anthropic connection is not configured. Please check .env file.")
                    await db_client.save_message(wallet_address, error_message)
                    await connection_manager.send_message(wallet_address, error_message)
                    return "Error: Anthropic connection is not configured."

                # 生成系統提示
                system_prompt = agent._construct_system_prompt()

                # 使用 generate-text-with-tools 動作
                result = agent.connection_manager.perform_action(
                    connection_name="anthropic",
                    action_name="generate-text",
                    params=[query, system_prompt]
                )

                # 格式化並發送回應
                ai_response = MessageStructure.format_message("agent", result)

                await db_client.save_message(wallet_address, ai_response)
                await connection_manager.send_message(wallet_address, ai_response)

                return result

            except Exception as e:
                logger.exception(f"Error generating response: {e}")
                error_message = MessageStructure.format_error(f"Error generating response: {str(e)}")
                await db_client.save_message(wallet_address, error_message)
                await connection_manager.send_message(wallet_address, error_message)
                return f"Error generating response: {str(e)}"

        except Exception as e:
            logger.exception(f"Error processing message: {e}")

            # 發送錯誤消息給客戶端
            error_message = MessageStructure.format_error(f"Sorry, I encountered an error: {str(e)}")
            await db_client.save_message(wallet_address, error_message)
            await connection_manager.send_message(wallet_address, error_message)

            return f"Error: {str(e)}"

        finally:
            # 將 agent 設置為非忙碌狀態
            connection_manager.set_agent_busy(wallet_address, False)

    # Database client
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "zerepy_db")
    db_client = MongoDBClient(mongodb_url, database_name)

    # Initialize DB indexes
    await db_client.initialize_indexes()

    # Initialize CLI
    cli = ZerePyCLI()

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
    app.state.cli = cli
    app.state.okx_client = okx_client
    app.state.third_party_client = third_party_client
    app.state.cave_client = cave_client
    app.state.wallet_service_client = wallet_service_client

    # Create connection manager
    app.state.connection_manager = MultiClientManager()

    # 註冊消息處理器
    app.state.connection_manager.register_message_handler(process_user_message)

    logger.info("Server initialized successfully")

    yield  # This is where the app runs

    # Cleanup (if needed)
    logger.info("Server shutting down")

    # Close any open client sessions
    try:
        await okx_client.close()
        await third_party_client.close()
        await cave_client.close()
        await wallet_service_client.close()
    except Exception as e:
        logger.error(f"Error closing client sessions: {e}")


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
        async def websocket_endpoint(websocket: WebSocket, wallet_address: str,
                                     agent_name: str = Query(default="StarterAgent")):
            """WebSocket endpoint for client connections"""
            wallet_address = wallet_address.lower()  # Normalize wallet address

            # Get connection manager from app state
            connection_manager = self.app.state.connection_manager
            db_client = self.app.state.db_client
            cli = self.app.state.cli

            # Connect client
            await connection_manager.connect(wallet_address, websocket)

            # Get or create user
            user = await db_client.get_user(wallet_address)
            if not user:
                await db_client.create_user(wallet_address)

            # Create a dedicated agent for this user if not exists
            if not connection_manager.get_agent_for_user(wallet_address):
                # Load specified agent
                try:
                    cli._load_agent_from_file(agent_name)
                    connection_manager.set_agent_for_user(wallet_address, cli.agent)
                except Exception as e:
                    logger.error(f"Error loading agent {agent_name}: {e}")
                    await connection_manager.send_message(
                        wallet_address,
                        MessageStructure.format_error(f"Error loading agent {agent_name}: {str(e)}")
                    )
                    connection_manager.disconnect(wallet_address)
                    return

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
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "agent_count": len(self.app.state.connection_manager.user_agents)
            }

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
            agent_id = str(uuid4())
            await self.app.state.db_client.db.users.update_one(
                {"wallet_address": wallet_address},
                {"$set": {
                    "agent_id": agent_id,
                    "has_agent": True,
                    "created_at": datetime.now(),
                    "last_active": datetime.now()
                }}
            )

            return {
                "success": True,
                "message": "Agent created successfully",
                "agent_id": agent_id
            }

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

        @self.app.get("/api/tools")
        async def get_available_tools():
            """Get list of available tools"""
            from src.action_handler import action_registry

            tools = []
            for tool_name, tool_func in action_registry.items():
                # Skip internal/system tools that shouldn't be exposed directly
                if tool_name.startswith("_"):
                    continue

                # Get the docstring for the tool
                doc = tool_func.__doc__ or "No description available."
                doc = doc.strip()

                # Add tool to list
                tools.append({
                    "name": tool_name,
                    "description": doc
                })

            return {"tools": tools}


def create_app():
    # Get MongoDB connection details from environment variables
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "zerepy_db")

    # Create and return server instance
    server = EnhancedZerePyServer(mongodb_url, database_name)
    return server.app