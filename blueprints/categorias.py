from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db

bp = Blueprint('categorias', __name__, url_prefix='/categorias')

COLORES_PRESET = [
    '#4361ee', '#3a86ff', '#06b6d4', '#10b981', '#22c55e',
    '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#f97316',
    '#14b8a6', '#64748b', '#1e293b', '#0891b2', '#7c3aed',
]


@bp.route('/')
def index():
    db = get_db()
    categorias = db.execute(
        'SELECT * FROM categorias ORDER BY activo DESC, nombre'
    ).fetchall()

    cats_con_subs = []
    for cat in categorias:
        subs = db.execute(
            'SELECT * FROM subcategorias WHERE categoria_id = ? ORDER BY activo DESC, nombre',
            (cat['id'],)
        ).fetchall()
        cats_con_subs.append({'cat': dict(cat), 'subs': [dict(s) for s in subs]})

    db.close()
    return render_template('categorias/index.html',
        cats_con_subs=cats_con_subs, colores=COLORES_PRESET)


@bp.route('/nueva', methods=['POST'])
def nueva_categoria():
    nombre = request.form.get('nombre', '').strip()
    color = request.form.get('color', '#6c757d').strip()
    tipo = request.form.get('tipo', 'gasto').strip()
    requiere_proveedor = 1 if request.form.get('requiere_proveedor') == '1' else 0
    clasificacion = request.form.get('clasificacion', 'gasto').strip() if tipo in ('gasto', 'ambos') else 'gasto'

    if not nombre:
        flash('El nombre de la categoría es obligatorio.', 'danger')
        return redirect(url_for('categorias.index'))

    db = get_db()
    existe = db.execute(
        'SELECT id FROM categorias WHERE nombre ILIKE ?', (nombre,)
    ).fetchone()
    if existe:
        flash('Ya existe una categoría con ese nombre.', 'warning')
        db.close()
        return redirect(url_for('categorias.index'))

    db.execute(
        'INSERT INTO categorias (nombre, color, tipo, requiere_proveedor, clasificacion) VALUES (?, ?, ?, ?, ?)',
        (nombre, color, tipo, requiere_proveedor, clasificacion)
    )
    db.commit()
    db.close()
    flash(f'Categoría "{nombre}" creada correctamente.', 'success')
    return redirect(url_for('categorias.index'))


@bp.route('/<int:cat_id>/editar', methods=['POST'])
def editar_categoria(cat_id):
    nombre = request.form.get('nombre', '').strip()
    color = request.form.get('color', '#6c757d').strip()
    tipo = request.form.get('tipo', 'gasto').strip()
    requiere_proveedor = 1 if request.form.get('requiere_proveedor') == '1' else 0
    clasificacion = request.form.get('clasificacion', 'gasto').strip() if tipo in ('gasto', 'ambos') else 'gasto'

    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('categorias.index'))

    db = get_db()
    db.execute(
        'UPDATE categorias SET nombre=?, color=?, tipo=?, requiere_proveedor=?, clasificacion=? WHERE id=?',
        (nombre, color, tipo, requiere_proveedor, clasificacion, cat_id)
    )
    db.commit()
    db.close()
    flash('Categoría actualizada.', 'success')
    return redirect(url_for('categorias.index'))


@bp.route('/<int:cat_id>/toggle', methods=['POST'])
def toggle_categoria(cat_id):
    db = get_db()
    cat = db.execute('SELECT activo FROM categorias WHERE id = ?', (cat_id,)).fetchone()
    if cat:
        nuevo = 0 if cat['activo'] else 1
        db.execute('UPDATE categorias SET activo = ? WHERE id = ?', (nuevo, cat_id))
        db.commit()
        msg = 'Categoría activada.' if nuevo else 'Categoría desactivada.'
        flash(msg, 'success' if nuevo else 'warning')
    db.close()
    return redirect(url_for('categorias.index'))


@bp.route('/<int:cat_id>/eliminar', methods=['POST'])
def eliminar_categoria(cat_id):
    db = get_db()
    en_uso = db.execute(
        'SELECT COUNT(*) as c FROM gastos WHERE categoria_id = ?', (cat_id,)
    ).fetchone()['c']
    en_uso_ingresos = db.execute(
        'SELECT COUNT(*) as c FROM ingresos WHERE categoria_id = ?', (cat_id,)
    ).fetchone()['c']
    if en_uso or en_uso_ingresos:
        flash('No se puede eliminar: la categoría tiene gastos o ingresos asociados. Podés desactivarla.', 'danger')
        db.close()
        return redirect(url_for('categorias.index'))
    db.execute('DELETE FROM subcategorias WHERE categoria_id = ?', (cat_id,))
    db.execute('DELETE FROM categorias WHERE id = ?', (cat_id,))
    db.commit()
    db.close()
    flash('Categoría eliminada.', 'success')
    return redirect(url_for('categorias.index'))


@bp.route('/<int:cat_id>/subcategoria/nueva', methods=['POST'])
def nueva_subcategoria(cat_id):
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash('El nombre de la subcategoría es obligatorio.', 'danger')
        return redirect(url_for('categorias.index'))

    db = get_db()
    existe = db.execute(
        'SELECT id FROM subcategorias WHERE categoria_id = ? AND nombre ILIKE ?',
        (cat_id, nombre)
    ).fetchone()
    if existe:
        flash('Ya existe una subcategoría con ese nombre en esta categoría.', 'warning')
        db.close()
        return redirect(url_for('categorias.index'))

    db.execute(
        'INSERT INTO subcategorias (categoria_id, nombre) VALUES (?, ?)',
        (cat_id, nombre)
    )
    db.commit()
    db.close()
    flash(f'Subcategoría "{nombre}" creada correctamente.', 'success')
    return redirect(url_for('categorias.index'))


@bp.route('/subcategoria/<int:sub_id>/editar', methods=['POST'])
def editar_subcategoria(sub_id):
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('categorias.index'))
    db = get_db()
    db.execute('UPDATE subcategorias SET nombre = ? WHERE id = ?', (nombre, sub_id))
    db.commit()
    db.close()
    flash('Subcategoría actualizada.', 'success')
    return redirect(url_for('categorias.index'))


@bp.route('/subcategoria/<int:sub_id>/toggle', methods=['POST'])
def toggle_subcategoria(sub_id):
    db = get_db()
    sub = db.execute('SELECT activo FROM subcategorias WHERE id = ?', (sub_id,)).fetchone()
    if sub:
        nuevo = 0 if sub['activo'] else 1
        db.execute('UPDATE subcategorias SET activo = ? WHERE id = ?', (nuevo, sub_id))
        db.commit()
        msg = 'Subcategoría activada.' if nuevo else 'Subcategoría desactivada.'
        flash(msg, 'success' if nuevo else 'warning')
    db.close()
    return redirect(url_for('categorias.index'))


@bp.route('/subcategoria/<int:sub_id>/eliminar', methods=['POST'])
def eliminar_subcategoria(sub_id):
    db = get_db()
    en_uso = db.execute(
        'SELECT COUNT(*) as c FROM gastos WHERE subcategoria_id = ?', (sub_id,)
    ).fetchone()['c']
    if en_uso:
        flash('No se puede eliminar: hay gastos asociados a esta subcategoría. Podés desactivarla.', 'danger')
        db.close()
        return redirect(url_for('categorias.index'))
    db.execute('DELETE FROM subcategorias WHERE id = ?', (sub_id,))
    db.commit()
    db.close()
    flash('Subcategoría eliminada.', 'success')
    return redirect(url_for('categorias.index'))
