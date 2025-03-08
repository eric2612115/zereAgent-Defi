# src/server/multi_client_handler.py

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, List
from uuid import uuid4
from datetime import datetime, timedelta
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("multi_client_handler")


class MultiClientManager:
    """Manages multiple client WebSocket connections with isolated session states"""

    def __init__(self, ping_interval: int = 30):
        # Store active connections by wallet address
        self.active_connections: Dict[str, WebSocket] = {}
        # Store session data for each user
        self.user_sessions: Dict[str, Dict[str, Any]] = {}
        # Store agents for each user
        self.user_agents: Dict[str, Any] = {}
        # Store message handlers
        self.message_handlers: List[Callable] = []
        # Ping interval in seconds
        self.ping_interval = ping_interval
        # Background ping task
        self.ping_task = None

    async def connect(self, wallet_address: str, websocket: WebSocket):
        """Accept a new WebSocket connection and store it"""
        await websocket.accept()
        self.active_connections[wallet_address] = websocket

        # Initialize session data if not exists
        if wallet_address not in self.user_sessions:
            self.user_sessions[wallet_address] = {
                "last_message_time": datetime.now(),
                "reconnect_count": 0,
                "conversation_history": [],
                "agent_busy": False
            }
        else:
            # Update reconnect stats
            self.user_sessions[wallet_address]["reconnect_count"] += 1
            self.user_sessions[wallet_address]["last_message_time"] = datetime.now()

        logger.info(f"WebSocket connection established for wallet: {wallet_address}")

        # Start ping task if not already running
        if self.ping_task is None or self.ping_task.done():
            self.ping_task = asyncio.create_task(self._ping_clients())

        # Return success message
        return {
            "status": "connected",
            "wallet_address": wallet_address,
            "session_id": str(uuid4()),
            "timestamp": datetime.now().isoformat()
        }

    def disconnect(self, wallet_address: str):
        """Handle client disconnection"""
        if wallet_address in self.active_connections:
            del self.active_connections[wallet_address]

            # Update session data
            if wallet_address in self.user_sessions:
                self.user_sessions[wallet_address]["last_disconnect_time"] = datetime.now()
                self.user_sessions[wallet_address]["agent_busy"] = False

            logger.info(f"WebSocket connection closed for wallet: {wallet_address}")

        # If no active connections, cancel ping task
        if not self.active_connections and self.ping_task and not self.ping_task.done():
            self.ping_task.cancel()
            self.ping_task = None

    async def send_message(self, wallet_address: str, message: Dict[str, Any]):
        """Send a message to a specific client"""
        if wallet_address in self.active_connections:
            websocket = self.active_connections[wallet_address]
            try:
                await websocket.send_json(message)
                logger.debug(f"Message sent to {wallet_address}: {message.get('id', 'unknown')}")

                # Update last activity time
                if wallet_address in self.user_sessions:
                    self.user_sessions[wallet_address]["last_message_time"] = datetime.now()

                return True
            except Exception as e:
                logger.error(f"Error sending message to {wallet_address}: {e}")
                # Connection might be broken, clean up
                self.disconnect(wallet_address)
                return False
        else:
            logger.warning(f"Attempted to send message to disconnected client: {wallet_address}")
            return False

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected clients"""
        disconnected_clients = []

        for wallet_address in self.active_connections:
            success = await self.send_message(wallet_address, message)
            if not success:
                disconnected_clients.append(wallet_address)

        # Clean up any clients that failed to receive message
        for wallet_address in disconnected_clients:
            self.disconnect(wallet_address)

    def set_agent_busy(self, wallet_address: str, busy: bool):
        """Set whether a client's agent is busy processing a request"""
        if wallet_address in self.user_sessions:
            self.user_sessions[wallet_address]["agent_busy"] = busy
            logger.info(f"Agent for {wallet_address} set to {'busy' if busy else 'available'}")

    def is_agent_busy(self, wallet_address: str) -> bool:
        """Check if a client's agent is busy"""
        if wallet_address in self.user_sessions:
            return self.user_sessions[wallet_address]["agent_busy"]
        return False

    def get_agent_for_user(self, wallet_address: str):
        """Get the agent instance for a specific user"""
        return self.user_agents.get(wallet_address)

    def set_agent_for_user(self, wallet_address: str, agent):
        """Set the agent instance for a specific user"""
        self.user_agents[wallet_address] = agent
        logger.info(f"Agent set for user {wallet_address}")

    def register_message_handler(self, handler: Callable):
        """Register a function to handle incoming messages"""
        self.message_handlers.append(handler)
        logger.info(f"Registered message handler: {handler.__name__}")

    async def handle_client_message(self, wallet_address: str, message_data: Any):
        """Process an incoming client message using registered handlers"""
        if not self.message_handlers:
            logger.warning("No message handlers registered")
            return {"error": "No message handlers configured"}

        # Update last activity time
        if wallet_address in self.user_sessions:
            self.user_sessions[wallet_address]["last_message_time"] = datetime.now()

        # Call all registered handlers
        results = []
        for handler in self.message_handlers:
            try:
                result = await handler(wallet_address, message_data)
                results.append(result)
            except Exception as e:
                logger.error(f"Error in message handler {handler.__name__}: {e}")
                results.append({"error": str(e)})

        return results[0] if results else {"error": "Message processing failed"}

    async def _ping_clients(self):
        """Periodically ping clients to keep connections alive and detect disconnections"""
        try:
            while True:
                if not self.active_connections:
                    await asyncio.sleep(self.ping_interval)
                    continue

                logger.debug(f"Pinging {len(self.active_connections)} active clients")
                disconnected_clients = []

                for wallet_address, websocket in self.active_connections.items():
                    try:
                        # Send ping message
                        ping_message = {
                            "id": str(uuid4()),
                            "type": "ping",
                            "timestamp": datetime.now().isoformat()
                        }
                        await websocket.send_json(ping_message)

                        # Check for inactive sessions (no messages for a long time)
                        if wallet_address in self.user_sessions:
                            last_time = self.user_sessions[wallet_address]["last_message_time"]
                            if datetime.now() - last_time > timedelta(minutes=30):  # 30 min timeout
                                logger.info(f"Session timeout for {wallet_address} - no activity for 30 minutes")
                                disconnected_clients.append(wallet_address)

                    except Exception as e:
                        logger.warning(f"Client {wallet_address} disconnected: {e}")
                        disconnected_clients.append(wallet_address)

                # Clean up disconnected clients
                for wallet_address in disconnected_clients:
                    self.disconnect(wallet_address)

                await asyncio.sleep(self.ping_interval)

        except asyncio.CancelledError:
            logger.info("Ping task cancelled")
        except Exception as e:
            logger.error(f"Error in ping task: {e}")