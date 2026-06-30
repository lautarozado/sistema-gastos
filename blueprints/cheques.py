from datetime import date, datetime, timedelta
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, Response)
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


def _filtros_cheques(args):
    """Construye el WHERE y los parámetros según los filtros de la query."""
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
    if args.get('estado'):
        query += ' AND ch.estado = ?'; params.append(args['estado'])
    if args.get('proveedor_id'):
        query += ' AND ch.proveedor_id = ?'; params.append(args['proveedor_id'])
    if args.get('banco'):
        query += ' AND ch.banco = ?'; params.append(args['banco'])
    if args.get('fecha_desde'):
        query += ' AND ch.fecha_pago >= ?'; params.append(args['fecha_desde'])
    if args.get('fecha_hasta'):
        query += ' AND ch.fecha_pago <= ?'; params.append(args['fecha_hasta'])
    query += ' ORDER BY ch.fecha_pago ASC, ch.id DESC'
    return query, params


def _suma_hasta(pendientes, hoy, dias):
    """Total pendiente a debitar desde hoy hasta hoy+dias (incluye vencidos)."""
    limite = str(hoy + timedelta(days=dias))
    return sum(
        c['monto'] for c in pendientes
        if c['fecha_pago'] and str(c['fecha_pago'])[:10] <= limite
    )


@bp.route('/')
def list_cheques():
    db = get_db()
    filtros = {k: request.args.get(k, '') for k in
               ('estado', 'proveedor_id', 'banco', 'fecha_desde', 'fecha_hasta')}

    query, params = _filtros_cheques(filtros)
    cheques = db.execute(query, params).fetchall()

    # Flujo de caja: solo cheques pendientes, separados por tipo
    pendientes = [c for c in cheques if c['estado'] == 'pendiente']
    emitidos   = [c for c in pendientes if (c['tipo'] or 'emitido') == 'emitido']
    recibidos  = [c for c in pendientes if (c['tipo'] or 'emitido') == 'recibido']

    total_emitidos  = sum(c['monto'] for c in emitidos)
    total_recibidos = sum(c['monto'] for c in recibidos)
    total_pendiente = total_emitidos  # compatibilidad

    hoy = date.today()
    horizontes = {
        7:  _suma_hasta(emitidos, hoy, 7),
        30: _suma_hasta(emitidos, hoy, 30),
        60: _suma_hasta(emitidos, hoy, 60),
        90: _suma_hasta(emitidos, hoy, 90),
    }
    horizontes_recibidos = {
        7:  _suma_hasta(recibidos, hoy, 7),
        30: _suma_hasta(recibidos, hoy, 30),
        60: _suma_hasta(recibidos, hoy, 60),
        90: _suma_hasta(recibidos, hoy, 90),
    }
    vencidos = sum(
        c['monto'] for c in emitidos
        if c['fecha_pago'] and str(c['fecha_pago'])[:10] < str(hoy)
    )
    cant_vencidos = sum(
        1 for c in emitidos
        if c['fecha_pago'] and str(c['fecha_pago'])[:10] < str(hoy)
    )

    # Pendiente por beneficiario (solo emitidos — son los que hay que pagar)
    agrup = {}
    for c in emitidos:
        nombre = c['proveedor_nombre'] or c['beneficiario'] or 'Sin beneficiario'
        d = agrup.setdefault(nombre, {'monto': 0.0, 'cant': 0})
        d['monto'] += c['monto']; d['cant'] += 1
    por_proveedor = sorted(
        ({'nombre': k, 'monto': v['monto'], 'cant': v['cant']} for k, v in agrup.items()),
        key=lambda x: -x['monto'])

    proveedores = db.execute(
        'SELECT * FROM proveedores WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()

    return render_template('cheques/list.html',
        cheques=cheques, proveedores=proveedores, estados=ESTADOS_CHEQUE,
        bancos=BANCOS, filtros=filtros,
        total_pendiente=total_pendiente,
        total_emitidos=total_emitidos,
        total_recibidos=total_recibidos,
        horizontes=horizontes,
        horizontes_recibidos=horizontes_recibidos,
        por_proveedor=por_proveedor,
        vencidos=vencidos, cant_vencidos=cant_vencidos, hoy=hoy)


@bp.route('/agenda')
def agenda():
    """Vista calendario mensual de débitos de cheques pendientes."""
    import calendar as _cal
    db = get_db()
    hoy = date.today()
    try:
        anio = int(request.args.get('anio', hoy.year))
        mes = int(request.args.get('mes', hoy.month))
        if not (1 <= mes <= 12):
            raise ValueError
    except (ValueError, TypeError):
        anio, mes = hoy.year, hoy.month

    primero = date(anio, mes, 1)
    ult_dia = _cal.monthrange(anio, mes)[1]
    ultimo = date(anio, mes, ult_dia)

    rows = db.execute(
        '''SELECT ch.id, ch.numero, ch.monto, ch.fecha_pago, ch.estado, ch.banco,
                  p.nombre as proveedor_nombre, ch.beneficiario
           FROM cheques ch
           LEFT JOIN proveedores p ON ch.proveedor_id = p.id
           WHERE ch.estado = 'pendiente'
             AND ch.fecha_pago >= ? AND ch.fecha_pago <= ?
           ORDER BY ch.fecha_pago ASC''',
        (str(primero), str(ultimo))).fetchall()
    db.close()

    # Agrupar por día
    por_dia = {}
    total_mes = 0.0
    for r in rows:
        dia = int(str(r['fecha_pago'])[8:10])
        por_dia.setdefault(dia, {'items': [], 'total': 0.0})
        por_dia[dia]['items'].append(r)
        por_dia[dia]['total'] += r['monto']
        total_mes += r['monto']

    # Matriz de semanas (lunes a domingo)
    _cal.setfirstweekday(_cal.MONDAY)
    semanas = _cal.monthcalendar(anio, mes)

    prev_mes = mes - 1 or 12
    prev_anio = anio - 1 if mes == 1 else anio
    next_mes = mes + 1 if mes < 12 else 1
    next_anio = anio + 1 if mes == 12 else anio
    nombres_mes = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

    return render_template('cheques/agenda.html',
        semanas=semanas, por_dia=por_dia, total_mes=total_mes,
        anio=anio, mes=mes, mes_nombre=nombres_mes[mes],
        prev_anio=prev_anio, prev_mes=prev_mes,
        next_anio=next_anio, next_mes=next_mes,
        hoy=hoy)


@bp.route('/exportar-csv')
def exportar_csv():
    import csv, io
    db = get_db()
    filtros = {k: request.args.get(k, '') for k in
               ('estado', 'proveedor_id', 'banco', 'fecha_desde', 'fecha_hasta')}
    query, params = _filtros_cheques(filtros)
    rows = db.execute(query, params).fetchall()
    db.close()

    def _fmt(val):
        if val is None:
            return ''
        if hasattr(val, 'strftime'):
            return val.strftime('%d/%m/%Y')
        s = str(val)[:10]; p = s.split('-')
        return f'{p[2]}/{p[1]}/{p[0]}' if len(p) == 3 else s

    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(['Numero', 'Banco', 'Tipo', 'Beneficiario', 'Emision',
                'Pago/Debito', 'Plazo (dias)', 'Monto', 'Moneda', 'Estado',
                'Gasto vinculado', 'Observaciones'])
    for r in rows:
        w.writerow([
            r['numero'] or '', r['banco'] or '', r['tipo'] or '',
            r['proveedor_nombre'] or r['beneficiario'] or '',
            _fmt(r['fecha_emision']), _fmt(r['fecha_pago']),
            r['plazo_dias'] or '', str(r['monto']).replace('.', ','),
            r['moneda'] or '', r['estado'] or '',
            r['gasto_descripcion'] or '', r['observaciones'] or '',
        ])
    return Response('﻿' + out.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="cheques.csv"'})


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
    if not d['numero']:
        errors.append('El número de cheque es obligatorio.')
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
        multiple = request.form.get('emision_multiple') == '1'

        if multiple:
            # Plazos elegidos (checkboxes) + personalizados (texto coma-separado)
            plazos = []
            for p in request.form.getlist('plazos'):
                try:
                    plazos.append(int(p))
                except ValueError:
                    pass
            for tok in request.form.get('plazos_extra', '').replace(';', ',').split(','):
                tok = tok.strip()
                if tok.isdigit():
                    plazos.append(int(tok))
            plazos = sorted({p for p in plazos if p > 0})

            errors = []
            if not d['numero']:
                errors.append('El número de cheque es obligatorio.')
            if not d['fecha_emision']:
                errors.append('La fecha de emisión es obligatoria.')
            if not plazos:
                errors.append('Elegí al menos un plazo (30/60/90 o personalizado).')
            if d['moneda'] not in ('ARS', 'USD'):
                d['moneda'] = 'ARS'
            if d['estado'] not in _ESTADOS_VALIDOS:
                d['estado'] = 'pendiente'
            try:
                d['monto'] = _parse_monto(d['monto_str'])
                if d['monto'] <= 0:
                    errors.append('El monto debe ser mayor a cero.')
            except (ValueError, AttributeError):
                errors.append('El monto ingresado no es válido.')
                d['monto'] = 0

            if errors:
                for e in errors:
                    flash(e, 'danger')
                db.close()
                return render_template('cheques/form.html',
                    proveedores=proveedores, locales=locales, gastos=gastos,
                    bancos=BANCOS, estados=ESTADOS_CHEQUE, plazos=PLAZOS_CHEQUE,
                    cheque=request.form, modo='nuevo')

            femi = datetime.strptime(d['fecha_emision'], '%Y-%m-%d').date()
            base_num = d['numero']
            num_correlativo = base_num.isdigit()
            for i, plazo in enumerate(plazos):
                fpago = (femi + timedelta(days=plazo)).strftime('%Y-%m-%d')
                numero = str(int(base_num) + i) if num_correlativo else base_num
                db.execute(
                    '''INSERT INTO cheques
                       (numero, banco, tipo, beneficiario, proveedor_id, local_id, gasto_id,
                        monto, fecha_emision, fecha_pago, plazo_dias, estado, moneda, observaciones)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (numero, d['banco'], d['tipo'], d['beneficiario'], d['proveedor_id'],
                     d['local_id'], d['gasto_id'], d['monto'], d['fecha_emision'], fpago,
                     plazo, d['estado'], d['moneda'], d['observaciones'])
                )
            db.commit()
            db.close()
            flash(f'Se emitieron {len(plazos)} cheques diferidos '
                  f'({", ".join(str(p) for p in plazos)} días).', 'success')
            return redirect(url_for('cheques.list_cheques'))

        # Modo individual
        errors = _validar(d)
        if errors:
            for e in errors:
                flash(e, 'danger')
            db.close()
            return render_template('cheques/form.html',
                proveedores=proveedores, locales=locales, gastos=gastos,
                bancos=BANCOS, estados=ESTADOS_CHEQUE, plazos=PLAZOS_CHEQUE,
                cheque=request.form, modo='nuevo')

        if d.get('gasto_id'):
            gasto_ref = db.execute(
                'SELECT monto FROM gastos WHERE id = ?', (d['gasto_id'],)
            ).fetchone()
            if gasto_ref and abs(d['monto'] - gasto_ref['monto']) > 0.01:
                flash(
                    f'Atención: el monto del cheque (${d["monto"]:,.2f}) no coincide con '
                    f'el monto del gasto vinculado (${gasto_ref["monto"]:,.2f}). '
                    f'Si es un pago parcial, ignorá este aviso.',
                    'warning'
                )

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

        if d.get('gasto_id'):
            gasto_ref = db.execute(
                'SELECT monto FROM gastos WHERE id = ?', (d['gasto_id'],)
            ).fetchone()
            if gasto_ref and abs(d['monto'] - gasto_ref['monto']) > 0.01:
                flash(
                    f'Atención: el monto del cheque (${d["monto"]:,.2f}) no coincide con '
                    f'el monto del gasto vinculado (${gasto_ref["monto"]:,.2f}). '
                    f'Si es un pago parcial, ignorá este aviso.',
                    'warning'
                )

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
