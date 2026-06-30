from flask import Blueprint, render_template, request, Response
from database import get_db
from datetime import date, timedelta

bp = Blueprint('movimientos', __name__, url_prefix='/movimientos')


def resolve_periodo(req):
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
    db = get_db()

    fecha_desde, fecha_hasta, periodo = resolve_periodo(request)
    local_id = request.args.get('local_id', '')
    categoria_id = request.args.get('categoria_id', '')
    proveedor_id = request.args.get('proveedor_id', '')
    tipo = request.args.get('tipo', '')  # 'ingreso' | 'gasto' | ''
    mostrar_anulados = request.args.get('mostrar_anulados', '0')

    # Gastos
    q_gastos = '''
        SELECT g.id, g.fecha, 'gasto' as tipo, g.monto, g.descripcion, g.anulado,
               COALESCE(g.moneda, 'ARS') as moneda,
               l.nombre as local_nombre,
               c.nombre as categoria_nombre,
               sc.nombre as subcategoria_nombre,
               p.nombre as proveedor_nombre,
               g.medio_pago
        FROM gastos g
        JOIN locales l ON g.local_id = l.id
        JOIN categorias c ON g.categoria_id = c.id
        LEFT JOIN subcategorias sc ON g.subcategoria_id = sc.id
        LEFT JOIN proveedores p ON g.proveedor_id = p.id
        WHERE 1=1
    '''
    params_g = []

    if mostrar_anulados != '1':
        q_gastos += ' AND g.anulado = 0'
    if fecha_desde:
        q_gastos += ' AND g.fecha >= ?'
        params_g.append(fecha_desde)
    if fecha_hasta:
        q_gastos += ' AND g.fecha <= ?'
        params_g.append(fecha_hasta)
    if local_id:
        q_gastos += ' AND g.local_id = ?'
        params_g.append(local_id)
    if categoria_id:
        q_gastos += ' AND g.categoria_id = ?'
        params_g.append(categoria_id)
    if proveedor_id:
        q_gastos += ' AND g.proveedor_id = ?'
        params_g.append(proveedor_id)

    # Ingresos
    q_ingresos = '''
        SELECT i.id, i.fecha_desde as fecha, 'ingreso' as tipo, i.total as monto,
               i.observaciones as descripcion, i.anulado,
               COALESCE(i.moneda, 'ARS') as moneda,
               l.nombre as local_nombre,
               COALESCE(c.nombre, 'Ingreso') as categoria_nombre,
               NULL as subcategoria_nombre,
               NULL as proveedor_nombre,
               NULL as medio_pago
        FROM ingresos i
        JOIN locales l ON i.local_id = l.id
        LEFT JOIN categorias c ON i.categoria_id = c.id
        WHERE 1=1
    '''
    params_i = []

    if mostrar_anulados != '1':
        q_ingresos += ' AND i.anulado = 0'
    if fecha_desde:
        q_ingresos += ' AND i.fecha_hasta >= ?'
        params_i.append(fecha_desde)
    if fecha_hasta:
        q_ingresos += ' AND i.fecha_desde <= ?'
        params_i.append(fecha_hasta)
    if local_id:
        q_ingresos += ' AND i.local_id = ?'
        params_i.append(local_id)
    if categoria_id:
        q_ingresos += ' AND i.categoria_id = ?'
        params_i.append(categoria_id)

    movimientos = []
    if tipo != 'ingreso':
        gastos = db.execute(q_gastos, params_g).fetchall()
        movimientos.extend([dict(g) for g in gastos])
    if tipo != 'gasto':
        ingresos = db.execute(q_ingresos, params_i).fetchall()
        movimientos.extend([dict(i) for i in ingresos])

    movimientos.sort(key=lambda x: x['fecha'], reverse=True)

    total_ingresos = sum(m['monto'] for m in movimientos if m['tipo'] == 'ingreso' and not m['anulado'] and m.get('moneda', 'ARS') == 'ARS')
    total_gastos   = sum(m['monto'] for m in movimientos if m['tipo'] == 'gasto'   and not m['anulado'] and m.get('moneda', 'ARS') == 'ARS')
    balance        = total_ingresos - total_gastos
    total_ingresos_usd = sum(m['monto'] for m in movimientos if m['tipo'] == 'ingreso' and not m['anulado'] and m.get('moneda', 'ARS') == 'USD')
    total_gastos_usd   = sum(m['monto'] for m in movimientos if m['tipo'] == 'gasto'   and not m['anulado'] and m.get('moneda', 'ARS') == 'USD')
    balance_usd    = total_ingresos_usd - total_gastos_usd

    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    categorias = db.execute('SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre').fetchall()
    proveedores = db.execute('SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()

    return render_template('movimientos/index.html',
        movimientos=movimientos,
        locales=locales,
        categorias=categorias,
        proveedores=proveedores,
        total_ingresos=total_ingresos,
        total_gastos=total_gastos,
        balance=balance,
        total_ingresos_usd=total_ingresos_usd,
        total_gastos_usd=total_gastos_usd,
        balance_usd=balance_usd,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_id=local_id,
        categoria_id=categoria_id,
        proveedor_id=proveedor_id,
        tipo=tipo,
        mostrar_anulados=mostrar_anulados,
        periodo=periodo,
    )


@bp.route('/exportar-csv')
def exportar_csv():
    import csv, io

    db = get_db()
    fecha_desde, fecha_hasta, _ = resolve_periodo(request)
    local_id         = request.args.get('local_id', '')
    categoria_id     = request.args.get('categoria_id', '')
    tipo             = request.args.get('tipo', '')
    mostrar_anulados = request.args.get('mostrar_anulados', '0')

    def _fmt(val):
        if val is None: return ''
        if hasattr(val, 'strftime'): return val.strftime('%d/%m/%Y')
        s = str(val)[:10]; p = s.split('-')
        return f'{p[2]}/{p[1]}/{p[0]}' if len(p) == 3 else s

    rows = []

    if tipo != 'ingreso':
        q = '''SELECT g.fecha, 'Gasto' as tipo, l.nombre as local,
                      c.nombre as categoria, COALESCE(g.descripcion,'') as descripcion,
                      g.monto, COALESCE(g.medio_pago,'') as medio_pago
               FROM gastos g
               JOIN locales l ON g.local_id = l.id
               JOIN categorias c ON g.categoria_id = c.id
               WHERE 1=1'''
        p = []
        if mostrar_anulados != '1': q += ' AND g.anulado = 0'
        if fecha_desde: q += ' AND g.fecha >= ?'; p.append(fecha_desde)
        if fecha_hasta: q += ' AND g.fecha <= ?'; p.append(fecha_hasta)
        if local_id:    q += ' AND g.local_id = ?'; p.append(local_id)
        if categoria_id: q += ' AND g.categoria_id = ?'; p.append(categoria_id)
        rows.extend([dict(r) for r in db.execute(q, p).fetchall()])

    if tipo != 'gasto':
        q = '''SELECT i.fecha_desde as fecha, 'Ingreso' as tipo, l.nombre as local,
                      COALESCE(cat.nombre,'Ingreso') as categoria,
                      COALESCE(i.observaciones,'') as descripcion,
                      i.total as monto, '' as medio_pago
               FROM ingresos i
               JOIN locales l ON i.local_id = l.id
               LEFT JOIN categorias cat ON i.categoria_id = cat.id
               WHERE 1=1'''
        p = []
        if mostrar_anulados != '1': q += ' AND i.anulado = 0'
        if fecha_desde: q += ' AND i.fecha_hasta >= ?'; p.append(fecha_desde)
        if fecha_hasta: q += ' AND i.fecha_desde <= ?'; p.append(fecha_hasta)
        if local_id:    q += ' AND i.local_id = ?'; p.append(local_id)
        rows.extend([dict(r) for r in db.execute(q, p).fetchall()])

    db.close()
    rows.sort(key=lambda x: str(x['fecha']), reverse=True)

    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(['Fecha', 'Tipo', 'Local', 'Categoría', 'Descripción', 'Monto', 'Medio de pago'])
    for r in rows:
        w.writerow([_fmt(r['fecha']), r['tipo'], r['local'], r['categoria'],
                    r['descripcion'], str(r['monto']).replace('.', ','), r['medio_pago']])

    fname = f'movimientos_{fecha_desde or "todo"}_{fecha_hasta or "hoy"}.csv'
    return Response('﻿' + out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{fname}"'})
