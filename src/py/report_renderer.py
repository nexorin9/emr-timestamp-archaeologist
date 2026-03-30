"""
EMR Timestamp Archaeologist - HTML 报告渲染器
将检测结果渲染为交互式 HTML 可视化报告
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import AnomalyType, TimestampAnomaly
from detection_engine import DetectionReport, DetectorResult
from stratum_builder import StratumMap


# 异常类型中文名称映射
ANOMALY_TYPE_NAMES: dict[str, str] = {
    "batch_processing": "批处理痕迹",
    "night_rush": "夜间突击补写",
    "time_contradiction": "时间线矛盾",
    "suspicious_sequence": "异常修改序列",
    "anchor_violation": "锚点违规",
}

# 风险等级颜色
RISK_LEVEL_COLORS: dict[str, str] = {
    "极低": "#4CAF50",
    "低": "#8BC34A",
    "中等": "#FFC107",
    "高": "#FF9800",
    "很高": "#FF5722",
    "极高": "#F44336",
}


@dataclass
class RenderOptions:
    """渲染选项"""
    include_css: bool = True
    include_js: bool = True
    interactive: bool = True
    dark_mode: bool = False


class ReportRenderer:
    """
    HTML 报告渲染器

    将检测结果渲染为交互式 HTML 可视化报告，支持：
    - 时序地层图（SVG 横向时间轴 + 纵向章节层）
    - 异常时间线
    - 批处理热力图
    - 夜间活动柱状图
    - 综合风险仪表盘
    """

    def __init__(self, template_dir: Optional[str] = None) -> None:
        """
        初始化渲染器

        Args:
            template_dir: 模板目录路径（可选，默认使用内置模板）
        """
        self.template_dir = template_dir
        self._render_options = RenderOptions()

    def set_options(self, options: RenderOptions) -> None:
        """设置渲染选项"""
        self._render_options = options

    def render_stratum_map(self, stratum_map: StratumMap) -> str:
        """
        渲染时序地层图（SVG 横向时间轴 + 纵向章节层）

        Args:
            stratum_map: 地层图数据

        Returns:
            str: SVG 格式的地层图 HTML
        """
        viz_data = stratum_map.to_visualization_data()
        meta = viz_data["meta"]
        time_scale = viz_data["time_scale"]
        chapter_layers = viz_data["chapter_layers"]
        anchor_lines = viz_data["anchor_lines"]

        # 计算 SVG 尺寸
        width = 1000
        height = 300 + len(chapter_layers) * 40
        time_axis_y = 50
        layer_start_y = 80
        layer_height = 35

        svg_parts = [
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="stratum-map">',
            f'  <!-- 标题 -->',
            f'  <text x="{width//2}" y="25" text-anchor="middle" class="map-title">病历时间戳地层图</text>',
            f'  <!-- 时间轴 -->',
            f'  <line x1="50" y1="{time_axis_y}" x2="{width-50}" y2="{time_axis_y}" stroke="#333" stroke-width="2"/>',
        ]

        # 绘制时间刻度
        for tick in time_scale:
            x = 50 + (width - 100) * tick["position"] / 100
            svg_parts.extend([
                f'  <line x1="{x}" y1="{time_axis_y-5}" x2="{x}" y2="{time_axis_y+5}" stroke="#333"/>',
                f'  <text x="{x}" y="{time_axis_y+20}" text-anchor="middle" class="tick-label">{tick["label"]}</text>',
            ])

        # 绘制锚点线
        for anchor in anchor_lines:
            x = 50 + (width - 100) * anchor["position"] / 100
            svg_parts.extend([
                f'  <line x1="{x}" y1="{time_axis_y-10}" x2="{x}" y2="{height-20}" stroke="#E91E63" stroke-width="2" stroke-dasharray="5,3"/>',
                f'  <text x="{x}" y="{time_axis_y-15}" text-anchor="middle" class="anchor-label" fill="#E91E63">{anchor["label"]}</text>',
            ])

        # 绘制地层
        for i, layer in enumerate(chapter_layers):
            layer_y = layer_start_y + i * layer_height
            entries = layer.get("entries", [])

            # 地层背景
            svg_parts.append(
                f'  <rect x="50" y="{layer_y}" width="{width-100}" height="{layer_height-5}" '
                f'fill="rgba(33, 150, 243, {0.1 + (i % 3) * 0.1})" rx="3"/>'
            )

            # 地层标签
            svg_parts.append(
                f'  <text x="55" y="{layer_y + layer_height//2}" dominant-baseline="middle" '
                f'class="layer-label">层{layer["layer_number"]}</text>'
            )

            # 章节节点
            for entry in entries:
                entry_x = 50 + (width - 100) * entry["position"] / 100
                has_anomaly = entry.get("has_anomaly", False)
                fill_color = "#F44336" if has_anomaly else "#2196F3"
                stroke_color = "#B71C1C" if has_anomaly else "#0D47A1"

                svg_parts.append(
                    f'  <circle cx="{entry_x}" cy="{layer_y + layer_height//2 - 5}" r="8" '
                    f'fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/>'
                )

                # 悬停提示
                svg_parts.append(
                    f'  <title>{entry["chapter_name"]} - {entry["timestamp"][:19]}</title>'
                )

        svg_parts.append('</svg>')

        return "\n".join(svg_parts)

    def render_anomaly_timeline(self, anomalies: list[TimestampAnomaly]) -> str:
        """
        渲染异常时间线（所有异常按时间排列，高亮标注）

        Args:
            anomalies: 异常列表

        Returns:
            str: SVG 格式的异常时间线 HTML
        """
        if not anomalies:
            return '<div class="empty-state">未检测到异常</div>'

        # 按类型分组颜色
        type_colors: dict[str, str] = {
            "batch_processing": "#FF5722",
            "night_rush": "#9C27B0",
            "time_contradiction": "#F44336",
            "suspicious_sequence": "#FF9800",
            "anchor_violation": "#E91E63",
        }

        width = 900
        height = 200
        dot_radius = 12
        spacing = width // (len(anomalies) + 1)

        svg_parts = [
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="anomaly-timeline">',
            f'  <line x1="30" y1="{height//2}" x2="{width-30}" y2="{height//2}" stroke="#ccc" stroke-width="2"/>',
        ]

        for i, anomaly in enumerate(anomalies[:10]):  # 最多显示10个
            x = 50 + i * spacing
            color = type_colors.get(anomaly.anomaly_type.value, "#999")
            severity = anomaly.severity

            # 节点大小根据严重程度变化
            r = dot_radius + severity * 0.3

            svg_parts.extend([
                f'  <circle cx="{x}" cy="{height//2}" r="{r}" fill="{color}" opacity="0.8"/>',
                f'  <text x="{x}" y="{height//2 + r + 15}" text-anchor="middle" class="anomaly-type-label">'
                f'{ANOMALY_TYPE_NAMES.get(anomaly.anomaly_type.value, anomaly.anomaly_type.value)}</text>',
                f'  <title>严重程度: {severity}/10\n{anomaly.description[:50]}</title>',
            ])

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    def render_batch_heatmap(
        self,
        anomalies: list[TimestampAnomaly],
        records_data: Optional[dict] = None,
    ) -> str:
        """
        渲染批处理热力图

        Args:
            anomalies: 异常列表
            records_data: 可选的记录数据（用于科室信息）

        Returns:
            str: SVG 格式的批处理热力图 HTML
        """
        # 筛选批处理异常
        batch_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.BATCH_PROCESSING
        ]

        if not batch_anomalies:
            return '<div class="empty-state">未检测到批处理痕迹</div>'

        width = 800
        height = 300
        max_count = max(len(a.affected_records) for a in batch_anomalies) if batch_anomalies else 1

        svg_parts = [
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="batch-heatmap">',
            f'  <text x="{width//2}" y="25" text-anchor="middle" class="heatmap-title">批处理痕迹热力图</text>',
        ]

        bar_width = (width - 100) // max(len(batch_anomalies), 1)
        for i, anomaly in enumerate(batch_anomalies[:8]):  # 最多8组
            count = len(anomaly.affected_records)
            bar_height = (count / max_count) * 150
            x = 50 + i * bar_width
            y = height - 50 - bar_height

            # 颜色深度根据数量变化
            intensity = count / max_count
            color = f"rgba(244, 67, 54, {0.3 + intensity * 0.7})"

            svg_parts.extend([
                f'  <rect x="{x}" y="{y}" width="{bar_width-10}" height="{bar_height}" '
                f'fill="{color}" rx="3"/>',
                f'  <text x="{x + (bar_width-10)//2}" y="{height-30}" text-anchor="middle">'
                f'组{i+1}</text>',
                f'  <text x="{x + (bar_width-10)//2}" y="{y-5}" text-anchor="middle" class="count-label">'
                f'{count}条</text>',
                f'  <title>受影响记录: {count}条</title>',
            ])

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    def render_night_activity_chart(
        self,
        anomalies: list[TimestampAnomaly],
        records_data: Optional[dict] = None,
    ) -> str:
        """
        渲染夜间活动柱状图

        Args:
            anomalies: 异常列表
            records_data: 可选的记录数据

        Returns:
            str: SVG 格式的夜间活动柱状图 HTML
        """
        # 筛选夜间异常
        night_anomalies = [
            a for a in anomalies
            if a.anomaly_type == AnomalyType.NIGHT_RUSH
        ]

        if not night_anomalies:
            return '<div class="empty-state">未检测到夜间异常活动</div>'

        # 从证据中提取夜间活动时间分布
        hour_counts: dict[int, int] = {h: 0 for h in range(24)}

        for anomaly in night_anomalies:
            evidence = anomaly.evidence
            if "hours" in evidence:
                for hour in evidence["hours"]:
                    if 0 <= hour < 24:
                        hour_counts[hour] += 1
            elif "affected_records" in anomaly.affected_records:
                # 假设均匀分布
                for _ in anomaly.affected_records[:3]:
                    hour = 22 + len(anomaly.affected_records) % 5
                    if hour < 24:
                        hour_counts[hour] += 1

        width = 800
        height = 250
        bar_width = (width - 100) / 24
        max_count = max(hour_counts.values()) if hour_counts.values() else 1

        svg_parts = [
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="night-chart">',
            f'  <text x="{width//2}" y="25" text-anchor="middle" class="chart-title">夜间活动分布 (22:00-05:00)</text>',
            f'  <rect x="50" y="50" width="{width-100}" height="{height-100}" fill="rgba(156, 39, 176, 0.1)" rx="5"/>',
        ]

        for hour in range(24):
            count = hour_counts.get(hour, 0)
            bar_height = (count / max_count) * 120 if max_count > 0 else 0
            x = 50 + hour * bar_width
            y = height - 50 - bar_height

            # 夜间时段(22-05)用深色
            is_night = hour >= 22 or hour < 5
            fill_color = "#9C27B0" if is_night else "#2196F3"
            opacity = 1.0 if is_night else 0.4

            svg_parts.append(
                f'  <rect x="{x+2}" y="{y}" width="{bar_width-4}" height="{bar_height}" '
                f'fill="{fill_color}" opacity="{opacity}" rx="2"/>'
            )
            svg_parts.append(
                f'  <text x="{x + bar_width//2}" y="{height-25}" text-anchor="middle" '
                f'class="hour-label" font-size="10">{hour:02d}</text>'
            )

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    def render_risk_dashboard(self, report: DetectionReport) -> str:
        """
        渲染综合风险仪表盘

        Args:
            report: 检测报告

        Returns:
            str: SVG 格式的风险仪表盘 HTML
        """
        score = report.overall_risk_score
        risk_level = report.risk_level
        color = RISK_LEVEL_COLORS.get(risk_level, "#999")

        # 仪表盘参数
        width = 400
        height = 250
        center_x = width // 2
        center_y = 140
        radius = 100
        stroke_width = 20

        # 计算弧度
        import math
        angle = (score / 100) * 180
        angle_rad = math.radians(angle)

        # 终点坐标
        end_x = center_x + radius * math.cos(math.radians(180 - angle))
        end_y = center_y - radius * math.sin(math.radians(180 - angle))

        svg_parts = [
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="risk-dashboard">',
            f'  <!-- 背景弧 -->',
            f'  <path d="M {center_x - radius} {center_y} A {radius} {radius} 0 0 1 {center_x + radius} {center_y}" '
            f'fill="none" stroke="#e0e0e0" stroke-width="{stroke_width}" stroke-linecap="round"/>',
            f'  <!-- 分数弧 -->',
            f'  <path d="M {center_x - radius} {center_y} A {radius} {radius} 0 0 1 {end_x} {end_y}" '
            f'fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round"/>',
            f'  <!-- 分数文字 -->',
            f'  <text x="{center_x}" y="{center_y - 10}" text-anchor="middle" class="score-value">{score:.1f}</text>',
            f'  <text x="{center_x}" y="{center_y + 20}" text-anchor="middle" class="score-label">风险分数</text>',
            f'  <text x="{center_x}" y="{center_y + 50}" text-anchor="middle" class="risk-level" fill="{color}">{risk_level}</text>',
            f'  <!-- 刻度 -->',
        ]

        # 添加刻度
        for i in range(0, 101, 20):
            tick_angle = 180 - (i / 100) * 180
            tick_x1 = center_x + (radius - 30) * math.cos(math.radians(tick_angle))
            tick_y1 = center_y - (radius - 30) * math.sin(math.radians(tick_angle))
            tick_x2 = center_x + (radius - 20) * math.cos(math.radians(tick_angle))
            tick_y2 = center_y - (radius - 20) * math.sin(math.radians(tick_angle))
            svg_parts.append(
                f'  <line x1="{tick_x1}" y1="{tick_y1}" x2="{tick_x2}" y2="{tick_y2}" stroke="#999"/>'
            )

        svg_parts.append('</svg>')

        # 添加统计数据
        stats_html = f'''
        <div class="stats-grid">
            <div class="stat-item">
                <span class="stat-value">{report.total_records}</span>
                <span class="stat-label">分析记录</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{report.total_anomalies}</span>
                <span class="stat-label">检测异常</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{report.anomalies_by_severity.get("严重 (8-10)", 0)}</span>
                <span class="stat-label">严重异常</span>
            </div>
        </div>
        '''

        return f'<div class="dashboard-container">{svg_parts[0]}\n' + '\n'.join(svg_parts[1:]) + stats_html + '</div>'

    def render_anomaly_list(self, anomalies: list[TimestampAnomaly]) -> str:
        """
        渲染异常列表（卡片式布局）

        Args:
            anomalies: 异常列表

        Returns:
            str: HTML 格式的异常列表
        """
        if not anomalies:
            return '<div class="empty-state">未检测到异常</div>'

        severity_colors = {
            "严重": "#F44336",
            "中等": "#FF9800",
            "轻微": "#FFC107",
            "提示": "#4CAF50",
        }

        items = []
        for anomaly in anomalies[:20]:  # 最多显示20个
            severity_label = anomaly.severity_label
            color = severity_colors.get(severity_label, "#999")
            type_name = ANOMALY_TYPE_NAMES.get(anomaly.anomaly_type.value, anomaly.anomaly_type.value)

            evidence_json = json.dumps(anomaly.evidence, ensure_ascii=False)[:200]
            affected = ", ".join(anomaly.affected_records[:3])
            if len(anomaly.affected_records) > 3:
                affected += f"... (+{len(anomaly.affected_records) - 3})"

            items.append(f'''
            <div class="anomaly-card" style="border-left: 4px solid {color};">
                <div class="anomaly-header">
                    <span class="anomaly-type">{type_name}</span>
                    <span class="anomaly-severity" style="background: {color};">{severity_label}</span>
                </div>
                <div class="anomaly-desc">{anomaly.description}</div>
                <div class="anomaly-meta">
                    <span>受影响记录: {affected}</span>
                </div>
                <details class="anomaly-details">
                    <summary>证据详情</summary>
                    <pre>{evidence_json}</pre>
                </details>
            </div>
            ''')

        return '\n'.join(items)

    def render_full_report(
        self,
        report: DetectionReport,
        stratum_map: Optional[StratumMap] = None,
        options: Optional[RenderOptions] = None,
    ) -> str:
        """
        渲染完整 HTML 报告

        Args:
            report: 检测报告
            stratum_map: 地层图数据（可选）
            options: 渲染选项

        Returns:
            str: 完整 HTML 报告
        """
        opts = options or self._render_options
        generated_at = report.generated_at.strftime("%Y-%m-%d %H:%M:%S") if report.generated_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        all_anomalies = []
        for dr in report.detector_results:
            all_anomalies.extend(dr.anomalies)

        # 各模块 HTML
        risk_dashboard = self.render_risk_dashboard(report)
        anomaly_list = self.render_anomaly_list(all_anomalies)
        anomaly_timeline = self.render_anomaly_timeline(all_anomalies)
        batch_heatmap = self.render_batch_heatmap(all_anomalies)
        night_chart = self.render_night_activity_chart(all_anomalies)
        stratum_map_html = self.render_stratum_map(stratum_map) if stratum_map else '<div class="empty-state">无地层图数据</div>'

        # 组装 HTML
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EMR 时间戳考古报告</title>
    {self._get_embedded_css() if opts.include_css else ''}
</head>
<body>
    <div class="container">
        <header class="report-header">
            <h1>🕐 EMR 时间戳考古报告</h1>
            <p class="subtitle">电子病历时间戳真实性审计分析</p>
            <p class="generated-time">生成时间: {generated_at}</p>
        </header>

        <nav class="toc">
            <h2>目录</h2>
            <ul>
                <li><a href="#summary">风险概览</a></li>
                <li><a href="#stratum">时序地层图</a></li>
                <li><a href="#anomaly-timeline">异常时间线</a></li>
                <li><a href="#batch">批处理热力图</a></li>
                <li><a href="#night">夜间活动分析</a></li>
                <li><a href="#anomalies">异常详情</a></li>
            </ul>
        </nav>

        <section id="summary" class="section">
            <h2>📊 风险概览</h2>
            <div class="dashboard-section">
                {risk_dashboard}
            </div>
            <div class="summary-stats">
                <h3>异常类型分布</h3>
                <div class="type-stats">
                    {self._render_type_stats(report.anomalies_by_type)}
                </div>
            </div>
        </section>

        <section id="stratum" class="section">
            <h2>🗺️ 时序地层图</h2>
            <p class="section-desc">横向为时间轴，纵向为不同病历章节的地层分布</p>
            <div class="visualization-container">
                {stratum_map_html}
            </div>
        </section>

        <section id="anomaly-timeline" class="section">
            <h2>⏱️ 异常时间线</h2>
            <div class="visualization-container">
                {anomaly_timeline}
            </div>
        </section>

        <section id="batch" class="section">
            <h2>🔥 批处理痕迹热力图</h2>
            <div class="visualization-container">
                {batch_heatmap}
            </div>
        </section>

        <section id="night" class="section">
            <h2>🌙 夜间活动分析</h2>
            <div class="visualization-container">
                {night_chart}
            </div>
        </section>

        <section id="anomalies" class="section">
            <h2>⚠️ 异常详情</h2>
            <div class="anomaly-list">
                {anomaly_list}
            </div>
        </section>

        <footer class="report-footer">
            <p>EMR Timestamp Archaeologist | 病历时间戳考古器</p>
            <p>本报告由 AI 自动生成，仅供辅助参考</p>
        </footer>
    </div>

    {self._get_embedded_js() if opts.include_js else ''}
</body>
</html>'''

        return html

    def _render_type_stats(self, anomalies_by_type: dict[str, int]) -> str:
        """渲染异常类型统计"""
        type_colors = {
            "batch_processing": "#FF5722",
            "night_rush": "#9C27B0",
            "time_contradiction": "#F44336",
            "suspicious_sequence": "#FF9800",
            "anchor_violation": "#E91E63",
        }

        items = []
        for atype, count in anomalies_by_type.items():
            color = type_colors.get(atype, "#999")
            name = ANOMALY_TYPE_NAMES.get(atype, atype)
            items.append(
                f'<div class="type-stat-item">'
                f'<span class="type-dot" style="background: {color};"></span>'
                f'<span class="type-name">{name}</span>'
                f'<span class="type-count">{count}</span>'
                f'</div>'
            )

        return '\n'.join(items) if items else '<div class="empty-state">无异常数据</div>'

    def _get_embedded_css(self) -> str:
        """获取嵌入式 CSS 样式"""
        return '''
<style>
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    background: #f5f5f5;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

.report-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 40px 30px;
    border-radius: 10px;
    text-align: center;
    margin-bottom: 30px;
}

.report-header h1 {
    font-size: 2.5em;
    margin-bottom: 10px;
}

.subtitle {
    font-size: 1.2em;
    opacity: 0.9;
}

.generated-time {
    font-size: 0.9em;
    opacity: 0.7;
    margin-top: 10px;
}

.toc {
    background: white;
    padding: 20px;
    border-radius: 8px;
    margin-bottom: 30px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.toc h2 {
    margin-bottom: 15px;
    color: #667eea;
}

.toc ul {
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}

.toc a {
    color: #667eea;
    text-decoration: none;
    padding: 5px 15px;
    background: #f0f0ff;
    border-radius: 20px;
    transition: background 0.3s;
}

.toc a:hover {
    background: #667eea;
    color: white;
}

.section {
    background: white;
    padding: 25px;
    border-radius: 8px;
    margin-bottom: 25px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.section h2 {
    color: #333;
    border-bottom: 2px solid #667eea;
    padding-bottom: 10px;
    margin-bottom: 20px;
}

.section-desc {
    color: #666;
    margin-bottom: 15px;
}

.visualization-container {
    background: #fafafa;
    border-radius: 8px;
    padding: 20px;
    overflow-x: auto;
}

.dashboard-section {
    display: flex;
    justify-content: center;
    gap: 40px;
    flex-wrap: wrap;
}

.dashboard-container {
    text-align: center;
}

.stats-grid {
    display: flex;
    justify-content: center;
    gap: 30px;
    margin-top: 20px;
}

.stat-item {
    text-align: center;
}

.stat-value {
    display: block;
    font-size: 2em;
    font-weight: bold;
    color: #667eea;
}

.stat-label {
    color: #666;
    font-size: 0.9em;
}

.type-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
}

.type-stat-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 15px;
    background: #f5f5f5;
    border-radius: 20px;
}

.type-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
}

.type-name {
    color: #333;
}

.type-count {
    font-weight: bold;
    color: #667eea;
}

.anomaly-list {
    display: flex;
    flex-direction: column;
    gap: 15px;
}

.anomaly-card {
    background: #fafafa;
    padding: 15px 20px;
    border-radius: 8px;
    transition: transform 0.2s, box-shadow 0.2s;
}

.anomaly-card:hover {
    transform: translateX(5px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.anomaly-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}

.anomaly-type {
    font-weight: bold;
    color: #333;
}

.anomaly-severity {
    color: white;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.85em;
}

.anomaly-desc {
    color: #555;
    margin-bottom: 10px;
}

.anomaly-meta {
    font-size: 0.85em;
    color: #888;
}

.anomaly-details {
    margin-top: 10px;
}

.anomaly-details summary {
    cursor: pointer;
    color: #667eea;
    font-size: 0.9em;
}

.anomaly-details pre {
    background: #f0f0f0;
    padding: 10px;
    border-radius: 5px;
    font-size: 0.8em;
    overflow-x: auto;
    margin-top: 5px;
}

.empty-state {
    text-align: center;
    color: #999;
    padding: 40px;
    font-style: italic;
}

/* SVG 样式 */
.stratum-map, .anomaly-timeline, .batch-heatmap, .night-chart, .risk-dashboard {
    display: block;
    max-width: 100%;
}

.map-title, .heatmap-title, .chart-title {
    font-size: 16px;
    font-weight: bold;
    fill: #333;
}

.tick-label, .layer-label, .hour-label {
    font-size: 10px;
    fill: #666;
}

.anchor-label {
    font-size: 10px;
    font-weight: bold;
}

.anomaly-type-label {
    font-size: 8px;
    fill: #333;
}

.count-label {
    font-size: 10px;
    font-weight: bold;
    fill: #333;
}

.score-value {
    font-size: 36px;
    font-weight: bold;
    fill: #333;
}

.score-label {
    font-size: 14px;
    fill: #666;
}

.risk-level {
    font-size: 18px;
    font-weight: bold;
}

.report-footer {
    text-align: center;
    padding: 30px;
    color: #888;
    font-size: 0.9em;
}

/* 响应式设计 */
@media (max-width: 768px) {
    .report-header h1 {
        font-size: 1.8em;
    }

    .dashboard-section {
        flex-direction: column;
        align-items: center;
    }

    .stats-grid {
        flex-direction: column;
        gap: 15px;
    }
}

/* 打印样式 */
@media print {
    body {
        background: white;
    }

    .container {
        max-width: 100%;
        padding: 0;
    }

    .toc {
        display: none;
    }

    .section {
        break-inside: avoid;
        box-shadow: none;
        border: 1px solid #ddd;
    }
}
</style>'''

    def _get_embedded_js(self) -> str:
        """获取嵌入式 JavaScript"""
        return '''
<script>
// 异常卡片交互
document.querySelectorAll('.anomaly-card').forEach(card => {
    card.addEventListener('click', function() {
        const details = this.querySelector('.anomaly-details');
        if (details) {
            details.open = !details.open;
        }
    });
});

// 平滑滚动
document.querySelectorAll('.toc a').forEach(link => {
    link.addEventListener('click', function(e) {
        e.preventDefault();
        const targetId = this.getAttribute('href').substring(1);
        const target = document.getElementById(targetId);
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// 图表悬停效果
document.querySelectorAll('svg circle, svg rect').forEach(elem => {
    elem.addEventListener('mouseenter', function() {
        this.style.opacity = '0.7';
    });
    elem.addEventListener('mouseleave', function() {
        this.style.opacity = '1';
    });
});
</script>'''

    def export_html(self, report: DetectionReport, output_path: str, stratum_map: Optional[StratumMap] = None) -> None:
        """
        导出 HTML 报告到文件

        Args:
            report: 检测报告
            output_path: 输出文件路径
            stratum_map: 地层图数据（可选）
        """
        html = self.render_full_report(report, stratum_map)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def export_pdf(self, report: DetectionReport, output_path: str, stratum_map: Optional[StratumMap] = None) -> None:
        """
        导出 PDF 报告（使用 weasyprint 或 playwright）

        Args:
            report: 检测报告
            output_path: 输出文件路径
            stratum_map: 地层图数据（可选）

        Note:
            需要安装 weasyprint 或 playwright 才能使用此功能
        """
        # 尝试使用 weasyprint
        try:
            from weasyprint import HTML
            import weasyprint

            html_content = self.render_full_report(report, stratum_map)
            temp_html = output_path.replace('.pdf', '_temp.html')
            with open(temp_html, "w", encoding="utf-8") as f:
                f.write(html_content)

            HTML(filename=temp_html).write_pdf(output_path)
            os.remove(temp_html)
            return
        except ImportError:
            pass

        # 尝试使用 playwright
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "PDF 导出需要安装 weasyprint 或 playwright。\n"
                "安装方式：pip install weasyprint 或 pip install playwright && playwright install"
            )

        html_content = self.render_full_report(report, stratum_map)
        temp_html = output_path.replace('.pdf', '_temp.html')
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(html_content)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{os.path.abspath(temp_html)}")
            page.pdf(path=output_path, format='A4')
            browser.close()

        os.remove(temp_html)


# 便捷函数
def render_report(
    report: DetectionReport,
    output_path: str,
    stratum_map: Optional[StratumMap] = None,
    template_dir: Optional[str] = None,
) -> None:
    """
    便捷函数：渲染并导出报告

    Args:
        report: 检测报告
        output_path: 输出文件路径
        stratum_map: 地层图数据（可选）
        template_dir: 模板目录（可选）
    """
    renderer = ReportRenderer(template_dir)
    if output_path.lower().endswith('.pdf'):
        renderer.export_pdf(report, output_path, stratum_map)
    else:
        renderer.export_html(report, output_path, stratum_map)
