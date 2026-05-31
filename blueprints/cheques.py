from datetime import date, timedelta
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash)
from database import get_db, BANCOS, ESTADOS_CHEQUE, PLAZOS_CHEQUE

bp = Blueprint('cheques', __name__, url_prefix='/cheques')

_ESTADOS_VALIDOS = {c for c, _ in ESTADOS_CHEQUE}


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


def _form_data(db):
    proveedores = db.execute(
        'SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    locales = db.execute(
        'SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    gastos = db.execute(
        '''SELECT g.id, g.fecha, g.monto, g.descripcion,
                  c.nombre as categoria_nombre, p.nombre as proveedor_nombre
           FROM gastos g
           JOIN categorias c ON g.categoria_id = c.id
           LEFT JOIN proveedores p ON g.proveedor_id = p.id
           WHERE g.anulado = 0
           ORDER BY g.fecha DESC, g.created_at DESC
           LIMIT 200''').fetchall()
    return proveedores, locales, gastos


@bp.route('/')
def list_cheques():
    db = get_db()
    estado = request.args.get('estado', '')
    proveedor_id = request.args.get('proveedor_id', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')

    query = '''
        SELECT ch.*, p.nombre as proveedor_nombre, l.nombre as local_nombre,
               g.descripcion as gasto_descripcion
        FROM cheques ch
        LEFT JOIN proveedores p ON ch.proveedor_id = p.id
        LEFT JOIN locales l ON ch.local_id = l.id
        LEFT JOIN gastos g ON ch.gasto_id = g.id
        WHERE 1=1
    '''
    params = []
    if estado:
        query += ' AND ch.estado = ?'; params.append(estado)
    if proveedor_id:
        query += ' AND ch.proveedor_id = ?'; params.append(proveedor_id)
    if fecha_desde:
        query += ' AND ch.fecha_pago >= ?'; params.append(fecha_desde)
    if fecha_hasta:
        query += ' AND ch.fecha_pago <= ?'; params.append(fecha_hasta)
    query += ' ORDER BY ch.fecha_pago ASC, ch.id DESC'

    cheques = db.execute(query, params).fetchall()

    # Totales por estado (solo pendientes para el flujo de caja)
    pendientes = [c for c in cheques if c['estado'] == 'pendiente']
    total_pendiente = sum(c['monto'] for c in pendientes)

    hoy = date.today()
    proximos_7d = sum(
        c['monto'] for c in pendientes
        if c['fecha_pago'] and str(c['fecha_pago'])[:10] <= str(hoy + timedelta(days=7))
    )
    vencidos = sum(
        c['monto'] for c in pendientes
        if c['fecha_pago'] and str(c['fecha_pago'])[:10] < str(hoy)
    )

    proveedores = db.execute(
        'SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()

    return render_template('cheques/list.html',
        cheques=cheques, proveedores=proveedores, estados=ESTADOS_CHEQUE,
        estado=estado, proveedor_id=proveedor_id,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        total_pendiente=total_pendiente, proximos_7d=proximos_7d,
        vencidos=vencidos, hoy=hoy)


def _leer_form():
    f = request.form
    return {
        'numero': f.get('numero', '').strip(),
        'banco': f.get('banco', 'Banco Nación').strip(),
        'tipo': f.get('tipo', 'emitido').strip() or 'emitido',
        'beneficiario': f.get('beneficiario', '').strip(),
        'proveedor_id': f.get('proveedor_id', '').strip() or None,
        'local_id': f.get('local_id', '').strip() or None,
        'gasto_id': f.get('gasto_id', '').strip() or None,
        'monto_str': f.get('monto', '').strip(),
        'fecha_emision': f.get('fecha_emision', '').strip(),
        'fecha_pago': f.get('fecha_pago', '').strip(),
        'plazo_dias': f.get('plazo_dias', '').strip() or None,
        'estado': f.get('estado', 'pendiente').strip() or 'pendiente',
        'moneda': f.get('moneda', 'ARS').strip() or 'ARS',
        'observaciones': f.get('observaciones', '').strip(),
    }


def _validar(d):
    errors = []
    if not d['fecha_emision']:
        errors.append('La fecha de emisión es obligatoria.')
    if not d['fecha_pago']:
        errors.append('La fecha de pago (débito) es obligatoria.')
    if d['fecha_emision'] and d['fecha_pago'] and d['fecha_pago'] < d['fecha_emision']:
        errors.append('La fecha de pago no puede ser anterior a la de emisión.')
    if d['estado'] not in _ESTADOS_VALIDOS:
        d['estado'] = 'pendiente'
    if d['moneda'] not in ('ARS', 'USD'):
        d['moneda'] = 'ARS'
    try:
        d['monto'] = _parse_monto(d['monto_str'])
        if d['monto'] <= 0:
            errors.append('El monto debe ser mayor a cero.')
    except (ValueError, AttributeError):
        errors.append('El monto ingresado no es válido.')
        d['monto'] = 0
    return errors


@bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo_cheque():
    db = get_db()
    proveedores, locales, gastos = _form_data(db)

    if request.method == 'POST':
        d = _leer_form()
        errors = _validar(d)
        if errors:
            for e in errors:
                flash(e, 'danger')
            db.close()
            return render_template('cheques/form.html',
                proveedores=proveedores, locales=locales, gastos=gastos,
                bancos=BANCOS, estados=ESTADOS_CHEQUE, plazos=PLAZOS_CHEQUE,
                cheque=request.form, modo='nuevo')

        db.execute(
            '''INSERT INTO cheques
               (numero, banco, tipo, beneficiario, proveedor_id, local_id, gasto_id,
                monto, fecha_emision, fecha_pago, plazo_dias, estado, moneda, observaciones)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (d['numero'], d['banco'], d['tipo'], d['beneficiario'], d['proveedor_id'],
             d['local_id'], d['gasto_id'], d['monto'], d['fecha_emision'], d['fecha_pago'],
             d['plazo_dias'], d['estado'], d['moneda'], d['observaciones'])
        )
        db.commit()
        db.close()
        flash('Cheque registrado correctamente.', 'success')
        return redirect(url_for('cheques.list_cheques'))

    db.close()
    hoy = date.today().strftime('%Y-%m-%d')
    gasto_id = request.args.get('gasto_id', '')
    return render_template('cheques/form.html',
        proveedores=proveedores, locales=locales, gastos=gastos,
        bancos=BANCOS, estados=ESTADOS_CHEQUE, plazos=PLAZOS_CHEQUE,
        cheque={'fecha_emision': hoy, 'gasto_id': gasto_id, 'banco': 'Banco Nación'},
        modo='nuevo')


@bp.route('/<int:cheque_id>/editar', methods=['GET', 'POST'])
def editar_cheque(cheque_id):
    db = get_db()
    cheque = db.execute('SELECT * FROM cheques WHERE id = ?', (cheque_id,)).fetchone()
    if not cheque:
        flash('Cheque no encontrado.', 'danger')
        db.close()
        return redirect(url_for('cheques.list_cheques'))

    proveedores, locales, gastos = _form_data(db)

    if request.method == 'POST':
        d = _leer_form()
        errors = _validar(d)
        if errors:
            for e in errors:
                flash(e, 'danger')
            db.close()
            return render_template('cheques/form.html',
                proveedores=proveedores, locales=locales, gastos=gastos,
                bancos=BANCOS, estados=ESTADOS_CHEQUE, plazos=PLAZOS_CHEQUE,
                cheque=request.form, modo='editar', cheque_id=cheque_id)

        db.execute(
            '''UPDATE cheques SET
               numero=?, banco=?, tipo=?, beneficiario=?, proveedor_id=?, local_id=?,
               gasto_id=?, monto=?, fecha_emision=?, fecha_pago=?, plazo_dias=?,
               estado=?, moneda=?, observaciones=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (d['numero'], d['banco'], d['tipo'], d['beneficiario'], d['proveedor_id'],
             d['local_id'], d['gasto_id'], d['monto'], d['fecha_emision'], d['fecha_pago'],
             d['plazo_dias'], d['estado'], d['moneda'], d['observaciones'], cheque_id)
        )
        db.commit()
        db.close()
        flash('Cheque actualizado correctamente.', 'success')
        return redirect(url_for('cheques.list_cheques'))

    db.close()
    return render_template('cheques/form.html',
        proveedores=proveedores, locales=locales, gastos=gastos,
        bancos=BANCOS, estados=ESTADOS_CHEQUE, plazos=PLAZOS_CHEQUE,
        cheque=cheque, modo='editar', cheque_id=cheque_id)


@bp.route('/<int:cheque_id>/estado', methods=['POST'])
def cambiar_estado(cheque_id):
    nuevo = request.form.get('estado', '').strip()
    if nuevo not in _ESTADOS_VALIDOS:
        flash('Estado no válido.', 'danger')
        return redirect(url_for('cheques.list_cheques'))
    db = get_db()
    db.execute(
        'UPDATE cheques SET estado=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
        (nuevo, cheque_id))
    db.commit()
    db.close()
    flash(f'Cheque marcado como {nuevo}.', 'success')
    return redirect(request.referrer or url_for('cheques.list_cheques'))


@bp.route('/<int:cheque_id>/eliminar', methods=['POST'])
def eliminar_cheque(cheque_id):
    db = get_db()
    db.execute('DELETE FROM cheques WHERE id = ?', (cheque_id,))
    db.commit()
    db.close()
    flash('Cheque eliminado definitivamente.', 'danger')
    return redirect(url_for('cheques.list_cheques'))
