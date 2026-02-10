"""
Database Tests

Tests for database backend and middleware using MockDatabaseBackend.
"""

import pytest

from vel_harness.backends.database import (
    DatabaseConfig,
    MockDatabaseBackend,
    QueryResult,
    is_write_query,
)
from vel_harness.middleware.database import DatabaseMiddleware


# Fixtures


@pytest.fixture
def mock_db() -> MockDatabaseBackend:
    """Create a mock database backend with sample data."""
    db = MockDatabaseBackend(readonly=False)

    # Add users table
    db.add_table(
        "users",
        columns=["id", "name", "email", "active"],
        rows=[
            [1, "Alice", "alice@example.com", True],
            [2, "Bob", "bob@example.com", True],
            [3, "Charlie", "charlie@example.com", False],
        ],
    )

    # Add products table
    db.add_table(
        "products",
        columns=["id", "name", "price", "category"],
        rows=[
            [1, "Widget", 9.99, "electronics"],
            [2, "Gadget", 19.99, "electronics"],
            [3, "Gizmo", 14.99, "tools"],
        ],
    )

    # Add orders table
    db.add_table(
        "orders",
        columns=["id", "user_id", "product_id", "quantity"],
        rows=[
            [1, 1, 1, 2],
            [2, 1, 2, 1],
            [3, 2, 3, 5],
        ],
    )

    return db


@pytest.fixture
def readonly_mock_db() -> MockDatabaseBackend:
    """Create a readonly mock database."""
    db = MockDatabaseBackend(readonly=True)
    db.add_table("test", columns=["id", "value"], rows=[[1, "data"]])
    return db


@pytest.fixture
def db_middleware(mock_db: MockDatabaseBackend) -> DatabaseMiddleware:
    """Create database middleware with mock backend."""
    return DatabaseMiddleware(backend=mock_db, readonly=False)


@pytest.fixture
def readonly_middleware(readonly_mock_db: MockDatabaseBackend) -> DatabaseMiddleware:
    """Create readonly database middleware."""
    return DatabaseMiddleware(backend=readonly_mock_db, readonly=True)


# is_write_query Tests


class TestIsWriteQuery:
    """Tests for write query detection."""

    def test_select_is_read(self) -> None:
        """SELECT queries are read-only."""
        assert is_write_query("SELECT * FROM users") is False
        assert is_write_query("select id, name from users") is False
        assert is_write_query("  SELECT * FROM users WHERE id = 1") is False

    def test_insert_is_write(self) -> None:
        """INSERT queries are writes."""
        assert is_write_query("INSERT INTO users (name) VALUES ('test')") is True
        assert is_write_query("insert into users values (1, 'a', 'b')") is True

    def test_update_is_write(self) -> None:
        """UPDATE queries are writes."""
        assert is_write_query("UPDATE users SET name = 'test'") is True
        assert is_write_query("  update users set active = false") is True

    def test_delete_is_write(self) -> None:
        """DELETE queries are writes."""
        assert is_write_query("DELETE FROM users WHERE id = 1") is True
        assert is_write_query("delete from users") is True

    def test_ddl_is_write(self) -> None:
        """DDL queries are writes."""
        assert is_write_query("CREATE TABLE test (id int)") is True
        assert is_write_query("DROP TABLE test") is True
        assert is_write_query("ALTER TABLE test ADD COLUMN name text") is True
        assert is_write_query("TRUNCATE users") is True


# QueryResult Tests


class TestQueryResult:
    """Tests for QueryResult dataclass."""

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = QueryResult(
            columns=["id", "name"],
            rows=[[1, "Alice"], [2, "Bob"]],
            row_count=2,
            query="SELECT * FROM users",
        )

        d = result.to_dict()
        assert d["columns"] == ["id", "name"]
        assert d["row_count"] == 2
        assert len(d["rows"]) == 2

    def test_to_dict_with_error(self) -> None:
        """Test result with error."""
        result = QueryResult(
            columns=[],
            rows=[],
            row_count=0,
            query="INVALID SQL",
            error="Syntax error",
        )

        d = result.to_dict()
        assert d["error"] == "Syntax error"

    def test_to_markdown_table(self) -> None:
        """Test markdown table formatting."""
        result = QueryResult(
            columns=["id", "name"],
            rows=[[1, "Alice"], [2, "Bob"]],
            row_count=2,
            query="SELECT * FROM users",
        )

        md = result.to_markdown_table()
        assert "| id | name |" in md
        assert "| 1 | Alice |" in md
        assert "| 2 | Bob |" in md

    def test_to_markdown_table_truncation(self) -> None:
        """Test markdown table with row truncation."""
        rows = [[i, f"User{i}"] for i in range(100)]
        result = QueryResult(
            columns=["id", "name"],
            rows=rows,
            row_count=100,
            query="SELECT * FROM users",
        )

        md = result.to_markdown_table(max_rows=10)
        assert "(90 more rows...)" in md

    def test_to_markdown_error(self) -> None:
        """Test markdown with error."""
        result = QueryResult(
            columns=[],
            rows=[],
            row_count=0,
            query="INVALID",
            error="Bad query",
        )

        md = result.to_markdown_table()
        assert "Error: Bad query" in md


# MockDatabaseBackend Tests


class TestMockDatabaseBackend:
    """Tests for MockDatabaseBackend."""

    @pytest.mark.asyncio
    async def test_select_all(self, mock_db: MockDatabaseBackend) -> None:
        """Test SELECT * query."""
        result = await mock_db.execute("SELECT * FROM users")

        assert result.error is None
        assert result.columns == ["id", "name", "email", "active"]
        assert result.row_count == 3

    @pytest.mark.asyncio
    async def test_select_columns(self, mock_db: MockDatabaseBackend) -> None:
        """Test SELECT with specific columns."""
        result = await mock_db.execute("SELECT name, email FROM users")

        assert result.error is None
        assert result.columns == ["name", "email"]
        assert result.row_count == 3

    @pytest.mark.asyncio
    async def test_select_nonexistent_table(self, mock_db: MockDatabaseBackend) -> None:
        """Test SELECT from nonexistent table."""
        result = await mock_db.execute("SELECT * FROM nonexistent")

        assert result.error is not None
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_insert(self, mock_db: MockDatabaseBackend) -> None:
        """Test INSERT query."""
        result = await mock_db.execute(
            "INSERT INTO users (id, name, email, active) VALUES ($1, $2, $3, $4)",
            [4, "Dave", "dave@example.com", True],
        )

        assert result.error is None
        assert result.affected_rows == 1

        # Verify inserted
        select_result = await mock_db.execute("SELECT * FROM users")
        assert select_result.row_count == 4

    @pytest.mark.asyncio
    async def test_readonly_blocks_write(
        self, readonly_mock_db: MockDatabaseBackend
    ) -> None:
        """Test that readonly mode blocks writes."""
        result = await readonly_mock_db.execute(
            "INSERT INTO test (id, value) VALUES (2, 'new')"
        )

        assert result.error is not None
        assert "readonly" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_tables(self, mock_db: MockDatabaseBackend) -> None:
        """Test listing tables."""
        result = await mock_db.get_tables()

        assert result.error is None
        table_names = [row[0] for row in result.rows]
        assert "users" in table_names
        assert "products" in table_names
        assert "orders" in table_names

    @pytest.mark.asyncio
    async def test_get_columns(self, mock_db: MockDatabaseBackend) -> None:
        """Test getting table columns."""
        result = await mock_db.get_columns("users")

        assert result.error is None
        column_names = [row[0] for row in result.rows]
        assert "id" in column_names
        assert "name" in column_names
        assert "email" in column_names

    @pytest.mark.asyncio
    async def test_get_schema(self, mock_db: MockDatabaseBackend) -> None:
        """Test getting full schema."""
        schema = await mock_db.get_schema()

        assert "tables" in schema
        assert len(schema["tables"]) == 3

        users_table = next(t for t in schema["tables"] if t["name"] == "users")
        assert len(users_table["columns"]) == 4

    @pytest.mark.asyncio
    async def test_get_schema_single_table(self, mock_db: MockDatabaseBackend) -> None:
        """Test getting schema for single table."""
        schema = await mock_db.get_schema("products")

        assert schema["table"] == "products"
        assert len(schema["columns"]) == 4

    def test_state_persistence(self, mock_db: MockDatabaseBackend) -> None:
        """Test state persistence."""
        state = mock_db.get_state()

        new_db = MockDatabaseBackend()
        new_db.load_state(state)

        assert "users" in new_db._tables
        assert "products" in new_db._tables


# DatabaseMiddleware Tests


class TestDatabaseMiddleware:
    """Tests for DatabaseMiddleware."""

    def test_get_tools(self, db_middleware: DatabaseMiddleware) -> None:
        """Test that middleware returns expected tools."""
        tools = db_middleware.get_tools()
        tool_names = [t.name for t in tools]

        assert "sql_query" in tool_names
        assert "list_tables" in tool_names
        assert "describe_table" in tool_names

    def test_tool_categories(self, db_middleware: DatabaseMiddleware) -> None:
        """Test that tools have correct categories."""
        tools = db_middleware.get_tools()

        for tool in tools:
            assert tool.category == "database"

    def test_system_prompt_segment(self, db_middleware: DatabaseMiddleware) -> None:
        """Test system prompt content."""
        segment = db_middleware.get_system_prompt_segment()

        assert "sql_query" in segment
        assert "list_tables" in segment
        assert "describe_table" in segment

    @pytest.mark.asyncio
    async def test_sql_query(self, db_middleware: DatabaseMiddleware) -> None:
        """Test executing SQL via middleware."""
        result = await db_middleware._sql_query("SELECT * FROM users")

        assert "error" not in result
        assert result["row_count"] == 3
        assert "id" in result["columns"]

    @pytest.mark.asyncio
    async def test_list_tables(self, db_middleware: DatabaseMiddleware) -> None:
        """Test listing tables via middleware."""
        result = await db_middleware._list_tables()

        assert "error" not in result
        table_names = [t["name"] for t in result["tables"]]
        assert "users" in table_names

    @pytest.mark.asyncio
    async def test_describe_table(self, db_middleware: DatabaseMiddleware) -> None:
        """Test describing table via middleware."""
        result = await db_middleware._describe_table("products")

        assert result["table"] == "products"
        assert len(result["columns"]) == 4

    @pytest.mark.asyncio
    async def test_readonly_middleware_blocks_write(
        self, readonly_middleware: DatabaseMiddleware
    ) -> None:
        """Test readonly middleware blocks writes."""
        result = await readonly_middleware._sql_query(
            "INSERT INTO test (id, value) VALUES (2, 'new')"
        )

        assert "error" in result
        assert "readonly" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_result_truncation(self, db_middleware: DatabaseMiddleware) -> None:
        """Test that results are truncated to max_rows."""
        # Add many rows
        db_middleware.backend.add_table(
            "large",
            columns=["id"],
            rows=[[i] for i in range(200)],
        )

        result = await db_middleware._sql_query("SELECT * FROM large")

        assert result["truncated"] is True
        assert result["row_count"] == 100  # default max_rows
        assert result["total_rows"] == 200

    def test_state_persistence(self, db_middleware: DatabaseMiddleware) -> None:
        """Test middleware state persistence."""
        state = db_middleware.get_state()

        assert "readonly" in state
        assert "max_rows" in state
        assert "timeout" in state


# Integration Tests


class TestDatabaseIntegration:
    """Integration tests for database functionality."""

    @pytest.mark.asyncio
    async def test_data_exploration_workflow(
        self, db_middleware: DatabaseMiddleware
    ) -> None:
        """Test a typical data exploration workflow."""
        # List available tables
        tables = await db_middleware._list_tables()
        assert len(tables["tables"]) == 3

        # Describe users table
        users_schema = await db_middleware._describe_table("users")
        assert "id" in [c["name"] for c in users_schema["columns"]]

        # Query users
        users = await db_middleware._sql_query("SELECT name, email FROM users")
        assert users["row_count"] == 3

    @pytest.mark.asyncio
    async def test_analytics_workflow(
        self, db_middleware: DatabaseMiddleware
    ) -> None:
        """Test analytics-style queries."""
        # Count users
        result = await db_middleware._sql_query("SELECT * FROM users")
        assert result["row_count"] >= 3

        # Query products
        products = await db_middleware._sql_query(
            "SELECT * FROM products"
        )
        assert products["row_count"] == 3

    @pytest.mark.asyncio
    async def test_write_and_read(self, db_middleware: DatabaseMiddleware) -> None:
        """Test write and read operations."""
        # Insert new user
        await db_middleware._sql_query(
            "INSERT INTO users (id, name, email, active) VALUES ($1, $2, $3, $4)",
            [4, "Dave", "dave@example.com", True],
        )

        # Verify insertion
        result = await db_middleware._sql_query("SELECT * FROM users")
        assert result["row_count"] == 4

        names = [row[1] for row in result["rows"]]
        assert "Dave" in names


# DatabaseConfig Tests


class TestDatabaseConfig:
    """Tests for DatabaseConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = DatabaseConfig()

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "postgres"
        assert config.readonly is False

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = DatabaseConfig(
            host="db.example.com",
            port=5433,
            database="mydb",
            user="myuser",
            password="secret",
            readonly=True,
        )

        assert config.host == "db.example.com"
        assert config.port == 5433
        assert config.readonly is True

    def test_dsn_generation(self) -> None:
        """Test DSN string generation."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test",
            user="admin",
            password="pass123",
        )

        dsn = config.to_dsn()
        assert "postgresql://" in dsn
        assert "admin:pass123" in dsn
        assert "localhost:5432" in dsn
        assert "/test" in dsn
