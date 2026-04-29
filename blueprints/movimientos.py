from flask import Blueprint, render_template, request
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
               l.nombre as local_nombre,
               'Ingreso' as categoria_nombre,
               NULL as subcategoria_nombre,
               NULL as proveedor_nombre,
               NULL as medio_pago
        FROM ingresos i
        JOIN locales l ON i.local_id = l.id
        WHERE 1=1
    '''
    params_i = []

    if mostrar_anulados != '1':
        q_ingresos += ' AND i.anulado = 0'
    if fecha_desde:
        q_ingresos += ' AND i.fecha_desde >= ?'
        params_i.append(fecha_desde)
    if fecha_hasta:
        q_ingresos += ' AND i.fecha_hasta <= ?'
        params_i.append(fecha_hasta)
    if local_id:
        q_ingresos += ' AND i.local_id = ?'
        params_i.append(local_id)

    movimientos = []
    if tipo != 'ingreso':
        gastos = db.execute(q_gastos, params_g).fetchall()
        movimientos.extend([dict(g) for g in gastos])
    if tipo != 'gasto':
        ingresos = db.execute(q_ingresos, params_i).fetchall()
        movimientos.extend([dict(i) for i in ingresos])

    movimientos.sort(key=lambda x: x['fecha'], reverse=True)

    total_ingresos = sum(m['monto'] for m in movimientos if m['tipo'] == 'ingreso' and not m['anulado'])
    total_gastos = sum(m['monto'] for m in movimientos if m['tipo'] == 'gasto' and not m['anulado'])
    balance = total_ingresos - total_gastos

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
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_id=local_id,
        categoria_id=categoria_id,
        proveedor_id=proveedor_id,
        tipo=tipo,
        mostrar_anulados=mostrar_anulados,
        periodo=periodo,
    )
