import psycopg2
import psycopg2.extras
import os
from urllib.parse import urlparse, unquote

def _get_db_params():
    """Parsea DATABASE_URL y devuelve los parámetros de conexión como dict.
    Pasar la contraseña como argumento separado evita problemas de URL-encoding."""
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        raise RuntimeError("La variable de entorno DATABASE_URL no está configurada.")
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    parsed = urlparse(url)
    return {
        'host':     parsed.hostname,
        'port':     parsed.port or 5432,
        'dbname':   parsed.path.lstrip('/'),
    'user':     unquote(parsed.username) if parsed.username else None,
'password': unquote(parsed.password) if parsed.password else None,  # urlparse decodifica %xx automáticamente
        'sslmode':  'require',
        'connect_timeout': 10,
    }

MEDIOS_PAGO = ['Efectivo', 'Transferencia', 'Tarjeta de crédito', 'Tarjeta de débito', 'Mercado Pago', 'Otro']

MEDIOS_COBRO = [
    ('efectivo', 'Efectivo'),
    ('transferencia', 'Transferencia'),
    ('tarjeta', 'Tarjeta'),
    ('mercado_pago', 'Mercado Pago'),
    ('otro', 'Otro'),
]


class PGCursor:
    """Envuelve el cursor de psycopg2 para imitar la interfaz de sqlite3."""

    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn

    def fetchall(self):
        try:
            rows = self._cur.fetchall()
            return rows if rows else []
        except Exception:
            return []

    def fetchone(self):
        try:
            return self._cur.fetchone()
        except Exception:
            return None

    @property
    def lastrowid(self):
        """Devuelve el id del último registro insertado usando lastval()."""
        try:
            raw_cur = self._conn.cursor()
            raw_cur.execute("SELECT lastval()")
            result = raw_cur.fetchone()
            return result[0] if result else None
        except Exception:
            return None


class PGConnection:
    """Envuelve la conexión de psycopg2 para imitar la interfaz de sqlite3."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        # Convertir placeholders ? de SQLite a %s de PostgreSQL
        pg_sql = sql.replace('?', '%s')
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_sql, params if params else None)
        return PGCursor(cur, self._conn)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    conn = psycopg2.connect(**_get_db_params())
    return PGConnection(conn)


def init_db():
    db = get_db()

    tablas = [
        '''CREATE TABLE IF NOT EXISTS configuracion (
            id SERIAL PRIMARY KEY,
            clave TEXT NOT NULL UNIQUE,
            valor TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS locales (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            activo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS categorias (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            tipo TEXT DEFAULT 'gasto',
            color TEXT DEFAULT '#6c757d',
            activo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS subcategorias (
            id SERIAL PRIMARY KEY,
            categoria_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id)
        )''',
        '''CREATE TABLE IF NOT EXISTS proveedores (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono TEXT,
            observaciones TEXT,
            activo INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (local_id) REFERENCES locales(id),
            FOREIGN KEY (categoria_id) REFERENCES categorias(id),
            FOREIGN KEY (subcategoria_id) REFERENCES subcategorias(id),
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
        )''',
        '''CREATE TABLE IF NOT EXISTS ingresos (
            id SERIAL PRIMARY KEY,
            fecha_desde DATE NOT NULL,
            fecha_hasta DATE NOT NULL,
            local_id INTEGER NOT NULL,
            total REAL NOT NULL,
            observaciones TEXT,
            anulado INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (local_id) REFERENCES locales(id)
        )''',
        '''CREATE TABLE IF NOT EXISTS detalle_ingresos_medios (
            id SERIAL PRIMARY KEY,
            ingreso_id INTEGER NOT NULL,
            medio TEXT NOT NULL,
            monto REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (ingreso_id) REFERENCES ingresos(id) ON DELETE CASCADE
        )''',
    ]

    for stmt in tablas:
        db.execute(stmt)

    defaults = [
        ('nombre_negocio', 'Mi Negocio'),
        ('moneda_simbolo', '$'),
    ]
    for clave, valor in defaults:
        db.execute(
            'INSERT INTO configuracion (clave, valor) VALUES (?, ?) ON CONFLICT (clave) DO NOTHING',
            (clave, valor)
        )

    db.commit()
    db.close()


def get_config():
    db = get_db()
    rows = db.execute('SELECT clave, valor FROM configuracion').fetchall()
    db.close()
    return {row['clave']: row['valor'] for row in rows}


def format_currency(amount, symbol='$'):
    if amount is None:
        return f'{symbol} 0,00'
    return f'{symbol} {amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
