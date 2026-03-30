"""
EMR Timestamp Archaeologist - 管道集成测试
测试主分析管道的完整流程
"""

from __future__ import annotations

import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    TimestampAnomaly,
    create_emr_chapter,
)
from pipeline import (
    AnalysisPipeline,
    PipelineConfig,
    PipelineResult,
    run_pipeline,
)


# 测试数据
def create_test_record(
    patient_id: str = "P001",
    visit_id: str = "V001",
    record_id: str = "R001",
    hours_offset: int = 0,
) -> EmrTimestampRecord:
    """创建测试病历记录"""
    base_time = datetime.now() + timedelta(hours=hours_offset)

    chapters = [
        create_emr_chapter(
            chapter_name="入院记录",
            created_time=base_time,
            author_id="D001",
        ),
        create_emr_chapter(
            chapter_name="病程记录",
            created_time=base_time + timedelta(hours=2),
            author_id="D001",
        ),
        create_emr_chapter(
            chapter_name="手术记录",
            created_time=base_time + timedelta(hours=5),
            author_id="D002",
        ),
    ]

    return EmrTimestampRecord(
        patient_id=patient_id,
        visit_id=visit_id,
        record_id=record_id,
        record_type="入院记录",
        chapters=chapters,
        business_time=base_time + timedelta(hours=4),
    )


def create_batch_test_records() -> list[EmrTimestampRecord]:
    """创建包含批处理痕迹的测试数据"""
    base_time = datetime.now().replace(hour=22, minute=0, second=0, microsecond=0)

    records = []
    # 5份病历在同一时间创建（批处理痕迹）
    for i in range(5):
        chapters = [
            create_emr_chapter(
                chapter_name=f"章节{j}",
                created_time=base_time,
                author_id=f"D{i}",
            )
            for j in range(3)
        ]
        records.append(EmrTimestampRecord(
            patient_id=f"P{i+10}",
            visit_id=f"V{i+10}",
            record_id=f"R{i+10}",
            record_type="批量病历",
            chapters=chapters,
        ))

    return records


def create_night_rush_records() -> list[EmrTimestampRecord]:
    """创建夜间突击补写的测试数据"""
    records = []
    base_date = datetime.now().replace(hour=2, minute=0, second=0, microsecond=0)

    # 夜间创建的多份病历
    for i in range(10):
        chapters = [
            create_emr_chapter(
                chapter_name=f"章节{j}",
                created_time=base_date + timedelta(minutes=i*5),
                author_id=f"D{i}",
            )
            for j in range(3)
        ]
        records.append(EmrTimestampRecord(
            patient_id=f"P{i+20}",
            visit_id=f"V{i+20}",
            record_id=f"R{i+20}",
            record_type="夜间突击",
            chapters=chapters,
            business_time=base_date - timedelta(hours=1),
        ))

    return records


class TestPipelineConfig:
    """测试管道配置"""

    def test_config_creation(self):
        """测试配置创建"""
        config = PipelineConfig(
            input_path="/path/to/data",
            output_dir="/output",
            llm_enabled=True,
            report_format="html",
        )

        assert config.input_path == "/path/to/data"
        assert config.output_dir == "/output"
        assert config.llm_enabled is True
        assert config.report_format == "html"

    def test_config_validation_empty_input(self):
        """测试空输入验证"""
        with pytest.raises(ValueError):
            PipelineConfig(input_path="")

    def test_config_defaults(self):
        """测试默认值"""
        config = PipelineConfig(input_path="/path/to/data")

        assert config.output_dir == "./output"
        assert config.llm_enabled is True
        assert config.detectors is None
        assert config.report_format == "html"
        assert config.verbose is False


class TestPipelineResult:
    """测试管道结果"""

    def test_result_success_property(self):
        """测试成功状态属性"""
        config = PipelineConfig(input_path="/test")

        # 无错误，有报告 = 成功
        result = PipelineResult(config=config)
        result.errors = []
        result.detection_report = object()  # mock report
        assert result.success is True

        # 有错误 = 失败
        result.errors = ["some error"]
        assert result.success is False

        # 无报告 = 失败
        result.errors = []
        result.detection_report = None
        assert result.success is False

    def test_result_to_dict(self):
        """测试结果转字典"""
        config = PipelineConfig(input_path="/test", output_dir="/output")
        result = PipelineResult(
            config=config,
            execution_time_seconds=10.5,
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 0, 10),
        )

        data = result.to_dict()

        assert data["config"]["input_path"] == "/test"
        assert data["config"]["output_dir"] == "/output"
        assert data["execution_time_seconds"] == 10.5
        # success is False because detection_report is None
        assert data["success"] is False


class TestPipelineIntegration:
    """管道集成测试"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.fixture
    def sample_data_dir(self, temp_dir):
        """创建包含示例数据的目录"""
        data_dir = temp_dir / "data"
        data_dir.mkdir()

        # 创建测试 JSON 数据
        records = [
            {
                "patient_id": f"P{i:03d}",
                "visit_id": f"V{i:03d}",
                "record_id": f"R{i:03d}",
                "record_type": "入院记录",
                "business_time": datetime.now().isoformat(),
                "chapters": [
                    {
                        "chapter_id": f"C{i:03d}_{j}",
                        "chapter_name": f"章节{j}",
                        "created_time": (
                            datetime.now() + timedelta(hours=i, minutes=j*10)
                        ).isoformat(),
                        "modified_time": (
                            datetime.now() + timedelta(hours=i, minutes=j*10 + 5)
                        ).isoformat(),
                        "author_id": f"D{i:03d}",
                        "chapter_order": j,
                    }
                    for j in range(3)
                ],
            }
            for i in range(5)
        ]

        json_path = data_dir / "test_records.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f)

        return data_dir

    def test_pipeline_with_json_file(self, temp_dir, sample_data_dir):
        """测试使用 JSON 文件运行管道"""
        json_file = sample_data_dir / "test_records.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,  # 禁用 LLM 加速测试
            report_format="json",  # 只生成 JSON
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run()

        assert result.success
        assert len(result.records) == 5
        assert result.detection_report is not None
        assert result.detection_report.total_records == 5

    def test_pipeline_with_directory(self, temp_dir, sample_data_dir):
        """测试使用目录运行管道"""
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(sample_data_dir),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="json",
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run()

        assert result.success
        assert len(result.records) >= 5

    def test_pipeline_generates_output_files(self, temp_dir, sample_data_dir):
        """测试管道生成输出文件"""
        json_file = sample_data_dir / "test_records.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="both",
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run()

        assert result.success

        # 检查输出文件
        assert (output_dir / "pipeline_result.json").exists()
        assert (output_dir / "detection_report.json").exists()
        assert (output_dir / "emr_archaeology_report.html").exists()

    def test_pipeline_with_progress_callback(self, temp_dir, sample_data_dir):
        """测试带进度回调的管道"""
        json_file = sample_data_dir / "test_records.json"
        output_dir = temp_dir / "output"

        progress_updates = []

        def progress_callback(step: str, pct: int):
            progress_updates.append((step, pct))

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="json",
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run_with_progress(progress_callback)

        assert result.success
        assert len(progress_updates) > 0

        # 检查进度单调递增
        percentages = [pct for _, pct in progress_updates]
        assert percentages == sorted(percentages)

    def test_pipeline_with_html_format(self, temp_dir, sample_data_dir):
        """测试 HTML 报告生成"""
        json_file = sample_data_dir / "test_records.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="html",
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run()

        assert result.success
        html_path = output_dir / "emr_archaeology_report.html"
        assert html_path.exists()

        # 验证 HTML 内容
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "EMR 时间戳考古报告" in content

    def test_pipeline_with_json_format(self, temp_dir, sample_data_dir):
        """测试 JSON 报告生成"""
        json_file = sample_data_dir / "test_records.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="json",
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run()

        assert result.success
        json_path = output_dir / "detection_report.json"
        assert json_path.exists()

        # 验证 JSON 内容
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "total_records" in data
            assert "overall_risk_score" in data


class TestPipelineIntermediateResults:
    """测试管道中间结果"""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.fixture
    def sample_data_dir(self, temp_dir):
        data_dir = temp_dir / "data"
        data_dir.mkdir()

        records = [
            {
                "patient_id": f"P{i:03d}",
                "visit_id": f"V{i:03d}",
                "record_id": f"R{i:03d}",
                "record_type": "测试",
                "chapters": [
                    {
                        "chapter_id": f"C{i:03d}_{j}",
                        "chapter_name": f"章节{j}",
                        "created_time": datetime.now().isoformat(),
                        "author_id": f"D{i:03d}",
                        "chapter_order": j,
                    }
                    for j in range(2)
                ],
            }
            for i in range(3)
        ]

        json_path = data_dir / "test.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f)

        return data_dir

    def test_get_intermediate_results(self, temp_dir, sample_data_dir):
        """测试获取中间结果"""
        json_file = sample_data_dir / "test.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="json",
        )

        pipeline = AnalysisPipeline(config)
        pipeline.run()

        intermediate = pipeline.get_intermediate_results()

        assert "records" in intermediate
        assert "stratum_map" in intermediate
        assert "detection_report" in intermediate
        assert len(intermediate["records"]) == 3

    def test_validate_results(self, temp_dir, sample_data_dir):
        """测试结果验证"""
        json_file = sample_data_dir / "test.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="json",
        )

        pipeline = AnalysisPipeline(config)
        pipeline.run()

        valid, errors = pipeline.validate_results()
        assert valid
        assert len(errors) == 0


class TestPipelineSaveLoad:
    """测试管道结果保存和加载"""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.fixture
    def sample_data_dir(self, temp_dir):
        data_dir = temp_dir / "data"
        data_dir.mkdir()

        records = [
            {
                "patient_id": f"P{i:03d}",
                "visit_id": f"V{i:03d}",
                "record_id": f"R{i:03d}",
                "record_type": "测试",
                "chapters": [
                    {
                        "chapter_id": f"C{i:03d}_{j}",
                        "chapter_name": f"章节{j}",
                        "created_time": datetime.now().isoformat(),
                        "author_id": f"D{i:03d}",
                        "chapter_order": j,
                    }
                    for j in range(2)
                ],
            }
            for i in range(3)
        ]

        json_path = data_dir / "test.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f)

        return data_dir

    def test_save_results(self, temp_dir, sample_data_dir):
        """测试保存结果"""
        json_file = sample_data_dir / "test.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="json",
        )

        pipeline = AnalysisPipeline(config)
        pipeline.run()

        save_path = temp_dir / "saved_result.json"
        pipeline.save_results(str(save_path))

        assert save_path.exists()

    def test_load_results(self, temp_dir, sample_data_dir):
        """测试加载结果"""
        json_file = sample_data_dir / "test.json"
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(json_file),
            output_dir=str(output_dir),
            llm_enabled=False,
            report_format="json",
        )

        pipeline = AnalysisPipeline(config)
        pipeline.run()

        save_path = temp_dir / "saved_result.json"
        pipeline.save_results(str(save_path))

        # 加载结果 - 使用 AnalysisPipeline.load_previous_results
        loaded_result = AnalysisPipeline.load_previous_results(str(save_path))

        assert loaded_result.config.input_path == str(json_file)
        # execution_time_seconds can be 0 if execution was very fast
        assert loaded_result.execution_time_seconds >= 0


class TestPipelineErrorHandling:
    """测试管道错误处理"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_nonexistent_input_file(self, temp_dir):
        """测试不存在的输入文件"""
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path="/nonexistent/file.json",
            output_dir=str(output_dir),
            llm_enabled=False,
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run()

        assert result.success is False
        assert len(result.errors) > 0

    def test_empty_directory(self, temp_dir):
        """测试空目录"""
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()
        output_dir = temp_dir / "output"

        config = PipelineConfig(
            input_path=str(empty_dir),
            output_dir=str(output_dir),
            llm_enabled=False,
        )

        pipeline = AnalysisPipeline(config)
        result = pipeline.run()

        # 空目录会解析为0条记录，导致失败
        assert result.success is False or len(result.records) == 0
