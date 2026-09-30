import os
import json
import asyncio 
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from agent import CodeFlowAgent
from sandbox import SandboxExecutor

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CodeFlow Agent Backend", version="1.0.0")



agent = CodeFlowAgent()

sandbox = SandboxExecutor()

@app.get("/")
def health_check():
    return {"status": "ok", "service": "CodeFlow Agent Backend"}

@app.websocket("/ws/refactor")
async def websocket_refactor(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket client connected.")
    
    try:
        # 1. Receive initial code
        data_str = await websocket.receive_text()
        data = json.loads(data_str)
        legacy_code = data.get("code", "")

        # 2. Create queue for Human-in-the-loop actions
        action_queue = asyncio.Queue()

        # 3. Background task to listen for UI button clicks
        async def listen_for_actions():
            try:
                while True:
                    msg = await websocket.receive_text()
                    await action_queue.put(json.loads(msg))
            except WebSocketDisconnect:
                pass

        listener_task = asyncio.create_task(listen_for_actions())
        
        # 4. Run Agent
        agent = CodeFlowAgent(action_queue=action_queue)
        async for update in agent.run_correction_loop("", legacy_code):
            await websocket.send_json(update)
            if update.get("step") in ["shipped", "rejected"]:
                break

        listener_task.cancel()

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=True)
