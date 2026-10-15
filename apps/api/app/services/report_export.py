"""Export a readiness report dict to JSON, CSV, or PDF bytes.

reportlab is imported lazily inside to_pdf so the module imports cleanly
even if the library is missing (the PDF endpoint would then fail at call
time with a clear ImportError).
"""
from __future__ import annotations

import csv
import io
import json


def to_json(report: dict) -> bytes:
    return json.dumps(report, indent=2, default=str).encode("utf-8")


def to_csv(report: dict) -> bytes:
    """Summary block, then one row per issue. BOM so Excel opens it."""
    buf = io.StringIO()
    w = csv.writer(buf)

    p = report["project"]
    s = report["summary"]

    w.writerow(["BIMGuard Readiness Report"])
    w.writerow(["Generated", report["generated_at"]])
    w.writerow(["Project", p["name"]])
    w.writerow(["Project ID", p["id"]])
    w.writerow(["Client", p["client"] or "-"])
    w.writerow(["Project status", p["status"]])
    w.writerow(["Readiness", s["readiness_status"]])
    w.writerow([])
    w.writerow(["Documents", s["documents"]])
    w.writerow(["Documents with revision", s["documents_with_revision"]])
    w.writerow(["Dependencies", s["dependencies"]])
    w.writerow(["Stale dependencies", s["stale_dependencies"]])
    w.writerow(["Open impacts", s["open_impacts"]["total"]])
    w.writerow(["Issues total", s["issue_counts"]["total"]])
    w.writerow(["Issues open", s["issue_counts"]["open"]])
    w.writerow(["Issues acknowledged", s["issue_counts"]["acknowledged"]])
    w.writerow([])

    w.writerow(["Severity", "Document", "Element", "Rule ID", "Title", "Status",
                "Message", "Recommended action", "Acknowledged by", "Note"])

    for i in report["issues"]:
        w.writerow([
            i.get("severity", ""),
            i.get("document_number", ""),
            i.get("element_tag", ""),
            i.get("rule_id", ""),
            i.get("title", ""),
            i.get("status", ""),
            i.get("message", ""),
            i.get("recommended_action", ""),
            i.get("acknowledged_by_name", ""),
            i.get("acknowledgement_note", ""),
        ])

    return buf.getvalue().encode("utf-8-sig")


def to_pdf(report: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    p = report["project"]
    s = report["summary"]

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Readiness report - {p['name']}",
        author="BIMGuard",
    )
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]

    story = []
    story.append(Paragraph("BIMGuard readiness report", h1))
    story.append(Paragraph(p["name"], h2))
    story.append(Paragraph(f"Client: {p['client'] or '-'}", body))
    story.append(Paragraph(f"Project status: {p['status']}", body))
    story.append(Paragraph(f"Readiness: {s['readiness_status']}", body))
    story.append(Paragraph(f"Generated: {report['generated_at']}", body))
    story.append(Spacer(1, 6 * mm))

    summary_rows = [
        ["Documents", str(s["documents"])],
        ["Documents with revision", str(s["documents_with_revision"])],
        ["Dependencies", str(s["dependencies"])],
        ["Stale dependencies", str(s["stale_dependencies"])],
        ["Open impacts", str(s["open_impacts"]["total"])],
        ["Issues total", str(s["issue_counts"]["total"])],
        ["Issues open", str(s["issue_counts"]["open"])],
        ["Issues acknowledged", str(s["issue_counts"]["acknowledged"])],
    ]
    t = Table(summary_rows, colWidths=[70 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"Issues ({len(report['issues'])})", h2))
    if not report["issues"]:
        story.append(Paragraph("No issues.", body))
    else:
        header = ["Severity", "Document", "Rule", "Title", "Status"]
        rows = [header]
        for i in report["issues"]:
            rows.append([
                i.get("severity", ""),
                i.get("document_number", "") or "-",
                i.get("rule_id", ""),
                (i.get("title", "") or "")[:70],
                i.get("status", ""),
            ])
        t = Table(
            rows,
            colWidths=[18 * mm, 22 * mm, 35 * mm, 75 * mm, 22 * mm],
            repeatRows=1,
        )
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)

    story.append(Spacer(1, 6 * mm))
    if s["document_health"]:
        story.append(Paragraph("Document health", h2))
        dh = s["document_health"]
        dh_rows = [["Healthy", "Warning", "Stale", "Critical"],
                   [str(dh.get("healthy", 0)), str(dh.get("warning", 0)),
                    str(dh.get("stale", 0)), str(dh.get("critical", 0))]]
        t = Table(dh_rows, colWidths=[35 * mm, 35 * mm, 35 * mm, 35 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(t)

    doc.build(story)
    return buf.getvalue()