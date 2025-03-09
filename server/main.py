import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4
from pathlib import Path

# --- Path Fix (Corrected) ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
# --- END Path Fix ---


from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import subprocess
from pydantic import BaseModel, Field
import uvicorn
from dotenv import load_dotenv, find_dotenv
import motor.motor_asyncio

# --- ZerePy Imports ---
from src.cli import ZerePyCLI
from backend.dex_api_client.wallet_service_client import WalletServiceClient  # type: ignore
from backend.dex_api_client.public_data import get_binance_tickers  # type: ignore

# --- Backend Imports ---
from backend.message_structure import MessageStructure  # type: ignore

# --- Load environment variables ---
load_dotenv(find_dotenv())

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Google Cloud Configuration ---
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
SERVICE_ACCOUNT_FILE = os.path.abspath("./gemini_defi_agent.json")
LOCATION = os.getenv("LOCATION", "us-central1")
MODEL = os.getenv("MODEL", "gemini-2.0-flash")

# --- API Keys ---
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Database Configuration ---
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "trading_assistant")

# OKX Web3 credentials (如果需要)
OKX_WEB3_PROJECT_ID = os.getenv("OKX_WEB3_PROJECT_ID")
OKX_WEB3_PROJECT_KEY = os.getenv("OKX_WEB3_PROJECT_KEY")
OKX_WEB3_PROJECT_SECRET = os.getenv("OKX_WEB3_PROJECT_SECRET")
OKX_WEB3_PROJECT_PASSWRD = os.getenv("OKX_WEB3_PROJECT_PASSWRD")

CAVE_API_KEY = os.getenv("CAVE_WEB3_PROJECT_API_KEY")

# --- Client Initializations (如果需要) ---
from backend.dex_api_client.okx_web3_client import OkxWeb3Client  # type: ignore
from backend.dex_api_client.third_client import ThirdPartyClient  # type: ignore
from backend.dex_api_client.cave_client import CaveClient  # type: ignore

okx_client_server: Optional[OkxWeb3Client] = None  # 使用 Optional
third_party_client_server: Optional[ThirdPartyClient] = None  # 使用 Optional
cave_client: Optional[CaveClient] = None  # 使用 Optional
wallet_service_client: Optional[WalletServiceClient] = None


# --- FastAPI Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global okx_client_server, third_party_client_server, db, cave_client, wallet_service_client
    try:
        await db.users.create_index("wallet_address", unique=True)
        await db.conversations.create_index("wallet_address")
        await db.multisig_whitelists.create_index("multisig_address")  # 如果需要
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating database indexes: {e}")

    # Initialize clients (如果需要)
    if OKX_WEB3_PROJECT_ID and OKX_WEB3_PROJECT_KEY and OKX_WEB3_PROJECT_SECRET and OKX_WEB3_PROJECT_PASSWRD:
        okx_client_server = OkxWeb3Client(
            project_id=OKX_WEB3_PROJECT_ID,
            api_key=OKX_WEB3_PROJECT_KEY,
            api_secret=OKX_WEB3_PROJECT_SECRET,
            api_passphrase=OKX_WEB3_PROJECT_PASSWRD,
        )
        await okx_client_server.initialize()
        logger.info("OKX client initialized successfully")

    if CAVE_API_KEY:
        cave_client = CaveClient(CAVE_API_KEY)
        await cave_client.initialize()
        logger.info("Cave client initialized successfully")

    third_party_client_server = ThirdPartyClient()
    await third_party_client_server.initialize()
    logger.info("Third-party client initialized successfully")

    wallet_service_client = WalletServiceClient()
    logger.info("Wallet service client initialized successfully")
    yield


# --- FastAPI App Setup ---
def get_git_version():
    try:
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            stderr=subprocess.STDOUT,
            text=True
        ).strip()
        return version
    except subprocess.CalledProcessError:
        return "0.0.0"


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Trading Assistant API",
        version=get_git_version(),
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI(title="Trading Assistant API", version="0.1", lifespan=lifespan)
app.openapi = custom_openapi

origins = [
    "https://gun-ai-wallet.onrender.com",
    "wss://gun-wallet-backend.zionpannel.com",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8026",
    "http://127.0.0.1:3000",
    "http://localhost:7788",
    "http://127.0.0.1:7788",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
news_db = client["crypto_news_db"]  # if needed


# --- Pydantic Models ---

class User(BaseModel):
    wallet_address: str
    created_at: datetime = Field(default_factory=datetime.now)
    has_agent: bool = False
    multisig_address: Optional[str] = None  # if needed


class Message(BaseModel):
    id: str
    sender: str
    text: Union[str, dict]  # Allow for text or structured data
    message_type: Optional[str] = None  # "normal", "thinking", "error", "status", "transaction"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    action: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),  # Serialize datetime objects
        }


class Conversation(BaseModel):
    wallet_address: str
    messages: List[Message] = []


# --- Helper Functions (Database) ---
def _serialize_for_mongo(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.dict()
    elif isinstance(data, list):
        return [_serialize_for_mongo(item) for item in data]
    elif isinstance(data, dict):
        return {key: _serialize_for_mongo(value) for key, value in data.items()}
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return data


def _deserialize_from_mongo(data: Any) -> Any:
    if isinstance(data, list):
        return [_deserialize_from_mongo(item) for item in data]
    elif isinstance(data, dict):
        return {key: _deserialize_from_mongo(value) for key, value in data.items()}
    elif isinstance(data, str):
        try:
            return datetime.fromisoformat(data)
        except ValueError:
            return data
    else:
        return data


async def get_user(wallet_address: str) -> Optional[Dict[str, Any]]:
    user = await db.users.find_one({"wallet_address": wallet_address})
    return _deserialize_from_mongo(user) if user else None


async def create_user(wallet_address: str) -> Dict[str, Any]:
    user = User(wallet_address=wallet_address)
    user_dict = _serialize_for_mongo(user)
    await db.users.insert_one(user_dict)
    return user_dict


async def set_has_agent(wallet_address: str, has_agent: bool) -> bool:
    result = await db.users.update_one(
        {"wallet_address": wallet_address},
        {"$set": {"has_agent": has_agent}}
    )
    return result.modified_count > 0


async def save_message(wallet_address: str, message_in: Dict[str, Any]) -> bool:
    message = _serialize_for_mongo(message_in)
    message["id"] = message.get("id", str(uuid4()))
    message["message_type"] = message.get("message_type", "normal")
    message["timestamp"] = message.get("timestamp", datetime.now().isoformat())

    if isinstance(message["timestamp"], datetime):
        message["timestamp"] = message["timestamp"].isoformat()

    result = await db.conversations.update_one(
        {"wallet_address": wallet_address},
        {"$push": {"messages": message}},
        upsert=True
    )
    return result.modified_count > 0 or result.upserted_id is not None


async def get_messages(wallet_address: str, show_history: bool = False) -> List[Dict[str, Any]]:
    conversation = await db.conversations.find_one({"wallet_address": wallet_address})
    if conversation and "messages" in conversation:
        messages = _deserialize_from_mongo(conversation["messages"])
        if show_history:
            return messages
        else:
            for msg in reversed(messages):
                if msg.get("message_type") == "normal":
                    return [msg]
            return []
    return []


async def get_previous_messages(wallet_address: str) -> List[Dict[str, Any]]:
    conversation = await db.conversations.find_one({"wallet_address": wallet_address})
    if conversation and "messages" in conversation:
        return [
            _deserialize_from_mongo(msg)
            for msg in conversation["messages"]
            if msg.get("message_type") != "status"
        ]
    return []


# --- Connection Manager  ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agent_instances: Dict[str, ZerePyCLI] = {}  # store Agent instances

    async def connect(self, wallet_address: str, websocket: WebSocket, agent_name: str):
        await websocket.accept()
        self.active_connections[wallet_address] = websocket

        # Create ZerePyCLI instance，and binding to wallet_address
        cli = ZerePyCLI()
        cli._load_agent(agent_name)  # load Agent following the agent_name
        self.agent_instances[wallet_address] = cli

        logger.info(f"WebSocket connection established for {wallet_address}")

    def disconnect(self, wallet_address: str):
        if wallet_address in self.active_connections:
            del self.active_connections[wallet_address]
            # 移除對應的 ZerePyCLI 實例
            if wallet_address in self.agent_instances:
                del self.agent_instances[wallet_address]
            logger.info(f"WebSocket connection closed for {wallet_address}")

    async def send_message(self, wallet_address: str, message: Dict[str, Any]):
        if wallet_address in self.active_connections:
            websocket = self.active_connections[wallet_address]
            try:
                await websocket.send_json(message)
                logger.debug(f"Message sent to {wallet_address}: {message.get('id', 'unknown')}")
            except Exception as e:
                logger.error(f"Error sending message to {wallet_address}: {e}")

    # 新增：獲取 Agent 實例
    def get_agent(self, wallet_address: str) -> Optional[ZerePyCLI]:
        return self.agent_instances.get(wallet_address)


manager = ConnectionManager()


# --- WebSocket Route ---

@app.websocket("/ws/{address}")
async def websocket_endpoint(websocket: WebSocket, address: str, agent_name: str = Query("StarterAgent")):
    wallet_address = address.lower()

    # 建立或獲取使用者
    user = await get_user(wallet_address)
    if not user:
        await create_user(wallet_address)
        await set_has_agent(wallet_address, True)  # 新使用者，設定 has_agent 為 True

    await manager.connect(wallet_address, websocket, agent_name)

    # 獲取 Agent 實例
    cli = manager.get_agent(wallet_address)
    if not cli:
        await websocket.close(code=1011, reason="Agent initialization failed.")
        return


    # 設定 update_callback
    async def update_callback(message: Dict[str, Any]):
        await manager.send_message(wallet_address, message)

    cli.set_update_callback(update_callback)

    try:
        welcome_message = MessageStructure.format_ai_response({"recommendation": "您好！我是您的 AI 交易助手。今天能為您做些什麼？"})
        await manager.send_message(wallet_address, welcome_message)
        await save_message(wallet_address, welcome_message)

        while True:
            data = await websocket.receive_text()
            logger.info(f"Received from {wallet_address}: {data}")

            try:
                data_json = json.loads(data)
                query = data_json.get("query")
                if not query:
                    raise ValueError("Missing 'query' field")
            except (json.JSONDecodeError, ValueError) as e:
                error_message = MessageStructure.format_error(str(e))
                await manager.send_message(wallet_address, error_message)
                await save_message(wallet_address, error_message)
                continue

            user_message = {
                "id": str(uuid4()),
                "sender": "user",
                "text": query,
                "message_type": "normal",
                "timestamp": datetime.now().isoformat()
            }
            await save_message(wallet_address, user_message)

            # 使用 cli 處理訊息
            asyncio.create_task(process_user_message(wallet_address, query, cli))

    except WebSocketDisconnect:
        manager.disconnect(wallet_address)
    except Exception as e:
        logger.exception(f"Error in WebSocket connection: {e}")
        error_message = MessageStructure.format_error(f"發生了意外錯誤：{e}")
        await manager.send_message(wallet_address, error_message)
        await save_message(wallet_address, error_message)
        manager.disconnect(wallet_address)


# --- Message Processing (修改後) ---
async def process_user_message(wallet_address: str, query: str, cli: ZerePyCLI):
    """Processes a user message, interacts with ZerePy, and sends updates."""
    try:
        # --- 1. Fetch Multisig Info (if not already present) ---
        if not cli.agent.multisig_info:
            multisig_info_result = cli.execute_custom_action("get_multisig_info", wallet_address=wallet_address)
            if isinstance(multisig_info_result, dict) and "error" not in multisig_info_result:
                cli.agent.set_multisig_info(multisig_info_result)
                await cli.agent.send_update(
                    MessageStructure.format_thinking(f"Retrieved multi-sig wallet info: {multisig_info_result}")
                )
            else:
                error_message = MessageStructure.format_error(
                    f"Failed to retrieve multi-sig wallet info: {multisig_info_result.get('error', 'Unknown error')}"
                )
                await cli.agent.send_update(error_message)
                return

        # --- 2. Prepare the Prompt ---
        system_prompt = """
        You are a helpful and reliable AI trading assistant that helps users manage their multi-signature wallets.
        You operate in phases to ensure accuracy and security.

        **Your Capabilities:**
        - You can use the following tools (via ZerePy):
            - `get_top5_tokens`: Get the top 5 trending tokens on a blockchain.
            - `discover_token_contract`: Find the contract address of a token.
            - `search_web`: Perform a web search.
            - `fetch_token_information`: Get detailed information about a specific token.
            - `store_transaction_context`: Store information about the current transaction.
            - `analyze_contract_security_with_api`: Check the security of a token contract.
            - `track_security_results`: Track the results of security analysis.
            - `analyze_portfolio_allocation`: Help with portfolio diversification.
            - `update_whitelist`: Add or remove tokens from a whitelist.
            - `approve_and_swap`: Perform a token swap (after approval).
            - `check-wallet-balance`: Check the user's wallet balance.
            - `create-multisig-transaction`: Create a multi-signature transaction (does not send).
            - `submit-multisig-transaction`: Submit a pre-signed multi-signature transaction.
            - `get-multisig-nonce`: Get the next nonce for a multi-signature wallet.
            - `gemini.generate-text`: Use the Gemini model to generate text. Use this for general reasoning.
            - You also have access to other connections set up in ZerePy, like different blockchains.

        - You *MUST* use available tools.  Do not make up information.
        - You *MUST* follow the reasoning process below strictly.

        **Reasoning Process:**

        1.  **Phase 1: Understanding and Planning**
            *   Analyze the user's request.
            *   Identify any ambiguities or missing information.  If any, *immediately* ask clarifying questions and stop.
            *   If the request is clear, break it down into main phases (high-level steps) and sub-phases (more detailed steps within each phase).
            *   For each phase and sub-phase, list the required tools.
            *   Output a JSON plan: `{"phases": [{"name": "Phase Name", "sub_phases": [{"name": "Sub-phase Name", "tools": ["tool1", "tool2"]}]}]}`

        2.  **Phase 2: Execution**
            *   For each phase and sub-phase in the plan:
                *   Formulate specific instructions for ZerePy, using the `execute_custom_action` function.
                *   Execute the instructions.
                *   Analyze the results.
                *   **Reflect:**
                    *   Was the action successful?
                    *   Are the results reasonable?
                    *   Are there any errors?
                *   If everything is correct, proceed to the next phase/sub-phase.
                *   If there is an error, describe the error, and then go back to Phase 1 to re-plan.

        3.  **Phase 3: Confirmation and Response**
            *   After all phases are complete, summarize the results.
            *   Present the response to the user.
            *   If a transaction was executed, include relevant details (transaction hash).

        **Important Notes:**

        *   Multi-signature wallets require two signatures: one from you (the AI agent) and one from the user.
        *   You will be responsible for creating and signing the transaction data.
        *   You will then send the *unsigned* transaction data to the user for their signature.
        *   Only after the user provides their signature can the transaction be submitted.
        """

        previous_messages = await get_previous_messages(wallet_address)
        previous_messages_text = "\n".join(
            [f"{msg['sender']}: {msg['text']}" for msg in previous_messages]
        )
        full_query = f"{previous_messages_text}\nUser: {query}"

        # --- 3. Phase 1: Understanding and Planning (Call Gemini) ---
        thinking_message = MessageStructure.format_thinking("Understanding your request and planning execution steps...")
        await cli.agent.send_update(thinking_message)

        try:
            initial_plan_str = cli.execute_custom_action(
                "generate-text-with-gemini",
                prompt=full_query,
                system_prompt=system_prompt,
            )
            logger.info(f"Initial plan from Gemini: {initial_plan_str}")

            try:
                initial_plan = json.loads(initial_plan_str)
            except json.JSONDecodeError:
                error_message = MessageStructure.format_error(
                    f"AI could not generate a valid execution plan (JSON parsing error). Original response: {initial_plan_str}"
                )
                await cli.agent.send_update(error_message)
                return

            # --- 4. Phase 2: 執行 (迭代) ---
            if "phases" in initial_plan:
                for phase in initial_plan["phases"]:
                    await cli.agent.send_update(
                        MessageStructure.format_thinking(f"Start Main Step：{phase['name']}"))
                    if "sub_phases" in phase:
                        for sub_phase in phase["sub_phases"]:
                            await cli.agent.send_update(
                                MessageStructure.format_thinking(f"Start Sub Step：{sub_phase['name']}"))
                            if "tools" in sub_phase:
                                for tool in sub_phase["tools"]:
                                    # --- 4.1 解析工具名稱 ---
                                    if "." in tool:
                                        connection_name, action_name = tool.split(".", 1)
                                    else:
                                        connection_name, action_name = None, tool

                                    params = {}

                                    # --- 4.2 根據工具名稱設定參數 ---
                                    if connection_name == "sonic":
                                        if action_name == "get-token-by-ticker":
                                            params["ticker"] = sub_phase.get("last_result", {}).get(
                                                "ticker") or initial_plan.get("ticker")
                                        elif action_name == "get-balance":
                                            params["address"] = cli.agent.multisig_info.get(
                                                "multisig_address") or initial_plan.get("address")
                                            params["token_address"] = sub_phase.get("last_result", {}).get(
                                                "token_address") or initial_plan.get("token_address")

                                    elif action_name == "check-wallet-balance":
                                        params["chain"] = cli.agent.multisig_info.get("chain") or initial_plan.get(
                                            "chain") or "ethereum"
                                        params["address"] = cli.agent.multisig_info.get(
                                            "multisig_address") or initial_plan.get("address")
                                        params["token_address"] = sub_phase.get("last_result", {}).get(
                                            "token_address") or initial_plan.get("token_address")
                                    elif action_name == "discover_token_contract":
                                        params["token_symbol"] = sub_phase.get("last_result", {}).get(
                                            "token_symbol") or initial_plan.get("token_symbol")
                                        params["blockchain"] = sub_phase.get("last_result", {}).get(
                                            "blockchain") or initial_plan.get("blockchain")
                                    elif action_name == "add-to-whitelist":
                                        params["address"] = sub_phase.get("last_result", {}).get(
                                            "address") or initial_plan.get("address")
                                    elif action_name == "create-multisig-transaction":
                                        params["to_address"] = sub_phase.get("last_result", {}).get(
                                            "to_address") or initial_plan.get("to_address")
                                        params["value"] = sub_phase.get("last_result", {}).get(
                                            "value") or initial_plan.get("value")
                                        params["data"] = sub_phase.get("last_result", {}).get(
                                            "data") or initial_plan.get("data")
                                    elif action_name == "get-multisig-nonce":
                                        pass
                                    elif action_name == "swap-tokens":
                                        params["chain"] = cli.agent.multisig_info.get("chain") or initial_plan.get(
                                            "chain")
                                        params["token_in"] = sub_phase.get("last_result", {}).get(
                                            "token_in") or initial_plan.get("token_in")
                                        params["token_out"] = sub_phase.get("last_result", {}).get(
                                            "token_out") or initial_plan.get("token_out")
                                        params["amount"] = sub_phase.get("last_result", {}).get(
                                            "amount") or initial_plan.get("amount")
                                        params["slippage"] = sub_phase.get("last_result", {}).get(
                                            "slippage") or initial_plan.get("slippage", 0.5)  # 預設值
                                    elif action_name == "get_multisig_info":
                                        pass

                                    # --- 4.3 執行動作 ---
                                    try:
                                        if connection_name:
                                            # 連接動作
                                            result = await asyncio.wait_for(
                                                cli.agent.perform_action(connection_name, action_name,
                                                                         list(params.values())),
                                                timeout=30  # 設定超時時間 (例如 30 秒)
                                            )
                                        else:
                                            # 自訂動作
                                            result = await asyncio.wait_for(
                                                cli.execute_custom_action(action_name, **params),
                                                timeout=30  # 設定超時時間
                                            )

                                        await cli.agent.send_update(
                                            MessageStructure.format_thinking(f"Tool: `{tool}` Result: {result}")
                                        )

                                        # --- 4.4 儲存結果 (重要) ---
                                        sub_phase["last_result"] = result  # 將結果儲存在 sub_phase 中

                                    except asyncio.TimeoutError:
                                        logger.error(f"Action {action_name} timed out!")
                                        await cli.agent.send_update(
                                            MessageStructure.format_error(f"Execution of tool `{tool}` timed out."))
                                        break  # 加上break

                                    except Exception as e:
                                        await cli.agent.send_update(
                                            MessageStructure.format_error(f"Execute `{tool}` error occurred：{e}")
                                        )
                                        break  # 發生錯誤時，退出目前工具的執行，並中斷迴圈

            # --- Phase 3: Confirmation and Response ---
            await cli.agent.send_update(MessageStructure.format_ai_response({"recommendation": "Task completed (simplified)"}))

        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            error_message = MessageStructure.format_error(f"An error occurred while processing message: {str(e)}")
            await cli.agent.send_update(error_message)

    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        error_message = MessageStructure.format_error(f"An error occurred: {str(e)}")
        await save_message(wallet_address, error_message)
        await manager.send_message(wallet_address, error_message)


# --- API Routes (RESTful, Optional) ---

@app.get("/")
async def root():
    return {"status": "running"}


@app.get("/agents")
async def list_agents():
    try:
        agents = []
        agents_dir = Path("../src/server/agents")
        if agents_dir.exists():
            for agent_file in agents_dir.glob("*.json"):
                if agent_file.stem != "general":
                    agents.append(agent_file.stem)
        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 快速測試用的 Client (使用 requests)
if __name__ == "__main__":
    # 使用 uvicorn 啟動 FastAPI 服務
    uvicorn.run("server.main:app", host="0.0.0.0", port=7788, reload=True)
