"""Run inside the disposable issuer container, using its temporary signing key."""

import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
from jose import jwt
from shared.auth import create_access_token, decode_token


def require(condition, label):
    if not condition:
        raise RuntimeError("Smoke check failed: " + label)


async def main():
    async with httpx.AsyncClient(
        base_url="http://nginx",
        headers={"Host": "localhost"},
        timeout=70,
        follow_redirects=False,
        trust_env=False,
    ) as client:

        async def request(method, path, *, token=None, expected=200, **kwargs):
            # Stay below nginx's normal request rate, without disabling its protection.
            await asyncio.sleep(0.15)
            headers = kwargs.pop("headers", {})
            if token:
                headers["Authorization"] = "Bearer " + token
            response = await client.request(method, path, headers=headers, **kwargs)
            require(
                response.status_code == expected,
                f"{method} {path}: HTTP {response.status_code}, expected {expected}",
            )
            return response

        async def rpc(token=None, *, method="tools/list", params=None, expected=200):
            response = await request(
                "POST",
                "/mcp",
                token=token,
                expected=expected,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": "2025-03-26",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            return response.json()

        for service, port in (
            ("api-gateway", 8000),
            ("ai-service", 8001),
            ("document-service", 8002),
            ("mcp-gateway", 8003),
        ):
            response = await request("GET", f"http://{service}:{port}/health")
            require(response.json()["status"] == "ok", service + " health")
        await request("GET", "/health")
        jwks = (await request("GET", "/.well-known/jwks.json")).json()
        require(
            len(jwks["keys"]) == 1
            and set(jwks["keys"][0]) == {"kty", "use", "alg", "kid", "n", "e"},
            "public-only JWKS",
        )
        print("PASS service health and nginx/JWKS routing", flush=True)

        users = []
        for label in ("alpha", "bravo"):
            credentials = {
                "email": f"smoke-{label}-{uuid.uuid4().hex}@example.com",
                "password": "SmokePassword123!",
            }
            user = (
                await request("POST", "/api/v1/auth/register", json=credentials, expected=201)
            ).json()["data"]
            tokens = (await request("POST", "/api/v1/auth/login", json=credentials)).json()["data"]
            public_key = Path(os.environ["JWT_PUBLIC_KEY_PATH"]).read_text()
            claims = decode_token(tokens["access_token"], public_key)
            require(claims.sub == user["id"], "signed user identity")
            require(
                jwt.get_unverified_header(tokens["access_token"])["kid"] == jwks["keys"][0]["kid"],
                "JWKS signing key",
            )
            profile = (
                await request("GET", "/api/v1/auth/me", token=tokens["access_token"])
            ).json()["data"]
            require(profile["id"] == user["id"], "persisted profile")
            users.append({**user, **tokens, "marker": f"{label}-private-smoke-context"})

        first, second = users
        await request("GET", "/api/v1/auth/me", expected=401)
        await request("GET", "/api/v1/documents/", token="invalid", expected=401)
        await request("GET", "/api/v1/auth/me", token=first["refresh_token"], expected=401)
        await rpc(expected=401)
        await rpc("invalid", expected=401)
        await request("POST", "/api/v1/agent/query", json={"question": "hello"}, expected=401)
        private_key = Path(os.environ["JWT_PRIVATE_KEY_PATH"]).read_text()
        limited = create_access_token(first["id"], first["email"], private_key)
        await request("GET", "/api/v1/documents/", token=limited, expected=403)
        await rpc(limited, expected=403)
        tool_only = create_access_token(
            first["id"], first["email"], private_key, scopes=["mcp:invoke"]
        )
        denied = await rpc(
            tool_only, method="tools/call", params={"name": "list_documents", "arguments": {}}
        )
        require(denied["result"]["isError"], "MCP tool scope denial")
        print("PASS registration, login, asymmetric verification and authorization", flush=True)

        # Both concurrent requests reach real PostgreSQL; only one may rotate the row.
        async def refresh_once():
            return await client.post(
                "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
            )

        rotations = await asyncio.gather(refresh_once(), refresh_once())
        require(
            sorted(r.status_code for r in rotations) == [200, 401],
            "concurrent refresh single winner",
        )
        rotated = next(r.json()["data"] for r in rotations if r.status_code == 200)
        require(rotated["refresh_token"] != first["refresh_token"], "unique refresh token")
        await request(
            "POST",
            "/api/v1/auth/refresh",
            json={"refresh_token": first["refresh_token"]},
            expected=401,
        )
        first.update(rotated)
        await request("GET", "/api/v1/auth/me", token=first["access_token"])
        print("PASS PostgreSQL refresh rotation, concurrency and replay rejection", flush=True)

        for user in users:
            uploaded = (
                await request(
                    "POST",
                    "/api/v1/documents/upload",
                    token=user["access_token"],
                    expected=201,
                    files={
                        "file": (user["marker"] + ".txt", user["marker"].encode(), "text/plain")
                    },
                )
            ).json()["data"]
            require(uploaded["status"] == "ready", "document embedded and stored")
            user["document_id"] = uploaded["id"]
        for user, other in ((first, second), (second, first)):
            listed = (
                await request("GET", "/api/v1/documents/", token=user["access_token"])
            ).json()["data"]
            require([d["id"] for d in listed] == [user["document_id"]], "document list ownership")
            await request(
                "GET",
                "/api/v1/documents/" + other["document_id"],
                token=user["access_token"],
                expected=404,
            )
            results = (
                await request(
                    "POST",
                    "/api/v1/documents/search",
                    token=user["access_token"],
                    json={"query": "smoke", "limit": 5},
                )
            ).json()["data"]
            require(
                len(results) == 1 and results[0]["document_id"] == user["document_id"],
                "pgvector search ownership",
            )
            require(results[0]["similarity"] > 0.99, "pgvector cosine operator")
            for name, args in (("list_documents", {}), ("search_documents", {"query": "smoke"})):
                result = (
                    await rpc(
                        user["access_token"],
                        method="tools/call",
                        params={"name": name, "arguments": args},
                    )
                )["result"]
                require(not result.get("isError", False), name + " succeeds through nginx")
                rendered = json.dumps(result)
                require(
                    user["marker"] in rendered and other["marker"] not in rendered,
                    name + " ownership",
                )
        print("PASS uploads, real pgvector queries, document ownership and MCP tools", flush=True)

        async def ask(user):
            response = await request(
                "POST",
                "/api/v1/agent/query",
                token=user["access_token"],
                json={"question": "Find my smoke document"},
            )
            return response.json()["data"]["answer"]

        answers = await asyncio.gather(*(ask(user) for user in users))
        for index, answer in enumerate(answers):
            require(
                users[index]["marker"] in answer and users[1 - index]["marker"] not in answer,
                "concurrent agent credential isolation",
            )
        print("PASS concurrent agent -> MCP -> document-service -> PostgreSQL flow", flush=True)

        for user in users:
            await request(
                "DELETE", "/api/v1/documents/" + user["document_id"], token=user["access_token"]
            )
            await request(
                "POST", "/api/v1/auth/logout", json={"refresh_token": user["refresh_token"]}
            )
            await request(
                "POST",
                "/api/v1/auth/refresh",
                json={"refresh_token": user["refresh_token"]},
                expected=401,
            )
        print("PASS document deletion, logout and refresh invalidation", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
