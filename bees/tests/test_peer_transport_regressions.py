"""Regression tests for BEE peer messages over HTTP."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bees.config import BeeConfig
from bees.protocol.envelope import BeeEnvelope
from bees.protocol.messages import BeeMessageType
from bees.service import BeeService


def make_service(tmp_path, node_id="bee-b", secret=None):
    return BeeService(
        BeeConfig(
            node_id=node_id,
            data_dir=tmp_path / node_id,
            host="127.0.0.1",
            port=0,
            shared_secret=secret,
        )
    )


def capability_request(receiver, target=None):
    return BeeEnvelope.create_request(
        source_node_id="peer-a",
        target_node_id=target or receiver.node_id,
        msg_type=BeeMessageType.CAPABILITY_QUERY,
        payload={"capability": "query"},
    )


@pytest.mark.asyncio
async def test_integrated_peer_route_validates_envelopes_and_signatures(tmp_path):
    receiver = make_service(tmp_path, secret="shared-secret")
    app = web.Application()
    await receiver._add_routes_to_app(app)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            unsigned = capability_request(receiver)
            denied = await client.post("/api/v1/bee/message", json=unsigned.to_dict())
            assert denied.status == 401

            signed = capability_request(receiver)
            receiver._handler.sign_envelope(signed)
            result = await client.post("/api/v1/bee/message", json=signed.to_dict())
            assert result.status == 200

            reply = BeeEnvelope.from_dict(await result.json())
            assert reply.msg_type == BeeMessageType.CAPABILITY_RESPONSE
            assert reply.payload["has_capability"] is True
            assert receiver._handler.verify_envelope(reply) is True

            malformed = await client.post("/api/v1/bee/message", json={"unknown": 1})
            assert malformed.status == 400

            wrong_target = capability_request(receiver, target="different-bee")
            receiver._handler.sign_envelope(wrong_target)
            rejected = await client.post("/api/v1/bee/message", json=wrong_target.to_dict())
            assert rejected.status == 400

            discover = await client.get("/api/cluster/discover")
            assert discover.status == 200


@pytest.mark.asyncio
async def test_authenticated_query_round_trip_between_two_bees(tmp_path):
    sender = make_service(tmp_path, node_id="bee-a", secret="shared-secret")
    receiver = make_service(tmp_path, node_id="bee-b", secret="shared-secret")
    receiver._librarian = SimpleNamespace(
        quick_knowledge_check=AsyncMock(
            return_value={
                "has_knowledge": True,
                "confidence": 0.91,
                "document_count": 3,
                "topics": ["python"],
            }
        )
    )
    app = web.Application()
    await receiver._add_routes_to_app(app)

    async with TestServer(app) as server:
        async with aiohttp.ClientSession() as session:
            sender._http_session = session
            peer = SimpleNamespace(node_id="bee-b", host="127.0.0.1", port=server.port)
            message = sender._handler.create_knowledge_query(
                target_node_id="bee-b", subject="python"
            )
            response = await sender._send_with_response(message, peer, timeout_ms=3000)

    assert response is not None
    assert response.msg_type == BeeMessageType.KNOWLEDGE_RESPONSE
    assert response.payload["has_knowledge"] is True
    assert response.payload["document_count"] == 3
    assert sender._handler.verify_envelope(response) is True


@pytest.mark.asyncio
async def test_standalone_server_registers_peer_endpoint(tmp_path):
    service = make_service(tmp_path)
    await service._start_http_server()
    try:
        paths = {resource.canonical for resource in service._http_runner.app.router.resources()}
        assert "/api/v1/bee/message" in paths
    finally:
        await service._http_runner.cleanup()
