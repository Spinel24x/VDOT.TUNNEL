#!/usr/bin/env python3
"""
VDOT Web Proxy – WebSocket tunnel with web browser interface.
Deploy on Railway.
"""
import asyncio
import json
import logging
import os
import sys
import websockets
from websockets.exceptions import ConnectionClosed
import httpx

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("vdot-web")

PORT = int(os.environ.get("PORT", "8080"))
WS_PATH = "/ws"

# Load the HTML page into memory
with open("index.html", "r", encoding="utf-8") as f:
    INDEX_HTML = f.read().encode("utf-8")

async def handle_ws(websocket, path):
    """Handle WebSocket requests: receive JSON, fetch URL, return response."""
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
                    await websocket.send(json.dumps({"error": "No URL provided"}))
                    continue
                method = req.get("method", "GET")
                headers = req.get("headers", {})
                body = req.get("body", None)

                # Clean headers that might cause issues
                for h in ["Host", "Connection", "Transfer-Encoding", "Upgrade"]:
                    headers.pop(h, None)

                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.request(method, url, headers=headers, content=body)
                    # We return only text-based content (HTML, CSS, JS, etc.)
                    # For full proxy you'd need to handle binary, but for a simple web browser this works.
                    content_type = resp.headers.get("content-type", "")
                    if "text" in content_type or "javascript" in content_type or "json" in content_type:
                        resp_body = resp.text
                    else:
                        # For images etc. we can base64 encode, but let's keep it simple: return an empty body
                        resp_body = ""
                    await websocket.send(json.dumps({
                        "status": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp_body
                    }))
            except Exception as e:
                logger.error(f"Request error: {e}")
                await websocket.send(json.dumps({"error": str(e)}))
    except ConnectionClosed:
        logger.info("WebSocket client disconnected")

async def process_request(connection, request):
    """Serve index.html for all non-WebSocket requests."""
    if request.path == WS_PATH:
        # Let WebSocket handshake proceed
        return None
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": str(len(INDEX_HTML)),
        "Connection": "close"
    }
    return (200, headers, INDEX_HTML)

async def main():
    logger.info(f"VDOT Web Proxy starting on port {PORT}")
    async with websockets.serve(
        handle_ws,
        "0.0.0.0",
        PORT,
        process_request=process_request
    ):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
