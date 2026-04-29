"""
SafestClaw Webhook System - Inbound and outbound webhooks.

Receive triggers from external services, send notifications out.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass
class WebhookEvent:
    """Incoming webhook event."""
    name: str
    payload: dict[str, Any]
    headers: dict[str, str]
    source_ip: str
    verified: bool = False


class WebhookHandler:
    """
    Handler for a specific webhook endpoint.

    Supports:
    - Secret verification (HMAC-SHA256)
    - Payload transformation
    - Action triggering
    """

    def __init__(
        self,
        name: str,
        action: str,
        secret: str | None = None,
        transform: Callable[[dict], dict] | None = None,
    ):
        self.name = name
        self.action = action
        self.secret = secret
        self.transform = transform

    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        algorithm: str = "sha256",
    ) -> bool:
        """Verify webhook signature using HMAC."""
        if not self.secret:
            return True

        expected = hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256 if algorithm == "sha256" else hashlib.sha1,
        ).hexdigest()

        # Handle various signature formats
        signature = signature.replace("sha256=", "").replace("sha1=", "")

        return hmac.compare_digest(expected, signature)

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process and transform payload."""
        if self.transform:
            return self.transform(payload)
        return payload


class WebhookServer:
    """
    FastAPI-based webhook server.

    Features:
    - Multiple webhook endpoints
    - Secret verification
    - GitHub/GitLab/Slack compatibility
    - Custom action triggers
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        self.host = host
        self.port = port
        self.handlers: dict[str, WebhookHandler] = {}
        self.event_queue: asyncio.Queue[WebhookEvent] = asyncio.Queue()

        self.app = FastAPI(
            title="SafestClaw Webhooks",
            description="Webhook receiver for SafestClaw automation",
            version="0.1.0",
        )
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Set up FastAPI routes."""

        @self.app.get("/health")
        async def health():
            return {"status": "ok", "service": "safestclaw-webhooks"}

        @self.app.get("/webhooks")
        async def list_webhooks():
            return {
                "webhooks": [
                    {"name": name, "action": h.action, "has_secret": bool(h.secret)}
                    for name, h in self.handlers.items()
                ]
            }

        @self.app.post("/webhook/{name}")
        async def receive_webhook(
            name: str,
            request: Request,
            x_hub_signature_256: str | None = Header(None),
            x_gitlab_token: str | None = Header(None),
            x_slack_signature: str | None = Header(None),
        ):
            # Check if handler exists
            if name not in self.handlers:
                raise HTTPException(status_code=404, detail=f"Webhook '{name}' not found")

            handler = self.handlers[name]

            # Get raw body for signature verification
            body = await request.body()

            # Verify signature
            signature = x_hub_signature_256 or x_gitlab_token or x_slack_signature
            verified = True
            if handler.secret:
                if not signature:
                    raise HTTPException(status_code=401, detail="Missing signature")
                verified = handler.verify_signature(body, signature)
                if not verified:
                    raise HTTPException(status_code=401, detail="Invalid signature")

            # Parse payload
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                # Try form data
                payload = dict(await request.form())

            # Create event
            event = WebhookEvent(
                name=name,
                payload=handler.process(payload),
                headers=dict(request.headers),
                source_ip=request.client.host if request.client else "unknown",
                verified=verified,
            )

            # Queue event for processing
            await self.event_queue.put(event)

            logger.info(f"Received webhook: {name} from {event.source_ip}")

            return JSONResponse(
                content={"status": "accepted", "webhook": name},
                status_code=202,
            )

    def register(
        self,
        name: str,
        action: str,
        secret: str | None = None,
        transform: Callable[[dict], dict] | None = None,
    ) -> None:
        """Register a webhook handler."""
        self.handlers[name] = WebhookHandler(
            name=name,
            action=action,
            secret=secret,
            transform=transform,
        )
        logger.info(f"Registered webhook: {name} -> {action}")

    def unregister(self, name: str) -> bool:
        """Unregister a webhook handler."""
        if name in self.handlers:
            del self.handlers[name]
            logger.info(f"Unregistered webhook: {name}")
            return True
        return False

    async def start(self) -> None:
        """Start the webhook server."""
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        logger.info(f"Starting webhook server on {self.host}:{self.port}")
        await server.serve()

    async def get_event(self, timeout: float | None = None) -> WebhookEvent | None:
        """Get next webhook event from queue."""
        try:
            if timeout:
                return await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=timeout,
                )
            return await self.event_queue.get()
        except TimeoutError:
            return None


class WebhookClient:
    """
    Client for sending outbound webhooks.

    Use this to notify external services of events.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def send(
        self,
        url: str,
        payload: dict[str, Any],
        secret: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Send a webhook to an external URL.

        Args:
            url: Target URL
            payload: JSON payload to send
            secret: Optional secret for HMAC signature
            headers: Additional headers

        Returns:
            Response info dict
        """
        # SSRF protection: prevent sending webhooks to internal networks
        from safestclaw.core.crawler import is_safe_url

        is_safe, reason = is_safe_url(url)
        if not is_safe:
            return {
                "success": False,
                "error": f"SSRF blocked: {reason}",
            }

        headers = headers or {}
        headers["Content-Type"] = "application/json"

        body = json.dumps(payload).encode()

        # Add HMAC signature if secret provided
        if secret:
            signature = hmac.new(
                secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-SafestClaw-Signature"] = f"sha256={signature}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, content=body, headers=headers)
                return {
                    "success": response.status_code < 400,
                    "status_code": response.status_code,
                    "response": response.text[:1000],
                }
            except httpx.RequestError as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def send_to_slack(
        self,
        webhook_url: str,
        text: str,
        blocks: list | None = None,
    ) -> dict[str, Any]:
        """Send a message to Slack via webhook."""
        payload: dict[str, Any] = {"text": text}
        if blocks:
            payload["blocks"] = blocks

        return await self.send(webhook_url, payload)

    async def send_to_discord(
        self,
        webhook_url: str,
        content: str,
        embeds: list | None = None,
    ) -> dict[str, Any]:
        """Send a message to Discord via webhook."""
        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        return await self.send(webhook_url, payload)
