"""D8Q News MCP Server

DataAgent API (47:8000):
  - GET /api/tracks                    列出所有赛道
  - GET /api/tracks/{id}/news          按赛道获取资讯 (time_window: 1h/6h/24h/7d/30d)
  - GET /api/news?keyword=             关键词搜索资讯 (time_window: 1h/6h/24h/7d/30d)
  - GET /api/tracks/detail/{id}        资讯详情（含正文、URL）

StockShark API (49:5000):
  - POST /api/stock/analyze            股票分析
  - GET /api/report/search             研报搜索（洞见研报）
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("d8q-news-mcp")


DATAAGENT_BASE = "http://47.99.57.152:8000"
SHARK_BASE = "http://localhost:5000"
TIMEOUT = 15

mcp = FastMCP(
    "d8q-news",
    instructions=(
        "D8Q 智能引擎资讯服务。"
        "可按赛道/主题获取资讯、关键词搜索资讯、查看资讯详情、查询股票综合画像、批量查询研报生成周报。"
        "6 个赛道：人工智能、具身智能、新材料、合成生物、碳纤维、量子计算。"
        "支持时间窗口过滤：1h（过去1小时）、6h、24h、7d、30d。"
        "研报数据源：洞见研报（券商研报、机构调研、定期报告）。"
    ),
    host="0.0.0.0",
    port=58178,
)



def _get(url: str, params: dict | None = None) -> dict | list | None:
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error("GET %s failed: %s", url, e)
        return None


def _post(url: str, data: dict) -> dict | None:
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(url, json=data)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error("POST %s failed: %s", url, e)
        return None




@mcp.tool()
def d8q_list_tracks() -> str:
    """列出所有资讯赛道（主题）。返回赛道 ID、名称、关键词、状态。

    示例返回：
    - 人工智能 (ID=1, 关键词: AI, 大模型, GPT, 智能体...)
    - 具身智能 (ID=2, 关键词: 机器人, 人形机器人...)
    - 新材料 / 合成生物 / 碳纤维 / 量子计算
    """
    data = _get(f"{DATAAGENT_BASE}/api/tracks")
    if not data:
        return "错误：无法连接 DataAgent 服务"

    lines = []
    for t in data:
        tid = t.get("id")
        name = t.get("name", "")
        status = t.get("status", "")
        keywords_raw = t.get("keywords", "[]")
        try:
            kws = json.loads(keywords_raw) if isinstance(keywords_raw, str) else keywords_raw
            kw_str = ", ".join(kws[:5])
            if len(kws) > 5:
                kw_str += f" 等{len(kws)}个"
        except (json.JSONDecodeError, TypeError):
            kw_str = str(keywords_raw)

        lines.append(f"- **{name}** (ID={tid}, {status})  关键词: {kw_str}")

    header = f"共 {len(data)} 个赛道：\n"
    return header + "\n".join(lines)


@mcp.tool()
def d8q_get_track_news(track_id: int, limit: int = 10, page: int = 1, time_window: str = "") -> str:
    """按赛道获取最新资讯列表。

    参数：
    - track_id: 赛道 ID（先用 d8q_list_tracks 查看）
    - limit: 返回条数（默认 10，最大 50）
    - page: 页码（默认 1）
    - time_window: 时间窗口，可选 "1h" "6h" "24h" "7d" "30d"（默认返回近 7 天）

    返回每条资讯的标题、来源、发布时间、原文链接。
    """
    limit = min(limit, 50)
    params: dict[str, Any] = {"limit": limit, "page": page}
    if time_window:
        params["time_window"] = time_window

    data = _get(f"{DATAAGENT_BASE}/api/tracks/{track_id}/news", params=params)
    if not data:
        return f"错误：无法获取赛道 {track_id} 的资讯"

    total = data.get("total", 0)
    items = data.get("items", [])

    if not items:
        return f"赛道 {track_id} 暂无资讯"

    lines = [f"共 {total} 条资讯，当前第 {page} 页：\n"]
    for i, n in enumerate(items, 1):
        title = n.get("title", "无标题")
        source = n.get("source", "")
        pub_time = n.get("publish_time", "")
        news_type = n.get("news_type", "")
        url = n.get("url", "")
        time_short = pub_time[:16] if pub_time else ""

        type_tag = {"newsflash": "快讯", "telegraph": "电报"}.get(news_type, news_type)
        link = f" | [链接]({url})" if url else ""
        lines.append(f"{i}. [{type_tag}] **{title}**\n   来源: {source} | 时间: {time_short}{link}")

    return "\n".join(lines)


@mcp.tool()
def d8q_search_news(keyword: str, limit: int = 10, time_window: str = "") -> str:
    """关键词搜索资讯。跨所有赛道搜索标题和内容匹配的资讯。

    参数：
    - keyword: 搜索关键词
    - limit: 返回条数（默认 10，最大 30）
    - time_window: 时间窗口，可选 "1h" "6h" "24h" "7d" "30d"（默认不限）

    返回匹配的资讯标题、来源、原文链接。
    """
    limit = min(limit, 30)
    params: dict[str, Any] = {"keyword": keyword, "size": limit}
    if time_window:
        params["time_window"] = time_window

    data = _get(f"{DATAAGENT_BASE}/api/news", params=params)
    if not data:
        return "错误：无法搜索资讯"

    items = data.get("items", [])
    total = data.get("total", 0)

    if not items:
        return f"未找到与「{keyword}」相关的资讯"

    lines = [f"搜索「{keyword}」共匹配 {total} 条资讯：\n"]
    for i, n in enumerate(items[:limit], 1):
        title = n.get("title", "无标题")
        source = n.get("source", "")
        subject = n.get("subject", "")
        pub_time = n.get("publish_time", "")[:16]
        url = n.get("url", "")
        link = f" | [链接]({url})" if url else ""
        lines.append(f"{i}. **{title}**\n   赛道: {subject} | 来源: {source} | 时间: {pub_time}{link}")

    return "\n".join(lines)


@mcp.tool()
def d8q_get_news_detail(news_id: int) -> str:
    """获取单条资讯的完整详情：正文、原文链接、作者、关联股票代码。

    参数：
    - news_id: 资讯 ID（从 d8q_get_track_news 或 d8q_search_news 结果中获取）

    返回完整正文、URL、来源、发布时间等。
    """
    data = _get(f"{DATAAGENT_BASE}/api/tracks/detail/{news_id}")
    if not data:
        return f"错误：无法获取资讯 {news_id}"

    if isinstance(data, dict) and "error" in data:
        return f"错误：{data['error']}"

    title = data.get("title", "无标题")
    url = data.get("url", "")
    content = data.get("content", "")
    author = data.get("author", "")
    source = data.get("source", "")
    pub_time = data.get("publish_time", "")[:16]
    subject = data.get("subject", "")
    news_type = data.get("news_type", "")
    stock_codes = data.get("stock_codes", "")

    lines = [f"## {title}\n"]
    lines.append(f"来源: {source} | 作者: {author} | 时间: {pub_time} | 赛道: {subject}")
    if url:
        lines.append(f"原文链接: {url}")
    if stock_codes and stock_codes != "None":
        lines.append(f"关联股票: {stock_codes}")

    lines.append(f"\n---\n{content}")

    return "\n".join(lines)


@mcp.tool()
def d8q_get_stock_profile(stock_code: str) -> str:
    """获取股票综合画像：行情分析 + 关联资讯。

    参数：
    - stock_code: 股票代码，如 600036

    返回股票名称、评分、风险等级、关联资讯。
    """
    quote = _post(f"{SHARK_BASE}/api/stock/analyze", {"symbol": stock_code})

    lines = [f"## 股票综合画像: {stock_code}\n"]

    if quote and quote.get("success"):
        data = quote.get("data", {})
        name = data.get("stock_name") or data.get("name") or stock_code
        lines[0] = f"## 股票综合画像: {name} ({stock_code})\n"

        score = data.get("investment_score", {})
        if score:
            total = score.get("total_score", "-")
            rating = score.get("rating", "-")
            lines.append(f"**投资评分**: {total} 分 ({rating})")

        risk = data.get("risk_score", {})
        if risk:
            level = risk.get("risk_level", "-")
            factors = risk.get("risk_factors", [])
            lines.append(f"**风险等级**: {level}")
            if factors:
                lines.append(f"  风险因素: {', '.join(factors)}")
    else:
        lines.append("⚠ 行情数据暂不可用")

    tracks = _get(f"{DATAAGENT_BASE}/api/tracks")
    news_found = []
    name = ""
    if quote and quote.get("success"):
        data_q = quote.get("data", {})
        name = data_q.get("stock_name") or data_q.get("name") or stock_code
    if tracks:
        for track in tracks[:10]:
            tid = track.get("id")
            if tid is None:
                continue
            resp = _get(f"{DATAAGENT_BASE}/api/tracks/{tid}/news", params={"limit": 50})
            if resp and "items" in resp:
                for n in resp["items"]:
                    title = n.get("title", "")
                    if stock_code in title or (name and name in title):
                        news_found.append(n)

    lines.append(f"\n### 关联资讯 ({len(news_found)} 条)")
    if news_found:
        for i, n in enumerate(news_found[:5], 1):
            lines.append(f"{i}. {n.get('title', '')} — {n.get('source', '')} ({n.get('publish_time', '')[:10]})")
    else:
        lines.append("暂无关联资讯")

    return "\n".join(lines)


@mcp.tool()
def d8q_search_reports(stocks: str, days: int = 7, limit_per_stock: int = 10) -> str:
    """批量查询股票研报。根据股票名称或代码搜索相关研报，适合生成周报。

    数据源：洞见研报（券商研报）+ 慧博投研（机构调研）+ 巨潮资讯（公告），三源聚合。

    参数：
    - stocks: 股票列表，逗号分隔，支持名称或代码。如 "宁德时代,比亚迪,600036"
    - days: 筛选最近N天的研报（默认7天）
    - limit_per_stock: 每只股票返回的最大研报数（默认10，最大20）

    返回每只股票的研报标题、机构、日期、摘要、来源链接。
    适合用于生成每周研报摘要推送给用户。
    """
    limit_per_stock = min(limit_per_stock, 20)
    stock_list = [s.strip() for s in stocks.split(",") if s.strip()]
    if not stock_list:
        return "错误：请提供至少一个股票名称或代码"

    all_sections = []
    total_reports = 0

    for stock in stock_list:
        data = _get(f"{SHARK_BASE}/api/report/stock/{stock}", params={"days": days, "stock_name": stock})
        if not data:
            all_sections.append(f"### {stock}\n\n⚠ 查询失败，无法获取研报数据\n")
            continue

        reports = data.get("reports", [])
        announcements = data.get("announcements", [])
        sources = data.get("sources_summary", {})
        src_desc = f"洞见研报 {sources.get('djyanbao', 0)} 篇，慧博投研 {sources.get('hibor', 0)} 篇，巨潮公告 {sources.get('cninfo', 0)} 条"

        combined = reports[:limit_per_stock]

        if not combined and not announcements:
            all_sections.append(f"### {stock}\n\n近 {days} 天暂无研报\n")
            continue

        total_reports += len(combined)

        section_lines = [f"### {stock}（{len(combined)} 篇研报）\n"]
        section_lines.append(f"数据源：{src_desc}\n")

        seen_titles = set()
        unique = []
        for r in combined:
            t = r.get("title", "")
            if t not in seen_titles:
                seen_titles.add(t)
                unique.append(r)

        for r in unique:
            title = r.get("title", "无标题")
            org = r.get("org", "")
            date = r.get("date", "")
            source = r.get("source", "")
            summary = (r.get("summary") or "")[:120]
            url = r.get("detail_url", "")
            src_tag = f"[{source}] " if source else ""
            link = f"  [详情]({url})" if url else ""
            section_lines.append(f"- **{src_tag}{title}**")
            meta_parts = []
            if org:
                meta_parts.append(f"机构: {org}")
            meta_parts.append(f"日期: {date}")
            meta_parts.append(link)
            section_lines.append("  " + " | ".join(filter(None, meta_parts)))
            if summary:
                section_lines.append(f"  摘要: {summary}")

        if announcements:
            section_lines.append(f"\n#### 巨潮公告（{len(announcements)} 条）\n")
            for a in announcements[:5]:
                section_lines.append(f"- {a.get('date', '')} {a.get('title', '')}  [详情]({a.get('detail_url', '')})")

        all_sections.append("\n".join(section_lines))

    header = f"# 研报周报（近 {days} 天）\n\n"
    header += f"查询股票: {', '.join(stock_list)} | 共 {total_reports} 篇研报\n"
    header += f"数据源：洞见研报 + 慧博投研 + 巨潮资讯\n"
    header += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"

    return header + "\n\n".join(all_sections)



if __name__ == "__main__":
    import sys

    transport = "stdio"
    port = 58178
    host = "0.0.0.0"

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--transport":
            transport = args[i + 1]
            i += 2
        elif arg == "--port":
            port = int(args[i + 1])
            i += 2
        elif arg == "--host":
            host = args[i + 1]
            i += 2
        elif arg in ("--sse", "--streamable-http"):
            transport = arg.lstrip("-")
            i += 1
        else:
            i += 1

    if transport in ("sse", "streamable-http"):
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport=transport)
    else:
        mcp.run(transport="stdio")
