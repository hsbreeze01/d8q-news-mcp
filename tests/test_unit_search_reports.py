"""Unit tests for d8q_search_reports — mock external API calls."""

import sys
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, "/Users/lancer.zhang/ProjectNIO/d8q-news-mcp")
import server

d8q_search_reports = server.d8q_search_reports


def _make_report(title="测试研报", org="华泰证券", date=None, category="券商研报",
                 summary="这是一篇摘要", report_id=1):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return {
        "id": report_id, "title": title, "category": category, "org": org,
        "date": date, "summary": summary,
        "detail_url": f"https://www.djyanbao.com/report/detail?id={report_id}",
    }


def _api_response(reports):
    return {"keyword": "test", "total": len(reports), "page": 1, "limit": 20, "reports": reports}


class TestInputValidation:
    """Test input parsing and validation."""

    @patch.object(server, "_get", return_value=_api_response([]))
    def test_empty_stocks_string(self, mock_get):
        result = d8q_search_reports(stocks="")
        assert "错误" in result
        mock_get.assert_not_called()

    @patch.object(server, "_get", return_value=_api_response([]))
    def test_whitespace_only_stocks(self, mock_get):
        result = d8q_search_reports(stocks="  ,  ,  ")
        assert "错误" in result
        mock_get.assert_not_called()

    @patch.object(server, "_get", return_value=_api_response([_make_report()]))
    def test_single_stock(self, mock_get):
        result = d8q_search_reports(stocks="宁德时代")
        assert "宁德时代" in result
        assert mock_get.call_count == 1

    @patch.object(server, "_get", return_value=_api_response([_make_report()]))
    def test_multiple_stocks_comma_separated(self, mock_get):
        d8q_search_reports(stocks="宁德时代,比亚迪,600036")
        assert mock_get.call_count == 3

    @patch.object(server, "_get", return_value=_api_response([_make_report()]))
    def test_stocks_with_spaces_trimmed(self, mock_get):
        d8q_search_reports(stocks="  宁德时代 ,  比亚迪  ")
        assert mock_get.call_count == 2


class TestDateFiltering:
    """Reports within date range included, outside excluded."""

    @patch.object(server, "_get")
    def test_reports_within_range(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="今日研报", date=today),
            _make_report(title="昨日研报", date=yesterday),
        ])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "今日研报" in result
        assert "昨日研报" in result
        assert "2 篇研报" in result

    @patch.object(server, "_get")
    def test_reports_outside_range_excluded(self, mock_get):
        old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="旧研报", date=old_date),
        ])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "旧研报" not in result
        assert "暂无研报" in result

    @patch.object(server, "_get")
    def test_boundary_exact_cutoff_included(self, mock_get):
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="边界研报", date=cutoff),
        ])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "边界研报" in result

    @patch.object(server, "_get")
    def test_default_days_is_7(self, mock_get):
        eight_days_ago = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
        six_days_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="8天前", date=eight_days_ago),
            _make_report(title="6天前", date=six_days_ago),
        ])
        result = d8q_search_reports(stocks="测试")
        assert "6天前" in result
        assert "8天前" not in result

    @patch.object(server, "_get")
    def test_days_30(self, mock_get):
        twenty_nine = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
        thirty_one = (datetime.now() - timedelta(days=31)).strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="29天前", date=twenty_nine),
            _make_report(title="31天前", date=thirty_one),
        ])
        result = d8q_search_reports(stocks="测试", days=30)
        assert "29天前" in result
        assert "31天前" not in result


class TestLimitPerStock:
    """Result count limiting per stock."""

    @patch.object(server, "_get")
    def test_default_limit_10(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title=f"研报{i}", date=today) for i in range(20)
        ])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "10 篇研报" in result

    @patch.object(server, "_get")
    def test_custom_limit(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title=f"研报{i}", date=today) for i in range(10)
        ])
        result = d8q_search_reports(stocks="测试", days=7, limit_per_stock=3)
        assert "3 篇研报" in result

    @patch.object(server, "_get")
    def test_limit_clamped_to_20(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title=f"研报{i}", date=today) for i in range(25)
        ])
        result = d8q_search_reports(stocks="测试", days=7, limit_per_stock=100)
        assert "20 篇研报" in result


class TestAPIFailure:
    """Error handling when external API fails."""

    @patch.object(server, "_get", return_value=None)
    def test_api_returns_none(self, mock_get):
        result = d8q_search_reports(stocks="测试", days=7)
        assert "查询失败" in result

    @patch.object(server, "_get")
    def test_partial_failure_shows_both(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.side_effect = [
            None,
            _api_response([_make_report(title="成功研报", date=today)]),
        ]
        result = d8q_search_reports(stocks="失败股,成功股", days=7)
        assert "查询失败" in result
        assert "成功研报" in result


class TestOutputFormat:
    """Structure and content of the output string."""

    @patch.object(server, "_get")
    def test_markdown_header(self, mock_get):
        mock_get.return_value = _api_response([])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "# 研报周报（近 7 天）" in result
        assert "生成时间:" in result

    @patch.object(server, "_get")
    def test_stock_section_with_count(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="研报A", date=today),
            _make_report(title="研报B", date=today),
        ])
        result = d8q_search_reports(stocks="测试股", days=7)
        assert "### 测试股（2 篇研报）" in result

    @patch.object(server, "_get")
    def test_category_grouping(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="研报A", date=today, category="券商研报"),
            _make_report(title="研报B", date=today, category="机构调研"),
        ])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "#### 券商研报" in result
        assert "#### 机构调研" in result

    @patch.object(server, "_get")
    def test_total_count_across_stocks(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.side_effect = [
            _api_response([_make_report(title="A1", date=today), _make_report(title="A2", date=today)]),
            _api_response([_make_report(title="B1", date=today)]),
        ]
        result = d8q_search_reports(stocks="股A,股B", days=7)
        assert "共 3 篇研报" in result

    @patch.object(server, "_get")
    def test_detail_link_included(self, mock_get):
        today = datetime.now().strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([
            _make_report(title="带链接研报", date=today, report_id=12345),
        ])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "djyanbao.com/report/detail?id=12345" in result

    @patch.object(server, "_get")
    def test_no_reports_message(self, mock_get):
        old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        mock_get.return_value = _api_response([_make_report(date=old)])
        result = d8q_search_reports(stocks="测试", days=7)
        assert "近 7 天暂无研报" in result

    @patch.object(server, "_get")
    def test_stock_list_in_header(self, mock_get):
        mock_get.return_value = _api_response([])
        result = d8q_search_reports(stocks="宁德时代,比亚迪,招商银行", days=7)
        assert "宁德时代, 比亚迪, 招商银行" in result
