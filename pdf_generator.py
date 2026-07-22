from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import io

# Paleta de colores
COLOR_PRIMARY = colors.HexColor('#4361ee')
COLOR_SUCCESS = colors.HexColor('#10b981')
COLOR_DANGER = colors.HexColor('#ef4444')
COLOR_DARK = colors.HexColor('#1e293b')
COLOR_GRAY = colors.HexColor('#64748b')
COLOR_LIGHT = colors.HexColor('#f1f5f9')
COLOR_WHITE = colors.white
COLOR_ROW_ALT = colors.HexColor('#f8fafc')
COLOR_BORDER = colors.HexColor('#e2e8f0')


def fmt(valor, simbolo='$'):
    if valor is None:
        return f'{simbolo} 0,00'
    return f'{simbolo} {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def generar_pdf_reporte(config, data, fecha_desde, fecha_hasta, local_nombre='', cat_nombre='', fija_label='', medio_pago=''):
    buffer = io.BytesIO()
    nombre_negocio = config.get('nombre_negocio', 'Mi Negocio')
    simbolo = config.get('moneda_simbolo', '$')

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    # Estilos personalizados
    style_title = ParagraphStyle(
        'CustomTitle',
        parent=styles['Normal'],
        fontSize=20,
        textColor=COLOR_WHITE,
        fontName='Helvetica-Bold',
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    style_subtitle = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#cbd5e1'),
        fontName='Helvetica',
        alignment=TA_LEFT,
    )
    style_section = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontSize=13,
        textColor=COLOR_PRIMARY,
        fontName='Helvetica-Bold',
        spaceBefore=16,
        spaceAfter=6,
    )
    style_normal = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=9,
        textColor=COLOR_DARK,
        fontName='Helvetica',
    )
    style_small = ParagraphStyle(
        'Small',
        parent=styles['Normal'],
        fontSize=8,
        textColor=COLOR_GRAY,
        fontName='Helvetica',
    )
    style_meta = ParagraphStyle(
        'Meta',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#94a3b8'),
        fontName='Helvetica',
        alignment=TA_RIGHT,
    )

    story = []

    # ── HEADER BLOCK ──────────────────────────────────────────────
    header_data = [[
        Paragraph(f'<b>{nombre_negocio}</b>', style_title),
        Paragraph(f'Generado el {datetime.now().strftime("%d/%m/%Y %H:%M")}', style_meta),
    ]]
    header_table = Table(header_data, colWidths=[12 * cm, 5 * cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_PRIMARY),
        ('PADDING', (0, 0), (-1, -1), 14),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(header_table)

    sub_data = [[
        Paragraph('Reporte de Ingresos y Gastos', style_subtitle),
        Paragraph('', style_subtitle),
    ]]
    sub_table = Table(sub_data, colWidths=[12 * cm, 5 * cm])
    sub_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#3651d4')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(sub_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── FILTROS APLICADOS ──────────────────────────────────────────
    filtros = [f'Período: {fecha_desde} al {fecha_hasta}']
    if local_nombre:
        filtros.append(f'Local: {local_nombre}')
    if cat_nombre:
        filtros.append(f'Categoría: {cat_nombre}')
    if fija_label:
        filtros.append(f'Egresos: {fija_label}')
    if medio_pago:
        filtros.append(f'Medio de pago: {medio_pago}')

    filtros_str = '   |   '.join(filtros)
    story.append(Paragraph(f'Filtros aplicados: {filtros_str}', style_small))
    story.append(HRFlowable(width='100%', thickness=1, color=COLOR_BORDER, spaceAfter=8))

    # ── RESUMEN EJECUTIVO ──────────────────────────────────────────
    story.append(Paragraph('Resumen Ejecutivo', style_section))

    balance = data['balance']
    bal_color = '#10b981' if balance >= 0 else '#ef4444'

    resumen_data = [
        ['Concepto', 'Monto'],
        ['Total Ingresos', fmt(data['total_ingresos'], simbolo)],
        ['Total Gastos', fmt(data['total_gastos'], simbolo)],
        ['Balance Neto', fmt(balance, simbolo)],
    ]
    resumen_table = Table(resumen_data, colWidths=[10 * cm, 7 * cm])
    resumen_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#ecfdf5')),
        ('TEXTCOLOR', (1, 1), (1, 1), COLOR_SUCCESS),
        ('FONTNAME', (1, 1), (1, 1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#fef2f2')),
        ('TEXTCOLOR', (1, 2), (1, 2), COLOR_DANGER),
        ('FONTNAME', (1, 2), (1, 2), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 3), (-1, 3), COLOR_LIGHT),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1, 3), (1, 3), colors.HexColor(bal_color)),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [COLOR_WHITE, COLOR_ROW_ALT]),
        ('PADDING', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(resumen_table)

    # ── GASTOS POR CATEGORÍA ──────────────────────────────────────
    if data['gastos_por_cat']:
        story.append(Paragraph('Gastos por Categoría', style_section))
        cat_data = [['Categoría', 'Cantidad', 'Total', '%']]
        total_g = data['total_gastos'] or 1
        for row in data['gastos_por_cat']:
            pct = (row['total'] / total_g * 100)
            cat_data.append([
                row['nombre'],
                str(row['cantidad']),
                fmt(row['total'], simbolo),
                f'{pct:.1f}%',
            ])
        cat_table = Table(cat_data, colWidths=[7 * cm, 3 * cm, 5 * cm, 2 * cm])
        cat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_DARK),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, COLOR_ROW_ALT]),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(cat_table)

    # ── GASTOS POR PROVEEDOR ──────────────────────────────────────
    if data['gastos_por_proveedor']:
        story.append(Paragraph('Gastos por Proveedor', style_section))
        prov_data = [['Proveedor', 'Cantidad', 'Total']]
        for row in data['gastos_por_proveedor']:
            prov_data.append([row['nombre'], str(row['cantidad']), fmt(row['total'], simbolo)])
        prov_table = Table(prov_data, colWidths=[9 * cm, 3 * cm, 5 * cm])
        prov_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_DARK),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, COLOR_ROW_ALT]),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(prov_table)

    # ── INGRESOS POR LOCAL ────────────────────────────────────────
    if data['ingresos_por_local']:
        story.append(Paragraph('Ingresos por Local', style_section))
        loc_data = [['Local', 'Períodos', 'Total']]
        for row in data['ingresos_por_local']:
            loc_data.append([row['nombre'], str(row['cantidad']), fmt(row['total'], simbolo)])
        loc_table = Table(loc_data, colWidths=[9 * cm, 3 * cm, 5 * cm])
        loc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_SUCCESS),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, colors.HexColor('#f0fdf4')]),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(loc_table)

    # ── MEDIOS DE COBRO ───────────────────────────────────────────
    if data['medios_cobro']:
        story.append(Paragraph('Composición de Ingresos por Medio de Cobro', style_section))
        med_data = [['Medio de Cobro', 'Total']]
        for row in data['medios_cobro']:
            label = row['medio'].replace('_', ' ').title()
            med_data.append([label, fmt(row['total'], simbolo)])
        med_table = Table(med_data, colWidths=[9 * cm, 8 * cm])
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_SUCCESS),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, colors.HexColor('#f0fdf4')]),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(med_table)

    # ── DETALLE DE GASTOS ─────────────────────────────────────────
    if data['detalle_gastos']:
        story.append(Paragraph('Detalle de Gastos', style_section))
        det_data = [['Fecha', 'Local', 'Categoría', 'Proveedor', 'Descripción', 'Monto']]
        for row in data['detalle_gastos']:
            det_data.append([
                row['fecha'],
                row['local'][:15],
                row['categoria'][:15],
                (row['proveedor'] or '')[:15],
                (row['descripcion'] or '')[:20],
                fmt(row['monto'], simbolo),
            ])
        det_table = Table(det_data, colWidths=[2 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3 * cm, 2.5 * cm])
        det_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_DANGER),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (5, 0), (5, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, colors.HexColor('#fff5f5')]),
            ('GRID', (0, 0), (-1, -1), 0.4, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(det_table)

    # ── DETALLE DE INGRESOS ───────────────────────────────────────
    if data['detalle_ingresos']:
        story.append(Paragraph('Detalle de Ingresos', style_section))
        ing_data = [['Desde', 'Hasta', 'Local', 'Observaciones', 'Total']]
        for row in data['detalle_ingresos']:
            ing_data.append([
                row['fecha_desde'],
                row['fecha_hasta'],
                row['local'][:20],
                (row['observaciones'] or '')[:25],
                fmt(row['total'], simbolo),
            ])
        ing_table = Table(ing_data, colWidths=[2.5 * cm, 2.5 * cm, 3 * cm, 4 * cm, 3 * cm])
        ing_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_SUCCESS),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, colors.HexColor('#f0fdf4')]),
            ('GRID', (0, 0), (-1, -1), 0.4, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(ing_table)

    # ── PIE DE PÁGINA ─────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=COLOR_BORDER))
    story.append(Paragraph(
        f'{nombre_negocio} — Reporte generado el {datetime.now().strftime("%d/%m/%Y a las %H:%M")}',
        style_small
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
