#!/usr/bin/env python3
"""
VDOT Web Proxy – WebSocket tunnel + built-in web interface.
Guaranteed HTTP response.
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

# Load HTML once at startup
try:
    with open("index.html", "r", encoding="utf-8") as f:
        INDEX_HTML = f.read().encode("utf-8")
except Exception as e:
    logger.error(f"Cannot read index.html: {e}")
    INDEX_HTML = b"<html><body><h1>Error loading page</h1></body></html>"

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
                # Remove problematic headers
                for h in ["Host", "Connection", "Transfer-Encoding", "Upgrade"]:
                    headers.pop(h, None)
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.request(method, url, headers=headers, content=body)
                    # Simplify: always return text (for web pages)
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
    """Serve index.html for any non-WebSocket HTTP request."""
    logger.info(f"HTTP request: {request.path}")
    if request.path == WS_PATH:
        return None  # WebSocket upgrade
    try:
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": str(len(INDEX_HTML)),
            "Connection": "close"
        }
        return (200, headers, INDEX_HTML)
    except Exception as e:
        logger.error(f"process_request error: {e}")
        return (500, {}, b"Internal Server Error")

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
