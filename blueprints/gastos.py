from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db, MEDIOS_PAGO
from datetime import date

bp = Blueprint('gastos', __name__, url_prefix='/gastos')


def get_form_data():
    db = get_db()
    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    categorias = db.execute('SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre').fetchall()
    proveedores = db.execute('SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()
    return locales, categorias, proveedores


@bp.route('/')
def list_gastos():
    db = get_db()

    # Filtros
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    local_id = request.args.get('local_id', '')
    categoria_id = request.args.get('categoria_id', '')
    proveedor_id = request.args.get('proveedor_id', '')
    mostrar_anulados = request.args.get('mostrar_anulados', '0')

    query = '''
        SELECT g.id, g.fecha, g.monto, g.descripcion, g.medio_pago, g.anulado,
               l.nombre as local_nombre,
               c.nombre as categoria_nombre,
               sc.nombre as subcategoria_nombre,
               p.nombre as proveedor_nombre
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
        query += ' AND g.fecha >= ?'
        params.append(fecha_desde)
    if fecha_hasta:
        query += ' AND g.fecha <= ?'
        params.append(fecha_hasta)
    if local_id:
        query += ' AND g.local_id = ?'
        params.append(local_id)
    if categoria_id:
        query += ' AND g.categoria_id = ?'
        params.append(categoria_id)
    if proveedor_id:
        query += ' AND g.proveedor_id = ?'
        params.append(proveedor_id)

    query += ' ORDER BY g.fecha DESC, g.created_at DESC'

    gastos = db.execute(query, params).fetchall()
    total_filtrado = sum(g['monto'] for g in gastos if not g['anulado'])

    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    categorias = db.execute('SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre').fetchall()
    proveedores = db.execute('SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()

    return render_template('gastos/list.html',
        gastos=gastos,
        locales=locales,
        categorias=categorias,
        proveedores=proveedores,
        total_filtrado=total_filtrado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_id=local_id,
        categoria_id=categoria_id,
        proveedor_id=proveedor_id,
        mostrar_anulados=mostrar_anulados,
    )


@bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo_gasto():
    locales, categorias, proveedores = get_form_data()

    if request.method == 'POST':
        fecha = request.form.get('fecha', '').strip()
        local_id = request.form.get('local_id', '').strip()
        categoria_id = request.form.get('categoria_id', '').strip()
        subcategoria_id = request.form.get('subcategoria_id', '').strip() or None
        proveedor_id = request.form.get('proveedor_id', '').strip() or None
        descripcion = request.form.get('descripcion', '').strip()
        monto_str = request.form.get('monto', '').strip()
        medio_pago = request.form.get('medio_pago', '').strip() or None
        observaciones = request.form.get('observaciones', '').strip()

        errors = []
        if not fecha:
            errors.append('La fecha es obligatoria.')
        if not local_id:
            errors.append('El local es obligatorio.')
        if not categoria_id:
            errors.append('La categoría es obligatoria.')
        try:
            monto = float(monto_str.replace('.', '').replace(',', '.') if ',' in monto_str else monto_str)
            if monto <= 0:
                errors.append('El monto debe ser mayor a cero.')
        except (ValueError, AttributeError):
            errors.append('El monto ingresado no es válido.')
            monto = 0

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('gastos/form.html',
                locales=locales, categorias=categorias, proveedores=proveedores,
                medios_pago=MEDIOS_PAGO, gasto=request.form, modo='nuevo')

        db = get_db()
        db.execute(
            '''INSERT INTO gastos (fecha, local_id, categoria_id, subcategoria_id, proveedor_id,
               descripcion, monto, medio_pago, observaciones)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (fecha, local_id, categoria_id, subcategoria_id, proveedor_id,
             descripcion, monto, medio_pago, observaciones)
        )
        db.commit()
        db.close()
        flash('Gasto registrado correctamente.', 'success')
        return redirect(url_for('gastos.list_gastos'))

    hoy = date.today().strftime('%Y-%m-%d')
    return render_template('gastos/form.html',
        locales=locales, categorias=categorias, proveedores=proveedores,
        medios_pago=MEDIOS_PAGO, gasto={'fecha': hoy}, modo='nuevo')


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
        fecha = request.form.get('fecha', '').strip()
        local_id = request.form.get('local_id', '').strip()
        categoria_id = request.form.get('categoria_id', '').strip()
        subcategoria_id = request.form.get('subcategoria_id', '').strip() or None
        proveedor_id = request.form.get('proveedor_id', '').strip() or None
        descripcion = request.form.get('descripcion', '').strip()
        monto_str = request.form.get('monto', '').strip()
        medio_pago = request.form.get('medio_pago', '').strip() or None
        observaciones = request.form.get('observaciones', '').strip()

        errors = []
        if not fecha:
            errors.append('La fecha es obligatoria.')
        if not local_id:
            errors.append('El local es obligatorio.')
        if not categoria_id:
            errors.append('La categoría es obligatoria.')
        try:
            monto = float(monto_str.replace('.', '').replace(',', '.') if ',' in monto_str else monto_str)
            if monto <= 0:
                errors.append('El monto debe ser mayor a cero.')
        except (ValueError, AttributeError):
            errors.append('El monto ingresado no es válido.')
            monto = 0

        if errors:
            for e in errors:
                flash(e, 'danger')
            db.close()
            return render_template('gastos/form.html',
                locales=locales, categorias=categorias, proveedores=proveedores,
                medios_pago=MEDIOS_PAGO, gasto=request.form, modo='editar', gasto_id=gasto_id)

        db.execute(
            '''UPDATE gastos SET fecha=?, local_id=?, categoria_id=?, subcategoria_id=?,
               proveedor_id=?, descripcion=?, monto=?, medio_pago=?, observaciones=?,
               updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (fecha, local_id, categoria_id, subcategoria_id, proveedor_id,
             descripcion, monto, medio_pago, observaciones, gasto_id)
        )
        db.commit()
        db.close()
        flash('Gasto actualizado correctamente.', 'success')
        return redirect(url_for('gastos.list_gastos'))

    # Cargar subcategorías del gasto actual
    subcategorias = db.execute(
        'SELECT * FROM subcategorias WHERE categoria_id = ? AND activo = 1',
        (gasto['categoria_id'],)
    ).fetchall()
    db.close()

    return render_template('gastos/form.html',
        locales=locales, categorias=categorias, proveedores=proveedores,
        medios_pago=MEDIOS_PAGO, gasto=gasto, modo='editar',
        gasto_id=gasto_id, subcategorias=subcategorias)


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
    db.execute('DELETE FROM gastos WHERE id = ?', (gasto_id,))
    db.commit()
    db.close()
    flash('Gasto eliminado definitivamente.', 'danger')
    return redirect(url_for('gastos.list_gastos'))


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
