"""
EMR Timestamp Archaeologist - 主分析管道
整合解析器、构建器、检测器、报告生成器，形成端到端分析管道
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from models import EmrTimestampRecord
from parser import parse_file, parse_directory
from stratum_builder import StratumBuilder, StratumMap
from detection_engine import DetectionEngine, DetectionReport, create_detection_engine
from report_renderer import ReportRenderer


# 进度回调类型
ProgressCallback = Callable[[str, int], None]


@dataclass
class PipelineConfig:
    """
    管道配置

    Attributes:
        input_path: 输入文件或目录路径
        output_dir: 输出目录路径
        llm_enabled: 是否启用 LLM 报告生成
        detectors: 启用的检测器列表（None 表示全部）
        report_format: 报告格式（html, json, both）
        verbose: 是否输出详细日志
    """
    input_path: str
    output_dir: str = "./output"
    llm_enabled: bool = True
    detectors: Optional[list[str]] = None
    report_format: str = "html"  # html, json, both
    verbose: bool = False

    def __post_init__(self) -> None:
        """验证配置有效性"""
        if not self.input_path:
            raise ValueError("input_path 不能为空")


@dataclass
class PipelineResult:
    """
    管道执行结果

    Attributes:
        config: 管道配置
        records: 解析的病历记录
        stratum_map: 地层图
        detection_report: 检测报告
        execution_time_seconds: 执行时间（秒）
        started_at: 开始时间
        completed_at: 完成时间
        errors: 执行过程中的错误列表
    """
    config: PipelineConfig
    records: list[EmrTimestampRecord] = field(default_factory=list)
    stratum_map: Optional[StratumMap] = None
    detection_report: Optional[DetectionReport] = None
    execution_time_seconds: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """是否成功完成"""
        return len(self.errors) == 0 and self.detection_report is not None

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "config": {
                "input_path": self.config.input_path,
                "output_dir": self.config.output_dir,
                "llm_enabled": self.config.llm_enabled,
                "detectors": self.config.detectors,
                "report_format": self.config.report_format,
            },
            "record_count": len(self.records),
            "stratum_map_record_count": self.stratum_map.record_count if self.stratum_map else 0,
            "detection_report": self.detection_report.to_dict() if self.detection_report else None,
            "execution_time_seconds": round(self.execution_time_seconds, 2),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "errors": self.errors,
            "success": self.success,
        }


class AnalysisPipeline:
    """
    主分析管道

    整合解析器、构建器、检测器、报告生成器，形成端到端分析流程：
    1. 解析输入数据（文件或目录）
    2. 构建时序地层图
    3. 运行异常检测
    4. 生成报告（HTML/JSON）

    支持进度回调、结果保存和加载、中断恢复等功能。
    """

    def __init__(self, config: PipelineConfig) -> None:
        """
        初始化分析管道

        Args:
            config: 管道配置
        """
        self.config = config
        self._logger = self._setup_logging()
        self._result: Optional[PipelineResult] = None

    def _setup_logging(self) -> logging.Logger:
        """配置日志"""
        logger = logging.getLogger("EMRArchaeologist")
        if self.config.verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        # 避免重复添加 handler
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def run(self) -> PipelineResult:
        """
        执行完整分析管道

        Returns:
            PipelineResult: 管道执行结果
        """
        return self.run_with_progress(None)

    def run_with_progress(
        self,
        progress_callback: Optional[ProgressCallback],
    ) -> PipelineResult:
        """
        带进度回调的管道执行

        Args:
            progress_callback: 进度回调函数，接收 (step_name, progress_pct) 参数

        Returns:
            PipelineResult: 管道执行结果
        """
        start_time = datetime.now()
        self._result = PipelineResult(
            config=self.config,
            started_at=start_time,
        )

        self._log("=" * 50)
        self._log("EMR 时间戳考古分析管道开始执行")
        self._log(f"输入路径: {self.config.input_path}")
        self._log(f"输出目录: {self.config.output_dir}")
        self._log("=" * 50)

        try:
            # Step 1: 解析数据
            self._step("正在解析病历数据...", progress_callback, 0)
            self._result.records = self._parse_input()
            self._log(f"成功解析 {len(self._result.records)} 条病历记录")
            self._report_progress(progress_callback, "数据解析完成", 25)

            if not self._result.records:
                raise ValueError("未能解析到任何病历记录")

            # Step 2: 构建地层图
            self._step("正在构建时序地层图...", progress_callback, 25)
            self._result.stratum_map = self._build_stratum_map()
            self._log(f"地层图构建完成: {self._result.stratum_map.record_count} 条记录, "
                     f"{self._result.stratum_map.chapter_count} 个章节")
            self._report_progress(progress_callback, "地层图构建完成", 50)

            # Step 3: 运行检测
            self._step("正在运行异常检测...", progress_callback, 50)
            self._result.detection_report = self._run_detection()
            self._log(f"检测完成: 发现 {self._result.detection_report.total_anomalies} 个异常")
            self._log(f"综合风险分数: {self._result.detection_report.overall_risk_score} "
                     f"({self._result.detection_report.risk_level})")
            self._report_progress(progress_callback, "异常检测完成", 75)

            # Step 4: 保存结果
            self._step("正在保存分析结果...", progress_callback, 75)
            self._save_results()
            self._report_progress(progress_callback, "结果保存完成", 90)

            # Step 5: 生成报告
            if self.config.report_format in ("html", "both"):
                self._step("正在生成 HTML 报告...", progress_callback, 90)
                self._generate_html_report()

            if self.config.report_format in ("json", "both"):
                self._step("正在生成 JSON 报告...", progress_callback, 95)
                self._generate_json_report()

            self._report_progress(progress_callback, "报告生成完成", 100)

        except Exception as e:
            error_msg = f"管道执行出错: {str(e)}"
            self._logger.error(error_msg)
            self._result.errors.append(error_msg)

        finally:
            end_time = datetime.now()
            self._result.completed_at = end_time
            self._result.execution_time_seconds = (
                end_time - start_time
            ).total_seconds()

        self._log("=" * 50)
        self._log(f"管道执行{'成功' if self._result.success else '失败'}")
        self._log(f"总耗时: {self._result.execution_time_seconds:.2f} 秒")
        self._log("=" * 50)

        return self._result

    def _parse_input(self) -> list[EmrTimestampRecord]:
        """解析输入数据"""
        input_path = Path(self.config.input_path)

        if not input_path.exists():
            raise FileNotFoundError(f"输入路径不存在: {input_path}")

        if input_path.is_file():
            self._log(f"解析文件: {input_path.name}")
            return parse_file(input_path)
        elif input_path.is_dir():
            self._log(f"解析目录: {input_path}")
            return parse_directory(input_path)
        else:
            raise ValueError(f"输入路径既不是文件也不是目录: {input_path}")

    def _build_stratum_map(self) -> StratumMap:
        """构建地层图"""
        builder = StratumBuilder()
        stratum_map = builder.build(self._result.records)

        # 添加业务时间锚点
        for record in self._result.records:
            if record.business_time:
                builder.add_anchor_line(
                    anchor_type="业务时间",
                    anchor_time=record.business_time,
                    record_id=record.record_id,
                    label=f"{record.record_type}业务时间",
                )

        return stratum_map

    def _run_detection(self) -> DetectionReport:
        """运行异常检测"""
        engine = create_detection_engine(llm_enabled=self.config.llm_enabled)
        engine.run_all_detectors(self._result.records)
        return engine.generate_report_data()

    def _save_results(self) -> None:
        """保存结果到 JSON 文件"""
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        result_file = output_dir / "pipeline_result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(self._result.to_dict(), f, indent=2, ensure_ascii=False)

        self._log(f"结果已保存到: {result_file}")

    def _generate_html_report(self) -> None:
        """生成 HTML 报告"""
        if self._result.detection_report is None:
            return

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        renderer = ReportRenderer()
        html_path = output_dir / "emr_archaeology_report.html"

        renderer.export_html(
            report=self._result.detection_report,
            output_path=str(html_path),
            stratum_map=self._result.stratum_map,
        )

        self._log(f"HTML 报告已生成: {html_path}")

    def _generate_json_report(self) -> None:
        """生成 JSON 报告"""
        if self._result.detection_report is None:
            return

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        json_path = output_dir / "detection_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._result.detection_report.to_dict(), f, indent=2, ensure_ascii=False)

        self._log(f"JSON 报告已生成: {json_path}")

    def get_intermediate_results(self) -> dict[str, Any]:
        """
        获取管道中间结果

        Returns:
            dict: 包含各阶段结果的字典
        """
        if self._result is None:
            return {}

        return {
            "records": self._result.records,
            "stratum_map": self._result.stratum_map,
            "detection_report": self._result.detection_report,
        }

    def save_results(self, output_path: str) -> None:
        """
        将结果保存到指定路径

        Args:
            output_path: 输出文件路径
        """
        if self._result is None:
            raise ValueError("管道尚未执行，请先调用 run()")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._result.to_dict(), f, indent=2, ensure_ascii=False)

        self._log(f"结果已保存到: {path}")

    @classmethod
    def load_previous_results(cls, result_path: str) -> PipelineResult:
        """
        从文件加载之前的分析结果

        Args:
            result_path: 结果文件路径

        Returns:
            PipelineResult: 加载的结果
        """
        path = Path(result_path)
        if not path.exists():
            raise FileNotFoundError(f"结果文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 重建 PipelineResult
        config = PipelineConfig(
            input_path=data["config"]["input_path"],
            output_dir=data["config"]["output_dir"],
            llm_enabled=data["config"].get("llm_enabled", True),
            detectors=data["config"].get("detectors"),
            report_format=data["config"].get("report_format", "html"),
        )

        result = PipelineResult(config=config)
        result.execution_time_seconds = data.get("execution_time_seconds", 0)
        result.started_at = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        result.completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        result.errors = data.get("errors", [])

        return result

    def validate_results(self) -> tuple[bool, list[str]]:
        """
        验证结果完整性

        Returns:
            tuple: (是否有效, 错误列表)
        """
        errors: list[str] = []

        if self._result is None:
            errors.append("管道尚未执行")
            return False, errors

        if not self._result.records:
            errors.append("病历记录为空")

        if self._result.stratum_map is None:
            errors.append("地层图为空")
        elif self._result.stratum_map.record_count == 0:
            errors.append("地层图记录数为0")

        if self._result.detection_report is None:
            errors.append("检测报告为空")

        if self._result.errors:
            errors.extend(self._result.errors)

        return len(errors) == 0, errors

    def _step(self, message: str, callback: Optional[ProgressCallback], progress: int) -> None:
        """记录步骤开始"""
        self._log(f"[{progress}%] {message}")
        if callback:
            callback(message, progress)

    def _report_progress(
        self,
        callback: Optional[ProgressCallback],
        message: str,
        progress: int,
    ) -> None:
        """报告进度"""
        if callback:
            callback(message, progress)

    def _log(self, message: str) -> None:
        """输出日志"""
        self._logger.info(message)


# 便捷函数
def run_pipeline(
    input_path: str,
    output_dir: str = "./output",
    llm_enabled: bool = True,
    report_format: str = "html",
    progress_callback: Optional[ProgressCallback] = None,
) -> PipelineResult:
    """
    便捷函数：运行完整分析管道

    Args:
        input_path: 输入文件或目录路径
        output_dir: 输出目录路径
        llm_enabled: 是否启用 LLM
        report_format: 报告格式（html, json, both）
        progress_callback: 进度回调函数

    Returns:
        PipelineResult: 管道执行结果
    """
    config = PipelineConfig(
        input_path=input_path,
        output_dir=output_dir,
        llm_enabled=llm_enabled,
        report_format=report_format,
    )

    pipeline = AnalysisPipeline(config)
    return pipeline.run_with_progress(progress_callback)


def create_pipeline_from_previous(
    result_path: str,
    new_output_dir: Optional[str] = None,
) -> AnalysisPipeline:
    """
    从之前的结果创建新管道（用于重新生成报告）

    Args:
        result_path: 之前的结果文件路径
        new_output_dir: 新的输出目录（可选）

    Returns:
        AnalysisPipeline: 新的管道实例
    """
    result = AnalysisPipeline.load_previous_results(result_path)

    if new_output_dir:
        result.config.output_dir = new_output_dir

    return AnalysisPipeline(result.config)
