# Authenticated document tools and agent

## Problem and boundaries

Expose a small document assistant while retaining deterministic user ownership and
permission checks. Only `api-gateway` issues credentials. nginx routes requests;
it does not authenticate them. Resource services independently verify credentials.

The issuer owns an RSA private key. AI, document, and MCP services receive only the
public key. The worker receives neither key. Keys never enter Docker build contexts.
Document-service remains authoritative for ownership: list/get/delete/search queries
filter by the authenticated subject, including searches restricted to a document ID.
MCP forwards credentials only to configured, fixed document-service routes.

## Token contract

RS256 only, RSA >= 2048 bits. Access and refresh JWTs require `sub` (user UUID),
`email`, `iat`, `exp`, `type`, `iss`, `aud`, `jti` (unique UUID), and `scope`
(space-delimited string; empty on refresh). The header `kid` is derived from the
public key fingerprint. Reject unexpected keys, algorithms, types, issuer, audience,
missing claims, expired tokens, and future issuance times.

One platform resource audience, `ai-platform`, is shared by the REST and MCP resource
services. This is a first-party platform policy, not service-specific token exchange.
The verifier checks this audience explicitly; SDK resource-URL equality checking is
intentionally disabled because the audience is an identifier rather than the MCP URL.
JWT issuer defaults to `http://localhost` for development. Production requires TLS.

The issuer publishes only RSA public parameters at `/.well-known/jwks.json`.
Services use mounted public material, not runtime JWKS fetching. Key replacement
requires coordinated service restarts and invalidates tokens signed by the old key.

## Functional and permission requirements

| Operation | Required scopes |
| --- | --- |
| Current profile | `profile:read` |
| Existing inference/templates | `ai:invoke` |
| Document list/get | `documents:read` |
| Upload/delete | `documents:write` |
| Document search | `documents:search` |
| MCP transport | `mcp:invoke` |
| MCP `list_documents` | additionally `documents:read` |
| MCP `search_documents(query, limit)` | additionally `documents:search` |
| Agent query | `ai:agent`, `mcp:invoke`, `documents:read`, `documents:search` |

Registration/login grants a fixed set of ordinary own-data scopes. Clients cannot
select their scopes. There is no administrator scope or role-management API.

The MCP gateway uses the official SDK v2, Streamable HTTP, stateless requests,
`TokenVerifier`, and request-local authenticated context. It exposes exactly two
tools, no arbitrary network or process execution, and no user-selection argument.
A search has 1-1000 characters and a result limit of 1-20. Requests are bounded to
16 KiB and downstream responses to 1 MB. Downstream calls time out after 15 seconds;
redirects and retries are disabled. Response schemas are validated before returning.

`POST /api/v1/agent/query` accepts only a question (1-4000 characters) and returns an
answer. A PydanticAI dynamic toolset factory runs once per agent run. Each run owns
a fresh HTTP client and MCP toolset with that run's bearer credential. No shared
authenticated connection exists. Runs have a 60-second deadline and at most six
model requests and six tool calls. Model/provider configuration comes from settings.

## Security and failures

Missing/invalid credentials return HTTP 401. Valid credentials with insufficient
REST or MCP transport scopes return 403. Tool-level denial is an MCP error result
with a fixed `Forbidden` message, as required by tool-result semantics. Downstream
401/403 responses remain explicit error results; they never become successful data.
Malformed, oversized, redirected, or unavailable downstream responses produce safe
errors. The agent maps failed runs to a fixed 503 response without SDK exception text.
Bearer credentials must not appear in logs, errors, model messages, or tool arguments.

Retrieved document contents are untrusted data. Instructions in those contents do
not change scopes, identity, tool destinations, or database predicates. Model guidance
helps answer quality; application and database checks enforce authorization.

Refresh tokens are stored as hashes and rotated once inside a database transaction.
A row lock serializes concurrent refresh attempts. Reusing a consumed token is rejected.
There is no token-family revocation, and logout does not revoke existing access tokens.

## Acceptance criteria

- Valid asymmetric tokens and properly scoped requests succeed.
- Tampering, symmetric tokens, missing/invalid claims, wrong issuer/audience, and
  access/refresh substitution fail.
- Repeated issuance is unique; JWKS contains no private parameters.
- Downstream deployment configuration contains no private signing material.
- HTTP MCP authentication, tool scopes, identity forwarding, and safe failures are tested.
- Concurrent agent runs against the MCP HTTP transport return only their own context.
- Ownership predicates remain enforced when supplied document content is adversarial.
- Both CI providers run the same compile, lint, type, and test policy without paid APIs.

## Non-goals and trade-offs

This is a production-style reference platform, not a complete identity provider.
Automatic OAuth login/consent/client registration, service-specific token exchange,
central access-token revocation, overlapping signing-key rotation, TLS termination,
and database-level tenant isolation are outside scope. MCP resource metadata is
published by the SDK; clients currently obtain tokens through the platform login API.

Document extraction, chunking, embeddings, and storage still execute during upload.
The optional Celery worker contains illustrative extensions; it does not implement
that processing pipeline, persist summaries, or perform the illustrated cleanup.
One database/account simplifies local setup but increases compromise impact.

## SDK references

- [Official MCP authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/)
- [MCP HTTP deployment](https://py.sdk.modelcontextprotocol.io/run/asgi/)
- [PydanticAI per-user MCP toolsets](https://pydantic.dev/docs/ai/mcp/client/)
