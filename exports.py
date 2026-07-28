"""
Bakery ERP System - Export Service
Generates PDF (reportlab) and Excel (openpyxl) downloads for:
  * Customer statement
  * Production order invoice
Both functions return a BytesIO buffer ready to send via Flask's
`send_file`. We keep zero file-system side effects so the service is
safe in serverless / read-only deployments.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from models import (
    db, Customer, Sale, Payment, ProductionOrder, Product, ProductionWaste,
)


# ---------------------------------------------------------------------------
# Shared styling helpers
# ---------------------------------------------------------------------------
def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ERPTitle', parent=styles['Title'],
        fontSize=20, spaceAfter=10, textColor=colors.HexColor('#2c3e50'),
    ))
    styles.add(ParagraphStyle(
        name='ERPInfo', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#34495e'),
    ))
    return styles


def _pdf_table_style():
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ])


# ---------------------------------------------------------------------------
# Customer Statement — PDF
# ---------------------------------------------------------------------------
def customer_statement_pdf(customer_id: int) -> io.BytesIO:
    customer: Customer = db.session.get(Customer, customer_id)
    if not customer:
        raise ValueError(f"Customer {customer_id} not found")

    sales: List[Sale] = (
        db.session.query(Sale)
        .filter(Sale.customer_id == customer_id)
        .order_by(Sale.date.asc())
        .all()
    )
    payments: List[Payment] = (
        db.session.query(Payment)
        .filter(Payment.customer_id == customer_id)
        .order_by(Payment.date.asc())
        .all()
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = _pdf_styles()
    story = [
        Paragraph("Bakery ERP — Customer Statement", styles['ERPTitle']),
        Paragraph(f"<b>Customer:</b> {customer.name}", styles['ERPInfo']),
        Paragraph(f"<b>Email:</b> {customer.email or '-'}", styles['ERPInfo']),
        Paragraph(f"<b>Phone:</b> {customer.phone or '-'}", styles['ERPInfo']),
        Paragraph(
            f"<b>Address:</b> {customer.address or '-'}",
            styles['ERPInfo'],
        ),
        Paragraph(
            f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles['ERPInfo'],
        ),
        Spacer(1, 8 * mm),
    ]

    # --- Sales table ---
    story.append(Paragraph("<b>Sales</b>", styles['Heading3']))
    if sales:
        sales_rows = [['#', 'Date', 'Total', 'Paid', 'Balance', 'Status']]
        total_due = 0.0
        for s in sales:
            paid = s.total_paid
            bal = s.balance_due
            total_due += bal
            sales_rows.append([
                str(s.id),
                str(s.date),
                f"{s.grand_total:.2f}",
                f"{paid:.2f}",
                f"{bal:.2f}",
                s.payment_status,
            ])
        sales_rows.append([
            '', 'Totals',
            f"{sum(s.grand_total for s in sales):.2f}",
            f"{sum(s.total_paid for s in sales):.2f}",
            f"{total_due:.2f}", '',
        ])
        t = Table(sales_rows, colWidths=[18 * mm, 28 * mm, 28 * mm,
                                          28 * mm, 28 * mm, 30 * mm])
        t.setStyle(_pdf_table_style())
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("<i>No sales recorded.</i>", styles['ERPInfo']))

    story.append(Spacer(1, 8 * mm))

    # --- Payments table ---
    story.append(Paragraph("<b>Payments</b>", styles['Heading3']))
    if payments:
        rows = [['#', 'Date', 'Sale #', 'Method', 'Amount', 'Notes']]
        for p in payments:
            rows.append([
                str(p.id), str(p.date), str(p.sale_id or '-'),
                p.payment_method, f"{p.amount:.2f}", p.notes or '',
            ])
        t = Table(rows, colWidths=[18 * mm, 28 * mm, 24 * mm, 32 * mm,
                                    30 * mm, 28 * mm])
        t.setStyle(_pdf_table_style())
        story.append(t)
    else:
        story.append(Paragraph("<i>No payments recorded.</i>", styles['ERPInfo']))

    doc.build(story)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Production Order Invoice — PDF
# ---------------------------------------------------------------------------
def production_order_invoice_pdf(order_id: int) -> io.BytesIO:
    order: ProductionOrder = db.session.get(ProductionOrder, order_id)
    if not order:
        raise ValueError(f"Production order {order_id} not found")
    product: Product = order.product

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = _pdf_styles()
    waste_units = order.total_waste

    story = [
        Paragraph("Bakery ERP — Production Order", styles['ERPTitle']),
        Paragraph(f"<b>Order #:</b> {order.id}", styles['ERPInfo']),
        Paragraph(f"<b>Date:</b> {order.date}", styles['ERPInfo']),
        Paragraph(f"<b>Status:</b> {order.status}", styles['ERPInfo']),
        Paragraph(f"<b>Product:</b> {product.name} "
                  f"({product.category})", styles['ERPInfo']),
        Paragraph(
            f"<b>Planned Qty:</b> {order.planned_qty} &nbsp;&nbsp; "
            f"<b>Actual Qty:</b> {order.actual_qty} &nbsp;&nbsp; "
            f"<b>Waste:</b> {waste_units}",
            styles['ERPInfo'],
        ),
        Spacer(1, 6 * mm),
        Paragraph("<b>Notes</b>", styles['Heading3']),
        Paragraph(order.notes or '-', styles['ERPInfo']),
        Spacer(1, 6 * mm),
    ]

    # --- Recipe (BOM) table ---
    story.append(Paragraph("<b>Bill of Materials</b>", styles['Heading3']))
    rows = [['Ingredient', 'Qty / unit', 'Unit cost', 'Line cost']]
    total_cost = 0.0
    for recipe in product.recipes:
        line = float(recipe.quantity_required) * float(recipe.item.cost or 0)
        total_cost += line
        rows.append([
            recipe.item.name,
            f"{recipe.quantity_required} {recipe.item.unit}",
            f"{recipe.item.cost:.2f}",
            f"{line:.2f}",
        ])
    rows.append(['', '', 'Unit cost', f"{total_cost:.2f}"])
    rows.append(['', '', f"x planned qty", f"{total_cost * order.planned_qty:.2f}"])
    t = Table(rows, colWidths=[60 * mm, 40 * mm, 35 * mm, 35 * mm])
    t.setStyle(_pdf_table_style())
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, -2), (-1, -2), colors.HexColor('#ecf0f1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#bdc3c7')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(t)

    # --- Waste breakdown ---
    if order.waste_records:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("<b>Waste Records</b>", styles['Heading3']))
        wrows = [['Recorded', 'Qty', 'Reason']]
        for w in order.waste_records:
            wrows.append([
                w.recorded_at.strftime('%Y-%m-%d %H:%M'),
                str(w.quantity),
                w.reason or '-',
            ])
        wt = Table(wrows, colWidths=[40 * mm, 25 * mm, 100 * mm])
        wt.setStyle(_pdf_table_style())
        story.append(wt)
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(
            f"<b>Total waste cost:</b> ${order.waste_cost:.2f}",
            styles['ERPInfo'],
        ))

    doc.build(story)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Generic XLSX exporter (for any iterable of dicts)
# ---------------------------------------------------------------------------
def _xlsx_header_style(cell):
    cell.font = Font(bold=True, color='FFFFFF')
    cell.fill = PatternFill('solid', fgColor='2C3E50')
    cell.alignment = Alignment(horizontal='center', vertical='center')


def _xlsx_border():
    side = Side(border_style='thin', color='CCCCCC')
    return Border(left=side, right=side, top=side, bottom=side)


def rows_to_xlsx(rows: List[dict], sheet_name: str = 'Report') -> io.BytesIO:
    """Convert a list of flat dicts to an XLSX workbook in memory."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31] or 'Report'

    if not rows:
        ws.append(['(no data)'])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    headers = list(rows[0].keys())
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        _xlsx_header_style(cell)
        cell.border = _xlsx_border()

    for r_idx, row in enumerate(rows, start=2):
        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=row.get(h))
            cell.border = _xlsx_border()

    # auto width
    for col_idx, h in enumerate(headers, 1):
        letter = get_column_letter(col_idx)
        max_len = max(
            [len(str(h))] +
            [len(str(r.get(h, ''))) for r in rows]
        )
        ws.column_dimensions[letter].width = min(max_len + 2, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def profitability_xlsx(summaries) -> io.BytesIO:
    """Convenience: convert ProfitabilityService results to XLSX."""
    rows = [s.to_dict() for s in summaries]
    return rows_to_xlsx(rows, sheet_name='Profitability')


def reorder_suggestions_xlsx(suggestions) -> io.BytesIO:
    rows = [s.to_dict() for s in suggestions]
    return rows_to_xlsx(rows, sheet_name='Reorder')
