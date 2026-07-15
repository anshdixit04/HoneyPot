"""
On-demand PDF summary report (see docs/02-design-doc.md section 8.4).
Renders server-side from the existing SQLite store - no new data source,
just the same aggregates behind /api/stats plus top sessions.
"""
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import store

ACCENT = colors.HexColor("#3b6fb0")
MUTED = colors.HexColor("#5a6b85")
GRID = colors.HexColor("#c9d3e0")


def _table(headers, rows, col_widths=None):
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5fa")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def build_report_pdf(range_str: str, hours: int) -> bytes:
    stats = store.get_stats(hours)
    sessions = store.get_top_sessions(hours)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=ACCENT)
    meta_style = ParagraphStyle("ReportMeta", parent=styles["Normal"], textColor=MUTED, fontSize=9)
    h2_style = ParagraphStyle("ReportH2", parent=styles["Heading2"], textColor=ACCENT, spaceBefore=14)

    total_connections = sum(h["count"] for h in stats["connections_by_hour"])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    story = [
        Paragraph("Live Honeypot Attack Map - Report", title_style),
        Paragraph(f"Range: {range_str} &nbsp;&nbsp;|&nbsp;&nbsp; Generated: {generated_at}", meta_style),
        Spacer(1, 4),
        Paragraph(
            f"{total_connections} connection(s) across {len(stats['top_countries'])} "
            f"countr{'y' if len(stats['top_countries']) == 1 else 'ies'} in this window.",
            meta_style,
        ),
    ]

    story.append(Paragraph("Top Countries", h2_style))
    if stats["top_countries"]:
        rows = [[c["country"], str(c["count"])] for c in stats["top_countries"]]
        story.append(_table(["Country", "Connections"], rows, col_widths=[3 * inch, 2 * inch]))
    else:
        story.append(Paragraph("No data in this window.", meta_style))

    story.append(Paragraph("Top Credentials Tried", h2_style))
    if stats["top_credentials"]:
        rows = [[c["username"] or "", c["password"] or "", str(c["count"])] for c in stats["top_credentials"]]
        story.append(_table(["Username", "Password", "Count"], rows, col_widths=[2 * inch, 2 * inch, 1 * inch]))
    else:
        story.append(Paragraph("No data in this window.", meta_style))

    story.append(Paragraph("Notable Sessions", h2_style))
    if sessions:
        rows = []
        for s in sessions:
            commands = [c for c in (s["commands"] or "").split("\n") if c]
            preview = ", ".join(commands[:3]) + ("…" if len(commands) > 3 else "")
            rows.append([s["src_ip"] or "", str(s["event_count"]), preview or "-"])
        story.append(_table(["Source IP", "Events", "Commands (preview)"], rows, col_widths=[1.5 * inch, 0.8 * inch, 2.7 * inch]))
    else:
        story.append(Paragraph("No sessions in this window.", meta_style))

    doc.build(story)
    return buf.getvalue()
