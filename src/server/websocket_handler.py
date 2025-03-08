import json
import logging
import asyncio
from typing import Dict, List, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("server.websocket_handler")


class ConnectionManager:
    def __init__(self):
        # 儲存所有活躍連接: {wallet_address: [websocket, agent_name]}
        self.active_connections: Dict[str, List[Any]] = {}
        # 用於處理來自用戶的請求的回調函數
        self.message_handler = None

    async def connect(self, websocket: WebSocket, wallet_address: str, agent_name: str):
        """處理新的 WebSocket 連接"""
        await websocket.accept()
        self.active_connections[wallet_address] = [websocket, agent_name]
        logger.info(f"WebSocket connection established for wallet: {wallet_address}, agent: {agent_name}")

        # 發送歡迎消息
        await self.send_message(
            wallet_address,
            {"text": f"Welcome! Connected with agent: {agent_name}", "message_type": "status"}
        )

    async def disconnect(self, wallet_address: str):
        """處理 WebSocket 斷開連接"""
        if wallet_address in self.active_connections:
            del self.active_connections[wallet_address]
            logger.info(f"WebSocket connection closed for wallet: {wallet_address}")

    async def send_message(self, wallet_address: str, message: dict):
        """向特定錢包地址發送消息"""
        if wallet_address in self.active_connections:
            websocket = self.active_connections[wallet_address][0]
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {wallet_address}: {str(e)}")
                await self.disconnect(wallet_address)
        else:
            logger.warning(f"Attempted to send message to disconnected wallet: {wallet_address}")

    async def broadcast(self, message: dict):
        """向所有連接的客戶端廣播消息"""
        for wallet_address in list(self.active_connections.keys()):
            await self.send_message(wallet_address, message)

    async def handle_incoming_message(self, wallet_address: str, message_data: dict):
        """處理從客戶端接收到的消息"""
        if self.message_handler:
            # 通知用戶我們正在處理請求
            await self.send_message(
                wallet_address,
                {"text": "Processing your request...", "message_type": "thinking"}
            )

            try:
                # 獲取當前使用的 agent
                agent_name = self.active_connections[wallet_address][1]

                # 處理消息並獲取響應
                response = await self.message_handler(wallet_address, agent_name, message_data)

                # 發送響應給用戶
                await self.send_message(
                    wallet_address,
                    {"text": response, "message_type": "normal"}
                )
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await self.send_message(
                    wallet_address,
                    {"text": f"Error processing your request: {str(e)}", "message_type": "error"}
                )
        else:
            logger.warning("No message handler registered")
            await self.send_message(
                wallet_address,
                {"text": "Server is not configured to handle messages", "message_type": "error"}
            )

    def register_message_handler(self, handler):
        """註冊處理消息的回調函數"""
        self.message_handler = handler