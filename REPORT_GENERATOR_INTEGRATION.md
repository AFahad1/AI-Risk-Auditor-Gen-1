# Report Generator — Documentation

`report_generator.py` takes a completed risk assessment (as a CSV) and produces a formatted, multi-sheet Excel workbook. It runs fully standalone — no Flask, no API keys, no database.

---

## What it produces

A single `.xlsx` file with five sheets:

| Sheet | Contents |
|---|---|
| Summary Dashboard | Org details, risk counts, inherent vs residual comparison, scoring legend |
| Risk Register | Full colour-coded table of every assessed control |
| Risk Heat Map | 5×5 likelihood/impact grid — inherent and residual side by side |
| Risk by Category | Controls grouped by category with rating and status |
| Actions Required | Only OPEN and ASSESSED items — the ones that still need attention |

---

## Setup

Only one dependency:

```bash
pip install openpyxl
```

---

## Running it

```bash
python report_generator.py results.csv --org "Acme Corp" --framework "ISO 27001"
```

The output file is saved as `results_report.xlsx` in the same folder as the CSV unless `--out` is specified.

### All flags

| Flag | Required | Description |
|---|---|---|
| `csv_path` | Yes | Path to the results CSV |
| `--org` | No | Organisation name (default: `Unknown Organisation`) |
| `--framework` | No | Framework key — `ISO 27001`, `SOC 2`, or `HIPAA` (default: `ISO 27001`) |
| `--date` | No | Report date string (default: today) |
| `--risk-owner` | No | Name of the Risk Owner / ISM |
| `--isms-rep` | No | Name of the ISMS Representative |
| `--approved-by` | No | Name of the approver (can be filled in later directly in Excel) |
| `--scope` | No | Assessment scope description |
| `--out` | No | Custom output file path |
| `--test` | No | Run built-in test cases and exit (no CSV needed) |

---

## CSV format

The CSV must match the shape the app exports. Required columns (used for risk scoring):

```
likelihood, impact, residual_risk_likelihood, residual_risk_impact
```

Recommended columns (appear in the report — blank if missing):

```
name, category, status, description, treatment,
application_name, loss_of_cia, assignee
```

### Minimal working example

```csv
name,category,status,likelihood,impact,residual_risk_likelihood,residual_risk_impact,treatment,application_name,loss_of_cia,assignee,description
Access Control Policy,Governance,OPEN,4,5,2,3,Implement MFA,Microsoft Entra,CIA,jane@acme.com,No formal access control policy in place
Data Backup,Resilience,TREATED,3,4,1,2,Daily automated backups configured,AWS S3,CI,john@acme.com,Backups exist but not regularly tested
```

---

## Error messages

The script prints `[ERROR]` or `[WARNING]` before any message. Errors stop generation; warnings let it continue.

| Message | Meaning | Fix |
|---|---|---|
| `[ERROR] File not found: path` | The CSV path doesn't exist | Check the path and try again |
| `[ERROR] File is empty (0 bytes)` | The file exists but has no content | Check the export — re-export if needed |
| `[ERROR] CSV contains no data rows` | File has column headers but no rows | The assessment may not have produced results |
| `[ERROR] Missing required columns: likelihood, ...` | One or more score columns are absent | Ensure the CSV comes from the app's export — don't rename columns |
| `[ERROR] Could not decode file` | The file isn't valid UTF-8 | Re-save the CSV as UTF-8 encoding |
| `[ERROR] Could not write report` | The output `.xlsx` is open in Excel, or no write permission | Close the file in Excel and retry |
| `[WARNING] Missing recommended columns: name, ...` | Optional columns are absent | Report generates but those fields will be blank |
| `[WARNING] Non-numeric values in score columns` | A score cell contains text instead of a number | Those cells default to 0; check the source data |

---

## Built-in tests

Run this to verify the script works correctly in any environment:

```bash
python report_generator.py --test
```

Six test cases run automatically:

| Test | Scenario | Expected result |
|---|---|---|
| TC1 | File does not exist | Error: file not found |
| TC2 | File exists but is empty (0 bytes) | Error: file is empty |
| TC3 | File has headers but no data rows | Error: no data rows |
| TC4 | CSV is missing required score columns | Error: lists which columns are missing |
| TC5 | Score columns contain non-numeric text | Warning issued — report still generates with those values defaulting to 0 |
| TC6 | Valid minimal CSV with one row | Report generated successfully |

All six should print `[PASS]`. A `[FAIL]` means something is wrong with the environment — check the Python version (3.9+) and that `openpyxl` is installed.

---

## Wiring into the Flask app (future)

When the team is ready to connect this to the "Complete Assessment" button, `build_workbook(rows, meta)` is the only function needed:

```python
from io import BytesIO
from flask import send_file
from report_generator import build_workbook, FRAMEWORK_LABELS

@app.route("/api/export-report", methods=["POST"])
@login_required
def export_report():
    data    = request.json
    results = data["results"]

    meta = {
        "org_name":        data.get("org_name", "Unknown Organisation"),
        "framework_label": FRAMEWORK_LABELS.get(data.get("framework", ""), data.get("framework", "")),
        "date":            data.get("date") or date.today().strftime("%d %B %Y"),
        "risk_owner":      data.get("risk_owner", ""),
        "isms_rep":        data.get("isms_rep", ""),
        "approved_by":     data.get("approved_by", ""),
        "scope":           data.get("scope", ""),
    }

    wb  = build_workbook(results, meta)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"{data.get('framework', 'report').replace(' ', '_')}_risk_report.xlsx"
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

The `results` rows must use the same field names as the CSV columns listed above. No frontend changes are needed — the app already produces them.
