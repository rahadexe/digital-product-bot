import asyncio

from app.services.catalog import CatalogService


class _Connection:
    def __init__(self):
        self.query = ""

    async def fetch(self, query, *args):
        self.query = query
        return [{"id": 2, "name": "Facebook"}]


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Database:
    def __init__(self, connection):
        self.connection_context = _ConnectionContext(connection)

    def connect(self):
        return self.connection_context


def test_available_category_query_excludes_empty_categories():
    connection = _Connection()
    catalog = CatalogService(_Database(connection))

    categories = asyncio.run(catalog.categories(active_only=True, with_products=True))

    assert [category["name"] for category in categories] == ["Facebook"]
    assert "WHERE is_active = 1 AND EXISTS" in connection.query
    assert "p.category_id = categories.id AND p.is_active = 1" in connection.query


def test_products_query_orders_by_is_pinned_first():
    connection = _Connection()
    catalog = CatalogService(_Database(connection))

    asyncio.run(catalog.products(category_id=1, active_only=True))

    assert "ORDER BY is_pinned DESC" in connection.query

