"""Regression tests for signed peer messages when an HMAC secret is configured."""

import pytest

from bees.protocol.envelope import BeeEnvelope
from bees.protocol.handler import BeeProtocolHandler
from bees.protocol.messages import BeeErrorCode, BeeMessageType


def make_request() -> BeeEnvelope:
    return BeeEnvelope.create_request(
        source_node_id="peer-a",
        target_node_id="peer-b",
        msg_type=BeeMessageType.CAPABILITY_QUERY,
        payload={"capability": "rag"},
    )


@pytest.mark.asyncio
async def test_unsigned_message_is_rejected_when_secret_configured():
    handler = BeeProtocolHandler(node_id="peer-b", shared_secret="cluster-secret")
    invoked = False

    async def process(_envelope):
        nonlocal invoked
        invoked = True
        return None

    handler.register_handler(BeeMessageType.CAPABILITY_QUERY, process)
    request = make_request()

    assert handler.verify_envelope(request) is False
    response = await handler.handle_message(request)

    assert response is not None
    assert response.msg_type == BeeMessageType.ERROR
    assert response.payload["code"] == BeeErrorCode.AUTH_FAILED.value
    assert not invoked
    assert handler.get_peer("peer-a") is None


@pytest.mark.asyncio
async def test_signed_message_is_dispatched_when_valid():
    handler = BeeProtocolHandler(node_id="peer-b", shared_secret="cluster-secret")
    invoked = False

    async def process(_envelope):
        nonlocal invoked
        invoked = True
        return None

    handler.register_handler(BeeMessageType.CAPABILITY_QUERY, process)
    request = make_request()
    handler.sign_envelope(request)

    assert request.signature
    assert handler.verify_envelope(request) is True
    assert await handler.handle_message(request) is None
    assert invoked


@pytest.mark.asyncio
async def test_tampered_signed_message_is_rejected():
    handler = BeeProtocolHandler(node_id="peer-b", shared_secret="cluster-secret")
    request = make_request()
    handler.sign_envelope(request)
    request.payload["capability"] = "vision"

    assert handler.verify_envelope(request) is False
    response = await handler.handle_message(request)

    assert response is not None
    assert response.payload["code"] == BeeErrorCode.AUTH_FAILED.value
    assert handler.get_peer("peer-a") is None


@pytest.mark.asyncio
async def test_unsigned_messages_remain_accepted_without_shared_secret():
    handler = BeeProtocolHandler(node_id="peer-b")
    invoked = False

    async def process(_envelope):
        nonlocal invoked
        invoked = True
        return None

    handler.register_handler(BeeMessageType.CAPABILITY_QUERY, process)
    request = make_request()

    assert handler.verify_envelope(request) is True
    assert await handler.handle_message(request) is None
    assert invoked
