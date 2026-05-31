-- =============================================
-- Sistema de Gastos - LibreriaCentro
-- Ejecutar en: Supabase → SQL Editor
-- =============================================

CREATE TABLE IF NOT EXISTS configuracion (
    id SERIAL PRIMARY KEY,
    clave TEXT NOT NULL UNIQUE,
    valor TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS locales (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categorias (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT DEFAULT 'gasto',
    color TEXT DEFAULT '#6c757d',
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subcategorias (
    id SERIAL PRIMARY KEY,
    categoria_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id)
);

CREATE TABLE IF NOT EXISTS proveedores (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    telefono TEXT,
    observaciones TEXT,
    activo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gastos (
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
);

CREATE TABLE IF NOT EXISTS ingresos (
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
);

CREATE TABLE IF NOT EXISTS detalle_ingresos_medios (
    id SERIAL PRIMARY KEY,
    ingreso_id INTEGER NOT NULL,
    medio TEXT NOT NULL,
    monto REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (ingreso_id) REFERENCES ingresos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cheques (
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
);

-- Datos iniciales de configuración
INSERT INTO configuracion (clave, valor) VALUES
    ('nombre_negocio', 'Mi Negocio'),
    ('moneda_simbolo', '$')
ON CONFLICT (clave) DO NOTHING;

-- Verificación: mostrar tablas creadas
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
