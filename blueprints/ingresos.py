from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db, MEDIOS_COBRO
from datetime import date

bp = Blueprint('ingresos', __name__, url_prefix='/ingresos')


def parse_monto(valor):
    """
    Convierte montos en formato argentino a float.

    Ejemplos:
    "1.000.000" -> 1000000.0
    "1.000.000,50" -> 1000000.50
    "1000000" -> 1000000.0
    "$ 1.000.000,50" -> 1000000.50
    """
    if valor is None:
        return 0.0

    valor = str(valor).strip()
    valor = valor.replace('$', '')
    valor = valor.replace(' ', '')

    if not valor:
        return 0.0

    # Formato argentino: 1.000.000,50
    if ',' in valor:
        valor = valor.replace('.', '')
        valor = valor.replace(',', '.')
    else:
        # Si tiene puntos y parecen separadores de miles: 1.000.000
        partes = valor.split('.')
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            valor = ''.join(partes)

    return float(valor)


@bp.route('/')
def list_ingresos():
    db = get_db()

    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    local_id = request.args.get('local_id', '')
    mostrar_anulados = request.args.get('mostrar_anulados', '0')

    query = '''
        SELECT i.id, i.fecha_desde, i.fecha_hasta, i.total, i.observaciones, i.anulado,
               l.nombre as local_nombre
        FROM ingresos i
        JOIN locales l ON i.local_id = l.id
        WHERE 1=1
    '''
    params = []

    if mostrar_anulados != '1':
        query += ' AND i.anulado = 0'
    if fecha_desde:
        query += ' AND i.fecha_desde >= ?'
        params.append(fecha_desde)
    if fecha_hasta:
        query += ' AND i.fecha_hasta <= ?'
        params.append(fecha_hasta)
    if local_id:
        query += ' AND i.local_id = ?'
        params.append(local_id)

    query += ' ORDER BY i.fecha_desde DESC, i.created_at DESC'

    ingresos = db.execute(query, params).fetchall()
    total_filtrado = sum(i['total'] for i in ingresos if not i['anulado'])

    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()
    db.close()

    return render_template(
        'ingresos/list.html',
        ingresos=ingresos,
        locales=locales,
        total_filtrado=total_filtrado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        local_id=local_id,
        mostrar_anulados=mostrar_anulados,
        medios_cobro=MEDIOS_COBRO,
    )


@bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo_ingreso():
    db = get_db()
    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()

    if request.method == 'POST':
        fecha_desde = request.form.get('fecha_desde', '').strip()
        fecha_hasta = request.form.get('fecha_hasta', '').strip()
        local_id = request.form.get('local_id', '').strip()
        total_str = request.form.get('total', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        errors = []

        if not fecha_desde:
            errors.append('La fecha desde es obligatoria.')

        if not fecha_hasta:
            errors.append('La fecha hasta es obligatoria.')

        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            errors.append('La fecha desde no puede ser posterior a la fecha hasta.')

        if not local_id:
            errors.append('El local es obligatorio.')

        try:
            total = parse_monto(total_str)
            if total <= 0:
                errors.append('El total debe ser mayor a cero.')
        except (ValueError, AttributeError):
            errors.append('El total ingresado no es válido.')
            total = 0.0

        # Medios de cobro
        medios_data = {}
        suma_medios = 0.0

        for codigo, _ in MEDIOS_COBRO:
            val_str = request.form.get(f'medio_{codigo}', '0').strip()

            try:
                val = parse_monto(val_str)
            except (ValueError, AttributeError):
                val = 0.0

            if val < 0:
                errors.append(f'El monto de {codigo} no puede ser negativo.')
                val = 0.0

            medios_data[codigo] = val
            suma_medios += val

        if not errors and total > 0:
            if abs(suma_medios - total) > 0.01:
                errors.append(
                    f'La suma de los medios de cobro (${suma_medios:,.2f}) '
                    f'debe coincidir con el total (${total:,.2f}).'
                )

        if errors:
            for e in errors:
                flash(e, 'danger')

            db.close()

            return render_template(
                'ingresos/form.html',
                locales=locales,
                medios_cobro=MEDIOS_COBRO,
                ingreso=request.form,
                medios_vals=medios_data,
                modo='nuevo'
            )

        cur = db.execute(
            '''INSERT INTO ingresos (fecha_desde, fecha_hasta, local_id, total, observaciones)
               VALUES (?, ?, ?, ?, ?)''',
            (fecha_desde, fecha_hasta, local_id, total, observaciones)
        )

        ingreso_id = cur.lastrowid

        for codigo, _ in MEDIOS_COBRO:
            monto_medio = medios_data.get(codigo, 0.0)

            if monto_medio > 0:
                db.execute(
                    'INSERT INTO detalle_ingresos_medios (ingreso_id, medio, monto) VALUES (?, ?, ?)',
                    (ingreso_id, codigo, monto_medio)
                )

        db.commit()
        db.close()

        flash('Ingreso registrado correctamente.', 'success')
        return redirect(url_for('ingresos.list_ingresos'))

    hoy = date.today().strftime('%Y-%m-%d')
    db.close()

    return render_template(
        'ingresos/form.html',
        locales=locales,
        medios_cobro=MEDIOS_COBRO,
        ingreso={
            'fecha_desde': hoy,
            'fecha_hasta': hoy
        },
        medios_vals={},
        modo='nuevo'
    )


@bp.route('/<int:ingreso_id>/editar', methods=['GET', 'POST'])
def editar_ingreso(ingreso_id):
    db = get_db()

    ingreso = db.execute(
        'SELECT * FROM ingresos WHERE id = ?',
        (ingreso_id,)
    ).fetchone()

    if not ingreso:
        flash('Ingreso no encontrado.', 'danger')
        db.close()
        return redirect(url_for('ingresos.list_ingresos'))

    locales = db.execute('SELECT * FROM locales WHERE activo = 1 ORDER BY nombre').fetchall()

    if request.method == 'POST':
        fecha_desde = request.form.get('fecha_desde', '').strip()
        fecha_hasta = request.form.get('fecha_hasta', '').strip()
        local_id = request.form.get('local_id', '').strip()
        total_str = request.form.get('total', '').strip()
        observaciones = request.form.get('observaciones', '').strip()

        errors = []

        if not fecha_desde:
            errors.append('La fecha desde es obligatoria.')

        if not fecha_hasta:
            errors.append('La fecha hasta es obligatoria.')

        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            errors.append('La fecha desde no puede ser posterior a la fecha hasta.')

        if not local_id:
            errors.append('El local es obligatorio.')

        try:
            total = parse_monto(total_str)
            if total <= 0:
                errors.append('El total debe ser mayor a cero.')
        except (ValueError, AttributeError):
            errors.append('El total ingresado no es válido.')
            total = 0.0

        medios_data = {}
        suma_medios = 0.0

        for codigo, _ in MEDIOS_COBRO:
            val_str = request.form.get(f'medio_{codigo}', '0').strip()

            try:
                val = parse_monto(val_str)
            except (ValueError, AttributeError):
                val = 0.0

            if val < 0:
                errors.append(f'El monto de {codigo} no puede ser negativo.')
                val = 0.0

            medios_data[codigo] = val
            suma_medios += val

        if not errors and total > 0:
            if abs(suma_medios - total) > 0.01:
                errors.append(
                    f'La suma de los medios de cobro (${suma_medios:,.2f}) '
                    f'debe coincidir con el total (${total:,.2f}).'
                )

        if errors:
            for e in errors:
                flash(e, 'danger')

            db.close()

            return render_template(
                'ingresos/form.html',
                locales=locales,
                medios_cobro=MEDIOS_COBRO,
                ingreso=request.form,
                medios_vals=medios_data,
                modo='editar',
                ingreso_id=ingreso_id
            )

        db.execute(
            '''UPDATE ingresos
               SET fecha_desde = ?,
                   fecha_hasta = ?,
                   local_id = ?,
                   total = ?,
                   observaciones = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?''',
            (fecha_desde, fecha_hasta, local_id, total, observaciones, ingreso_id)
        )

        db.execute(
            'DELETE FROM detalle_ingresos_medios WHERE ingreso_id = ?',
            (ingreso_id,)
        )

        for codigo, _ in MEDIOS_COBRO:
            monto_medio = medios_data.get(codigo, 0.0)

            if monto_medio > 0:
                db.execute(
                    'INSERT INTO detalle_ingresos_medios (ingreso_id, medio, monto) VALUES (?, ?, ?)',
                    (ingreso_id, codigo, monto_medio)
                )

        db.commit()
        db.close()

        flash('Ingreso actualizado correctamente.', 'success')
        return redirect(url_for('ingresos.list_ingresos'))

    medios_rows = db.execute(
        'SELECT medio, monto FROM detalle_ingresos_medios WHERE ingreso_id = ?',
        (ingreso_id,)
    ).fetchall()

    medios_vals = {r['medio']: r['monto'] for r in medios_rows}

    db.close()

    return render_template(
        'ingresos/form.html',
        locales=locales,
        medios_cobro=MEDIOS_COBRO,
        ingreso=ingreso,
        medios_vals=medios_vals,
        modo='editar',
        ingreso_id=ingreso_id
    )


@bp.route('/<int:ingreso_id>/detalle')
def detalle_ingreso(ingreso_id):
    db = get_db()

    ingreso = db.execute(
        '''SELECT i.*, l.nombre as local_nombre
           FROM ingresos i
           JOIN locales l ON i.local_id = l.id
           WHERE i.id = ?''',
        (ingreso_id,)
    ).fetchone()

    if not ingreso:
        flash('Ingreso no encontrado.', 'danger')
        db.close()
        return redirect(url_for('ingresos.list_ingresos'))

    medios = db.execute(
        'SELECT * FROM detalle_ingresos_medios WHERE ingreso_id = ?',
        (ingreso_id,)
    ).fetchall()

    db.close()

    return render_template(
        'ingresos/detalle.html',
        ingreso=ingreso,
        medios=medios,
        medios_cobro=MEDIOS_COBRO
    )


@bp.route('/<int:ingreso_id>/anular', methods=['POST'])
def anular_ingreso(ingreso_id):
    db = get_db()

    db.execute(
        'UPDATE ingresos SET anulado = 1 WHERE id = ?',
        (ingreso_id,)
    )

    db.commit()
    db.close()

    flash('Ingreso anulado correctamente.', 'warning')
    return redirect(url_for('ingresos.list_ingresos'))


@bp.route('/<int:ingreso_id>/eliminar', methods=['POST'])
def eliminar_ingreso(ingreso_id):
    db = get_db()

    db.execute(
        'DELETE FROM detalle_ingresos_medios WHERE ingreso_id = ?',
        (ingreso_id,)
    )

    db.execute(
        'DELETE FROM ingresos WHERE id = ?',
        (ingreso_id,)
    )

    db.commit()
    db.close()

    flash('Ingreso eliminado definitivamente.', 'danger')
    return redirect(url_for('ingresos.list_ingresos'))
