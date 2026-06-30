from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db

bp = Blueprint('configuracion', __name__, url_prefix='/configuracion')


@bp.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()

    CLAVES = [
        'nombre_negocio', 'moneda_simbolo', 'cuit', 'condicion_iva',
        'direccion', 'tipo_cambio_usd',
    ]

    if request.method == 'POST':
        nombre_negocio = request.form.get('nombre_negocio', '').strip()
        if not nombre_negocio:
            flash('El nombre del negocio es obligatorio.', 'danger')
            db.close()
            return redirect(url_for('configuracion.index'))

        for clave in CLAVES:
            valor = request.form.get(clave, '').strip()
            if clave == 'moneda_simbolo' and not valor:
                valor = '$'
            db.execute(
                '''INSERT INTO configuracion (clave, valor, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = CURRENT_TIMESTAMP''',
                (clave, valor)
            )
        db.commit()
        db.close()
        flash('Configuración guardada correctamente.', 'success')
        return redirect(url_for('configuracion.index'))

    config_rows = db.execute('SELECT clave, valor FROM configuracion').fetchall()
    config = {r['clave']: r['valor'] for r in config_rows}

    # Stats generales
    total_locales = db.execute('SELECT COUNT(*) as c FROM locales WHERE activo = 1').fetchone()['c']
    total_categorias = db.execute('SELECT COUNT(*) as c FROM categorias WHERE activo = 1').fetchone()['c']
    total_proveedores = db.execute('SELECT COUNT(*) as c FROM proveedores WHERE activo = 1').fetchone()['c']
    total_gastos = db.execute('SELECT COUNT(*) as c FROM gastos WHERE anulado = 0').fetchone()['c']
    total_ingresos = db.execute('SELECT COUNT(*) as c FROM ingresos WHERE anulado = 0').fetchone()['c']
    db.close()

    stats = {
        'locales': total_locales,
        'categorias': total_categorias,
        'proveedores': total_proveedores,
        'gastos': total_gastos,
        'ingresos': total_ingresos,
    }

    return render_template('configuracion/index.html', config=config, stats=stats)
