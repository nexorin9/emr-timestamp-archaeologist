"""
EMR Timestamp Archaeologist - 时序地层图构建器
将病历时间戳记录转换为可视化地层图数据结构
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from models import EmrChapter, EmrTimestampRecord, StratumEntry


@dataclass
class AnchorLine:
    """
    业务时间锚点 - 表示病历中的关键业务时间节点

    Attributes:
        anchor_type: 锚点类型（如"手术开始"、"入院时间"）
        anchor_time: 锚点时间
        record_id: 关联的病历记录ID
        label: 锚点标签（用于显示）
    """
    anchor_type: str
    anchor_time: datetime
    record_id: str
    label: str = ""

    def __post_init__(self) -> None:
        """设置默认值"""
        if not self.label:
            self.label = self.anchor_type


@dataclass
class StratumLayer:
    """
    地层 - 表示同一时间层级的所有章节

    Attributes:
        layer_number: 地层序号（越小越早）
        entries: 该层包含的地层条目
        start_time: 该层起始时间
        end_time: 该层结束时间
    """
    layer_number: int
    entries: list[StratumEntry] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def add_entry(self, entry: StratumEntry) -> None:
        """添加地层条目"""
        self.entries.append(entry)

    def get_time_range(self) -> tuple[Optional[datetime], Optional[datetime]]:
        """获取该层的时间范围"""
        if not self.entries:
            return None, None
        timestamps = [e.timestamp for e in self.entries]
        return min(timestamps), max(timestamps)


@dataclass
class StratumMap:
    """
    地层图 - 病历时间戳的完整地层表示

    Attributes:
        records: 按 record_id 分组的病历记录
        all_timestamps: 全局排序的所有时间戳
        layers: 地层列表（按时间顺序排列）
        anchor_lines: 业务时间锚点列表
        record_count: 记录总数
        chapter_count: 章节总数
    """
    records: dict[str, EmrTimestampRecord] = field(default_factory=dict)
    all_timestamps: list[datetime] = field(default_factory=list)
    layers: list[StratumLayer] = field(default_factory=list)
    anchor_lines: list[AnchorLine] = field(default_factory=list)
    record_count: int = 0
    chapter_count: int = 0

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "record_count": self.record_count,
            "chapter_count": self.chapter_count,
            "all_timestamps": [ts.isoformat() for ts in self.all_timestamps],
            "layers": [
                {
                    "layer_number": layer.layer_number,
                    "start_time": layer.start_time.isoformat() if layer.start_time else None,
                    "end_time": layer.end_time.isoformat() if layer.end_time else None,
                    "entries": [
                        {
                            "record_id": e.record_id,
                            "chapter_id": e.chapter_id,
                            "timestamp": e.timestamp.isoformat(),
                            "stratum_layer": e.stratum_layer,
                            "anomaly_flags": e.anomaly_flags,
                        }
                        for e in layer.entries
                    ],
                }
                for layer in self.layers
            ],
            "anchor_lines": [
                {
                    "anchor_type": a.anchor_type,
                    "anchor_time": a.anchor_time.isoformat(),
                    "record_id": a.record_id,
                    "label": a.label,
                }
                for a in self.anchor_lines
            ],
            "records": {
                rid: {
                    "patient_id": r.patient_id,
                    "visit_id": r.visit_id,
                    "record_id": r.record_id,
                    "record_type": r.record_type,
                    "business_time": r.business_time.isoformat() if r.business_time else None,
                    "chapters": [
                        {
                            "chapter_id": c.chapter_id,
                            "chapter_name": c.chapter_name,
                            "chapter_order": c.chapter_order,
                            "created_time": c.created_time.isoformat(),
                            "modified_time": c.modified_time.isoformat(),
                            "author_id": c.author_id,
                        }
                        for c in r.chapters
                    ],
                }
                for rid, r in self.records.items()
            },
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        """导出为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_visualization_data(self) -> dict:
        """
        生成 HTML 可视化所需的 JSON 数据结构

        Returns:
            包含时间轴、章节层、业务锚点、异常标记的字典
        """
        # 构建时间轴数据
        if self.all_timestamps:
            min_time = min(self.all_timestamps)
            max_time = max(self.all_timestamps)
            time_span_seconds = (max_time - min_time).total_seconds()
        else:
            min_time = datetime.now()
            max_time = datetime.now()
            time_span_seconds = 1

        # 生成时间刻度
        time_scale = []
        if time_span_seconds > 0:
            # 生成约10个时间刻度点
            num_ticks = min(10, max(3, len(self.all_timestamps) // 10 + 1))
            tick_interval = time_span_seconds / num_ticks
            for i in range(num_ticks + 1):
                tick_time = min_time.replace(microsecond=0) + (
                    (max_time - min_time) * i / num_ticks
                )
                time_scale.append({
                    "time": tick_time.isoformat(),
                    "position": i / num_ticks * 100,  # 百分比位置
                    "label": tick_time.strftime("%H:%M:%S"),
                })

        # 构建章节层数据
        chapter_layers_data = []
        for layer in self.layers:
            layer_entries = []
            for entry in layer.entries:
                # 计算相对位置
                if self.all_timestamps and entry.timestamp in self.all_timestamps:
                    idx = self.all_timestamps.index(entry.timestamp)
                    position = idx / max(len(self.all_timestamps) - 1, 1) * 100
                else:
                    position = 50

                record = self.records.get(entry.record_id)
                chapter_name = ""
                if record:
                    chapter = record.get_chapter_by_id(entry.chapter_id)
                    if chapter:
                        chapter_name = chapter.chapter_name

                layer_entries.append({
                    "record_id": entry.record_id,
                    "chapter_id": entry.chapter_id,
                    "chapter_name": chapter_name,
                    "timestamp": entry.timestamp.isoformat(),
                    "position": position,
                    "anomaly_flags": entry.anomaly_flags,
                    "has_anomaly": len(entry.anomaly_flags) > 0,
                })

            chapter_layers_data.append({
                "layer_number": layer.layer_number,
                "start_time": layer.start_time.isoformat() if layer.start_time else None,
                "end_time": layer.end_time.isoformat() if layer.end_time else None,
                "entries": layer_entries,
            })

        # 构建锚点数据
        anchor_data = []
        for anchor in self.anchor_lines:
            if self.all_timestamps and anchor.anchor_time:
                if min_time <= anchor.anchor_time <= max_time:
                    position = (anchor.anchor_time - min_time).total_seconds() / time_span_seconds * 100
                elif anchor.anchor_time < min_time:
                    position = 0
                else:
                    position = 100
            else:
                position = 50

            anchor_data.append({
                "anchor_type": anchor.anchor_type,
                "anchor_time": anchor.anchor_time.isoformat(),
                "record_id": anchor.record_id,
                "label": anchor.label or anchor.anchor_type,
                "position": position,
            })

        return {
            "meta": {
                "record_count": self.record_count,
                "chapter_count": self.chapter_count,
                "layer_count": len(self.layers),
                "time_span_seconds": time_span_seconds,
                "min_time": min_time.isoformat(),
                "max_time": max_time.isoformat(),
            },
            "time_scale": time_scale,
            "chapter_layers": chapter_layers_data,
            "anchor_lines": anchor_data,
            "all_timestamps": [ts.isoformat() for ts in self.all_timestamps],
        }


class StratumBuilder:
    """
    地层图构建器

    将病历时间戳记录转换为地层图数据结构，支持：
    - 自动分配地层序号
    - 标注业务时间锚点
    - 导出为可视化数据
    """

    def __init__(self) -> None:
        """初始化地层图构建器"""
        self._records: dict[str, EmrTimestampRecord] = {}
        self._all_timestamps: list[datetime] = []
        self._stratum_map: Optional[StratumMap] = None

    def build(self, records: list[EmrTimestampRecord]) -> StratumMap:
        """
        构建地层图

        Args:
            records: 病历时间戳记录列表

        Returns:
            StratumMap: 构建完成的地层图
        """
        if not records:
            # 返回空地层图
            self._stratum_map = StratumMap()
            return self._stratum_map

        # 存储记录
        self._records = {r.record_id: r for r in records}

        # 收集所有时间戳
        self._all_timestamps = []
        for record in records:
            for chapter in record.chapters:
                if chapter.created_time not in self._all_timestamps:
                    self._all_timestamps.append(chapter.created_time)
                if chapter.modified_time not in self._all_timestamps:
                    self._all_timestamps.append(chapter.modified_time)

        # 全局排序
        self._all_timestamps = sorted(set(self._all_timestamps))

        # 分配地层层号
        entries = self._assign_stratum_layers(records)

        # 构建地层
        layers = self._build_layers(entries)

        # 创建地层图
        chapter_count = sum(len(r.chapters) for r in records)
        self._stratum_map = StratumMap(
            records=self._records,
            all_timestamps=self._all_timestamps,
            layers=layers,
            anchor_lines=[],  # 锚点由外部添加
            record_count=len(records),
            chapter_count=chapter_count,
        )

        return self._stratum_map

    def _assign_stratum_layers(
        self, records: list[EmrTimestampRecord]
    ) -> list[StratumEntry]:
        """
        为每个章节分配地层序号

        地层序号基于创建时间的全局排序：
        - 同一时间创建的章节在同一地层
        - 时间越早，地层序号越小

        Args:
            records: 病历记录列表

        Returns:
            地层条目列表
        """
        entries: list[StratumEntry] = []
        timestamp_to_layer: dict[datetime, int] = {}

        # 为每个唯一时间戳分配层号
        unique_timestamps = sorted(set(self._all_timestamps))
        for idx, ts in enumerate(unique_timestamps):
            timestamp_to_layer[ts] = idx

        # 为每个章节创建地层条目
        for record in records:
            for chapter in record.chapters:
                # 使用创建时间确定地层
                layer_num = timestamp_to_layer.get(chapter.created_time, 0)

                entry = StratumEntry(
                    record_id=record.record_id,
                    chapter_id=chapter.chapter_id,
                    timestamp=chapter.created_time,
                    stratum_layer=layer_num,
                    anomaly_flags=[],
                )
                entries.append(entry)

                # 如果修改时间不同，也创建一个条目
                if chapter.modified_time != chapter.created_time:
                    mod_layer = timestamp_to_layer.get(chapter.modified_time, layer_num)
                    mod_entry = StratumEntry(
                        record_id=record.record_id,
                        chapter_id=chapter.chapter_id,
                        timestamp=chapter.modified_time,
                        stratum_layer=mod_layer,
                        anomaly_flags=[],
                    )
                    entries.append(mod_entry)

        return entries

    def _build_layers(
        self, entries: list[StratumEntry]
    ) -> list[StratumLayer]:
        """
        将地层条目组织为地层列表

        Args:
            entries: 地层条目列表

        Returns:
            地层列表
        """
        # 按地层序号分组
        layer_dict: dict[int, list[StratumEntry]] = {}
        for entry in entries:
            if entry.stratum_layer not in layer_dict:
                layer_dict[entry.stratum_layer] = []
            layer_dict[entry.stratum_layer].append(entry)

        # 构建地层列表
        layers: list[StratumLayer] = []
        for layer_num in sorted(layer_dict.keys()):
            layer_entries = layer_dict[layer_num]
            layer = StratumLayer(layer_number=layer_num)

            for entry in layer_entries:
                layer.add_entry(entry)

            # 设置时间范围
            layer.start_time, layer.end_time = layer.get_time_range()
            layers.append(layer)

        return layers

    def add_anchor_line(
        self,
        anchor_type: str,
        anchor_time: datetime,
        record_id: str,
        label: Optional[str] = None,
    ) -> None:
        """
        添加业务时间锚点

        Args:
            anchor_type: 锚点类型（如"手术开始"、"入院时间"）
            anchor_time: 锚点时间
            record_id: 关联的病历记录ID
            label: 锚点标签（可选）
        """
        if self._stratum_map is None:
            raise ValueError("必须先调用 build() 方法")

        anchor = AnchorLine(
            anchor_type=anchor_type,
            anchor_time=anchor_time,
            record_id=record_id,
            label=label or anchor_type,
        )
        self._stratum_map.anchor_lines.append(anchor)

    def get_stratum_map(self) -> Optional[StratumMap]:
        """获取构建的地层图"""
        return self._stratum_map


# 便捷函数
def build_stratum_map(records: list[EmrTimestampRecord]) -> StratumMap:
    """
    便捷函数：构建地层图

    Args:
        records: 病历时间戳记录列表

    Returns:
        StratumMap: 构建完成的地层图
    """
    builder = StratumBuilder()
    return builder.build(records)


def export_visualization_json(stratum_map: StratumMap, filepath: str) -> None:
    """
    将可视化数据导出为 JSON 文件

    Args:
        stratum_map: 地层图
        filepath: 输出文件路径
    """
    data = stratum_map.to_visualization_data()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)