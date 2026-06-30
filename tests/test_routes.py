"""
Tests de humo: todos los endpoints GET deben devolver 200 (o redirect válido).
"""
import pytest


GET_ROUTES = [
    '/',
    '/gastos/',
    '/gastos/?fecha_desde=&fecha_hasta=',          # "Ver todos"
    '/gastos/?fecha_desde=2026-06-01&fecha_hasta=2026-06-30',
    '/gastos/nuevo',
    '/gastos/2/editar',
    '/gastos/3/desde-recurrente',
    '/gastos/recurrentes',
    '/gastos/exportar-csv',
    '/cheques/',
    '/cheques/nuevo',
    '/cheques/1/editar',
    '/cheques/agenda',
    '/categorias/',
    '/proveedores/',
    '/proveedores/?buscar=alfa',
    '/locales/',
    '/movimientos/',
    '/movimientos/?periodo=hoy',
    '/movimientos/?periodo=7d',
    '/movimientos/?periodo=todo',
    '/ingresos/',
    '/ingresos/nuevo',
    '/reportes/',
    '/configuracion/',
]


@pytest.mark.parametrize('url', GET_ROUTES)
def test_get_returns_ok(client, url):
    rv = client.get(url)
    assert rv.status_code in (200, 302), f"{url} → HTTP {rv.status_code}"
