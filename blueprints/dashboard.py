from flask import Blueprint, render_template, request
from database import get_db
from datetime import date, datetime, timedelta
import json

bp = Blueprint('dashboard', __name__)


def resolve_periodo(req):
    """Resuelve el período rápido a fechas. Devuelve (fecha_desde, fecha_hasta, periodo)."""
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
    default_desde = today.replace(day=1).strftime('%Y-%m-%d')
    default_hasta = today.strftime('%Y-%m-%d')
    return req.args.get('fecha_desde', default_desde), req.args.get('fecha_hasta', default_hasta), ''


@bp.route('/')
def index():
    fecha_desde, fecha_hasta, periodo = resolve_periodo(request)
    local_id = request.args.get('local_id', '')

    db = get_db()

    # Locales para filtro
    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()

    # Filtro de local
    local_filter = ''
    params_gastos = [fecha_desde, fecha_hasta]
    params_ingresos = [fecha_desde, fecha_hasta]

    if local_id:
        local_filter_gastos = ' AND g.local_id = ?'
        local_filter_ingresos = ' AND i.local_id = ?'
        params_gastos.append(local_id)
        params_ingresos.append(local_id)
    else:
        local_filter_gastos = ''
        local_filter_ingresos = ''

    # Totales (solo locales activos)
    total_gastos = db.execute(
        f'SELECT COALESCE(SUM(g.monto), 0) as total FROM gastos g JOIN locales l ON g.local_id = l.id WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{local_filter_gastos}',
        params_gastos
    ).fetchone()['total']

    total_ingresos = db.execute(
        f'SELECT COALESCE(SUM(i.total), 0) as total FROM ingresos i JOIN locales l ON i.local_id = l.id WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{local_filter_ingresos}',
        params_ingresos
    ).fetchone()['total']

    balance = total_ingresos - total_gastos

    # Gastos por categoría (para pie chart) — solo locales activos
    gastos_por_cat = db.execute(
        f'''SELECT c.nombre, c.color, COALESCE(SUM(g.monto), 0) as total
            FROM gastos g
            JOIN categorias c ON g.categoria_id = c.id
            JOIN locales l ON g.local_id = l.id
            WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{local_filter_gastos}
            GROUP BY c.id, c.nombre, c.color
            ORDER BY total DESC LIMIT 8''',
        params_gastos
    ).fetchall()

    # Ingresos por local (para bar chart) — solo locales activos
    ingresos_por_local = db.execute(
        f'''SELECT l.nombre, COALESCE(SUM(i.total), 0) as total
            FROM ingresos i
            JOIN locales l ON i.local_id = l.id
            WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{local_filter_ingresos}
            GROUP BY l.id, l.nombre
            ORDER BY total DESC''',
        params_ingresos
    ).fetchall()

    # Gastos por local — solo locales activos
    gastos_por_local = db.execute(
        f'''SELECT l.nombre, COALESCE(SUM(g.monto), 0) as total
            FROM gastos g
            JOIN locales l ON g.local_id = l.id
            WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1{local_filter_gastos}
            GROUP BY l.id, l.nombre
            ORDER BY total DESC''',
        params_gastos
    ).fetchall()

    # Tendencia mensual últimos 6 meses
    def _primer_dia_hace_n_meses(n):
        today = date.today()
        month = today.month - n
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        return date(year, month, 1)

    meses = []
    for i in range(5, -1, -1):
        mes_inicio = _primer_dia_hace_n_meses(i)
        if mes_inicio.month == 12:
            mes_fin = date(mes_inicio.year + 1, 1, 1) - timedelta(days=1)
        else:
            mes_fin = date(mes_inicio.year, mes_inicio.month + 1, 1) - timedelta(days=1)
        meses.append((mes_inicio, mes_fin, mes_inicio.strftime('%b %Y')))

    tendencia_labels = [m[2] for m in meses]
    tendencia_gastos = []
    tendencia_ingresos = []
    for mes_ini, mes_fin, _ in meses:
        g = db.execute(
            'SELECT COALESCE(SUM(g.monto), 0) as t FROM gastos g JOIN locales l ON g.local_id = l.id WHERE g.fecha BETWEEN ? AND ? AND g.anulado = 0 AND l.activo = 1',
            [mes_ini.strftime('%Y-%m-%d'), mes_fin.strftime('%Y-%m-%d')]
        ).fetchone()['t']
        i = db.execute(
            'SELECT COALESCE(SUM(i.total), 0) as t FROM ingresos i JOIN locales l ON i.local_id = l.id WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1',
            [mes_ini.strftime('%Y-%m-%d'), mes_fin.strftime('%Y-%m-%d')]
        ).fetchone()['t']
        tendencia_gastos.append(round(g, 2))
        tendencia_ingresos.append(round(i, 2))

    # Últimos movimientos (solo locales activos)
    ultimos = []
    gastos_recientes = db.execute(
        '''SELECT g.id, g.fecha, 'gasto' as tipo, l.nombre as local,
                  c.nombre as categoria, g.descripcion, g.monto
           FROM gastos g
           JOIN locales l ON g.local_id = l.id
           JOIN categorias c ON g.categoria_id = c.id
           WHERE g.anulado = 0 AND l.activo = 1
           ORDER BY g.created_at DESC LIMIT 5'''
    ).fetchall()
    ingresos_recientes = db.execute(
        '''SELECT i.id, i.fecha_desde as fecha, 'ingreso' as tipo, l.nombre as local,
                  'Ingreso' as categoria, i.observaciones as descripcion, i.total as monto
           FROM ingresos i
           JOIN locales l ON i.local_id = l.id
           WHERE i.anulado = 0 AND l.activo = 1
           ORDER BY i.created_at DESC LIMIT 5'''
    ).fetchall()

    for r in gastos_recientes:
        ultimos.append(dict(r))
    for r in ingresos_recientes:
        ultimos.append(dict(r))
    ultimos.sort(key=lambda x: x['fecha'], reverse=True)
    ultimos = ultimos[:8]

    # Medios de cobro (ingresos, solo locales activos)
    medios_cobro = db.execute(
        f'''SELECT dim.medio, COALESCE(SUM(dim.monto), 0) as total
            FROM detalle_ingresos_medios dim
            JOIN ingresos i ON dim.ingreso_id = i.id
            JOIN locales l ON i.local_id = l.id
            WHERE i.fecha_hasta >= ? AND i.fecha_desde <= ? AND i.anulado = 0 AND l.activo = 1{local_filter_ingresos}
            GROUP BY dim.medio''',
        params_ingresos
    ).fetchall()

    db.close()

    # Chart data as JSON
    chart_categorias = {
        'labels': [r['nombre'] for r in gastos_por_cat],
        'data': [round(r['total'], 2) for r in gastos_por_cat],
        'colors': [r['color'] or '#6c757d' for r in gastos_por_cat],
    }
    chart_locales = {
        'labels': [r['nombre'] for r in ingresos_por_local],
        'ingresos': [round(r['total'], 2) for r in ingresos_por_local],
        'gastos': [round(next((x['total'] for x in gastos_por_local if x['nombre'] == r['nombre']), 0), 2)
                   for r in ingresos_por_local],
    }
    chart_tendencia = {
        'labels': tendencia_labels,
        'gastos': tendencia_gastos,
        'ingresos': tendencia_ingresos,
    }
    chart_medios = {
        'labels': [r['medio'].replace('_', ' ').title() for r in medios_cobro],
        'data': [round(r['total'], 2) for r in medios_cobro],
    }

    return render_template('dashboard/index.html',
        total_gastos=total_gastos,
        total_ingresos=total_ingresos,
        balance=balance,
        locales=locales,
        gastos_por_local=gastos_por_local,
        ingresos_por_local=ingresos_por_local,
        ultimos=ultimos,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_id=local_id,
        periodo=periodo,
        chart_categorias=json.dumps(chart_categorias),
        chart_locales=json.dumps(chart_locales),
        chart_tendencia=json.dumps(chart_tendencia),
        chart_medios=json.dumps(chart_medios),
    )
