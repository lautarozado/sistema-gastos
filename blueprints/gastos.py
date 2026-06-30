import os
import uuid
from datetime import date, timedelta
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, send_from_directory, current_app)
from werkzeug.utils import secure_filename
from database import get_db, MEDIOS_PAGO

bp = Blueprint('gastos', __name__, url_prefix='/gastos')

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
MONEDAS = [('ARS', 'ARS – Peso'), ('USD', 'USD – Dólar')]
FRECUENCIAS = [('mensual', 'Mensual'), ('semanal', 'Semanal'), ('anual', 'Anual')]


def _upload_folder():
    folder = os.path.join(current_app.root_path, 'uploads', 'comprobantes')
    os.makedirs(folder, exist_ok=True)
    return folder


def _save_comprobante(file):
    """Guarda el archivo y devuelve (filename, error_msg)."""
    if not file or not file.filename:
        return None, None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return None, 'Extensión no permitida. Usá JPG, PNG o PDF.'
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(_upload_folder(), filename))
    return filename, None


def get_form_data():
    db = get_db()
    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    categorias = db.execute(
        "SELECT * FROM categorias WHERE activo = 1 AND tipo IN ('gasto', 'ambos') ORDER BY nombre"
    ).fetchall()
    proveedores = db.execute('SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()
    return locales, categorias, proveedores


def _categoria_requiere_proveedor(db, categoria_id):
    """True si la categoría tiene el flag requiere_proveedor activo."""
    if not categoria_id:
        return False
    row = db.execute('SELECT requiere_proveedor FROM categorias WHERE id = ?', (categoria_id,)).fetchone()
    if not row:
        return False
    return bool(row['requiere_proveedor'])


def _parse_monto(val):
    val = str(val).strip().replace('$', '').replace(' ', '')
    if not val:
        return 0.0
    if ',' in val:
        val = val.replace('.', '').replace(',', '.')
    else:
        partes = val.split('.')
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            val = ''.join(partes)
    return float(val)


@bp.route('/')
def list_gastos():
    db = get_db()

    hoy = date.today()
    # Si los parámetros no están en la URL, usar el mes actual por defecto.
    # Si están presentes pero vacíos (?fecha_desde=&fecha_hasta=), mostrar todos.
    if 'fecha_desde' not in request.args and 'fecha_hasta' not in request.args:
        fecha_desde = hoy.replace(day=1).strftime('%Y-%m-%d')
        fecha_hasta = hoy.strftime('%Y-%m-%d')
    else:
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
    local_id         = request.args.get('local_id', '')
    categoria_id     = request.args.get('categoria_id', '')
    proveedor_id     = request.args.get('proveedor_id', '')
    mostrar_anulados = request.args.get('mostrar_anulados', '0')

    query = '''
        SELECT g.id, g.fecha, g.monto, g.descripcion, g.medio_pago, g.anulado,
               COALESCE(g.moneda, 'ARS') as moneda,
               g.comprobante_path,
               g.es_recurrente,
               l.nombre as local_nombre,
               c.nombre as categoria_nombre,
               sc.nombre as subcategoria_nombre,
               p.nombre as proveedor_nombre,
               (SELECT COUNT(*) FROM cheques ch WHERE ch.gasto_id = g.id) as cheques_count,
               (SELECT COUNT(*) FROM cheques ch WHERE ch.gasto_id = g.id
                  AND ch.estado = 'pendiente') as cheques_pendientes,
               (SELECT MIN(ch.fecha_pago) FROM cheques ch WHERE ch.gasto_id = g.id
                  AND ch.estado = 'pendiente') as cheque_proxima_fecha
        FROM gastos g
        JOIN locales l ON g.local_id = l.id
        JOIN categorias c ON g.categoria_id = c.id
        LEFT JOIN subcategorias sc ON g.subcategoria_id = sc.id
        LEFT JOIN proveedores p ON g.proveedor_id = p.id
        WHERE 1=1
    '''
    params = []

    if mostrar_anulados != '1':
        query += ' AND g.anulado = 0'
    if fecha_desde:
        query += ' AND g.fecha >= ?'; params.append(fecha_desde)
    if fecha_hasta:
        query += ' AND g.fecha <= ?'; params.append(fecha_hasta)
    if local_id:
        query += ' AND g.local_id = ?'; params.append(local_id)
    if categoria_id:
        query += ' AND g.categoria_id = ?'; params.append(categoria_id)
    if proveedor_id:
        query += ' AND g.proveedor_id = ?'; params.append(proveedor_id)

    query += ' ORDER BY g.fecha DESC, g.created_at DESC'

    gastos = db.execute(query, params).fetchall()

    total_ars = sum(g['monto'] for g in gastos if not g['anulado'] and g['moneda'] == 'ARS')
    total_usd = sum(g['monto'] for g in gastos if not g['anulado'] and g['moneda'] == 'USD')
    total_filtrado = total_ars  # compatibilidad con tfoot

    # Alerta de recurrentes vencidos o próximos en 7 días
    try:
        rec = db.execute(
            """SELECT COUNT(*) as c FROM gastos
               WHERE es_recurrente = 1 AND anulado = 0
               AND proxima_fecha IS NOT NULL
               AND proxima_fecha <= CURRENT_DATE + INTERVAL '7 days'"""
        ).fetchone()
        recurrentes_pendientes = rec['c'] if rec else 0
    except Exception:
        recurrentes_pendientes = 0

    locales     = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    categorias  = db.execute(
        "SELECT * FROM categorias WHERE activo = 1 AND tipo IN ('gasto', 'ambos') ORDER BY nombre"
    ).fetchall()
    proveedores = db.execute('SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()

    return render_template('gastos/list.html',
        gastos=gastos,
        locales=locales,
        categorias=categorias,
        proveedores=proveedores,
        total_filtrado=total_filtrado,
        total_ars=total_ars,
        total_usd=total_usd,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_id=local_id,
        categoria_id=categoria_id,
        proveedor_id=proveedor_id,
        mostrar_anulados=mostrar_anulados,
        recurrentes_pendientes=recurrentes_pendientes,
    )


@bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo_gasto():
    locales, categorias, proveedores = get_form_data()

    if request.method == 'POST':
        fecha           = request.form.get('fecha', '').strip()
        local_id        = request.form.get('local_id', '').strip()
        categoria_id    = request.form.get('categoria_id', '').strip()
        subcategoria_id = request.form.get('subcategoria_id', '').strip() or None
        proveedor_id    = request.form.get('proveedor_id', '').strip() or None
        descripcion     = request.form.get('descripcion', '').strip()
        monto_str       = request.form.get('monto', '').strip()
        medio_pago      = request.form.get('medio_pago', '').strip() or None
        observaciones   = request.form.get('observaciones', '').strip()
        moneda          = request.form.get('moneda', 'ARS').strip()
        es_recurrente   = 1 if request.form.get('es_recurrente') == '1' else 0
        frecuencia      = request.form.get('frecuencia', '').strip() or None
        proxima_fecha   = request.form.get('proxima_fecha', '').strip() or None

        errors = []
        if not fecha:
            errors.append('La fecha es obligatoria.')
        if not local_id:
            errors.append('El local es obligatorio.')
        if not categoria_id:
            errors.append('La categoría es obligatoria.')
        if categoria_id and not proveedor_id:
            _db_chk = get_db()
            if _categoria_requiere_proveedor(_db_chk, categoria_id):
                errors.append('Esta categoría requiere que selecciones un proveedor.')
            _db_chk.close()
        if moneda not in ('ARS', 'USD'):
            moneda = 'ARS'
        try:
            monto = _parse_monto(monto_str)
            if monto <= 0:
                errors.append('El monto debe ser mayor a cero.')
        except (ValueError, AttributeError):
            errors.append('El monto ingresado no es válido.')
            monto = 0
        if es_recurrente and not proxima_fecha:
            errors.append('Indicá la próxima fecha para el gasto recurrente.')

        # Comprobante
        comprobante_path = None
        file = request.files.get('comprobante')
        if file and file.filename:
            comprobante_path, err = _save_comprobante(file)
            if err:
                errors.append(err)

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('gastos/form.html',
                locales=locales, categorias=categorias, proveedores=proveedores,
                medios_pago=MEDIOS_PAGO, monedas=MONEDAS, frecuencias=FRECUENCIAS,
                gasto=request.form, modo='nuevo')

        db = get_db()
        db.execute(
            '''INSERT INTO gastos
               (fecha, local_id, categoria_id, subcategoria_id, proveedor_id,
                descripcion, monto, medio_pago, observaciones, moneda,
                comprobante_path, es_recurrente, frecuencia, proxima_fecha)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (fecha, local_id, categoria_id, subcategoria_id, proveedor_id,
             descripcion, monto, medio_pago, observaciones, moneda,
             comprobante_path, es_recurrente, frecuencia, proxima_fecha)
        )
        db.commit()
        db.close()
        flash('Gasto registrado correctamente.', 'success')
        return redirect(url_for('gastos.list_gastos'))

    hoy = date.today().strftime('%Y-%m-%d')
    return render_template('gastos/form.html',
        locales=locales, categorias=categorias, proveedores=proveedores,
        medios_pago=MEDIOS_PAGO, monedas=MONEDAS, frecuencias=FRECUENCIAS,
        gasto={'fecha': hoy}, modo='nuevo')


@bp.route('/<int:gasto_id>/editar', methods=['GET', 'POST'])
def editar_gasto(gasto_id):
    db = get_db()
    gasto = db.execute('SELECT * FROM gastos WHERE id = ?', (gasto_id,)).fetchone()
    if not gasto:
        flash('Gasto no encontrado.', 'danger')
        db.close()
        return redirect(url_for('gastos.list_gastos'))

    locales, categorias, proveedores = get_form_data()

    if request.method == 'POST':
        fecha           = request.form.get('fecha', '').strip()
        local_id        = request.form.get('local_id', '').strip()
        categoria_id    = request.form.get('categoria_id', '').strip()
        subcategoria_id = request.form.get('subcategoria_id', '').strip() or None
        proveedor_id    = request.form.get('proveedor_id', '').strip() or None
        descripcion     = request.form.get('descripcion', '').strip()
        monto_str       = request.form.get('monto', '').strip()
        medio_pago      = request.form.get('medio_pago', '').strip() or None
        observaciones   = request.form.get('observaciones', '').strip()
        moneda          = request.form.get('moneda', 'ARS').strip()
        es_recurrente   = 1 if request.form.get('es_recurrente') == '1' else 0
        frecuencia      = request.form.get('frecuencia', '').strip() or None
        proxima_fecha   = request.form.get('proxima_fecha', '').strip() or None

        errors = []
        if not fecha:
            errors.append('La fecha es obligatoria.')
        if not local_id:
            errors.append('El local es obligatorio.')
        if not categoria_id:
            errors.append('La categoría es obligatoria.')
        if categoria_id and not proveedor_id and _categoria_requiere_proveedor(db, categoria_id):
            errors.append('Esta categoría requiere que selecciones un proveedor.')
        if moneda not in ('ARS', 'USD'):
            moneda = 'ARS'
        try:
            monto = _parse_monto(monto_str)
            if monto <= 0:
                errors.append('El monto debe ser mayor a cero.')
        except (ValueError, AttributeError):
            errors.append('El monto ingresado no es válido.')
            monto = 0
        if es_recurrente and not proxima_fecha:
            errors.append('Indicá la próxima fecha para el gasto recurrente.')

        # Comprobante: mantener existente si no se sube uno nuevo
        comprobante_path = gasto['comprobante_path']
        file = request.files.get('comprobante')
        if file and file.filename:
            new_path, err = _save_comprobante(file)
            if err:
                errors.append(err)
            else:
                comprobante_path = new_path

        if errors:
            for e in errors:
                flash(e, 'danger')
            db.close()
            return render_template('gastos/form.html',
                locales=locales, categorias=categorias, proveedores=proveedores,
                medios_pago=MEDIOS_PAGO, monedas=MONEDAS, frecuencias=FRECUENCIAS,
                gasto=request.form, modo='editar', gasto_id=gasto_id,
                comprobante_path_actual=gasto['comprobante_path'])

        db.execute(
            '''UPDATE gastos SET
               fecha=?, local_id=?, categoria_id=?, subcategoria_id=?,
               proveedor_id=?, descripcion=?, monto=?, medio_pago=?, observaciones=?,
               moneda=?, comprobante_path=?, es_recurrente=?, frecuencia=?, proxima_fecha=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (fecha, local_id, categoria_id, subcategoria_id, proveedor_id,
             descripcion, monto, medio_pago, observaciones, moneda,
             comprobante_path, es_recurrente, frecuencia, proxima_fecha, gasto_id)
        )
        db.commit()
        db.close()
        flash('Gasto actualizado correctamente.', 'success')
        return redirect(url_for('gastos.list_gastos'))

    subcategorias = db.execute(
        'SELECT * FROM subcategorias WHERE categoria_id = ? AND activo = 1',
        (gasto['categoria_id'],)
    ).fetchall()
    db.close()

    return render_template('gastos/form.html',
        locales=locales, categorias=categorias, proveedores=proveedores,
        medios_pago=MEDIOS_PAGO, monedas=MONEDAS, frecuencias=FRECUENCIAS,
        gasto=gasto, modo='editar', gasto_id=gasto_id,
        subcategorias=subcategorias,
        comprobante_path_actual=gasto['comprobante_path'])


@bp.route('/recurrentes')
def recurrentes():
    db = get_db()
    hoy = date.today()
    gastos_rec = db.execute(
        '''SELECT g.id, g.descripcion, g.monto, g.frecuencia, g.proxima_fecha,
                  COALESCE(g.moneda, 'ARS') as moneda, g.anulado,
                  l.nombre as local_nombre,
                  c.nombre as categoria_nombre
           FROM gastos g
           JOIN locales l ON g.local_id = l.id
           JOIN categorias c ON g.categoria_id = c.id
           WHERE g.es_recurrente = 1 AND g.anulado = 0
           ORDER BY g.proxima_fecha ASC NULLS LAST, g.descripcion'''
    ).fetchall()
    db.close()
    return render_template('gastos/recurrentes.html',
        gastos=gastos_rec, hoy=hoy, hoy_7d=hoy + timedelta(days=7))


@bp.route('/comprobante/<filename>')
def ver_comprobante(filename):
    """Sirve archivos de comprobantes de forma segura."""
    return send_from_directory(_upload_folder(), filename)


@bp.route('/<int:gasto_id>/anular', methods=['POST'])
def anular_gasto(gasto_id):
    db = get_db()
    db.execute('UPDATE gastos SET anulado = 1 WHERE id = ?', (gasto_id,))
    db.commit()
    db.close()
    flash('Gasto anulado correctamente.', 'warning')
    return redirect(url_for('gastos.list_gastos'))


@bp.route('/<int:gasto_id>/eliminar', methods=['POST'])
def eliminar_gasto(gasto_id):
    db = get_db()
    en_uso_cheques = db.execute(
        'SELECT COUNT(*) as c FROM cheques WHERE gasto_id = ?', (gasto_id,)
    ).fetchone()['c']
    if en_uso_cheques:
        flash('No se puede eliminar: el gasto tiene cheques vinculados. Anulá el gasto o eliminá primero los cheques.', 'danger')
        db.close()
        return redirect(url_for('gastos.list_gastos'))
    db.execute('DELETE FROM gastos WHERE id = ?', (gasto_id,))
    db.commit()
    db.close()
    flash('Gasto eliminado definitivamente.', 'danger')
    return redirect(url_for('gastos.list_gastos'))


@bp.route('/exportar-csv')
def exportar_csv():
    import csv, io
    from flask import Response

    db = get_db()
    fecha_desde      = request.args.get('fecha_desde', '')
    fecha_hasta      = request.args.get('fecha_hasta', '')
    local_id         = request.args.get('local_id', '')
    categoria_id     = request.args.get('categoria_id', '')
    proveedor_id     = request.args.get('proveedor_id', '')
    mostrar_anulados = request.args.get('mostrar_anulados', '0')

    query = '''
        SELECT g.fecha, l.nombre as local, c.nombre as categoria,
               COALESCE(sc.nombre, '') as subcategoria,
               COALESCE(p.nombre, '') as proveedor,
               COALESCE(g.descripcion, '') as descripcion,
               g.monto, COALESCE(g.moneda, 'ARS') as moneda,
               COALESCE(g.medio_pago, '') as medio_pago,
               COALESCE(g.observaciones, '') as observaciones
        FROM gastos g
        JOIN locales l ON g.local_id = l.id
        JOIN categorias c ON g.categoria_id = c.id
        LEFT JOIN subcategorias sc ON g.subcategoria_id = sc.id
        LEFT JOIN proveedores p ON g.proveedor_id = p.id
        WHERE 1=1
    '''
    params = []
    if mostrar_anulados != '1':
        query += ' AND g.anulado = 0'
    if fecha_desde:
        query += ' AND g.fecha >= ?'; params.append(fecha_desde)
    if fecha_hasta:
        query += ' AND g.fecha <= ?'; params.append(fecha_hasta)
    if local_id:
        query += ' AND g.local_id = ?'; params.append(local_id)
    if categoria_id:
        query += ' AND g.categoria_id = ?'; params.append(categoria_id)
    if proveedor_id:
        query += ' AND g.proveedor_id = ?'; params.append(proveedor_id)
    query += ' ORDER BY g.fecha DESC'

    rows = db.execute(query, params).fetchall()
    db.close()

    def _fmt(val):
        if val is None: return ''
        if hasattr(val, 'strftime'): return val.strftime('%d/%m/%Y')
        s = str(val)[:10]; p = s.split('-')
        return f'{p[2]}/{p[1]}/{p[0]}' if len(p) == 3 else s

    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(['Fecha', 'Local', 'Categoría', 'Subcategoría', 'Proveedor',
                'Descripción', 'Monto', 'Moneda', 'Medio de pago', 'Observaciones'])
    for r in rows:
        w.writerow([_fmt(r['fecha']), r['local'], r['categoria'], r['subcategoria'],
                    r['proveedor'], r['descripcion'],
                    str(r['monto']).replace('.', ','), r['moneda'],
                    r['medio_pago'], r['observaciones']])

    fname = f'gastos_{fecha_desde or "todo"}_{fecha_hasta or "hoy"}.csv'
    return Response('﻿' + out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{fname}"'})


@bp.route('/api/subcategorias/<int:categoria_id>')
def api_subcategorias(categoria_id):
    from flask import jsonify
    db = get_db()
    subs = db.execute(
        'SELECT id, nombre FROM subcategorias WHERE categoria_id = ? AND activo = 1 ORDER BY nombre',
        (categoria_id,)
    ).fetchall()
    db.close()
    return jsonify([dict(s) for s in subs])
