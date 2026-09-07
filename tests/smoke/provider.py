"""Deterministic OpenAI-compatible fixture; never contacts an external provider."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Provider(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.respond({"status": "ok"}, 200 if self.path == "/health" else 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/v1/embeddings":
            inputs = body["input"]
            if isinstance(inputs, str):
                inputs = [inputs]
            # A nonzero 1536-dimensional vector exercises real pgvector storage/search.
            # This fixture tests plumbing and ownership, not retrieval quality.
            self.respond(
                {
                    "object": "list",
                    "model": body["model"],
                    "data": [
                        {"object": "embedding", "index": i, "embedding": [1.0] + [0.0] * 1535}
                        for i in range(len(inputs))
                    ],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                }
            )
            return
        if self.path != "/v1/chat/completions":
            self.respond({"error": "Unsupported fixture endpoint"}, 404)
            return
        messages = body["messages"]
        results = [m["content"] for m in messages if m["role"] == "tool"]
        if results:
            message = {"role": "assistant", "content": "Retrieved context: " + str(results[-1])}
            reason = "stop"
        else:
            tool = next(
                t["function"]["name"]
                for t in body["tools"]
                if t["function"]["name"].endswith("search_documents")
            )
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "smoke-search",
                        "type": "function",
                        "function": {
                            "name": tool,
                            "arguments": json.dumps({"query": "smoke document", "limit": 5}),
                        },
                    }
                ],
            }
            reason = "tool_calls"
        self.respond(
            {
                "id": "smoke-completion",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8010), Provider).serve_forever()
