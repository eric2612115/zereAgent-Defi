import json

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi import WebSocket, WebSocketDisconnect, Query
from .websocket_handler import ConnectionManager
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import asyncio
import signal
import threading
from pathlib import Path
from src.cli import ZerePyCLI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server/app")

class ActionRequest(BaseModel):
    """Request model for agent actions"""
    connection: str
    action: str
    params: Optional[List[str]] = []

class ConfigureRequest(BaseModel):
    """Request model for configuring connections"""
    connection: str
    params: Optional[Dict[str, Any]] = {}

class ServerState:
    """Simple state management for the server"""
    def __init__(self):
        self.cli = ZerePyCLI()
        self.agent_running = False
        self.agent_task = None
        self._stop_event = threading.Event()

    def _run_agent_loop(self):
        """Run agent loop in a separate thread"""
        try:
            log_once = False
            while not self._stop_event.is_set():
                if self.cli.agent:
                    try:
                        if not log_once:
                            logger.info("Loop logic not implemented")
                            log_once = True

                    except Exception as e:
                        logger.error(f"Error in agent action: {e}")
                        if self._stop_event.wait(timeout=30):
                            break
        except Exception as e:
            logger.error(f"Error in agent loop thread: {e}")
        finally:
            self.agent_running = False
            logger.info("Agent loop stopped")

    async def start_agent_loop(self):
        """Start the agent loop in background thread"""
        if not self.cli.agent:
            raise ValueError("No agent loaded")
        
        if self.agent_running:
            raise ValueError("Agent already running")

        self.agent_running = True
        self._stop_event.clear()
        self.agent_task = threading.Thread(target=self._run_agent_loop)
        self.agent_task.start()

    async def stop_agent_loop(self):
        """Stop the agent loop"""
        if self.agent_running:
            self._stop_event.set()
            if self.agent_task:
                self.agent_task.join(timeout=5)
            self.agent_running = False

class ZerePyServer:
    def __init__(self):
        self.app = FastAPI(title="ZerePy Server")
        self.state = ServerState()
        self.setup_routes()

        self.connection_manager = ConnectionManager()
        self.connection_manager.register_message_handler(self.handle_websocket_message)

    async def handle_websocket_message(self, wallet_address: str, agent_name: str, message_data: dict):
        """處理從 WebSocket 接收到的消息，並使用 agent 生成響應"""
        query = message_data.get("query", "")

        # 確保加載了正確的代理
        try:
            if not self.state.cli.agent or self.state.cli.agent.name != agent_name:
                self.state.cli._load_agent_from_file(agent_name)
                logger.info(f"Loaded agent: {agent_name}")
        except Exception as e:
            return f"Error loading agent {agent_name}: {str(e)}"

        try:
            # 直接指定使用 Anthropic
            provider = "anthropic"

            # 檢查 Anthropic 是否已配置
            if provider not in self.state.cli.agent.connection_manager.connections:
                logger.error(f"Provider '{provider}' not found in available connections")
                return f"Provider '{provider}' not found. Please check agent configuration."

            connection = self.state.cli.agent.connection_manager.connections[provider]
            if not connection.is_configured():
                logger.error(f"Provider '{provider}' is not configured")
                return f"Provider '{provider}' is not configured. Please check .env file."

            # 生成系統提示
            system_prompt = self.state.cli.agent._construct_system_prompt()

            # 執行 generate-text 動作
            result = self.state.cli.agent.connection_manager.perform_action(
                connection_name=provider,
                action_name="generate-text",
                params=[query, system_prompt]
            )

            return result
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return f"Error generating response: {str(e)}"

    def setup_routes(self):

        @self.app.websocket("/ws/{wallet_address}")
        async def websocket_endpoint(
                websocket: WebSocket,
                wallet_address: str,
                agent_name: str = Query(default="StarterAgent")
        ):
            """WebSocket 端點處理連接和消息"""
            await self.connection_manager.connect(websocket, wallet_address, agent_name)

            try:
                while True:
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    await self.connection_manager.handle_incoming_message(wallet_address, message_data)
            except WebSocketDisconnect:
                await self.connection_manager.disconnect(wallet_address)
            except Exception as e:
                logger.error(f"WebSocket error: {str(e)}")
                await self.connection_manager.send_message(
                    wallet_address,
                    {"text": f"Server error: {str(e)}", "message_type": "error"}
                )
                await self.connection_manager.disconnect(wallet_address)

        # 在 ZerePyServer 類中添加新方法

        @self.app.get("/")
        async def root():
            """Server status endpoint"""
            return {
                "status": "running",
                "agent": self.state.cli.agent.name if self.state.cli.agent else None,
                "agent_running": self.state.agent_running
            }

        @self.app.get("/agents")
        async def list_agents():
            """List available agents"""
            try:
                agents = []
                agents_dir = Path("agents")
                if agents_dir.exists():
                    for agent_file in agents_dir.glob("*.json"):
                        if agent_file.stem != "general":
                            agents.append(agent_file.stem)
                return {"agents": agents}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/agents/{name}/load")
        async def load_agent(name: str):
            """Load a specific agent"""
            try:
                self.state.cli._load_agent_from_file(name)
                return {
                    "status": "success",
                    "agent": name
                }
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get("/connections")
        async def list_connections():
            """List all available connections"""
            if not self.state.cli.agent:
                raise HTTPException(status_code=400, detail="No agent loaded")
            
            try:
                connections = {}
                for name, conn in self.state.cli.agent.connection_manager.connections.items():
                    connections[name] = {
                        "configured": conn.is_configured(),
                        "is_llm_provider": conn.is_llm_provider
                    }
                return {"connections": connections}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/agent/action")
        async def agent_action(action_request: ActionRequest):
            """Execute a single agent action"""
            if not self.state.cli.agent:
                raise HTTPException(status_code=400, detail="No agent loaded")
            
            try:
                result = await asyncio.to_thread(
                    self.state.cli.agent.perform_action,
                    connection=action_request.connection,
                    action=action_request.action,
                    params=action_request.params
                )
                return {"status": "success", "result": result}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.post("/agent/start")
        async def start_agent():
            """Start the agent loop"""
            if not self.state.cli.agent:
                raise HTTPException(status_code=400, detail="No agent loaded")
            
            try:
                await self.state.start_agent_loop()
                return {"status": "success", "message": "Agent loop started"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.post("/agent/stop")
        async def stop_agent():
            """Stop the agent loop"""
            try:
                await self.state.stop_agent_loop()
                return {"status": "success", "message": "Agent loop stopped"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.post("/connections/{name}/configure")
        async def configure_connection(name: str, config: ConfigureRequest):
            """Configure a specific connection"""
            if not self.state.cli.agent:
                raise HTTPException(status_code=400, detail="No agent loaded")
            
            try:
                connection = self.state.cli.agent.connection_manager.connections.get(name)
                if not connection:
                    raise HTTPException(status_code=404, detail=f"Connection {name} not found")
                
                success = connection.configure(**config.params)
                if success:
                    return {"status": "success", "message": f"Connection {name} configured successfully"}
                else:
                    raise HTTPException(status_code=400, detail=f"Failed to configure {name}")
                    
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/connections/{name}/status")
        async def connection_status(name: str):
            """Get configuration status of a connection"""
            if not self.state.cli.agent:
                raise HTTPException(status_code=400, detail="No agent loaded")
                
            try:
                connection = self.state.cli.agent.connection_manager.connections.get(name)
                if not connection:
                    raise HTTPException(status_code=404, detail=f"Connection {name} not found")
                    
                return {
                    "name": name,
                    "configured": connection.is_configured(verbose=True),
                    "is_llm_provider": connection.is_llm_provider
                }
                
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

def create_app():
    server = ZerePyServer()
    return server.app