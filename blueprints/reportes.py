from flask import Blueprint, render_template, request, make_response
from database import get_db, MEDIOS_COBRO, MEDIOS_PAGO
from datetime import date, timedelta
import json

bp = Blueprint('reportes', __name__, url_prefix='/reportes')


def resolve_periodo(req):
    """Resuelve el período a fechas concretas. Devuelve (fecha_desde, fecha_hasta, periodo)."""
    today = date.today()
    periodo = req.args.get('periodo', '')
    if periodo == 'hoy':
        return today.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'), periodo
    elif periodo == '7d':
        return (today - timedelta(days=7)).strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'), periodo
    elif periodo == '30d':
        return (today - timedelta(days=30)).strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'), periodo
    elif periodo == '90d':
        return (today - timedelta(days=90)).strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'), periodo
    elif periodo == 'todo':
        return '2000-01-01', today.strftime('%Y-%m-%d'), periodo
    # Sin periodo rápido: usar los inputs manuales o el mes actual por defecto
    default_desde = today.replace(day=1).strftime('%Y-%m-%d')
    default_hasta = today.strftime('%Y-%m-%d')
    return req.args.get('fecha_desde', default_desde), req.args.get('fecha_hasta', default_hasta), ''


def build_filters(request):
    fecha_desde, fecha_hasta, periodo = resolve_periodo(request)
    local_id = request.args.get('local_id', '')
    categoria_id = request.args.get('categoria_id', '')
    proveedor_id = request.args.get('proveedor_id', '')
    tipo = request.args.get('tipo', '')
    clasificacion = request.args.get('clasificacion', '')
    fija = request.args.get('fija', '')
    medio_pago = request.args.get('medio_pago', '')
    return fecha_desde, fecha_hasta, local_id, categoria_id, proveedor_id, tipo, clasificacion, fija, medio_pago


def get_report_data(fecha_desde, fecha_hasta, local_id, categoria_id, proveedor_id, clasificacion='', fija='', medio_pago=''):
    db = get_db()

    # Params
    gp = [fecha_desde, fecha_hasta]
    gf = ''
    ip = [fecha_desde, fecha_hasta]
    if_str = ''

    if local_id:
        gf += ' AND g.local_id = ?'; gp.append(local_id)
        if_str += ' AND i.local_id = ?'; ip.append(local_id)
    if categoria_id:
        gf += ' AND g.categoria_id = ?'; gp.append(categoria_id)
        if_str += ' AND i.categoria_id = ?'; ip.append(categoria_id)
    if proveedor_id:
        gf += ' AND g.proveedor_id = ?'; gp.append(proveedor_id)
    if clasificacion:
        gf += " AND COALESCE(c.clasificacion, 'gasto') = ?"; gp.append(clasificacion)
    # Filtro fija/no-fija (solo aplica a egresos; se basa en la subcategoría actual).
    # "No fija" incluye egresos sin subcategoría. Los ingresos no se ven afectados.
    if fija == '1':
        gf += ' AND EXISTS (SELECT 1 FROM subcategorias s WHERE s.id = g.subcategoria_id AND COALESCE(s.es_fija, 0) = 1)'
    elif fija == '0':
        gf += ' AND NOT EXISTS (SELECT 1 FROM subcategorias s WHERE s.id = g.subcategoria_id AND COALESCE(s.es_fija, 0) = 1)'
    # Filtro por medio de pago (solo aplica a egresos; los ingresos no lo tienen)
    if medio_pago:
        gf += ' AND g.medio_pago = ?'; gp.append(medio_pago)

    total_gastos = db.execute(
        f'SELECT COALESCE(SUM(g.monto), 0) as t FROM gastos g JOIN locales l ON g.local_id = l.id WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{gf}',
        gp
    ).fetchone()['t']

    total_ingresos = db.execute(
        f'SELECT COALESCE(SUM(i.total), 0) as t FROM ingresos i JOIN locales l ON i.local_id = l.id WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{if_str}',
        ip
    ).fetchone()['t']

    gastos_por_cat = db.execute(
        f'''SELECT c.nombre, c.color, COALESCE(SUM(g.monto), 0) as total, COUNT(*) as cantidad
            FROM gastos g JOIN categorias c ON g.categoria_id = c.id
            JOIN locales l ON g.local_id = l.id
            WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{gf}
            GROUP BY c.id, c.nombre, c.color ORDER BY total DESC''', gp
    ).fetchall()

    gastos_por_proveedor = db.execute(
        f'''SELECT COALESCE(p.nombre, 'Sin proveedor') as nombre,
                   COALESCE(SUM(g.monto), 0) as total, COUNT(*) as cantidad
            FROM gastos g LEFT JOIN proveedores p ON g.proveedor_id = p.id
            JOIN locales l ON g.local_id = l.id
            WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{gf}
            GROUP BY g.proveedor_id, p.nombre ORDER BY total DESC''', gp
    ).fetchall()

    ingresos_por_local = db.execute(
        f'''SELECT l.nombre, COALESCE(SUM(i.total), 0) as total, COUNT(*) as cantidad
            FROM ingresos i JOIN locales l ON i.local_id = l.id
            WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{if_str}
            GROUP BY l.id, l.nombre ORDER BY total DESC''', ip
    ).fetchall()

    gastos_por_local = db.execute(
        f'''SELECT l.nombre, COALESCE(SUM(g.monto), 0) as total, COUNT(*) as cantidad
            FROM gastos g JOIN locales l ON g.local_id = l.id
            WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{gf}
            GROUP BY l.id, l.nombre ORDER BY total DESC''', gp
    ).fetchall()

    medios_cobro_data = db.execute(
        f'''SELECT dim.medio, COALESCE(SUM(dim.monto), 0) as total
            FROM detalle_ingresos_medios dim JOIN ingresos i ON dim.ingreso_id = i.id
            JOIN locales l ON i.local_id = l.id
            WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{if_str}
            GROUP BY dim.medio''', ip
    ).fetchall()

    detalle_gastos = db.execute(
        f'''SELECT g.fecha, l.nombre as local, c.nombre as categoria,
                   COALESCE(sc.nombre, '') as subcategoria,
                   COALESCE(p.nombre, '') as proveedor,
                   g.descripcion, g.monto, g.medio_pago
            FROM gastos g
            JOIN locales l ON g.local_id = l.id
            JOIN categorias c ON g.categoria_id = c.id
            LEFT JOIN subcategorias sc ON g.subcategoria_id = sc.id
            LEFT JOIN proveedores p ON g.proveedor_id = p.id
            WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{gf}
            ORDER BY g.fecha DESC''', gp
    ).fetchall()

    detalle_ingresos = db.execute(
        f'''SELECT i.fecha_desde, i.fecha_hasta, l.nombre as local,
                   COALESCE(cat.nombre, '') as categoria, i.total, i.observaciones
            FROM ingresos i
            JOIN locales l ON i.local_id = l.id
            LEFT JOIN categorias cat ON i.categoria_id = cat.id
            WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{if_str}
            ORDER BY i.fecha_desde DESC''', ip
    ).fetchall()

    count_gastos = db.execute(
        f'SELECT COUNT(*) as c FROM gastos g JOIN locales l ON g.local_id = l.id WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{gf}', gp
    ).fetchone()['c']
    count_ingresos = db.execute(
        f'SELECT COUNT(*) as c FROM ingresos i JOIN locales l ON i.local_id = l.id WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{if_str}', ip
    ).fetchone()['c']

    gastos_por_clasificacion = db.execute(
        f'''SELECT COALESCE(c.clasificacion, 'gasto') as clasificacion,
               COALESCE(SUM(g.monto), 0) as total, COUNT(*) as cantidad
            FROM gastos g JOIN categorias c ON g.categoria_id = c.id
            JOIN locales l ON g.local_id = l.id
            WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{gf}
            GROUP BY c.clasificacion ORDER BY total DESC''', gp
    ).fetchall()

    db.close()
    return {
        'total_gastos': total_gastos,
        'total_ingresos': total_ingresos,
        'balance': total_ingresos - total_gastos,
        'count_gastos': count_gastos,
        'count_ingresos': count_ingresos,
        'gastos_por_cat': [dict(r) for r in gastos_por_cat],
        'gastos_por_clasificacion': [dict(r) for r in gastos_por_clasificacion],
        'gastos_por_proveedor': [dict(r) for r in gastos_por_proveedor],
        'ingresos_por_local': [dict(r) for r in ingresos_por_local],
        'gastos_por_local': [dict(r) for r in gastos_por_local],
        'medios_cobro': [dict(r) for r in medios_cobro_data],
        'detalle_gastos': [dict(r) for r in detalle_gastos],
        'detalle_ingresos': [dict(r) for r in detalle_ingresos],
    }


@bp.route('/')
def index():
    fecha_desde, fecha_hasta, local_id, categoria_id, proveedor_id, tipo, clasificacion, fija, medio_pago = build_filters(request)
    _, _, periodo = resolve_periodo(request)

    db = get_db()
    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    categorias = db.execute('SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre').fetchall()
    proveedores = db.execute('SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()

    data = get_report_data(fecha_desde, fecha_hasta, local_id, categoria_id, proveedor_id, clasificacion, fija, medio_pago)

    chart_cat = {
        'labels': [r['nombre'] for r in data['gastos_por_cat']],
        'data': [round(r['total'], 2) for r in data['gastos_por_cat']],
        'colors': [r['color'] or '#6c757d' for r in data['gastos_por_cat']],
    }
    chart_local = {
        'labels': [r['nombre'] for r in data['ingresos_por_local']],
        'ingresos': [round(r['total'], 2) for r in data['ingresos_por_local']],
    }
    chart_medios = {
        'labels': [r['medio'].replace('_', ' ').title() for r in data['medios_cobro']],
        'data': [round(r['total'], 2) for r in data['medios_cobro']],
    }

    return render_template('reportes/index.html',
        data=data,
        locales=locales,
        categorias=categorias,
        proveedores=proveedores,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_id=local_id,
        categoria_id=categoria_id,
        proveedor_id=proveedor_id,
        clasificacion=clasificacion,
        fija=fija,
        medio_pago=medio_pago,
        medios_pago=MEDIOS_PAGO,
        periodo=periodo,
        medios_cobro=MEDIOS_COBRO,
        chart_cat=json.dumps(chart_cat),
        chart_local=json.dumps(chart_local),
        chart_medios=json.dumps(chart_medios),
    )


@bp.route('/pdf')
def generar_pdf():
    fecha_desde, fecha_hasta, local_id, categoria_id, proveedor_id, tipo, clasificacion, fija, medio_pago = build_filters(request)

    db = get_db()
    config = {r['clave']: r['valor'] for r in db.execute('SELECT clave, valor FROM configuracion').fetchall()}
    local_nombre = ''
    if local_id:
        loc = db.execute('SELECT nombre FROM locales WHERE id = ?', (local_id,)).fetchone()
        local_nombre = loc['nombre'] if loc else ''
    cat_nombre = ''
    if categoria_id:
        cat = db.execute('SELECT nombre FROM categorias WHERE id = ?', (categoria_id,)).fetchone()
        cat_nombre = cat['nombre'] if cat else ''
    db.close()

    data = get_report_data(fecha_desde, fecha_hasta, local_id, categoria_id, proveedor_id, clasificacion, fija, medio_pago)

    fija_label = {'1': 'Solo fijas', '0': 'Solo no fijas'}.get(fija, '')

    from pdf_generator import generar_pdf_reporte
    pdf_bytes = generar_pdf_reporte(
        config=config,
        data=data,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_nombre=local_nombre,
        cat_nombre=cat_nombre,
        fija_label=fija_label,
        medio_pago=medio_pago,
    )

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=reporte_{fecha_desde}_{fecha_hasta}.pdf'
    return response
