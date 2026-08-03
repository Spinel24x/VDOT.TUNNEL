#!/usr/bin/env python3
"""
VDOT Web Proxy – aiohttp server with WebSocket tunnel + web interface.
"""
import asyncio
import json
import logging
import os
import sys
import traceback

from aiohttp import web, WSMsgType
import httpx

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("vdot-web")

PORT = int(os.environ.get("PORT", "8080"))
WS_PATH = "/ws"

# Load HTML page once
try:
    with open("index.html", "r", encoding="utf-8") as f:
        INDEX_HTML = f.read()
except Exception as e:
    logger.error(f"Cannot read index.html: {e}")
    INDEX_HTML = "<html><body><h1>Error loading page</h1></body></html>"

# ----- HTTP handler: serve index.html for all GET requests except WS -----
async def index_handler(request):
    return web.Response(text=INDEX_HTML, content_type="text/html")

# ----- WebSocket handler -----
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info("WebSocket client connected")
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    req = json.loads(msg.data)
                    url = req.get("url")
                    if not url:
                        await ws.send_json({"error": "No URL"})
                        continue
                    method = req.get("method", "GET")
                    headers = req.get("headers", {})
                    body = req.get("body")
                    # Remove problematic headers
                    for h in ["Host", "Connection", "Transfer-Encoding", "Upgrade"]:
                        headers.pop(h, None)
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        resp = await client.request(method, url, headers=headers, content=body)
                        try:
                            text = resp.text
                        except Exception:
                            text = ""
                        await ws.send_json({
                            "status": resp.status_code,
                            "headers": dict(resp.headers),
                            "body": text
                        })
                except Exception as e:
                    logger.error(f"Request error: {e}\n{traceback.format_exc()}")
                    await ws.send_json({"error": str(e)})
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        logger.info("WebSocket client disconnected")
    return ws

# ----- Main application -----
async def create_app():
    app = web.Application()
    # Route: WebSocket
    app.router.add_get(WS_PATH, websocket_handler)
    # Route: everything else -> index.html
    app.router.add_get("/{tail:.*}", index_handler)
    return app

if __name__ == "__main__":
    logger.info(f"Starting VDOT Web Proxy on port {PORT}")
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
