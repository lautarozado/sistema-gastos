"""
Test suite para sistema-gastos.

Usa SQLite en memoria en lugar de Supabase/PostgreSQL.
La BD de producción NO se toca en ningún momento.
"""
import os
import re
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('SECRET_KEY', 'test-secret')


# ── SQLite Adapter ─────────────────────────────────────────────────────────────

class _SQLiteCursor:
    """Cursor que presenta la misma interfaz que PGCursor pero trabaja con SQLite."""

    def __init__(self, conn):
        self._conn = conn
        self._cur = None

    def execute(self, sql, params=None):
        # Traducciones de sintaxis PostgreSQL → SQLite
        sql = sql.replace('%s', '?')
        sql = re.sub(r'\bILIKE\b', 'LIKE', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bNULLS\s+(?:LAST|FIRST)\b', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'lastval\(\)', 'last_insert_rowid()', sql)
        sql = sql.replace("CURRENT_DATE + INTERVAL '7 days'", "date('now','+7 days')")
        sql = sql.replace("CURRENT_DATE - INTERVAL", "date('now','-")  # best-effort
        self._cur = self._conn.execute(sql, params or [])
        return self

    def fetchall(self):
        if self._cur is None:
            return []
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in self._cur.description]
        return [dict(zip(cols, r)) for r in rows]

    def fetchone(self):
        if self._cur is None:
            return None
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._cur.description]
        return dict(zip(cols, row))

    @property
    def lastrowid(self):
        return self._cur.lastrowid if self._cur else None


class _SQLiteConn:
    """Conexión que presenta la misma interfaz que PGConnection pero usa SQLite."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self, cursor_factory=None):
        return _SQLiteCursor(self._conn)

    def execute(self, sql, params=None):
        return _SQLiteCursor(self._conn).execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        pass  # mantener la conexión abierta durante todo el test


# ── Schema SQLite ──────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS configuracion (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT NOT NULL UNIQUE,
    valor TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS locales (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS categorias (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    tipo TEXT DEFAULT 'gasto',
    color TEXT DEFAULT '#6c757d',
    activo INTEGER DEFAULT 1,
    requiere_proveedor INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS subcategorias (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS proveedores (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    observaciones TEXT,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS gastos (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    local_id INTEGER NOT NULL,
    categoria_id INTEGER NOT NULL,
    subcategoria_id INTEGER,
    proveedor_id INTEGER,
    descripcion TEXT,
    monto REAL NOT NULL,
    medio_pago TEXT,
    observaciones TEXT,
    anulado INTEGER DEFAULT 0,
    comprobante_path TEXT,
    es_recurrente INTEGER DEFAULT 0,
    frecuencia TEXT,
    proxima_fecha DATE,
    moneda TEXT DEFAULT 'ARS',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ingresos (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_desde DATE NOT NULL,
    fecha_hasta DATE NOT NULL,
    local_id INTEGER NOT NULL,
    categoria_id INTEGER,
    total REAL NOT NULL,
    observaciones TEXT,
    anulado INTEGER DEFAULT 0,
    moneda TEXT DEFAULT 'ARS',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS detalle_ingresos_medios (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ingreso_id INTEGER NOT NULL,
    medio TEXT NOT NULL,
    monto REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cheques (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT,
    banco TEXT DEFAULT 'Banco Nación',
    tipo TEXT DEFAULT 'emitido',
    beneficiario TEXT,
    proveedor_id INTEGER,
    local_id INTEGER,
    gasto_id INTEGER,
    monto REAL NOT NULL,
    fecha_emision DATE NOT NULL,
    fecha_pago DATE NOT NULL,
    plazo_dias INTEGER,
    estado TEXT DEFAULT 'pendiente',
    moneda TEXT DEFAULT 'ARS',
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _seed(conn):
    conn.executescript("""
        INSERT INTO configuracion (clave, valor) VALUES ('nombre_negocio', 'Test Negocio');
        INSERT INTO configuracion (clave, valor) VALUES ('moneda_simbolo', '$');

        INSERT INTO locales (id, nombre, activo) VALUES (1, 'Local A', 1);
        INSERT INTO locales (id, nombre, activo) VALUES (2, 'Local B', 1);

        -- categorías: gasto sin flag, gasto CON flag (requiere proveedor), ingreso
        INSERT INTO categorias (id, nombre, tipo, activo, requiere_proveedor) VALUES (1, 'Servicios', 'gasto', 1, 0);
        INSERT INTO categorias (id, nombre, tipo, activo, requiere_proveedor) VALUES (2, 'Proveedor Insumos', 'gasto', 1, 1);
        INSERT INTO categorias (id, nombre, tipo, activo, requiere_proveedor) VALUES (3, 'Ventas', 'ingreso', 1, 0);
        INSERT INTO categorias (id, nombre, tipo, activo, requiere_proveedor) VALUES (4, 'Ambos Test', 'ambos', 1, 0);

        INSERT INTO proveedores (id, nombre, telefono, activo) VALUES (1, 'Proveedor Alfa', '11 1234-5678', 1);
        INSERT INTO proveedores (id, nombre, telefono, activo) VALUES (2, 'Proveedor Beta', NULL, 1);

        -- gasto normal (sin cheques vinculados)
        INSERT INTO gastos (id, fecha, local_id, categoria_id, monto, moneda, anulado)
            VALUES (1, '2026-06-01', 1, 1, 1000.00, 'ARS', 0);

        -- gasto CON cheque vinculado (no se puede eliminar)
        INSERT INTO gastos (id, fecha, local_id, categoria_id, monto, moneda, anulado)
            VALUES (2, '2026-06-05', 1, 1, 500.00, 'ARS', 0);

        -- gasto recurrente mensual
        INSERT INTO gastos (id, fecha, local_id, categoria_id, monto, moneda, anulado,
                            es_recurrente, frecuencia, proxima_fecha)
            VALUES (3, '2026-06-01', 1, 1, 200.00, 'ARS', 0, 1, 'mensual', '2026-07-01');

        -- gasto en USD
        INSERT INTO gastos (id, fecha, local_id, categoria_id, monto, moneda, anulado)
            VALUES (4, '2026-06-10', 2, 1, 100.00, 'USD', 0);

        -- ingreso con categoria
        INSERT INTO ingresos (id, fecha_desde, fecha_hasta, local_id, categoria_id, total, moneda, anulado)
            VALUES (1, '2026-06-01', '2026-06-30', 1, 3, 5000.00, 'ARS', 0);

        INSERT INTO detalle_ingresos_medios (ingreso_id, medio, monto)
            VALUES (1, 'efectivo', 2000.00);
        INSERT INTO detalle_ingresos_medios (ingreso_id, medio, monto)
            VALUES (1, 'transferencia', 3000.00);

        -- cheque emitido vinculado al gasto 2
        INSERT INTO cheques (id, numero, monto, fecha_emision, fecha_pago, tipo, estado, gasto_id, local_id, proveedor_id)
            VALUES (1, 'CH001', 500.00, '2026-06-05', '2026-07-05', 'emitido', 'pendiente', 2, 1, 1);

        -- cheque recibido (sin gasto)
        INSERT INTO cheques (id, numero, monto, fecha_emision, fecha_pago, tipo, estado, local_id, proveedor_id)
            VALUES (2, 'CH002', 800.00, '2026-06-10', '2026-08-10', 'recibido', 'pendiente', 1, 2);
    """)
    conn.commit()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def sqlite_conn():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.executescript(_SCHEMA)
    _seed(conn)
    yield conn
    conn.close()


@pytest.fixture(scope='session')
def app(sqlite_conn):
    """Flask app usando SQLite en lugar de Supabase."""
    pg_conn = _SQLiteConn(sqlite_conn)

    def mock_get_db():
        return pg_conn

    def mock_get_config():
        return {'nombre_negocio': 'Test Negocio', 'moneda_simbolo': '$'}

    # Parchar psycopg2.connect para que init_db() no falle al arrancar la app
    mock_psycopg2_conn = MagicMock()
    mock_psycopg2_conn.cursor.return_value.__enter__ = MagicMock()
    mock_psycopg2_conn.cursor.return_value.__exit__ = MagicMock()

    modules_to_patch = [
        'blueprints.gastos.get_db',
        'blueprints.cheques.get_db',
        'blueprints.categorias.get_db',
        'blueprints.proveedores.get_db',
        'blueprints.locales.get_db',
        'blueprints.movimientos.get_db',
        'blueprints.ingresos.get_db',
        'blueprints.configuracion.get_db',
        'blueprints.dashboard.get_db',
        'blueprints.reportes.get_db',
    ]

    patchers = [patch(m, side_effect=mock_get_db) for m in modules_to_patch]
    patchers.append(patch('database.get_config', side_effect=mock_get_config))
    patchers.append(patch('database.init_db', return_value=None))
    patchers.append(patch('psycopg2.connect', return_value=MagicMock()))

    for p in patchers:
        p.start()

    try:
        from app import create_app
        flask_app = create_app()
        flask_app.config['TESTING'] = True
        flask_app.config['WTF_CSRF_ENABLED'] = False
        yield flask_app
    finally:
        for p in patchers:
            p.stop()


@pytest.fixture
def client(app):
    return app.test_client()
