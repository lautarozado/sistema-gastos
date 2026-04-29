from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db

bp = Blueprint('proveedores', __name__, url_prefix='/proveedores')


@bp.route('/')
def index():
    db = get_db()
    buscar = request.args.get('buscar', '').strip()

    if buscar:
        proveedores = db.execute(
            "SELECT * FROM proveedores WHERE nombre ILIKE ? ORDER BY activo DESC, nombre",
            (f'%{buscar}%',)
        ).fetchall()
    else:
        proveedores = db.execute(
            'SELECT * FROM proveedores ORDER BY activo DESC, nombre'
        ).fetchall()

    db.close()
    return render_template('proveedores/index.html', proveedores=proveedores, buscar=buscar)


@bp.route('/nuevo', methods=['POST'])
def nuevo_proveedor():
    nombre = request.form.get('nombre', '').strip()
    telefono = request.form.get('telefono', '').strip()
    observaciones = request.form.get('observaciones', '').strip()

    if not nombre:
        flash('El nombre del proveedor es obligatorio.', 'danger')
        return redirect(url_for('proveedores.index'))

    db = get_db()
    existe = db.execute(
        'SELECT id FROM proveedores WHERE nombre ILIKE ?', (nombre,)
    ).fetchone()
    if existe:
        flash('Ya existe un proveedor con ese nombre.', 'warning')
        db.close()
        return redirect(url_for('proveedores.index'))

    db.execute(
        'INSERT INTO proveedores (nombre, telefono, observaciones) VALUES (?, ?, ?)',
        (nombre, telefono or None, observaciones or None)
    )
    db.commit()
    db.close()
    flash(f'Proveedor "{nombre}" creado correctamente.', 'success')
    return redirect(url_for('proveedores.index'))


@bp.route('/<int:prov_id>/editar', methods=['POST'])
def editar_proveedor(prov_id):
    nombre = request.form.get('nombre', '').strip()
    telefono = request.form.get('telefono', '').strip()
    observaciones = request.form.get('observaciones', '').strip()

    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('proveedores.index'))

    db = get_db()
    db.execute(
        'UPDATE proveedores SET nombre=?, telefono=?, observaciones=? WHERE id=?',
        (nombre, telefono or None, observaciones or None, prov_id)
    )
    db.commit()
    db.close()
    flash('Proveedor actualizado correctamente.', 'success')
    return redirect(url_for('proveedores.index'))


@bp.route('/<int:prov_id>/toggle', methods=['POST'])
def toggle_proveedor(prov_id):
    db = get_db()
    prov = db.execute('SELECT activo FROM proveedores WHERE id = ?', (prov_id,)).fetchone()
    if prov:
        nuevo = 0 if prov['activo'] else 1
        db.execute('UPDATE proveedores SET activo = ? WHERE id = ?', (nuevo, prov_id))
        db.commit()
        flash('Proveedor activado.' if nuevo else 'Proveedor desactivado.',
              'success' if nuevo else 'warning')
    db.close()
    return redirect(url_for('proveedores.index'))


@bp.route('/<int:prov_id>/eliminar', methods=['POST'])
def eliminar_proveedor(prov_id):
    db = get_db()
    en_uso = db.execute(
        'SELECT COUNT(*) as c FROM gastos WHERE proveedor_id = ?', (prov_id,)
    ).fetchone()['c']
    if en_uso:
        flash('No se puede eliminar: el proveedor tiene gastos asociados. Podés desactivarlo.', 'danger')
        db.close()
        return redirect(url_for('proveedores.index'))
    db.execute('DELETE FROM proveedores WHERE id = ?', (prov_id,))
    db.commit()
    db.close()
    flash('Proveedor eliminado.', 'success')
    return redirect(url_for('proveedores.index'))
