#!/usr/bin/env python3
"""
VDOT Web Proxy – WebSocket tunnel + web interface.
Uses send_response / send for reliable HTTP delivery.
"""
import asyncio
import json
import logging
import os
import sys
import traceback
import websockets
from websockets.exceptions import ConnectionClosed
import httpx

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("vdot-web")

PORT = int(os.environ.get("PORT", "8080"))
WS_PATH = "/ws"

# Load HTML page
try:
    with open("index.html", "rb") as f:
        INDEX_HTML = f.read()
except Exception as e:
    logger.error(f"Cannot read index.html: {e}")
    INDEX_HTML = b"<html><body><h1>Error</h1></body></html>"

async def handle_ws(websocket, path):
    if path != WS_PATH:
        await websocket.close(1008, "Invalid path")
        return
    logger.info("WebSocket client connected")
    try:
        async for message in websocket:
            try:
                req = json.loads(message)
                url = req.get("url")
                if not url:
                    await websocket.send(json.dumps({"error": "No URL"}))
                    continue
                method = req.get("method", "GET")
                headers = req.get("headers", {})
                body = req.get("body")
                for h in ["Host", "Connection", "Transfer-Encoding", "Upgrade"]:
                    headers.pop(h, None)
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.request(method, url, headers=headers, content=body)
                    try:
                        text = resp.text
                    except Exception:
                        text = ""
                    await websocket.send(json.dumps({
                        "status": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": text
                    }))
            except Exception as e:
                logger.error(f"Request error: {e}\n{traceback.format_exc()}")
                try:
                    await websocket.send(json.dumps({"error": str(e)}))
                except Exception:
                    break
    except ConnectionClosed:
        logger.info("WebSocket closed")

async def process_request(connection, request):
    """Manually send HTTP response using send_response / send."""
    logger.info(f"HTTP request: {request.path}")
    if request.path == WS_PATH:
        return None  # let websockets upgrade

    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": str(len(INDEX_HTML)),
        "Connection": "close"
    }
    try:
        # send_response is async in websockets >= 12.0
        await connection.send_response(200, "OK", headers)
        await connection.send(INDEX_HTML)
        # After sending, we tell websockets not to send anything else
        return None
    except Exception as e:
        logger.error(f"Failed to send response: {e}")
        await connection.close(1011, "Internal error")
        return None

async def main():
    logger.info(f"Starting on port {PORT}")
    async with websockets.serve(
        handle_ws,
        "0.0.0.0",
        PORT,
        process_request=process_request
    ):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
