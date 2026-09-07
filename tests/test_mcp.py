import json
import uuid

import httpx
import pytest
from shared.auth import create_access_token, decode_token
from starlette.testclient import TestClient

from tests.service_loader import load_service


@pytest.fixture
def mcp_factory():
    module = load_service("mcp-gateway")
    return module.create_app


def request(client, token=None, method="tools/list", arguments=None, tool="search_documents"):
    headers = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-03-26",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {"name": tool, "arguments": arguments or {}} if method == "tools/call" else {}
    return client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


@pytest.mark.parametrize("credential,status", [(None, 401), ("invalid", 401), ("no-scope", 403)])
def test_mcp_http_auth(mcp_factory, keys, credential, status):
    if credential == "no-scope":
        credential = create_access_token(str(uuid.uuid4()), "user@example.com", keys[0])
    with TestClient(mcp_factory(), base_url="http://localhost") as client:
        assert request(client, credential).status_code == status


def test_tool_scope_is_enforced_before_downstream(mcp_factory, keys):
    calls = []

    def downstream(req):
        calls.append(req)
        return httpx.Response(200, json={"success": True, "data": []})

    token = create_access_token(
        str(uuid.uuid4()), "user@example.com", keys[0], scopes=["mcp:invoke"]
    )
    with TestClient(
        mcp_factory(transport=httpx.MockTransport(downstream)), base_url="http://localhost"
    ) as client:
        result = request(client, token, "tools/call", {"query": "hello"}).json()["result"]
        assert result["isError"] is True
        assert "Forbidden" in str(result)
        assert not calls


def test_permitted_tools_forward_authenticated_identity(mcp_factory, keys):
    user = str(uuid.uuid4())
    calls = []

    def downstream(req):
        calls.append(req)
        assert decode_token(req.headers["Authorization"].split()[1], keys[1]).sub == user
        assert "user_id" not in req.url.params
        return httpx.Response(200, json={"success": True, "data": []})

    token = create_access_token(
        user,
        "user@example.com",
        keys[0],
        scopes=["mcp:invoke", "documents:read", "documents:search"],
    )
    with TestClient(
        mcp_factory(transport=httpx.MockTransport(downstream)), base_url="http://localhost"
    ) as client:
        tools = request(client, token).json()["result"]["tools"]
        assert {t["name"] for t in tools} == {"list_documents", "search_documents"}
        assert all("user_id" not in t["inputSchema"].get("properties", {}) for t in tools)
        assert (
            not request(client, token, "tools/call", tool="list_documents")
            .json()["result"]
            .get("isError", False)
        )
        assert (
            not request(client, token, "tools/call", {"query": "hello", "limit": 3})
            .json()["result"]
            .get("isError", False)
        )
        assert json.loads(calls[-1].content) == {"query": "hello", "limit": 3}
        result = request(
            client, token, "tools/call", {"query": "hello", "user_id": str(uuid.uuid4())}
        ).json()
        # Even if the SDK ignores extra arguments, the forwarded search contains only its allowlist.
        if "error" not in result and not result["result"].get("isError", False):
            assert json.loads(calls[-1].content) == {"query": "hello", "limit": 5}


@pytest.mark.parametrize(
    "failure", ["malformed", "oversized", "unauthorized", "forbidden", "unavailable", "redirect"]
)
def test_downstream_failures_are_safe(mcp_factory, keys, failure, caplog):
    token = create_access_token(
        str(uuid.uuid4()), "user@example.com", keys[0], scopes=["mcp:invoke", "documents:search"]
    )

    def downstream(req):
        if failure == "malformed":
            return httpx.Response(200, json={"success": True, "data": [{"content": token}]})
        if failure == "oversized":
            return httpx.Response(200, content=b"x" * 1_100_000)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://untrusted.example"})
        return httpx.Response(
            {"unauthorized": 401, "forbidden": 403, "unavailable": 503}[failure], text=token
        )

    with TestClient(
        mcp_factory(transport=httpx.MockTransport(downstream)), base_url="http://localhost"
    ) as client:
        result = request(client, token, "tools/call", {"query": "hello"}).json()["result"]
        assert result["isError"] is True
        assert token not in str(result)
        assert token not in caplog.text


def test_untrusted_host_is_rejected(mcp_factory, keys):
    token = create_access_token(
        str(uuid.uuid4()), "user@example.com", keys[0], scopes=["mcp:invoke"]
    )
    with TestClient(mcp_factory(), base_url="http://untrusted.example") as client:
        assert request(client, token).status_code == 421


def test_mcp_request_size_is_bounded(mcp_factory, keys):
    token = create_access_token(
        str(uuid.uuid4()), "user@example.com", keys[0], scopes=["mcp:invoke"]
    )
    with TestClient(mcp_factory(), base_url="http://localhost") as client:
        response = request(client, token, "tools/call", {"query": "x" * 20000})
        assert response.status_code == 413
