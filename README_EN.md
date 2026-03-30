# EMR Timestamp Archaeologist

Using archaeological "stratigraphy" methods to analyze timestamps across Electronic Medical Record (EMR) chapters, constructing an "EMR Archaeological Stratum Map," automatically detecting abnormal time patterns such as backdating, rush documentation, and batch fabrication, generating visualized authenticity audit reports.

## Project Background

The authenticity of EMR timestamps is a critical concern in medical quality management and medical insurance compliance auditing. Traditional medical record review relies on manual inspection of each record, which is inefficient and struggles to detect systematic fabrication patterns. This tool borrows archaeological stratigraphy methods, arranging EMR chapter timestamps in creation order as "strata," and detecting abnormal time patterns through multi-dimensional algorithms.

## Core Features

### 1. EMR Metadata Parsing
- Supports XML, JSON, CSV multiple formats
- Automatically extracts creation and modification times for each EMR chapter
- Unified time format processing (supports ISO8601, Unix timestamp, common date formats)

### 2. Temporal Stratum Map Construction
- Constructs a visual "stratum map" of EMR chapters in chronological order
- Marks key business time anchors (surgery start, admission time, etc.)
- Supports JSON export for subsequent analysis

### 3. Multi-Type Timestamp Anomaly Detection
- **Batch Processing Detection**: Detects patterns where multiple medical records have identical timestamps (to the second) within the same time window
- **Night Rush Detection**: Identifies concentrated medical record modifications during nighttime hours (22:00-05:00)
- **Timeline Contradiction Detection**: Detects contradictions between chapter timestamps and business time anchors
- **Abnormal Sequence Pattern Detection**: Detects backdated modifications, periodic modifications, and other abnormal patterns

### 4. LLM Narrative Analysis Report
- Calls large language model to generate archaeological-style narrative audit reports
- Automatically generates department risk rankings and rectification suggestions

### 5. CLI + HTML Visualization Interface
- Complete command-line tool supporting batch analysis and report generation
- Interactive HTML report with stratum map visualization and anomaly filtering

## Technical Architecture

```
emr-timestamp-archaeologist/
├── src/
│   ├── py/                    # Python data processing and detection engine
│   │   ├── models.py          # Core data models
│   │   ├── parser.py          # EMR metadata parser
│   │   ├── stratum_builder.py # Temporal stratum map builder
│   │   ├── detectors/         # Anomaly detectors
│   │   ├── detection_engine.py# Comprehensive anomaly detection engine
│   │   ├── llm_reporter.py    # LLM report generator
│   │   ├── report_renderer.py # HTML report renderer
│   │   ├── pipeline.py        # Main analysis pipeline
│   │   ├── config.py          # Configuration management
│   │   ├── debug_tools.py     # Debugging tools
│   │   └── cli.py             # Python CLI entry point
│   └── cli/                   # TypeScript/Node.js CLI
│       ├── index.ts           # Main entry point
│       └── commands/          # Command modules
├── data/                      # Sample data and test data
├── templates/                 # HTML report templates
└── tests/                     # Test files
```

## Tech Stack

- **Python**: Data processing, statistics, LLM integration
- **TypeScript/Node.js**: CLI interface
- **HTML/CSS/JavaScript**: Visualization reports

## Installation

### Environment Requirements

- Python >= 3.10
- Node.js >= 18.0.0

### Installation Steps

1. **Clone the project**
   ```bash
   git clone <repository-url>
   cd emr-timestamp-archaeologist
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Node.js dependencies**
   ```bash
   npm install
   ```

4. **Build the project**
   ```bash
   npm run build
   ```

## Quick Start

### 1. Configure API Key

```bash
# First use requires configuring LLM API key
emr-archaeologist config set-api-key
```

Or create a `.env` file:
```env
ANTHROPIC_API_KEY=your-api-key-here
```

### 2. Prepare Data

Export EMR metadata to XML, JSON, or CSV format. Example data formats:

**XML format**:
```xml
<emr_record>
  <patient_id>P12345</patient_id>
  <visit_id>V20240301</visit_id>
  <chapter id="admission" name="入院记录">
    <created_time>2024-03-01 08:30:00</created_time>
    <modified_time>2024-03-01 08:30:00</modified_time>
    <author_id>DR001</author_id>
  </chapter>
  <chapter id="surgery" name="手术记录">
    <created_time>2024-03-01 10:00:00</created_time>
    <modified_time>2024-03-01 14:30:00</modified_time>
    <author_id>DR002</author_id>
  </chapter>
</emr_record>
```

**JSON format**:
```json
{
  "patient_id": "P12345",
  "visit_id": "V20240301",
  "record_type": "inpatient",
  "business_time": "2024-03-01T09:00:00",
  "chapters": [
    {
      "chapter_id": "admission",
      "chapter_name": "入院记录",
      "chapter_order": 1,
      "created_time": "2024-03-01T08:30:00",
      "modified_time": "2024-03-01T08:30:00",
      "author_id": "DR001"
    }
  ]
}
```

### 3. Run Analysis

```bash
# Analyze EMR data
emr-archaeologist analyze --input ./data/sample.xml --output ./output/

# Generate HTML report
emr-archaeologist report --input ./output/analysis_result.json --output ./output/report.html

# Start local server to preview report
emr-archaeologist serve --port 8080
```

### 4. View Report

HTML report includes:
- **EMR Archaeological Stratum Map**: Visual display of chapter timestamp relationships
- **Anomaly Timeline**: Highlighted annotations of all detected anomalies
- **Batch Processing Heatmap**: Shows spatial-temporal distribution of batch processing traces
- **Night Activity Chart**: Shows distribution of nighttime modification activities
- **Comprehensive Risk Dashboard**: Shows overall risk score and breakdown by type

## Command Reference

### analyze - Analyze EMR

```bash
emr-archaeologist analyze [options]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--input, -i` | Input file path or directory | Required |
| `--output, -o` | Output directory | ./output/ |
| `--format, -f` | Input format (auto/xml/json/csv) | auto |
| `--llm` | Enable LLM report generation | true |
| `--detectors` | Specify enabled detectors | all |
| `--verbose` | Output detailed logs | false |
| `--debug` | Enable debug mode | false |

### report - Generate Report

```bash
emr-archaeologist report [options]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--input, -i` | Analysis result JSON file path | Required |
| `--output, -o` | Output HTML file path | report.html |
| `--template` | Report template path | Built-in template |
| `--no-browser` | Don't auto-open browser after generation | false |

### serve - Start Preview Server

```bash
emr-archaeologist serve [options]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--port, -p` | Server port | 8080 |
| `--host` | Server address | localhost |
| `--no-browser` | Don't auto-open browser | false |

### config - Configuration Management

```bash
emr-archaeologist config [options]
```

| Subcommand | Description |
|------------|-------------|
| `set-api-key` | Set API key |
| `show` | Show current configuration |
| `reset` | Reset configuration |

## Anomaly Type Descriptions

### 1. Batch Processing (BATCH_PROCESSING)

**Characteristics**: Within the same time window, multiple medical records have identical timestamps (accurate to the second).

**Possible causes**:
- Batch import of historical medical records
- Timestamp unification during system migration
- Intentional timestamp batch fabrication

**Recommended actions**:
1. Verify paper originals of related medical records
2. Check if a large number of records were archived concurrently during the period
3. Make comprehensive judgment combined with other anomalies

### 2. Night Rush (NIGHT_RUSH)

**Characteristics**: Medical records are created or modified concentrated during nighttime hours (22:00-05:00).

**Possible causes**:
- On-duty doctors supplementing medical records
- Concentrated archiving of discharged medical records
- Malicious rush documentation to evade inspection

**Recommended actions**:
1. Calculate nighttime modification ratios by department
2. Compare with historical baseline to identify abnormal peaks
3. Focus on departments with high nighttime modification volumes

### 3. Timeline Contradiction (TIME_CONTRADICTION)

**Characteristics**: The chronological order of medical record chapters does not comply with medical standards.

**Examples**:
- Surgery record creation time is earlier than surgery start time
- Discharge summary creation time is earlier than discharge time
- Progress notes time is earlier than admission time

**Recommended actions**:
1. Verify accuracy of business time anchors
2. Check for system time setting errors
3. Determine if timestamp tampering occurred based on other evidence

### 4. Anchor Violation (ANCHOR_VIOLATION)

**Characteristics**: Chapter timestamps are earlier than key business time anchors.

**Examples**:
- Surgery record was created before surgery started
- Deceased cases were archived before death time

**Recommended actions**:
1. Immediately verify related business facts
2. Check system time settings
3. Report to competent authorities for investigation

### 5. Suspicious Sequence (SUSPICIOUS_SEQUENCE)

**Characteristics**: Modification times show backdating, periodic patterns, or abnormal proximity.

**Examples**:
- Second modification time is earlier than first
- Modifications at fixed time every day
- Multiple chapters modified consecutively within 5 minutes

**Recommended actions**:
1. Analyze time interval distribution of modification sequences
2. Detect if automated modification patterns exist
3. Focus on medical records with high risk scores

## Input Data Format

### XML Format

```xml
<?xml version="1.0" encoding="UTF-8"?>
<emr_batch>
  <record>
    <patient_id>P12345</patient_id>
    <visit_id>V20240301</visit_id>
    <record_type>inpatient</record_type>
    <business_time>2024-03-01 09:00:00</business_time>
    <chapters>
      <chapter id="admission" name="入院记录" order="1">
        <created_time>2024-03-01 08:30:00</created_time>
        <modified_time>2024-03-01 08:30:00</modified_time>
        <author_id>DR001</author_id>
      </chapter>
    </chapters>
  </record>
</emr_batch>
```

### JSON Format

```json
{
  "records": [
    {
      "patient_id": "P12345",
      "visit_id": "V20240301",
      "record_type": "inpatient",
      "business_time": "2024-03-01T09:00:00",
      "chapters": [
        {
          "chapter_id": "admission",
          "chapter_name": "入院记录",
          "chapter_order": 1,
          "created_time": "2024-03-01T08:30:00",
          "modified_time": "2024-03-01T08:30:00",
          "author_id": "DR001"
        }
      ]
    }
  ]
}
```

### CSV Format

```csv
patient_id,visit_id,record_type,chapter_id,chapter_name,chapter_order,created_time,modified_time,author_id
P12345,V20240301,inpatient,admission,入院记录,1,2024-03-01 08:30:00,2024-03-01 08:30:00,DR001
P12345,V20240301,inpatient,surgery,手术记录,2,2024-03-01 14:30:00,2024-03-01 14:30:00,DR002
```

## Output Report Interpretation

### Stratum Map

The horizontal axis is the timeline, and the vertical axis shows chapter levels. Each chapter is displayed as a colored block, with color indicating chapter type. Key business anchors (such as surgery start time) are marked on the timeline.

**Reading guide**:
- Under normal circumstances, chapters are arranged from bottom to top in chronological order
- If chapters cross over others (e.g., surgery record appears before admission record), special attention is needed
- Anomalous chapters are marked in red

### Risk Score

The comprehensive risk score is a 0-100 rating; the higher the score, the greater the risk.

| Score Range | Risk Level | Description |
|-------------|------------|-------------|
| 0-30 | Low Risk | Basically normal |
| 31-60 | Medium Risk | Minor anomalies exist, recommend attention |
| 61-80 | High Risk | Significant anomalies exist, verification needed |
| 81-100 | Very High Risk | Severe anomalies exist, must be addressed |

## FAQ

**Q: Which EMR system exported data formats are supported?**
A: Currently supports standard XML, JSON, CSV format general export formats. For specific EMR system format support, please submit an Issue.

**Q: Is LLM report generation required?**
A: You can use the `--no-llm` option to disable LLM report generation and only output structured JSON results.

**Q: How to process large volumes of medical record data?**
A: It is recommended to use `--input` to specify a directory containing multiple files; the program will automatically batch process them.

**Q: Can the nighttime time window be modified?**
A: Yes, you can modify the `night_start` and `night_end` parameters in the configuration file.

**Q: Can reports be exported as PDF?**
A: Yes, use the `--export-pdf` option (requires installing Playwright or WeasyPrint).

**Q: How to debug detection results?**
A: Using `--debug` and `--verbose` options outputs detailed detection processes and intermediate results.

**Q: How to control the false positive rate?**
A: You can balance sensitivity and false positive rate by setting threshold parameters for detectors.

**Q: Is network-based EMR data retrieval supported?**
A: Yes, the `--api-proxy` option of the `serve` command can proxy API requests.

**Q: How is data security ensured?**
A: All data processing is completed locally; no data is uploaded to any server. API keys use encrypted storage.

**Q: How to contribute to development?**
A: Pull Requests and Issues are welcome.

## License

Apache License 2.0 - See LICENSE file for details

---

## Support the Author

If you find this project helpful, feel free to buy me a coffee! ☕

![Buy Me a Coffee](buymeacoffee.png)

**Buy me a coffee (crypto)**

| Chain | Address |
|-------|---------|
| BTC | `bc1qc0f5tv577z7yt59tw8sqaq3tey98xehy32frzd` |
| ETH / USDT | `0x3b7b6c47491e4778157f0756102f134d05070704` |
| SOL | `6Xuk373zc6x6XWcAAuqvbWW92zabJdCmN3CSwpsVM6sd` |
