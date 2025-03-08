# test_client.py (一個簡單的 WebSocket 客戶端)

import asyncio
import websockets
import json

async def test_websocket_client(wallet_address: str, agent_name: str = "StarterAgent"):
    uri = f"ws://localhost:7788/ws/{wallet_address}?agent_name={agent_name}"  # 包含 agent_name
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")

        # 發送第一條訊息
        await websocket.send(json.dumps({"query": "你好"}))

        while True:
            try:
                response = await websocket.recv()
                print(f"Received: {response}")

                # 模擬使用者輸入 (您可以根據需要修改)
                message = input("Enter your message (or 'exit' to quit): ")
                if message.lower() == 'exit':
                    break
                await websocket.send(json.dumps({"query": message}))

            except websockets.exceptions.ConnectionClosedOK:
                print("Connection closed.")
                break

if __name__ == "__main__":
    wallet_address = "0xYourWalletAddress"  # 換成您的錢包地址
    asyncio.run(test_websocket_client(wallet_address))