"""
EMR Timestamp Archaeologist - 报告渲染器测试
"""

import json
import tempfile
import os
from datetime import datetime
from pathlib import Path

import pytest

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    TimestampAnomaly,
    create_emr_chapter,
    create_timestamp_anomaly,
)
from detection_engine import DetectionReport, DetectorResult
from stratum_builder import StratumMap, StratumLayer, StratumEntry, build_stratum_map
from report_renderer import (
    ReportRenderer,
    RenderOptions,
    render_report,
    ANOMALY_TYPE_NAMES,
    RISK_LEVEL_COLORS,
)


class TestReportRendererInit:
    """测试 ReportRenderer 初始化"""

    def test_init_default(self):
        """测试默认初始化"""
        renderer = ReportRenderer()
        assert renderer.template_dir is None
        assert renderer._render_options.include_css is True
        assert renderer._render_options.include_js is True

    def test_init_with_template_dir(self):
        """测试指定模板目录"""
        renderer = ReportRenderer("/some/path")
        assert renderer.template_dir == "/some/path"


class TestRenderOptions:
    """测试 RenderOptions"""

    def test_default_options(self):
        """测试默认选项"""
        opts = RenderOptions()
        assert opts.include_css is True
        assert opts.include_js is True
        assert opts.interactive is True
        assert opts.dark_mode is False

    def test_custom_options(self):
        """测试自定义选项"""
        opts = RenderOptions(include_css=False, dark_mode=True)
        assert opts.include_css is False
        assert opts.dark_mode is True


class TestRenderRiskDashboard:
    """测试风险仪表盘渲染"""

    def test_risk_dashboard_empty_report(self):
        """测试空报告"""
        renderer = ReportRenderer()
        report = DetectionReport(
            total_records=0,
            total_anomalies=0,
            overall_risk_score=0.0,
            risk_level="极低",
        )
        result = renderer.render_risk_dashboard(report)
        assert "<svg" in result
        assert "风险分数" in result or "score-label" in result

    def test_risk_dashboard_high_risk(self):
        """测试高风险"""
        renderer = ReportRenderer()
        report = DetectionReport(
            total_records=100,
            total_anomalies=20,
            overall_risk_score=85.5,
            risk_level="很高",
        )
        result = renderer.render_risk_dashboard(report)
        assert "<svg" in result
        assert "85" in result or "85.5" in result


class TestRenderAnomalyTimeline:
    """测试异常时间线渲染"""

    def test_timeline_empty(self):
        """测试空时间线"""
        renderer = ReportRenderer()
        result = renderer.render_anomaly_timeline([])
        assert "empty-state" in result

    def test_timeline_with_anomalies(self):
        """测试有时间线"""
        renderer = ReportRenderer()
        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING,
                7,
                "Test anomaly 1",
                ["rec1", "rec2"],
            ),
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH,
                9,
                "Test anomaly 2",
                ["rec3"],
            ),
        ]
        result = renderer.render_anomaly_timeline(anomalies)
        assert "<svg" in result
        assert "批处理痕迹" in result or "batch_processing" in result.lower()


class TestRenderBatchHeatmap:
    """测试批处理热力图"""

    def test_heatmap_empty(self):
        """测试空热力图"""
        renderer = ReportRenderer()
        result = renderer.render_batch_heatmap([])
        assert "empty-state" in result

    def test_heatmap_with_batch_anomalies(self):
        """测试有批处理异常"""
        renderer = ReportRenderer()
        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.BATCH_PROCESSING,
                8,
                "Batch processing detected",
                ["rec1", "rec2", "rec3", "rec4", "rec5"],
            ),
        ]
        result = renderer.render_batch_heatmap(anomalies)
        assert "<svg" in result


class TestRenderNightActivityChart:
    """测试夜间活动图"""

    def test_night_chart_empty(self):
        """测试空夜间图"""
        renderer = ReportRenderer()
        result = renderer.render_night_activity_chart([])
        assert "empty-state" in result

    def test_night_chart_with_anomalies(self):
        """测试有夜间异常"""
        renderer = ReportRenderer()
        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.NIGHT_RUSH,
                6,
                "Night activity detected",
                ["rec1", "rec2"],
                evidence={"hours": [22, 23, 1, 2, 3]},
            ),
        ]
        result = renderer.render_night_activity_chart(anomalies)
        assert "<svg" in result


class TestRenderAnomalyList:
    """测试异常列表渲染"""

    def test_anomaly_list_empty(self):
        """测试空列表"""
        renderer = ReportRenderer()
        result = renderer.render_anomaly_list([])
        assert "empty-state" in result

    def test_anomaly_list_with_anomalies(self):
        """测试有异常"""
        renderer = ReportRenderer()
        anomalies = [
            create_timestamp_anomaly(
                AnomalyType.TIME_CONTRADICTION,
                9,
                "Time contradiction in medical record",
                ["rec1", "rec2", "rec3"],
                evidence={"anchor_type": "surgery_start"},
            ),
        ]
        result = renderer.render_anomaly_list(anomalies)
        assert "anomaly-card" in result
        assert "时间线矛盾" in result


class TestRenderStratumMap:
    """测试地层图渲染"""

    def test_stratum_map_empty(self):
        """测试空地层图"""
        renderer = ReportRenderer()
        stratum_map = StratumMap()
        result = renderer.render_stratum_map(stratum_map)
        assert "<svg" in result

    def test_stratum_map_with_data(self):
        """测试有数据的地层图"""
        renderer = ReportRenderer()

        # 创建测试记录
        chapters = [
            create_emr_chapter("病程记录", datetime(2024, 1, 15, 8, 0), "doctor1", chapter_order=0),
            create_emr_chapter("手术记录", datetime(2024, 1, 15, 10, 0), "doctor1", chapter_order=1),
        ]
        record = EmrTimestampRecord(
            patient_id="P001",
            visit_id="V001",
            record_id="R001",
            record_type="入院记录",
            chapters=chapters,
        )

        stratum_map = build_stratum_map([record])
        result = renderer.render_stratum_map(stratum_map)
        assert "<svg" in result
        assert "stratum-map" in result


class TestRenderFullReport:
    """测试完整报告渲染"""

    def test_full_report_basic(self):
        """测试基本完整报告"""
        renderer = ReportRenderer()

        report = DetectionReport(
            total_records=50,
            total_anomalies=5,
            overall_risk_score=35.0,
            risk_level="低",
            anomalies_by_type={"batch_processing": 2, "night_rush": 3},
            anomalies_by_severity={"严重 (8-10)": 1, "中等 (5-7)": 4},
            top_anomalies=[],
            detector_results=[],
            summary_stats={},
        )

        result = renderer.render_full_report(report)
        assert "<!DOCTYPE html>" in result
        assert "EMR 时间戳考古报告" in result
        assert "风险概览" in result
        assert "异常详情" in result

    def test_full_report_with_stratum_map(self):
        """测试带地层图的完整报告"""
        renderer = ReportRenderer()

        chapters = [
            create_emr_chapter("病程记录", datetime(2024, 1, 15, 8, 0), "doctor1"),
        ]
        record = EmrTimestampRecord(
            patient_id="P001",
            visit_id="V001",
            record_id="R001",
            record_type="入院记录",
            chapters=chapters,
        )
        stratum_map = build_stratum_map([record])

        report = DetectionReport(
            total_records=1,
            total_anomalies=0,
            overall_risk_score=0.0,
            risk_level="极低",
        )

        result = renderer.render_full_report(report, stratum_map)
        assert "时序地层图" in result
        assert "stratum-map" in result

    def test_full_report_without_css(self):
        """测试不带 CSS 的报告"""
        renderer = ReportRenderer()
        opts = RenderOptions(include_css=False)

        report = DetectionReport(
            total_records=10,
            total_anomalies=2,
            overall_risk_score=25.0,
            risk_level="低",
        )

        result = renderer.render_full_report(report, options=opts)
        assert "<!DOCTYPE html>" in result
        assert "<style>" not in result


class TestExportHtml:
    """测试 HTML 导出"""

    def test_export_html_basic(self):
        """测试基本导出"""
        renderer = ReportRenderer()

        report = DetectionReport(
            total_records=10,
            total_anomalies=3,
            overall_risk_score=40.0,
            risk_level="中等",
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            temp_path = f.name

        try:
            renderer.export_html(report, temp_path)
            assert os.path.exists(temp_path)
            with open(temp_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            assert "EMR 时间戳考古报告" in content
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_export_html_creates_directory(self):
        """测试导出时创建目录"""
        renderer = ReportRenderer()

        report = DetectionReport(
            total_records=5,
            total_anomalies=1,
            overall_risk_score=20.0,
            risk_level="低",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "subdir", "report.html")
            renderer.export_html(report, output_path)
            assert os.path.exists(output_path)


class TestExportPdf:
    """测试 PDF 导出"""

    def test_export_pdf_raises_when_no_library(self):
        """测试无 PDF 库时抛出正确错误"""
        import builtins

        renderer = ReportRenderer()

        report = DetectionReport(
            total_records=5,
            total_anomalies=1,
            overall_risk_score=20.0,
            risk_level="低",
        )

        # 保存原始 import
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'weasyprint' or name == 'playwright':
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            temp_path = f.name

        try:
            builtins.__import__ = mock_import
            with pytest.raises(ImportError) as exc_info:
                renderer.export_pdf(report, temp_path)
            assert "weasyprint" in str(exc_info.value) or "playwright" in str(exc_info.value)
        finally:
            builtins.__import__ = original_import
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestConvenienceFunction:
    """测试便捷函数"""

    def test_render_report_html(self):
        """测试 render_report 函数"""
        report = DetectionReport(
            total_records=10,
            total_anomalies=2,
            overall_risk_score=30.0,
            risk_level="低",
        )

        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            temp_path = f.name

        try:
            render_report(report, temp_path)
            assert os.path.exists(temp_path)
            with open(temp_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestConstants:
    """测试常量定义"""

    def test_anomaly_type_names(self):
        """测试异常类型名称映射"""
        assert "batch_processing" in ANOMALY_TYPE_NAMES
        assert "night_rush" in ANOMALY_TYPE_NAMES
        assert ANOMALY_TYPE_NAMES["batch_processing"] == "批处理痕迹"

    def test_risk_level_colors(self):
        """测试风险等级颜色"""
        assert "极低" in RISK_LEVEL_COLORS
        assert "极高" in RISK_LEVEL_COLORS
        assert RISK_LEVEL_COLORS["极高"] == "#F44336"


class TestEmbeddedCssJs:
    """测试嵌入式 CSS 和 JS"""

    def test_embedded_css(self):
        """测试 CSS 嵌入"""
        renderer = ReportRenderer()
        css = renderer._get_embedded_css()
        assert "<style>" in css
        assert "body" in css
        assert ".report-header" in css

    def test_embedded_js(self):
        """测试 JS 嵌入"""
        renderer = ReportRenderer()
        js = renderer._get_embedded_js()
        assert "<script>" in js
        assert "anomaly-card" in js
        assert "smooth" in js


class TestReportRendererSetOptions:
    """测试设置渲染选项"""

    def test_set_options(self):
        """测试设置选项"""
        renderer = ReportRenderer()
        opts = RenderOptions(include_css=False, interactive=False)
        renderer.set_options(opts)
        assert renderer._render_options.include_css is False
        assert renderer._render_options.interactive is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
