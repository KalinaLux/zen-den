#!/usr/bin/env python3
"""
Zen Den — One-Click PDF Report Generator

Generates professional client performance reports from campaign data
using ReportLab Platypus. Zero typing required.

Usage:
    from report_generator import generate_client_report
    pdf_bytes = generate_client_report(client_data, date_range="Last 30 Days")
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# Zen Den palette
ZEN_NAVY = colors.HexColor("#1a2236")
ZEN_DARK = colors.HexColor("#111827")
ZEN_LAVENDER = colors.HexColor("#a78bfa")
ZEN_LAVENDER_LIGHT = colors.HexColor("#c4b5fd")
ZEN_SAGE = colors.HexColor("#a7c4a0")
ZEN_GREEN = colors.HexColor("#4ade80")
ZEN_CORAL = colors.HexColor("#fca5a5")
ZEN_YELLOW = colors.HexColor("#fcd34d")
ZEN_PEACH = colors.HexColor("#fdba74")
ZEN_BLUE = colors.HexColor("#93c5fd")
ZEN_TEXT = colors.HexColor("#2d3047")
ZEN_TEXT_DIM = colors.HexColor("#5c5f7a")
ZEN_TEXT_MUTED = colors.HexColor("#8b8ea8")
ZEN_BG_LIGHT = colors.HexColor("#f5f0eb")
ZEN_CARD_BG = colors.HexColor("#faf8f5")
ZEN_TABLE_HEADER = colors.HexColor("#ede7e0")
ZEN_TABLE_ROW_ALT = colors.HexColor("#f9f6f2")
ZEN_WHITE = colors.HexColor("#ffffff")
ZEN_BORDER = colors.HexColor("#d4d0ca")


def _styles():
    ss = getSampleStyleSheet()
    custom = {}

    custom["cover_title"] = ParagraphStyle(
        "cover_title", parent=ss["Title"],
        fontName="Helvetica-Bold", fontSize=32, leading=38,
        textColor=ZEN_WHITE, alignment=TA_CENTER, spaceAfter=8,
    )
    custom["cover_sub"] = ParagraphStyle(
        "cover_sub", parent=ss["Normal"],
        fontName="Helvetica", fontSize=14, leading=20,
        textColor=colors.HexColor("#d0cfe8"), alignment=TA_CENTER, spaceAfter=4,
    )
    custom["cover_detail"] = ParagraphStyle(
        "cover_detail", parent=ss["Normal"],
        fontName="Helvetica", fontSize=11, leading=16,
        textColor=colors.HexColor("#b0afc8"), alignment=TA_CENTER,
    )
    custom["section"] = ParagraphStyle(
        "section", parent=ss["Heading2"],
        fontName="Helvetica-Bold", fontSize=16, leading=22,
        textColor=ZEN_TEXT, spaceBefore=18, spaceAfter=10,
    )
    custom["subsection"] = ParagraphStyle(
        "subsection", parent=ss["Heading3"],
        fontName="Helvetica-Bold", fontSize=12, leading=16,
        textColor=ZEN_LAVENDER, spaceBefore=12, spaceAfter=6,
    )
    custom["body"] = ParagraphStyle(
        "body", parent=ss["Normal"],
        fontName="Helvetica", fontSize=10, leading=15,
        textColor=ZEN_TEXT, spaceAfter=6,
    )
    custom["body_dim"] = ParagraphStyle(
        "body_dim", parent=ss["Normal"],
        fontName="Helvetica", fontSize=9.5, leading=14,
        textColor=ZEN_TEXT_DIM, spaceAfter=4,
    )
    custom["metric_big"] = ParagraphStyle(
        "metric_big", parent=ss["Normal"],
        fontName="Helvetica-Bold", fontSize=22, leading=26,
        textColor=ZEN_LAVENDER, alignment=TA_CENTER,
    )
    custom["metric_label"] = ParagraphStyle(
        "metric_label", parent=ss["Normal"],
        fontName="Helvetica", fontSize=8, leading=11,
        textColor=ZEN_TEXT_MUTED, alignment=TA_CENTER,
    )
    custom["alert_critical"] = ParagraphStyle(
        "alert_critical", parent=ss["Normal"],
        fontName="Helvetica-Bold", fontSize=10, leading=14,
        textColor=colors.HexColor("#dc2626"), spaceAfter=4,
    )
    custom["alert_warning"] = ParagraphStyle(
        "alert_warning", parent=ss["Normal"],
        fontName="Helvetica", fontSize=10, leading=14,
        textColor=colors.HexColor("#d97706"), spaceAfter=4,
    )
    custom["alert_good"] = ParagraphStyle(
        "alert_good", parent=ss["Normal"],
        fontName="Helvetica", fontSize=10, leading=14,
        textColor=colors.HexColor("#16a34a"), spaceAfter=4,
    )
    custom["footer"] = ParagraphStyle(
        "footer", parent=ss["Normal"],
        fontName="Helvetica", fontSize=8, leading=10,
        textColor=ZEN_TEXT_MUTED, alignment=TA_CENTER,
    )
    return custom


def _cover_bg(canvas, doc):
    w, h = letter
    canvas.saveState()
    canvas.setFillColor(ZEN_NAVY)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#1f2b45"))
    canvas.circle(w * 0.8, h * 0.85, 200, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#16203a"))
    canvas.circle(w * 0.15, h * 0.2, 150, fill=1, stroke=0)
    canvas.restoreState()


def _body_page(canvas, doc):
    w, h = letter
    canvas.saveState()
    canvas.setFillColor(ZEN_BG_LIGHT)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    canvas.setStrokeColor(ZEN_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.6 * inch, w - 0.75 * inch, 0.6 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(ZEN_TEXT_MUTED)
    canvas.drawString(0.75 * inch, 0.38 * inch, "Zen Den — Confidential")
    canvas.drawRightString(w - 0.75 * inch, 0.38 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _fmt_num(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}"


def _fmt_money(n):
    if n >= 1_000_000:
        return f"${n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n / 1_000:.1f}K"
    return f"${n:,.2f}"


def _fmt_pct(n):
    return f"{n:.2f}%"


def _status_color(s):
    s = s.upper()
    if s == "ENABLED":
        return colors.HexColor("#16a34a")
    if s == "PAUSED":
        return colors.HexColor("#d97706")
    return colors.HexColor("#dc2626")


def _metric_cell(value, label, st):
    return Table(
        [[Paragraph(str(value), st["metric_big"])],
         [Paragraph(label, st["metric_label"])]],
        colWidths=[1.6 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ZEN_CARD_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, ZEN_BORDER),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]),
    )


def generate_client_report(client_data, date_range="Last 30 Days"):
    """Generate a PDF report and return bytes.

    Args:
        client_data: dict with 'name', 'account_lead', 'customer_id', 'campaigns' list
        date_range: string like "Last 30 Days", "Last 7 Days", etc.

    Returns:
        bytes: PDF file content
    """
    buf = io.BytesIO()
    st = _styles()
    page_w, page_h = letter
    margin = 0.75 * inch

    cover_frame = Frame(margin, margin, page_w - 2 * margin, page_h - 2 * margin, id="cover")
    body_frame = Frame(margin, 0.8 * inch, page_w - 2 * margin, page_h - 1.6 * inch, id="body")

    doc = BaseDocTemplate(
        buf, pagesize=letter,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=0.8 * inch,
    )
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=_cover_bg),
        PageTemplate(id="body", frames=[body_frame], onPage=_body_page),
    ])

    story = []
    client_name = client_data["name"]
    campaigns = client_data.get("campaigns", [])
    account_lead = client_data.get("account_lead", "—")
    customer_id = client_data.get("customer_id", "—")
    now = datetime.now()

    # ── Cover page ──
    story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph("PERFORMANCE REPORT", ParagraphStyle(
        "cover_kicker", fontName="Helvetica", fontSize=11, leading=14,
        textColor=ZEN_LAVENDER_LIGHT, alignment=TA_CENTER,
        spaceAfter=12, letterSpacing=3,
    )))
    story.append(Paragraph(client_name, st["cover_title"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(date_range, st["cover_sub"]))
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f"Prepared by Zen Den<br/>Account Lead: {account_lead}<br/>"
        f"Customer ID: {customer_id}",
        st["cover_detail"],
    ))
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Generated {now.strftime('%B %d, %Y at %I:%M %p')}",
        st["cover_detail"],
    ))
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())

    # ── Aggregate metrics ──
    active = [c for c in campaigns if c.get("status", "").upper() not in ("REMOVED",)]
    perf_campaigns = [c for c in active if c.get("performance")]

    tot_impr = sum(c["performance"].get("impressions", 0) for c in perf_campaigns)
    tot_clicks = sum(c["performance"].get("clicks", 0) for c in perf_campaigns)
    tot_cost = sum(c["performance"].get("cost", 0) for c in perf_campaigns)
    tot_conv = sum(c["performance"].get("conversions", 0) for c in perf_campaigns)
    tot_conv_val = sum(c["performance"].get("conv_value", 0) for c in perf_campaigns)
    overall_ctr = (tot_clicks / tot_impr * 100) if tot_impr else 0
    overall_cpc = (tot_cost / tot_clicks) if tot_clicks else 0
    overall_roas = (tot_conv_val / tot_cost) if tot_cost else 0

    story.append(Paragraph("Executive Summary", st["section"]))
    story.append(Paragraph(
        f"Reporting period: <b>{date_range}</b> &bull; "
        f"{len(active)} active campaigns &bull; "
        f"{sum(1 for c in active if c.get('status','').upper() == 'ENABLED')} enabled, "
        f"{sum(1 for c in active if c.get('status','').upper() == 'PAUSED')} paused",
        st["body"],
    ))

    metrics_row = [
        _metric_cell(_fmt_money(tot_cost), "TOTAL SPEND", st),
        _metric_cell(_fmt_num(tot_conv), "CONVERSIONS", st),
        _metric_cell(f"{overall_roas:.2f}x", "ROAS", st),
        _metric_cell(_fmt_num(tot_impr), "IMPRESSIONS", st),
    ]
    metrics_table = Table([metrics_row], colWidths=[1.75 * inch] * 4)
    metrics_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(Spacer(1, 6))
    story.append(metrics_table)
    story.append(Spacer(1, 8))

    summary_parts = []
    if overall_roas >= 3:
        summary_parts.append(f"Strong overall ROAS of {overall_roas:.2f}x")
    elif overall_roas >= 1.5:
        summary_parts.append(f"Moderate ROAS of {overall_roas:.2f}x — room for optimization")
    elif tot_cost > 0:
        summary_parts.append(f"ROAS of {overall_roas:.2f}x is below target — review recommended")

    if tot_clicks:
        summary_parts.append(f"Average CPC of {_fmt_money(overall_cpc)} across {_fmt_num(tot_clicks)} clicks")
    if tot_conv:
        conv_rate = tot_conv / tot_clicks * 100 if tot_clicks else 0
        summary_parts.append(f"Conversion rate: {conv_rate:.1f}% ({_fmt_num(tot_conv)} conversions)")
    if tot_conv_val:
        summary_parts.append(f"Total revenue attributed: {_fmt_money(tot_conv_val)}")

    for part in summary_parts:
        story.append(Paragraph(f"• {part}", st["body"]))

    # ── Campaign Breakdown ──
    story.append(Spacer(1, 10))
    story.append(Paragraph("Campaign Breakdown", st["section"]))

    hdr_style = ParagraphStyle("thdr", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=ZEN_TEXT)
    cell_style = ParagraphStyle("tcell", fontName="Helvetica", fontSize=8, leading=11, textColor=ZEN_TEXT)
    cell_r_style = ParagraphStyle("tcellr", fontName="Helvetica", fontSize=8, leading=11, textColor=ZEN_TEXT, alignment=TA_RIGHT)

    headers = [
        Paragraph("Campaign", hdr_style),
        Paragraph("Status", hdr_style),
        Paragraph("Budget", hdr_style),
        Paragraph("Impr.", hdr_style),
        Paragraph("Clicks", hdr_style),
        Paragraph("CTR", hdr_style),
        Paragraph("CPC", hdr_style),
        Paragraph("Conv.", hdr_style),
        Paragraph("Cost", hdr_style),
        Paragraph("ROAS", hdr_style),
    ]
    table_data = [headers]

    col_widths = [2.0 * inch, 0.6 * inch, 0.6 * inch, 0.6 * inch, 0.5 * inch, 0.45 * inch, 0.45 * inch, 0.45 * inch, 0.6 * inch, 0.5 * inch]

    for c in active:
        perf = c.get("performance", {})
        name_short = c["name"]
        if len(name_short) > 40:
            name_short = name_short[:38] + "…"
        row = [
            Paragraph(name_short, cell_style),
            Paragraph(c.get("status", "—"), cell_style),
            Paragraph(c.get("budget_daily", "—"), cell_r_style),
            Paragraph(_fmt_num(perf.get("impressions", 0)), cell_r_style),
            Paragraph(_fmt_num(perf.get("clicks", 0)), cell_r_style),
            Paragraph(_fmt_pct(perf.get("ctr", 0)), cell_r_style),
            Paragraph(_fmt_money(perf.get("avg_cpc", 0)), cell_r_style),
            Paragraph(str(int(perf.get("conversions", 0))), cell_r_style),
            Paragraph(_fmt_money(perf.get("cost", 0)), cell_r_style),
            Paragraph(f"{perf.get('roas', 0):.2f}x", cell_r_style),
        ]
        table_data.append(row)

    # Totals row
    table_data.append([
        Paragraph("<b>TOTAL</b>", cell_style), Paragraph("", cell_style),
        Paragraph("", cell_r_style),
        Paragraph(f"<b>{_fmt_num(tot_impr)}</b>", cell_r_style),
        Paragraph(f"<b>{_fmt_num(tot_clicks)}</b>", cell_r_style),
        Paragraph(f"<b>{_fmt_pct(overall_ctr)}</b>", cell_r_style),
        Paragraph(f"<b>{_fmt_money(overall_cpc)}</b>", cell_r_style),
        Paragraph(f"<b>{_fmt_num(tot_conv)}</b>", cell_r_style),
        Paragraph(f"<b>{_fmt_money(tot_cost)}</b>", cell_r_style),
        Paragraph(f"<b>{overall_roas:.2f}x</b>", cell_r_style),
    ])

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), ZEN_TABLE_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), ZEN_TEXT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, ZEN_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        # Totals row
        ("BACKGROUND", (0, -1), (-1, -1), ZEN_TABLE_HEADER),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]
    for i in range(1, len(table_data) - 1):
        if i % 2 == 0:
            tbl_style.append(("BACKGROUND", (0, i), (-1, i), ZEN_TABLE_ROW_ALT))
        status = active[i - 1].get("status", "").upper()
        if status == "ENABLED":
            tbl_style.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#16a34a")))
        elif status == "PAUSED":
            tbl_style.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#d97706")))

    tbl.setStyle(TableStyle(tbl_style))
    story.append(tbl)

    # ── Promotions ──
    all_promos = []
    for c in campaigns:
        for p in c.get("promos", []):
            all_promos.append({"campaign": c["name"], "status": c.get("status", ""), "promo": p})

    if all_promos:
        story.append(Spacer(1, 14))
        story.append(Paragraph("Promotions &amp; Extensions", st["section"]))
        for entry in all_promos:
            promo = entry["promo"]
            pstatus = promo.get("status", "UNKNOWN")
            serving = promo.get("serving", False)
            icon = "✓" if serving else ("✗" if pstatus == "DISAPPROVED" else "○")

            if pstatus == "DISAPPROVED":
                pstyle = st["alert_critical"]
            elif serving:
                pstyle = st["alert_good"]
            else:
                pstyle = st["alert_warning"]

            story.append(Paragraph(
                f"{icon} <b>{entry['campaign']}</b> — {promo.get('text', '')}",
                pstyle,
            ))
            if promo.get("reason"):
                story.append(Paragraph(f"    ↳ {promo['reason']}", st["body_dim"]))
            dates = []
            if promo.get("start_date"):
                dates.append(f"Start: {promo['start_date']}")
            if promo.get("end_date"):
                dates.append(f"End: {promo['end_date']}")
            if dates:
                story.append(Paragraph(f"    {' | '.join(dates)}", st["body_dim"]))

    # ── Alerts & Recommendations ──
    alerts = []
    for c in campaigns:
        perf = c.get("performance", {})
        if c.get("status", "").upper() == "PAUSED":
            alerts.append(("warning", f"{c['name']} is PAUSED — review if intentional"))
        for p in c.get("promos", []):
            if p.get("status") == "DISAPPROVED":
                alerts.append(("critical", f"{c['name']} has a DISAPPROVED promo: {p.get('reason', 'unknown reason')}"))
        roas = perf.get("roas", 0)
        cost = perf.get("cost", 0)
        if cost > 0 and roas < 1.0:
            alerts.append(("warning", f"{c['name']} ROAS is {roas:.2f}x — below breakeven"))
        if cost > 0 and roas >= 4.0:
            alerts.append(("good", f"{c['name']} ROAS is {roas:.2f}x — consider scaling budget"))

    if alerts:
        story.append(Spacer(1, 14))
        story.append(Paragraph("Alerts &amp; Recommendations", st["section"]))
        for level, msg in alerts:
            icon = {"critical": "🔴", "warning": "🟡", "good": "🟢"}.get(level, "•")
            style_key = f"alert_{level}"
            story.append(Paragraph(f"{icon} {msg}", st.get(style_key, st["body"])))

    # ── Next Steps ──
    story.append(Spacer(1, 14))
    story.append(Paragraph("Next Steps", st["section"]))

    next_steps = []
    paused_with_future = [c for c in campaigns
                          if c.get("status", "").upper() == "PAUSED"
                          and c.get("start_date", "") > now.strftime("%Y-%m-%d")]
    for c in paused_with_future:
        next_steps.append(f"<b>{c['name']}</b> scheduled to launch {c.get('start_date', 'soon')}")

    disapproved = [c for c in campaigns for p in c.get("promos", []) if p.get("status") == "DISAPPROVED"]
    if disapproved:
        names = ", ".join(set(c["name"] for c in disapproved))
        next_steps.append(f"Review disapproved promotions on: {names}")

    low_roas = [c for c in campaigns
                if c.get("performance", {}).get("cost", 0) > 0
                and c.get("performance", {}).get("roas", 0) < 1.0]
    if low_roas:
        names = ", ".join(c["name"] for c in low_roas)
        next_steps.append(f"Optimize underperforming campaigns: {names}")

    high_roas = [c for c in campaigns
                 if c.get("performance", {}).get("roas", 0) >= 4.0]
    if high_roas:
        names = ", ".join(c["name"] for c in high_roas)
        next_steps.append(f"Consider budget increases for top performers: {names}")

    if not next_steps:
        next_steps.append("Continue monitoring performance — all campaigns healthy")

    for step in next_steps:
        story.append(Paragraph(f"→ {step}", st["body"]))

    # ── Footer note ──
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "This report was auto-generated by Zen Den. "
        "Data sourced from Google Ads API (demo mode: mock data). "
        "Confidential — do not distribute externally.",
        st["footer"],
    ))

    doc.build(story)
    return buf.getvalue()


if __name__ == "__main__":
    import json
    from pathlib import Path

    mock_path = Path(__file__).parent / "mock_campaigns.json"
    with open(mock_path) as f:
        data = json.load(f)

    for client in data["clients"]:
        pdf_bytes = generate_client_report(client, "Last 30 Days")
        out_name = client["name"].replace(" ", "_").lower() + "_report.pdf"
        out_path = Path(__file__).parent / out_name
        with open(out_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"Generated: {out_path} ({len(pdf_bytes):,} bytes)")
