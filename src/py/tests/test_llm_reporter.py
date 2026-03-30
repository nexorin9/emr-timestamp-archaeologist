"""
EMR Timestamp Archaeologist - LLM Reporter 测试
使用 mock 测试，不调用真实 API
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from llm_reporter import (
    LLMReporter,
    LLMReport,
    DepartmentRisk,
    create_llm_reporter,
    generate_mock_report_data,
)


class TestLLMReporter:
    """LLMReporter 测试类"""

    @pytest.fixture
    def mock_api_key(self):
        """Mock API key"""
        return "test-api-key-12345"

    @pytest.fixture
    def reporter(self, mock_api_key):
        """创建 LLMReporter 实例"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                return LLMReporter(api_key=mock_api_key, model="gpt-4o-mini")

    @pytest.fixture
    def mock_report_data(self):
        """Mock 检测报告数据"""
        return generate_mock_report_data()

    def test_reporter_initialization(self, mock_api_key):
        """测试 LLMReporter 初始化"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = LLMReporter(api_key=mock_api_key, model="gpt-4o-mini")

                assert reporter.api_key == mock_api_key
                assert reporter.model == "gpt-4o-mini"
                assert reporter.max_retries == 3
                assert reporter.retry_delay == 1.0

    def test_reporter_initialization_custom_params(self, mock_api_key):
        """测试自定义参数的初始化"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = LLMReporter(
                    api_key=mock_api_key,
                    model="claude-sonnet-4-20250514",
                    max_retries=5,
                    retry_delay=2.0,
                )

                assert reporter.max_retries == 5
                assert reporter.retry_delay == 2.0

    def test_detect_provider_openai(self, mock_api_key):
        """测试 OpenAI 提供商检测"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", False):
                reporter = LLMReporter(api_key=mock_api_key, model="gpt-4o-mini")
                assert reporter._provider == "openai"

    def test_detect_provider_anthropic(self, mock_api_key):
        """测试 Anthropic 提供商检测"""
        with patch("llm_reporter.HAS_OPENAI", False):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = LLMReporter(api_key=mock_api_key, model="claude-sonnet-4-20250514")
                assert reporter._provider == "anthropic"

    def test_build_system_prompt(self, reporter):
        """测试系统提示词构建"""
        system_prompt = reporter.build_system_prompt()

        assert "考古学家" in system_prompt
        assert "病历时间戳" in system_prompt
        assert "地层学" in system_prompt
        assert "文物鉴定" in system_prompt
        assert len(system_prompt) > 400  # 确保有实质内容

    def test_build_user_prompt_basic(self, reporter, mock_report_data):
        """测试用户提示词构建（基础信息）"""
        user_prompt = reporter.build_user_prompt(mock_report_data, include_details=False)

        assert "150" in user_prompt  # total_records
        assert "23" in user_prompt  # total_anomalies
        assert "58.5" in user_prompt  # overall_risk_score
        assert "高" in user_prompt  # risk_level

    def test_build_user_prompt_with_details(self, reporter, mock_report_data):
        """测试用户提示词构建（含详情）"""
        user_prompt = reporter.build_user_prompt(mock_report_data, include_details=True)

        assert "Top 10" in user_prompt
        assert "夜间突击补写" in user_prompt
        assert "批处理痕迹" in user_prompt

    def test_generate_summary_table(self, reporter, mock_report_data):
        """测试异常汇总表格生成"""
        table = reporter.generate_summary_table(mock_report_data)

        assert "## 异常汇总表" in table
        assert "总体概况" in table
        assert "150" in table
        assert "23" in table
        assert "58.5" in table
        assert "高" in table

    def test_generate_summary_table_type_distribution(self, reporter, mock_report_data):
        """测试异常类型分布"""
        table = reporter.generate_summary_table(mock_report_data)

        assert "批处理痕迹" in table
        assert "夜间突击补写" in table
        assert "时间线矛盾" in table

    def test_generate_summary_table_severity_distribution(self, reporter, mock_report_data):
        """测试严重程度分布"""
        table = reporter.generate_summary_table(mock_report_data)

        assert "严重" in table
        assert "中等" in table
        assert "轻微" in table

    def test_generate_department_ranking_with_data(self, reporter):
        """测试科室风险排行（有数据）"""
        report_data = {
            "detector_results": [
                {
                    "detector_name": "night",
                    "anomalies": [
                        {
                            "anomaly_type": "night_rush",
                            "severity": 9,
                            "description": "夜间异常",
                            "affected_records": ["R001"],
                            "evidence": {"department": "内科", "night_modification_count": 15},
                        },
                        {
                            "anomaly_type": "night_rush",
                            "severity": 8,
                            "description": "夜间异常",
                            "affected_records": ["R002"],
                            "evidence": {"department": "外科", "night_modification_count": 10},
                        },
                    ],
                }
            ]
        }

        ranking = reporter.generate_department_ranking(report_data)

        assert "## 科室风险排行" in ranking
        assert "内科" in ranking
        assert "外科" in ranking

    def test_generate_department_ranking_no_data(self, reporter):
        """测试科室风险排行（无数据）"""
        report_data = {"detector_results": []}

        ranking = reporter.generate_department_ranking(report_data)

        assert "## 科室风险排行" in ranking
        assert "暂无科室级别数据" in ranking

    def test_generate_recommendations_batch_processing(self, reporter):
        """测试批处理痕迹整改建议"""
        report_data = {
            "overall_risk_score": 60,
            "risk_level": "高",
            "anomalies_by_type": {
                "batch_processing": 10,
            },
        }

        recommendations = reporter.generate_recommendations(report_data)

        assert "## 考古报告审批意见" in recommendations
        assert "批处理痕迹" in recommendations
        assert "10例" in recommendations

    def test_generate_recommendations_night_rush(self, reporter):
        """测试夜间突击补写整改建议"""
        report_data = {
            "overall_risk_score": 75,
            "risk_level": "很高",
            "anomalies_by_type": {
                "night_rush": 15,
            },
        }

        recommendations = reporter.generate_recommendations(report_data)

        assert "夜间突击补写" in recommendations
        assert "15例" in recommendations
        assert "立即开展专项检查" in recommendations

    def test_generate_recommendations_all_types(self, reporter):
        """测试各类型异常的建议"""
        report_data = {
            "overall_risk_score": 85,
            "risk_level": "极高",
            "anomalies_by_type": {
                "batch_processing": 5,
                "night_rush": 8,
                "time_contradiction": 3,
                "suspicious_sequence": 2,
                "anchor_violation": 1,
            },
        }

        recommendations = reporter.generate_recommendations(report_data)

        assert "批处理痕迹" in recommendations
        assert "夜间突击补写" in recommendations
        assert "时间线矛盾" in recommendations
        assert "异常修改序列" in recommendations
        assert "锚点违规" in recommendations

    def test_generate_recommendations_high_risk(self, reporter):
        """测试高风险整改建议"""
        report_data = {
            "overall_risk_score": 80,
            "risk_level": "很高",
            "anomalies_by_type": {},
        }

        recommendations = reporter.generate_recommendations(report_data)

        assert "立即开展专项检查" in recommendations
        assert "上报主管部门" in recommendations

    def test_generate_recommendations_medium_risk(self, reporter):
        """测试中等风险整改建议"""
        report_data = {
            "overall_risk_score": 45,
            "risk_level": "中等",
            "anomalies_by_type": {},
        }

        recommendations = reporter.generate_recommendations(report_data)

        assert "纳入常规质控" in recommendations

    def test_generate_recommendations_low_risk(self, reporter):
        """测试低风险整改建议"""
        report_data = {
            "overall_risk_score": 15,
            "risk_level": "低",
            "anomalies_by_type": {},
        }

        recommendations = reporter.generate_recommendations(report_data)

        assert "继续保持当前质控措施" in recommendations

    @patch.object(LLMReporter, "_get_client")
    def test_generate_narrative_openai(self, mock_get_client, reporter):
        """测试 OpenAI 叙述报告生成"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="这是一份考古学风格的报告"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        report_data = generate_mock_report_data()
        narrative = reporter.generate_narrative(report_data)

        assert "考古学风格的报告" in narrative
        mock_client.chat.completions.create.assert_called_once()

    @patch.object(LLMReporter, "_get_client")
    def test_generate_narrative_anthropic(self, mock_get_client):
        """测试 Anthropic 叙述报告生成"""
        with patch("llm_reporter.HAS_OPENAI", False):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = LLMReporter(api_key="test-key", model="claude-sonnet-4-20250514")

                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="这是一份考古学风格的报告")]
                mock_client.messages.create.return_value = mock_response
                mock_get_client.return_value = mock_client

                report_data = generate_mock_report_data()
                narrative = reporter.generate_narrative(report_data)

                assert "考古学风格的报告" in narrative
                mock_client.messages.create.assert_called_once()

    def test_generate_full_report_structure(self, reporter, mock_report_data):
        """测试完整报告结构"""
        with patch.object(reporter, "generate_narrative") as mock_narrative:
            mock_narrative.return_value = "这是叙述报告内容"

            report = reporter.generate_full_report(mock_report_data)

            assert isinstance(report, LLMReport)
            assert report.narrative == "这是叙述报告内容"
            assert "异常汇总表" in report.summary_table
            assert "科室风险排行" in report.department_ranking
            assert "考古报告审批意见" in report.recommendations
            assert "叙述报告内容" in report.full_report
            assert report.generated_at is not None

    def test_llm_report_to_dict(self):
        """测试 LLMReport.to_dict()"""
        report = LLMReport(
            narrative="叙述内容",
            summary_table="汇总表格",
            department_ranking="科室排行",
            recommendations="建议",
            full_report="完整报告",
        )

        result = report.to_dict()

        assert result["narrative"] == "叙述内容"
        assert result["summary_table"] == "汇总表格"
        assert result["department_ranking"] == "科室排行"
        assert result["recommendations"] == "建议"
        assert result["full_report"] == "完整报告"
        assert result["generated_at"] is not None

    def test_call_llm_with_retry_success(self, reporter):
        """测试带重试的成功调用"""
        with patch.object(reporter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="成功响应"))]
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            messages = [{"role": "user", "content": "测试消息"}]
            result = reporter.call_llm_with_retry(messages)

            assert result == "成功响应"
            mock_client.chat.completions.create.assert_called_once()

    def test_call_llm_with_retry_retry_on_error(self, reporter):
        """测试错误重试"""
        with patch.object(reporter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            # 前两次失败，第三次成功
            mock_client.chat.completions.create.side_effect = [
                Exception("Network error"),
                Exception("Timeout"),
                MagicMock(choices=[MagicMock(message=MagicMock(content="成功"))]),
            ]
            mock_get_client.return_value = mock_client

            messages = [{"role": "user", "content": "测试消息"}]
            result = reporter.call_llm_with_retry(messages, max_tokens=1000)

            assert result == "成功"
            assert mock_client.chat.completions.create.call_count == 3

    def test_call_llm_with_retry_all_fail(self, reporter):
        """测试所有重试都失败"""
        with patch.object(reporter, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("Persistent error")
            mock_get_client.return_value = mock_client

            messages = [{"role": "user", "content": "测试消息"}]

            with pytest.raises(Exception) as exc_info:
                reporter.call_llm_with_retry(messages)

            assert "Persistent error" in str(exc_info.value)
            assert mock_client.chat.completions.create.call_count == 3  # max_retries = 3

    def test_create_llm_reporter(self):
        """测试便捷构造函数"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = create_llm_reporter(api_key="test-key", model="gpt-4o-mini")

                assert isinstance(reporter, LLMReporter)
                assert reporter.api_key == "test-key"
                assert reporter.model == "gpt-4o-mini"

    def test_generate_mock_report_data(self):
        """测试模拟数据生成"""
        data = generate_mock_report_data()

        assert data["total_records"] == 150
        assert data["total_anomalies"] == 23
        assert data["overall_risk_score"] == 58.5
        assert data["risk_level"] == "高"
        assert "batch_processing" in data["anomalies_by_type"]
        assert "night_rush" in data["anomalies_by_type"]
        assert len(data["top_anomalies"]) == 3
        assert "summary_stats" in data


class TestDepartmentRisk:
    """DepartmentRisk 数据类测试"""

    def test_department_risk_creation(self):
        """测试 DepartmentRisk 创建"""
        dept_risk = DepartmentRisk(
            department="内科",
            anomaly_count=10,
            risk_score=75.5,
            primary_anomaly_types=["night_rush", "batch_processing"],
        )

        assert dept_risk.department == "内科"
        assert dept_risk.anomaly_count == 10
        assert dept_risk.risk_score == 75.5
        assert len(dept_risk.primary_anomaly_types) == 2


class TestAnomalyTypeMapping:
    """异常类型映射测试"""

    def test_anomaly_type_names(self):
        """测试异常类型中文名称映射"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = LLMReporter(api_key="test-key")

                # 直接测试映射
                mapping = reporter.ANOMALY_TYPE_NAMES

                # 验证所有异常类型都有中文名称
                from models import AnomalyType
                for atype in AnomalyType:
                    assert atype in mapping or atype.value in mapping


class TestSeverityLabels:
    """严重程度标签测试"""

    def test_severity_labels(self):
        """测试严重程度标签"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = LLMReporter(api_key="test-key")
                labels = reporter.SEVERITY_LABELS

                # 验证标签覆盖了所有范围
                all_ranges = []
                for (low, high), label in labels.items():
                    all_ranges.extend(range(low, high + 1))

                # 应该覆盖 0-10
                assert set(all_ranges) == set(range(0, 11))

    def test_severity_label_lookup(self):
        """测试严重程度标签查询"""
        with patch("llm_reporter.HAS_OPENAI", True):
            with patch("llm_reporter.HAS_ANTHROPIC", True):
                reporter = LLMReporter(api_key="test-key")
                # 测试各严重程度对应的标签
                assert reporter.SEVERITY_LABELS.get((8, 10)) == "严重"
                assert reporter.SEVERITY_LABELS.get((5, 7)) == "中等"
                assert reporter.SEVERITY_LABELS.get((3, 4)) == "轻微"
                assert reporter.SEVERITY_LABELS.get((0, 2)) == "提示"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])