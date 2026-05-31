import os
from flask import Flask
from database import init_db, get_config


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'clave-secreta-sistema-gastos-2024')
    app.debug = os.environ.get('FLASK_DEBUG', '0') == '1'

    with app.app_context():
        init_db()

    # ── Filtros de fecha: soportan tanto datetime.date/datetime como strings YYYY-MM-DD
    @app.template_filter('fmt_date')
    def fmt_date(value):
        if value is None:
            return '—'
        if hasattr(value, 'strftime'):
            return value.strftime('%d/%m/%Y')
        s = str(value)[:10]
        parts = s.split('-')
        return f'{parts[2]}/{parts[1]}/{parts[0]}' if len(parts) == 3 else s

    @app.template_filter('fmt_datetime')
    def fmt_datetime(value):
        if value is None:
            return '—'
        if hasattr(value, 'strftime'):
            return value.strftime('%d/%m/%Y %H:%M')
        return str(value)[:16]

    # Context processor: disponible en todos los templates
    @app.context_processor
    def inject_globals():
        config = get_config()
        return {
            'app_config': config,
            'nombre_negocio': config.get('nombre_negocio', 'Mi Negocio'),
            'moneda': config.get('moneda_simbolo', '$'),
        }

    # Blueprints
    from blueprints.dashboard import bp as dashboard_bp
    from blueprints.gastos import bp as gastos_bp
    from blueprints.ingresos import bp as ingresos_bp
    from blueprints.movimientos import bp as movimientos_bp
    from blueprints.categorias import bp as categorias_bp
    from blueprints.proveedores import bp as proveedores_bp
    from blueprints.locales import bp as locales_bp
    from blueprints.reportes import bp as reportes_bp
    from blueprints.configuracion import bp as configuracion_bp
    from blueprints.cheques import bp as cheques_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(gastos_bp)
    app.register_blueprint(ingresos_bp)
    app.register_blueprint(movimientos_bp)
    app.register_blueprint(categorias_bp)
    app.register_blueprint(proveedores_bp)
    app.register_blueprint(locales_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(configuracion_bp)
    app.register_blueprint(cheques_bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
