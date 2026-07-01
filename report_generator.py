"""
Standalone CSV -> formal Excel risk assessment report generator.

Independent of app.py on purpose: run it directly from the CLI against any
results CSV (the same shape /api/export produces) to test the report layout
before it's wired into the Flask app.

Usage:
    python report_generator.py path/to/results.csv --org "Acme Inc" --framework "ISO 27001"
"""

import argparse
import csv
import os
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

FONT_NAME = "Arial"
WHITE = "FFFFFFFF"
BRAND_BLUE = "FF154360"
DARK_BG = "FF2C2C2C"
LIGHT_GRAY = "FFEEEEEE"
TEXT_DARK = "FF2C2C2C"

RATING_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

RATING_COLORS = {
    "CRITICAL": "FFC0392B",
    "HIGH": "FFE67E22",
    "MEDIUM": "FFD4AC0D",
    "LOW": "FF27AE60",
}

RATING_LIGHT_TINT = {
    "CRITICAL": "FFFDECEA",
    "HIGH": "FFFFF8F0",
    "MEDIUM": "FFFEFDE7",
    "LOW": "FFE8F8F0",
}

STATUS_COLORS = {
    "TREATED": "FF27AE60",
    "ASSESSED": "FF2980B9",
    "CLOSED": "FF555555",
    "OPEN": "FFC0392B",
}

STATUS_ROW_TINT = {
    "TREATED": "FFE8F8F0",
    "ASSESSED": "FFEAF4FF",
    "CLOSED": "FFF5F5F5",
    "OPEN": "FFFDECEA",
}

CATEGORY_COLORS = {
    "CUSTOMER": "FF0E6655",
    "GOVERNANCE": "FF6C3483",
    "OPERATIONS": "FF1B4F72",
    "PEOPLES": "FF922B21",
    "REGULATORY": "FF7D6608",
    "RESILIENCE": "FF7E5109",
    "TECHNOLOGY": "FF1A5276",
    "VENDOR MANAGEMENT": "FF117A65",
    "OTHER": "FF515A5A",
}

FRAMEWORK_LABELS = {
    "ISO 27001": "ISO/IEC 27001:2022",
    "SOC 2": "SOC 2",
    "HIPAA": "HIPAA Security Rule",
}

REQUIRED_COLS = {"likelihood", "impact", "residual_risk_likelihood", "residual_risk_impact"}
EXPECTED_COLS  = REQUIRED_COLS | {
    "name", "category", "status", "treatment",
    "application_name", "loss_of_cia", "assignee", "description",
}


def rating_from_score(score):
    if score >= 15:
        return "CRITICAL"
    if score >= 10:
        return "HIGH"
    if score >= 5:
        return "MEDIUM"
    return "LOW"


def _light_tint(hex_color, factor=0.83):
    hex_color = hex_color[-6:]
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"FF{r:02X}{g:02X}{b:02X}"


def _font(color=TEXT_DARK, bold=False, size=9, italic=False):
    return Font(name=FONT_NAME, color=color, bold=bold, size=size, italic=italic)


def _set(ws, coord, value, fill=None, font=None, align="left", wrap=False):
    cell = ws[coord]
    cell.value = value
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.font = font or _font()
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    return cell


def read_rows_from_csv(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"[ERROR] File not found: {path}")
        return None
    except PermissionError:
        print(f"[ERROR] Permission denied reading: {path}")
        return None
    except UnicodeDecodeError:
        print(f"[ERROR] Could not decode {path} — ensure the file is saved as UTF-8.")
        return None


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _enrich(rows):
    enriched = []
    for i, row in enumerate(rows, start=1):
        likelihood = _to_int(row.get("likelihood"))
        impact = _to_int(row.get("impact"))
        res_l = _to_int(row.get("residual_risk_likelihood"))
        res_i = _to_int(row.get("residual_risk_impact"))
        inherent_score = likelihood * impact
        residual_score = res_l * res_i
        enriched.append({
            **row,
            "risk_id": f"R-{i:02d}",
            "category": (row.get("category") or "OTHER").upper().strip() or "OTHER",
            "status": (row.get("status") or "").upper().strip(),
            "likelihood": likelihood,
            "impact": impact,
            "residual_risk_likelihood": res_l,
            "residual_risk_impact": res_i,
            "inherent_score": inherent_score,
            "inherent_rating": rating_from_score(inherent_score),
            "residual_score": residual_score,
            "residual_rating": rating_from_score(residual_score),
        })
    return enriched


def _build_dashboard(wb, rows, meta):
    ws = wb.create_sheet("Summary Dashboard")
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["I"].width = 22

    ws.merge_cells("B2:I2")
    _set(ws, "B2", meta["org_name"], fill=BRAND_BLUE, font=_font(WHITE, True, 20))

    ws.merge_cells("B3:I3")
    subtitle = f"{meta['framework_label']} Information Security Risk Assessment Report  |  {meta['date']}  |  RESTRICTED"
    _set(ws, "B3", subtitle, fill=DARK_BG, font=_font("FFBBBBBB", False, 11))

    r = 5
    for label, value in [
        ("Assessment Date:", meta["date"]),
        ("Standard:", meta["framework_label"]),
        ("Risk Owner / ISM:", meta["risk_owner"]),
        ("ISMS Representative:", meta["isms_rep"]),
        ("Approved By:", meta["approved_by"]),
        ("Scope:", meta["scope"]),
        ("Classification:", "RESTRICTED — Internal Use Only"),
    ]:
        _set(ws, f"B{r}", label, fill=LIGHT_GRAY, font=_font(bold=True, size=10))
        ws.merge_cells(f"C{r}:I{r}")
        _set(ws, f"C{r}", value, font=_font(size=10))
        r += 1

    r += 1
    ws.merge_cells(f"B{r}:I{r}")
    _set(ws, f"B{r}", "RISK ASSESSMENT SUMMARY", fill=BRAND_BLUE, font=_font(WHITE, True, 12))
    r += 1

    total = len(rows)
    counts = [
        ("Total Risks Assessed", total),
        ("Treated", sum(1 for x in rows if x["status"] == "TREATED")),
        ("Assessed (Monitoring)", sum(1 for x in rows if x["status"] == "ASSESSED")),
        ("Closed / Out of Scope", sum(1 for x in rows if x["status"] == "CLOSED")),
        ("Open (Action Required)", sum(1 for x in rows if x["status"] == "OPEN")),
    ]
    for label, value in counts:
        ws.merge_cells(f"B{r}:G{r}")
        _set(ws, f"B{r}", label, fill=LIGHT_GRAY, font=_font(bold=True, size=10))
        ws.merge_cells(f"H{r}:I{r}")
        _set(ws, f"H{r}", value, fill=LIGHT_GRAY, font=_font(bold=True, size=10), align="center")
        r += 1

    r += 1
    ws.merge_cells(f"B{r}:I{r}")
    _set(ws, f"B{r}", "RISK LEVEL COMPARISON — INHERENT vs RESIDUAL", fill=BRAND_BLUE, font=_font(WHITE, True, 12))
    r += 1

    ws.merge_cells(f"B{r}:C{r}")
    _set(ws, f"B{r}", "Risk Level", fill=DARK_BG, font=_font(WHITE, True, 10))
    ws.merge_cells(f"D{r}:E{r}")
    _set(ws, f"D{r}", "Inherent Count", fill=DARK_BG, font=_font(WHITE, True, 10), align="center")
    ws.merge_cells(f"F{r}:G{r}")
    _set(ws, f"F{r}", "Residual Count", fill=DARK_BG, font=_font(WHITE, True, 10), align="center")
    ws.merge_cells(f"H{r}:K{r}")
    _set(ws, f"H{r}", "Risk Reduction", fill=DARK_BG, font=_font(WHITE, True, 10), align="center")
    r += 1

    for level in RATING_LEVELS:
        inherent_count = sum(1 for x in rows if x["inherent_rating"] == level)
        residual_count = sum(1 for x in rows if x["residual_rating"] == level)
        diff = residual_count - inherent_count
        arrow = "↓" if diff <= 0 else "↑"
        arrow_color = "FF27AE60" if diff <= 0 else "FFC0392B"

        ws.merge_cells(f"B{r}:C{r}")
        _set(ws, f"B{r}", level, fill=RATING_COLORS[level], font=_font(WHITE, True, 10), align="center")
        ws.merge_cells(f"D{r}:E{r}")
        _set(ws, f"D{r}", inherent_count, fill=RATING_LIGHT_TINT[level], font=_font(RATING_COLORS[level], True, 10), align="center")
        ws.merge_cells(f"F{r}:G{r}")
        _set(ws, f"F{r}", residual_count, fill=RATING_LIGHT_TINT[level], font=_font(RATING_COLORS[level], True, 10), align="center")
        ws.merge_cells(f"H{r}:I{r}")
        _set(ws, f"H{r}", f"{arrow} {abs(diff)}", fill=RATING_LIGHT_TINT[level], font=_font(arrow_color, True, 10), align="center")
        r += 1

    r += 1
    ws.merge_cells(f"B{r}:I{r}")
    _set(ws, f"B{r}", "RISK SCORING LEGEND", fill=BRAND_BLUE, font=_font(WHITE, True, 12))
    r += 1

    for level, desc in [
        ("CRITICAL", "Score ≥ 15  (Likelihood × Impact)"),
        ("HIGH", "Score 10–14"),
        ("MEDIUM", "Score 5–9"),
        ("LOW", "Score 1–4"),
    ]:
        ws.merge_cells(f"B{r}:C{r}")
        _set(ws, f"B{r}", level, fill=RATING_COLORS[level], font=_font(WHITE, True, 10), align="center")
        ws.merge_cells(f"D{r}:I{r}")
        _set(ws, f"D{r}", desc, font=_font(size=10))
        r += 1

    ws.merge_cells(f"B{r}:I{r}")
    _set(ws, f"B{r}", "Likelihood / Impact scale: 1 (Very Low) → 5 (Very High)", font=_font(italic=True, size=9))


def _build_register(wb, rows, meta):
    ws = wb.create_sheet("Risk Register")
    widths = {"A": 8, "B": 16, "C": 32, "D": 52, "E": 28, "F": 10, "G": 20,
              "H": 12, "I": 10, "J": 12, "K": 12, "L": 10, "M": 10, "N": 10,
              "O": 12, "P": 12, "Q": 55}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A3"

    ws.merge_cells("A1:Q1")
    title = f"{meta['org_name'].upper()} — {meta['framework_label']} RISK REGISTER — Assessment Date: {meta['date']}"
    _set(ws, "A1", title, fill=BRAND_BLUE, font=_font(WHITE, True, 13))

    headers = ["Risk ID", "Category", "Risk Name", "Description", "Systems / Tools",
               "CIA Impact", "Assignee", "Likelihood\n(Inherent)", "Impact\n(Inherent)",
               "Inherent\nScore", "Inherent\nRating", "Residual\nLikelihood",
               "Residual\nImpact", "Residual\nScore", "Residual\nRating", "Status",
               "Treatment / Recommendation"]
    for i, h in enumerate(headers):
        col = get_column_letter(i + 1)
        _set(ws, f"{col}2", h, fill=BRAND_BLUE, font=_font(WHITE, True, 10), align="center", wrap=True)

    for idx, row in enumerate(rows, start=3):
        tint = STATUS_ROW_TINT.get(row["status"], "FFFFFFFF")
        cat_color = CATEGORY_COLORS.get(row["category"], CATEGORY_COLORS["OTHER"])
        status_color = STATUS_COLORS.get(row["status"], "FF888888")
        inherent_color = RATING_COLORS[row["inherent_rating"]]
        residual_color = RATING_COLORS[row["residual_rating"]]

        _set(ws, f"A{idx}", row["risk_id"], fill=tint, font=_font(bold=True, size=9))
        _set(ws, f"B{idx}", row["category"], fill=cat_color, font=_font(WHITE, True, 9), align="center")
        _set(ws, f"C{idx}", row.get("name", ""), fill=tint, font=_font(bold=True, size=9), wrap=True)
        _set(ws, f"D{idx}", row.get("description", ""), fill=tint, font=_font(size=9), wrap=True)
        _set(ws, f"E{idx}", row.get("application_name", ""), fill=tint, font=_font("FF555555", size=9), wrap=True)
        _set(ws, f"F{idx}", row.get("loss_of_cia", ""), fill=tint, font=_font(bold=True, size=9), align="center")
        _set(ws, f"G{idx}", row.get("assignee", ""), fill=tint, font=_font(size=9))
        _set(ws, f"H{idx}", row["likelihood"], fill=tint, font=_font(bold=True, size=9), align="center")
        _set(ws, f"I{idx}", row["impact"], fill=tint, font=_font(bold=True, size=9), align="center")
        _set(ws, f"J{idx}", row["inherent_score"], fill=tint, font=_font(inherent_color, True, 11), align="center")
        _set(ws, f"K{idx}", row["inherent_rating"], fill=inherent_color, font=_font(WHITE, True, 9), align="center")
        _set(ws, f"L{idx}", row["residual_risk_likelihood"], fill=tint, font=_font(bold=True, size=9), align="center")
        _set(ws, f"M{idx}", row["residual_risk_impact"], fill=tint, font=_font(bold=True, size=9), align="center")
        _set(ws, f"N{idx}", row["residual_score"], fill=tint, font=_font(residual_color, True, 11), align="center")
        _set(ws, f"O{idx}", row["residual_rating"], fill=residual_color, font=_font(WHITE, True, 9), align="center")
        _set(ws, f"P{idx}", row["status"], fill=status_color, font=_font(WHITE, True, 9), align="center")
        _set(ws, f"Q{idx}", row.get("treatment", ""), fill=tint, font=_font("FF333333", size=9), wrap=True)
        ws.row_dimensions[idx].height = 60


def _build_heatmap(wb, rows):
    ws = wb.create_sheet("Risk Heat Map")
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 18
    for col in "CDEFG":
        ws.column_dimensions[col].width = 16
    ws.column_dimensions["H"].width = 3

    impact_labels = ["1\nVery Low", "2\nLow", "3\nMedium", "4\nHigh", "5\nVery High"]
    likelihood_labels = ["5\nVery High", "4\nHigh", "3\nMedium", "2\nLow", "1\nVery Low"]

    def _grid(start_row, title, likelihood_key, impact_key):
        r = start_row
        ws.merge_cells(f"B{r}:G{r}")
        _set(ws, f"B{r}", title, fill=BRAND_BLUE, font=_font(WHITE, True, 14))
        r += 2
        axis_row = r
        _set(ws, f"B{axis_row}", "Likelihood ↕  /  Impact →", fill=DARK_BG, font=_font(WHITE, True, 11))
        for i, label in enumerate(impact_labels):
            col = get_column_letter(3 + i)
            _set(ws, f"{col}{axis_row}", label, fill=DARK_BG, font=_font(WHITE, True, 10), align="center", wrap=True)
        r += 1
        for li, l_label in enumerate(likelihood_labels):
            likelihood_val = 5 - li
            _set(ws, f"B{r}", l_label, fill=DARK_BG, font=_font(WHITE, True, 10), align="center", wrap=True)
            for ii in range(5):
                impact_val = ii + 1
                score = likelihood_val * impact_val
                rating = rating_from_score(score)
                ids = [
                    x["risk_id"] for x in rows
                    if x[likelihood_key] == likelihood_val and x[impact_key] == impact_val
                ]
                text = f"Score: {score}\n{rating}"
                if ids:
                    text += "\n" + ", ".join(ids)
                col = get_column_letter(3 + ii)
                _set(ws, f"{col}{r}", text, fill=RATING_COLORS[rating], font=_font(WHITE, True, 9), align="center", wrap=True)
            ws.row_dimensions[r].height = 45
            r += 1
        return r + 1

    next_row = _grid(2, "RISK HEAT MAP — INHERENT RISK (Likelihood × Impact)", "likelihood", "impact")
    _grid(next_row + 1, "RISK HEAT MAP — RESIDUAL RISK (After Treatment)", "residual_risk_likelihood", "residual_risk_impact")


def _build_by_category(wb, rows, meta):
    ws = wb.create_sheet("Risk by Category")
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 14

    r = 2
    ws.merge_cells(f"B{r}:E{r}")
    _set(ws, f"B{r}", f"RISKS BY CATEGORY — Assessment Date: {meta['date']}", fill=BRAND_BLUE, font=_font(WHITE, True, 14))
    r += 2

    by_cat = {}
    for row in rows:
        by_cat.setdefault(row["category"], []).append(row)

    for category in sorted(by_cat):
        items = by_cat[category]
        color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["OTHER"])
        tint = _light_tint(color)

        ws.merge_cells(f"B{r}:E{r}")
        _set(ws, f"B{r}", f"  {category}  ({len(items)} risks)", fill=color, font=_font(WHITE, True, 12))
        r += 1
        for col, label in zip("BCDE", ["Risk Name", "Inherent Rating", "Residual Rating", "Status"]):
            _set(ws, f"{col}{r}", label, fill=color, font=_font(WHITE, True, 10), align="center")
        r += 1
        for item in items:
            _set(ws, f"B{r}", item.get("name", ""), fill=tint, font=_font(size=10))
            _set(ws, f"C{r}", item["inherent_rating"], fill=RATING_COLORS[item["inherent_rating"]], font=_font(WHITE, True, 10), align="center")
            _set(ws, f"D{r}", item["residual_rating"], fill=RATING_COLORS[item["residual_rating"]], font=_font(WHITE, True, 10), align="center")
            _set(ws, f"E{r}", item["status"], fill=STATUS_COLORS.get(item["status"], "FF888888"), font=_font(WHITE, True, 10), align="center")
            r += 1
        r += 1


def _build_actions(wb, rows):
    ws = wb.create_sheet("Actions Required")
    widths = {"A": 3, "B": 8, "C": 30, "D": 12, "E": 12, "F": 20, "G": 55}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    r = 2
    ws.merge_cells(f"B{r}:G{r}")
    _set(ws, f"B{r}", "RISKS REQUIRING ACTION — Open & Assessed (Monitoring Required)", fill=STATUS_COLORS["OPEN"], font=_font(WHITE, True, 13))
    r += 2

    headers = ["Risk ID", "Risk Name", "Residual Rating", "Status", "Assignee", "Treatment / Recommendation"]
    for col, h in zip("BCDEFG", headers):
        _set(ws, f"{col}{r}", h, fill=BRAND_BLUE, font=_font(WHITE, True, 10), align="center")
    r += 1

    action_rows = [x for x in rows if x["status"] in ("OPEN", "ASSESSED")]
    for item in action_rows:
        tint = STATUS_ROW_TINT.get(item["status"], "FFFFFFFF")
        _set(ws, f"B{r}", item["risk_id"], fill=tint, font=_font(bold=True, size=10))
        _set(ws, f"C{r}", item.get("name", ""), fill=tint, font=_font(bold=True, size=10), wrap=True)
        _set(ws, f"D{r}", item["residual_rating"], fill=RATING_COLORS[item["residual_rating"]], font=_font(WHITE, True, 10), align="center")
        _set(ws, f"E{r}", item["status"], fill=STATUS_COLORS.get(item["status"], "FF888888"), font=_font(WHITE, True, 10), align="center")
        _set(ws, f"F{r}", item.get("assignee", ""), fill=tint, font=_font(size=10))
        _set(ws, f"G{r}", item.get("treatment", ""), fill=tint, font=_font(size=9), wrap=True)
        ws.row_dimensions[r].height = 45
        r += 1

    if not action_rows:
        ws.merge_cells(f"B{r}:G{r}")
        _set(ws, f"B{r}", "No open items — all risks are treated or closed.", font=_font(italic=True))


def build_workbook(rows, meta):
    rows = _enrich(rows)
    wb = Workbook()
    wb.remove(wb.active)
    _build_dashboard(wb, rows, meta)
    _build_register(wb, rows, meta)
    _build_heatmap(wb, rows)
    _build_by_category(wb, rows, meta)
    _build_actions(wb, rows)
    return wb


def validate_csv(path, rows):
    """Return (errors, warnings) — each a list of strings. errors block generation; warnings don't."""
    errors, warnings = [], []

    if not os.path.exists(path):
        errors.append(f"File not found: {path}")
        return errors, warnings

    if os.path.getsize(path) == 0:
        errors.append(f"File is empty (0 bytes): {path}")
        return errors, warnings

    if not rows:
        errors.append("CSV contains no data rows — file may have headers only or be blank.")
        return errors, warnings

    actual_cols = set(rows[0].keys())

    missing_required = REQUIRED_COLS - actual_cols
    if missing_required:
        errors.append(
            f"Missing required columns: {', '.join(sorted(missing_required))}. "
            "These columns are needed to compute risk scores and cannot be omitted."
        )

    missing_recommended = (EXPECTED_COLS - REQUIRED_COLS) - actual_cols
    if missing_recommended:
        warnings.append(
            f"Missing recommended columns: {', '.join(sorted(missing_recommended))}. "
            "These fields will appear blank in the report."
        )

    bad_cells = []
    for i, row in enumerate(rows, start=2):
        for col in REQUIRED_COLS & actual_cols:
            val = row.get(col, "").strip()
            if val == "":
                continue
            try:
                float(val)
            except (TypeError, ValueError):
                bad_cells.append(f"  Row {i}, column '{col}': got '{val}' (expected a number)")

    if bad_cells:
        sample = bad_cells[:10]
        note = f"  ... and {len(bad_cells) - 10} more." if len(bad_cells) > 10 else ""
        warnings.append(
            "Non-numeric values found in score columns — these will default to 0:\n"
            + "\n".join(sample) + (("\n" + note) if note else "")
        )

    return errors, warnings


def run_tests():
    import tempfile, shutil

    GREEN = "\033[32m"
    RED   = "\033[31m"
    RESET = "\033[0m"
    passed = failed = 0

    def result(name, ok, detail=""):
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"  {GREEN}[PASS]{RESET} {name}")
        else:
            failed += 1
            print(f"  {RED}[FAIL]{RESET} {name}" + (f" — {detail}" if detail else ""))

    def make_csv(content):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return f.name

    VALID_HEADER = "name,category,status,likelihood,impact,residual_risk_likelihood,residual_risk_impact,treatment,application_name,loss_of_cia,assignee,description\n"
    VALID_ROW    = "Access Control,Governance,OPEN,4,5,2,3,Implement MFA,Entra ID,CIA,test@test.com,No policy\n"
    META = {"org_name": "Test Org", "framework_label": "ISO/IEC 27001:2022",
            "date": "01 January 2025", "risk_owner": "", "isms_rep": "", "approved_by": "", "scope": "Test"}

    tmpdir = tempfile.mkdtemp()
    print("\nRunning report_generator tests...\n")

    # TC1 — file does not exist
    rows = read_rows_from_csv(os.path.join(tmpdir, "nonexistent.csv"))
    errors, _ = validate_csv(os.path.join(tmpdir, "nonexistent.csv"), rows or [])
    result("TC1: File does not exist", any("not found" in e.lower() for e in errors))

    # TC2 — empty file (0 bytes)
    p = make_csv("")
    rows = read_rows_from_csv(p)
    errors, _ = validate_csv(p, rows or [])
    result("TC2: Empty file (0 bytes)", any("empty" in e.lower() for e in errors))
    os.unlink(p)

    # TC3 — headers only, no data rows
    p = make_csv(VALID_HEADER)
    rows = read_rows_from_csv(p)
    errors, _ = validate_csv(p, rows or [])
    result("TC3: Headers only, no data rows", any("no data rows" in e.lower() for e in errors))
    os.unlink(p)

    # TC4 — missing required columns
    p = make_csv("name,category\nTest,Governance\n")
    rows = read_rows_from_csv(p)
    errors, _ = validate_csv(p, rows or [])
    result("TC4: Missing required columns", any("missing required" in e.lower() for e in errors))
    os.unlink(p)

    # TC5 — non-numeric score values (warning, not error — report still generated)
    p = make_csv(VALID_HEADER + "Bad Scores,Governance,OPEN,abc,xyz,foo,bar,Fix it,Tool,CIA,a@b.com,Desc\n")
    rows = read_rows_from_csv(p)
    errors, warnings = validate_csv(p, rows or [])
    no_blocking_errors = len(errors) == 0
    has_warning = any("non-numeric" in w.lower() for w in warnings)
    try:
        wb = build_workbook(rows, META)
        out = os.path.join(tmpdir, "tc5_report.xlsx")
        wb.save(out)
        generated = True
    except Exception as e:
        generated = False
    result("TC5: Non-numeric scores — warning issued, report still generated",
           no_blocking_errors and has_warning and generated,
           "" if (no_blocking_errors and has_warning and generated) else
           f"errors={errors} warnings={warnings} generated={generated}")
    os.unlink(p)

    # TC6 — valid minimal CSV, happy path
    p = make_csv(VALID_HEADER + VALID_ROW)
    rows = read_rows_from_csv(p)
    errors, warnings = validate_csv(p, rows or [])
    try:
        wb = build_workbook(rows, META)
        out = os.path.join(tmpdir, "tc6_report.xlsx")
        wb.save(out)
        generated = True
    except Exception as e:
        generated = False
        print(f"    Exception: {e}")
    result("TC6: Valid CSV — report generated successfully", len(errors) == 0 and generated)
    os.unlink(p)

    shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n  {passed} passed, {failed} failed\n")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Generate a formal Excel risk assessment report from a results CSV.")
    parser.add_argument("csv_path", nargs="?", help="Path to the results CSV (same shape as /api/export)")
    parser.add_argument("--org", default="Unknown Organisation", help="Client organisation name")
    parser.add_argument("--framework", default="ISO 27001", help="Framework key, e.g. 'ISO 27001', 'SOC 2', 'HIPAA'")
    parser.add_argument("--date", default=date.today().strftime("%d %B %Y"))
    parser.add_argument("--risk-owner", default="")
    parser.add_argument("--isms-rep", default="")
    parser.add_argument("--approved-by", default="")
    parser.add_argument("--scope", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--test", action="store_true", help="Run built-in test cases and exit")
    args = parser.parse_args()

    if args.test:
        ok = run_tests()
        raise SystemExit(0 if ok else 1)

    if not args.csv_path:
        parser.error("csv_path is required unless --test is used")

    rows = read_rows_from_csv(args.csv_path)
    if rows is None:
        raise SystemExit(1)

    errors, warnings = validate_csv(args.csv_path, rows)

    for w in warnings:
        print(f"[WARNING] {w}")
    for e in errors:
        print(f"[ERROR]   {e}")

    if errors:
        print("\nReport was not generated. Fix the errors above and try again.")
        raise SystemExit(1)

    meta = {
        "org_name": args.org,
        "framework_label": FRAMEWORK_LABELS.get(args.framework, args.framework),
        "date": args.date,
        "risk_owner": args.risk_owner,
        "isms_rep": args.isms_rep,
        "approved_by": args.approved_by,
        "scope": args.scope or f"All information assets, systems and processes within {args.org} assessment boundary",
    }

    try:
        wb = build_workbook(rows, meta)
        out_path = args.out or os.path.splitext(args.csv_path)[0] + "_report.xlsx"
        wb.save(out_path)
        print(f"Report written to {out_path}")
    except PermissionError:
        print(f"[ERROR] Could not write report — '{out_path}' may be open in Excel or you lack write permission.")
        raise SystemExit(1)
    except OSError as exc:
        print(f"[ERROR] Failed to save report: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
