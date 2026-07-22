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

# Cheques
BANCOS = ['Banco Nación', 'Banco Provincia', 'Banco Galicia', 'Santander',
          'BBVA', 'Macro', 'Credicoop', 'Otro']

ESTADOS_CHEQUE = [
    ('pendiente', 'Pendiente'),
    ('debitado',  'Debitado'),
    ('rechazado', 'Rechazado'),
    ('anulado',   'Anulado'),
]

PLAZOS_CHEQUE = [30, 60, 90]


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
            es_fija INTEGER DEFAULT 0,
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
        '''CREATE TABLE IF NOT EXISTS cheques (
            id SERIAL PRIMARY KEY,
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
            FOREIGN KEY (local_id) REFERENCES locales(id),
            FOREIGN KEY (gasto_id) REFERENCES gastos(id)
        )''',
    ]

    for stmt in tablas:
        db.execute(stmt)

    # Migraciones idempotentes
    migraciones = [
        'ALTER TABLE ingresos ADD COLUMN IF NOT EXISTS categoria_id INTEGER',
        # Comprobantes en gastos
        'ALTER TABLE gastos ADD COLUMN IF NOT EXISTS comprobante_path TEXT',
        # Gastos recurrentes
        'ALTER TABLE gastos ADD COLUMN IF NOT EXISTS es_recurrente INTEGER DEFAULT 0',
        'ALTER TABLE gastos ADD COLUMN IF NOT EXISTS frecuencia TEXT',
        'ALTER TABLE gastos ADD COLUMN IF NOT EXISTS proxima_fecha DATE',
        # Moneda por transacción (ARS / USD)
        "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS moneda TEXT DEFAULT 'ARS'",
        "ALTER TABLE ingresos ADD COLUMN IF NOT EXISTS moneda TEXT DEFAULT 'ARS'",
        # Flag configurable: categoría requiere proveedor
        'ALTER TABLE categorias ADD COLUMN IF NOT EXISTS requiere_proveedor INTEGER DEFAULT 0',
        # Clasificación contable de la categoría: gasto (operativo) o costo (directo)
        "ALTER TABLE categorias ADD COLUMN IF NOT EXISTS clasificacion TEXT DEFAULT 'gasto'",
        # Subcategoría fija (Sí/No) para distinguir gastos fijos de variables
        'ALTER TABLE subcategorias ADD COLUMN IF NOT EXISTS es_fija INTEGER DEFAULT 0',
    ]
    for m in migraciones:
        db.execute(m)

    # Actualizar nombre del negocio
    db.execute("UPDATE configuracion SET valor = 'Libreria Centro' WHERE clave = 'nombre_negocio'")

    # Backfill: registros previos sin moneda → ARS
    db.execute("UPDATE gastos SET moneda = 'ARS' WHERE moneda IS NULL")
    db.execute("UPDATE ingresos SET moneda = 'ARS' WHERE moneda IS NULL")
    db.execute("UPDATE gastos SET es_recurrente = 0 WHERE es_recurrente IS NULL")
    # Backfill: categorías cuyo nombre contenía "proveedor" pasan a tener el flag activo
    db.execute("UPDATE categorias SET requiere_proveedor = 1 WHERE nombre ILIKE '%proveedor%' AND requiere_proveedor = 0")
    db.execute("UPDATE categorias SET clasificacion = 'gasto' WHERE clasificacion IS NULL")
    # Subcategorías previas quedan como "no fijas" por defecto (nunca en estado nulo)
    db.execute("UPDATE subcategorias SET es_fija = 0 WHERE es_fija IS NULL")

    defaults = [
        ('nombre_negocio', 'Libreria Centro'),
        ('moneda_simbolo', '$'),
    ]
    for clave, valor in defaults:
        db.execute(
            'INSERT INTO configuracion (clave, valor) VALUES (?, ?) ON CONFLICT (clave) DO NOTHING',
            (clave, valor)
        )

    # Crear categorías iniciales de ingreso solo si no existe ninguna
    count_ing = db.execute(
        "SELECT COUNT(*) as c FROM categorias WHERE tipo IN ('ingreso', 'ambos')"
    ).fetchone()['c']
    if count_ing == 0:
        for nombre, color in [
            ('Ventas mostrador', '#10b981'),
            ('Ventas online',    '#4361ee'),
            ('Transferencias',   '#06b6d4'),
            ('Otros ingresos',   '#64748b'),
        ]:
            db.execute(
                "INSERT INTO categorias (nombre, tipo, color) VALUES (?, 'ingreso', ?)",
                (nombre, color)
            )

    db.commit()
    db.close()


def get_config():
    db = get_db()
    rows = db.execute('SELECT clave, valor FROM configuracion').fetchall()
    db.close()
    return {row['clave']: row['valor'] for row in rows}


def format_currency(amount, symbol='$'):  # noqa: E305
    if amount is None:
        return f'{symbol} 0,00'
    return f'{symbol} {amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
