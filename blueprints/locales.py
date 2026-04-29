from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db

bp = Blueprint('locales', __name__, url_prefix='/locales')


@bp.route('/')
def index():
    db = get_db()
    locales = db.execute('SELECT * FROM locales ORDER BY activo DESC, nombre').fetchall()

    # Stats por local
    stats = {}
    for local in locales:
        total_gastos = db.execute(
            'SELECT COALESCE(SUM(monto), 0) as t FROM gastos WHERE local_id = ? AND anulado = 0',
            (local['id'],)
        ).fetchone()['t']
        total_ingresos = db.execute(
            'SELECT COALESCE(SUM(total), 0) as t FROM ingresos WHERE local_id = ? AND anulado = 0',
            (local['id'],)
        ).fetchone()['t']
        stats[local['id']] = {
            'gastos': total_gastos,
            'ingresos': total_ingresos,
            'balance': total_ingresos - total_gastos,
        }

    db.close()
    return render_template('locales/index.html', locales=locales, stats=stats)


@bp.route('/nuevo', methods=['POST'])
def nuevo_local():
    nombre = request.form.get('nombre', '').strip()
    descripcion = request.form.get('descripcion', '').strip()

    if not nombre:
        flash('El nombre del local es obligatorio.', 'danger')
        return redirect(url_for('locales.index'))

    db = get_db()
    existe = db.execute(
        'SELECT id FROM locales WHERE nombre ILIKE ?', (nombre,)
    ).fetchone()
    if existe:
        flash('Ya existe un local con ese nombre.', 'warning')
        db.close()
        return redirect(url_for('locales.index'))

    db.execute(
        'INSERT INTO locales (nombre, descripcion) VALUES (?, ?)',
        (nombre, descripcion or None)
    )
    db.commit()
    db.close()
    flash(f'Local "{nombre}" creado correctamente.', 'success')
    return redirect(url_for('locales.index'))


@bp.route('/<int:local_id>/editar', methods=['POST'])
def editar_local(local_id):
    nombre = request.form.get('nombre', '').strip()
    descripcion = request.form.get('descripcion', '').strip()

    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('locales.index'))

    db = get_db()
    db.execute(
        'UPDATE locales SET nombre=?, descripcion=? WHERE id=?',
        (nombre, descripcion or None, local_id)
    )
    db.commit()
    db.close()
    flash('Local actualizado correctamente.', 'success')
    return redirect(url_for('locales.index'))


@bp.route('/<int:local_id>/toggle', methods=['POST'])
def toggle_local(local_id):
    db = get_db()
    local = db.execute('SELECT activo FROM locales WHERE id = ?', (local_id,)).fetchone()
    if local:
        nuevo = 0 if local['activo'] else 1
        db.execute('UPDATE locales SET activo = ? WHERE id = ?', (nuevo, local_id))
        db.commit()
        flash('Local activado.' if nuevo else 'Local desactivado.',
              'success' if nuevo else 'warning')
    db.close()
    return redirect(url_for('locales.index'))


@bp.route('/<int:local_id>/eliminar', methods=['POST'])
def eliminar_local(local_id):
    db = get_db()
    en_uso_g = db.execute(
        'SELECT COUNT(*) as c FROM gastos WHERE local_id = ?', (local_id,)
    ).fetchone()['c']
    en_uso_i = db.execute(
        'SELECT COUNT(*) as c FROM ingresos WHERE local_id = ?', (local_id,)
    ).fetchone()['c']
    if en_uso_g or en_uso_i:
        flash('No se puede eliminar: el local tiene movimientos asociados. Podés desactivarlo.', 'danger')
        db.close()
        return redirect(url_for('locales.index'))
    db.execute('DELETE FROM locales WHERE id = ?', (local_id,))
    db.commit()
    db.close()
    flash('Local eliminado.', 'success')
    return redirect(url_for('locales.index'))
