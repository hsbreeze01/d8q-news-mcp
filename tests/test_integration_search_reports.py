"""Integration tests for d8q_search_reports — real MCP HTTP calls."""

import json
import urllib.request

import pytest

MCP_URL = "http://localhost:58178/mcp"


def _mcp_call(method: str, params: dict | None = None, session_id: str | None = None) -> dict:
    body = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params:
        body["params"] = params

    req = urllib.request.Request(MCP_URL, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    if session_id:
        req.add_header("mcp-session-id", session_id)

    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()

    for line in raw.split("\n"):
        if line.startswith("data: "):
            return json.loads(line[6:])

    return {"error": "no data line in SSE response"}


def _init_session() -> str:
    body = json.dumps({
        "jsonrpc": "2.0", "method": "initialize", "id": 1,
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "1.0"},
        }
    }).encode()
    req = urllib.request.Request(MCP_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")

    with urllib.request.urlopen(req, timeout=10) as resp:
        session_id = resp.headers.get("mcp-session-id")
        raw = resp.read().decode()

    assert session_id, f"no session-id in response headers"
    return session_id


@pytest.fixture(scope="module")
def session():
    return _init_session()


class TestToolRegistration:
    """d8q_search_reports appears in tools/list."""

    def test_tool_listed(self, session):
        result = _mcp_call("tools/list", session_id=session)
        tools = result.get("result", {}).get("tools", [])
        names = [t["name"] for t in tools]
        assert "d8q_search_reports" in names

    def test_tool_has_correct_schema(self, session):
        result = _mcp_call("tools/list", session_id=session)
        tools = result.get("result", {}).get("tools", [])
        tool = next(t for t in tools if t["name"] == "d8q_search_reports")

        props = tool["inputSchema"]["properties"]
        assert "stocks" in props
        assert "days" in props
        assert "limit_per_stock" in props

        assert tool["inputSchema"]["required"] == ["stocks"]


class TestToolCall:
    """d8q_search_reports returns valid data for real queries."""

    def test_single_stock_returns_markdown(self, session):
        result = _mcp_call("tools/call", {
            "name": "d8q_search_reports",
            "arguments": {"stocks": "宁德时代", "days": 30, "limit_per_stock": 3},
        }, session_id=session)

        content = result.get("result", {}).get("content", [])
        assert len(content) > 0
        text = content[0].get("text", "")
        assert "# 研报周报" in text
        assert "宁德时代" in text

    def test_multi_stock_returns_all(self, session):
        result = _mcp_call("tools/call", {
            "name": "d8q_search_reports",
            "arguments": {"stocks": "宁德时代,比亚迪", "days": 45, "limit_per_stock": 2},
        }, session_id=session)

        content = result.get("result", {}).get("content", [])
        text = content[0].get("text", "")
        assert "宁德时代" in text
        assert "比亚迪" in text

    def test_empty_stocks_returns_error(self, session):
        result = _mcp_call("tools/call", {
            "name": "d8q_search_reports",
            "arguments": {"stocks": ""},
        }, session_id=session)

        content = result.get("result", {}).get("content", [])
        text = content[0].get("text", "")
        assert "错误" in text

    def test_output_includes_generation_time(self, session):
        result = _mcp_call("tools/call", {
            "name": "d8q_search_reports",
            "arguments": {"stocks": "宁德时代", "days": 7},
        }, session_id=session)

        content = result.get("result", {}).get("content", [])
        text = content[0].get("text", "")
        assert "生成时间:" in text

    def test_days_reflected_in_header(self, session):
        result = _mcp_call("tools/call", {
            "name": "d8q_search_reports",
            "arguments": {"stocks": "宁德时代", "days": 14},
        }, session_id=session)

        content = result.get("result", {}).get("content", [])
        text = content[0].get("text", "")
        assert "近 14 天" in text
