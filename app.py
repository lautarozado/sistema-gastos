from flask import Flask
from database import init_db, get_config


def create_app():
    app = Flask(__name__)
    app.secret_key = 'clave-secreta-sistema-gastos-2024'

    with app.app_context():
        init_db()

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

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(gastos_bp)
    app.register_blueprint(ingresos_bp)
    app.register_blueprint(movimientos_bp)
    app.register_blueprint(categorias_bp)
    app.register_blueprint(proveedores_bp)
    app.register_blueprint(locales_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(configuracion_bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
