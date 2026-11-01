"""Regression coverage for BEE research replies from local librarian searches."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bees.config import BeeConfig
from bees.protocol.envelope import BeeEnvelope
from bees.protocol.messages import BeeMessageType, BeeResearchRequest
from bees.service import BeeService


def make_service(tmp_path, search_result):
    service = BeeService(
        BeeConfig(node_id="bee-b", data_dir=tmp_path, host="127.0.0.1")
    )
    service._librarian = SimpleNamespace(search=AsyncMock(return_value=search_result))
    return service


def request_for(service):
    return BeeEnvelope.create_request(
        source_node_id="peer-a",
        target_node_id=service.node_id,
        msg_type=BeeMessageType.RESEARCH_REQUEST,
        payload=BeeResearchRequest(
            request_id="research-1",
            query="Python concurrency",
            max_results=3,
        ).to_dict(),
    )


@pytest.mark.asyncio
async def test_librarian_synthesized_answer_is_returned_as_research_item(tmp_path):
    service = make_service(
        tmp_path,
        {
            "answer": "Use asyncio for cooperative concurrency.",
            "source": "local_files",
            "confidence": 0.84,
            "metadata": {"sources": ["notes.txt"]},
        },
    )

    response = await service._handle_research_request(request_for(service))

    assert response.msg_type == BeeMessageType.RESEARCH_RESULT
    assert response.payload["total_results"] == 1
    assert response.payload["results"][0]["content"] == (
        "Use asyncio for cooperative concurrency."
    )
    assert response.payload["results"][0]["source"] == "local_files"
    assert response.payload["results"][0]["confidence"] == 0.84
    assert response.payload["results"][0]["metadata"] == {"sources": ["notes.txt"]}


@pytest.mark.asyncio
async def test_no_research_item_for_local_miss(tmp_path):
    service = make_service(
        tmp_path,
        {"answer": "No matching documents.", "source": "none", "confidence": 0.0},
    )
    response = await service._handle_research_request(request_for(service))

    assert response.payload["results"] == []
    assert response.payload["total_results"] == 0


@pytest.mark.asyncio
async def test_existing_explicit_research_items_are_preserved(tmp_path):
    service = make_service(
        tmp_path,
        {
            "answer": "Summary should not create a duplicate item.",
            "source": "lancedb",
            "confidence": 0.9,
            "results": [
                {"content": "Document result", "source": "manual.txt", "confidence": 0.8}
            ],
        },
    )
    response = await service._handle_research_request(request_for(service))

    assert response.payload["total_results"] == 1
    assert response.payload["results"][0]["content"] == "Document result"
