# src/server/run_enhanced_server.py

import uvicorn
import os
from dotenv import load_dotenv
from enhanced_server import create_enhanced_server

# Load environment variables
load_dotenv()

# Get port number from environment variable or use default
port = int(os.getenv("PORT", 8000))

# Get host from environment variable or use default
host = os.getenv("HOST", "0.0.0.0")

# Create the enhanced server
app = create_enhanced_server()

if __name__ == "__main__":
    print(f"Starting Enhanced ZerePy Server on {host}:{port}")
    uvicorn.run("run_enhanced_server:app", host=host, port=port, log_level="info")