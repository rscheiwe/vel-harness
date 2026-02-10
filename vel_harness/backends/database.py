"""
Database Backend

Provides safe SQL execution with asyncpg for PostgreSQL databases.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# asyncpg is optional - only import if available
try:
    import asyncpg
    from asyncpg import Pool, Connection

    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    Pool = Any  # type: ignore
    Connection = Any  # type: ignore


class DatabaseNotAvailableError(Exception):
    """Raised when database functionality is not available."""

    pass


class DatabaseConnectionError(Exception):
    """Raised when database connection fails."""

    pass


class DatabaseQueryError(Exception):
    """Raised when a query execution fails."""

    pass


# SQL statement classification patterns
WRITE_PATTERNS = [
    r"^\s*INSERT\s+",
    r"^\s*UPDATE\s+",
    r"^\s*DELETE\s+",
    r"^\s*DROP\s+",
    r"^\s*CREATE\s+",
    r"^\s*ALTER\s+",
    r"^\s*TRUNCATE\s+",
    r"^\s*GRANT\s+",
    r"^\s*REVOKE\s+",
]


def is_write_query(sql: str) -> bool:
    """Check if SQL is a write query."""
    sql_upper = sql.upper()
    for pattern in WRITE_PATTERNS:
        if re.match(pattern, sql_upper, re.IGNORECASE):
            return True
    return False


@dataclass
class QueryResult:
    """Result of a SQL query execution."""

    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    query: str
    affected_rows: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result: Dict[str, Any] = {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "query": self.query,
        }
        if self.affected_rows is not None:
            result["affected_rows"] = self.affected_rows
        if self.error:
            result["error"] = self.error
        return result

    def to_markdown_table(self, max_rows: int = 50) -> str:
        """Format results as markdown table."""
        if self.error:
            return f"Error: {self.error}"

        if not self.columns:
            return f"Query executed. Affected rows: {self.affected_rows or 0}"

        lines = []

        # Header
        header = "| " + " | ".join(str(col) for col in self.columns) + " |"
        lines.append(header)

        # Separator
        separator = "| " + " | ".join("---" for _ in self.columns) + " |"
        lines.append(separator)

        # Rows (with truncation)
        display_rows = self.rows[:max_rows]
        for row in display_rows:
            row_str = "| " + " | ".join(str(val) if val is not None else "NULL" for val in row) + " |"
            lines.append(row_str)

        if len(self.rows) > max_rows:
            lines.append(f"\n*({len(self.rows) - max_rows} more rows...)*")

        return "\n".join(lines)


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: str = ""
    min_connections: int = 1
    max_connections: int = 10
    readonly: bool = False

    def to_dsn(self) -> str:
        """Build connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class DatabaseBackend:
    """
    Async PostgreSQL database backend using asyncpg.

    Provides:
    - Connection pooling
    - Safe SQL execution with read-only mode
    - Query result formatting
    - Schema introspection
    """

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        readonly: bool = False,
    ) -> None:
        """
        Initialize database backend.

        Args:
            config: Database connection configuration
            readonly: If True, block all write queries
        """
        if not ASYNCPG_AVAILABLE:
            raise DatabaseNotAvailableError(
                "asyncpg is not installed. Install with: pip install vel-harness[database]"
            )

        self.config = config or DatabaseConfig()
        self.readonly = readonly or self.config.readonly
        self._pool: Optional[Pool] = None

    async def connect(self) -> None:
        """Establish database connection pool."""
        if self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                min_size=self.config.min_connections,
                max_size=self.config.max_connections,
            )
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to connect to database: {e}")

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _ensure_connected(self) -> Pool:
        """Ensure connection pool exists."""
        if self._pool is None:
            await self.connect()
        assert self._pool is not None
        return self._pool

    async def execute(
        self,
        sql: str,
        params: Optional[List[Any]] = None,
        timeout: float = 30.0,
    ) -> QueryResult:
        """
        Execute a SQL query.

        Args:
            sql: SQL query to execute
            params: Query parameters (positional)
            timeout: Query timeout in seconds

        Returns:
            QueryResult with columns, rows, and metadata
        """
        # Check readonly mode
        if self.readonly and is_write_query(sql):
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error="Write queries are not allowed in readonly mode",
            )

        pool = await self._ensure_connected()
        params = params or []

        try:
            async with pool.acquire() as conn:
                conn: Connection
                if is_write_query(sql):
                    # Execute write query
                    result = await conn.execute(sql, *params, timeout=timeout)
                    # Parse affected rows from result string (e.g., "UPDATE 5")
                    affected = 0
                    if result:
                        parts = result.split()
                        if len(parts) >= 2 and parts[-1].isdigit():
                            affected = int(parts[-1])

                    return QueryResult(
                        columns=[],
                        rows=[],
                        row_count=0,
                        query=sql,
                        affected_rows=affected,
                    )
                else:
                    # Execute read query
                    rows = await conn.fetch(sql, *params, timeout=timeout)

                    if not rows:
                        return QueryResult(
                            columns=[],
                            rows=[],
                            row_count=0,
                            query=sql,
                        )

                    columns = list(rows[0].keys())
                    data = [list(row.values()) for row in rows]

                    return QueryResult(
                        columns=columns,
                        rows=data,
                        row_count=len(data),
                        query=sql,
                    )

        except asyncpg.PostgresError as e:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error=str(e),
            )
        except Exception as e:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error=f"Query execution failed: {e}",
            )

    async def execute_many(
        self,
        sql: str,
        params_list: List[List[Any]],
        timeout: float = 30.0,
    ) -> QueryResult:
        """
        Execute a query with multiple parameter sets.

        Args:
            sql: SQL query with parameter placeholders
            params_list: List of parameter lists
            timeout: Query timeout in seconds

        Returns:
            QueryResult with execution status
        """
        if self.readonly and is_write_query(sql):
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error="Write queries are not allowed in readonly mode",
            )

        pool = await self._ensure_connected()

        try:
            async with pool.acquire() as conn:
                conn: Connection
                await conn.executemany(sql, params_list, timeout=timeout)

                return QueryResult(
                    columns=[],
                    rows=[],
                    row_count=0,
                    query=sql,
                    affected_rows=len(params_list),
                )

        except asyncpg.PostgresError as e:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error=str(e),
            )

    async def get_tables(self) -> QueryResult:
        """Get list of tables in the database."""
        sql = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        return await self.execute(sql)

    async def get_columns(self, table_name: str) -> QueryResult:
        """Get columns for a specific table."""
        sql = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
        """
        return await self.execute(sql, [table_name])

    async def get_schema(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get database schema information.

        Args:
            table_name: If provided, get schema for specific table only

        Returns:
            Dict with schema information
        """
        if table_name:
            columns_result = await self.get_columns(table_name)
            return {
                "table": table_name,
                "columns": [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "YES",
                        "default": row[3],
                    }
                    for row in columns_result.rows
                ],
            }

        tables_result = await self.get_tables()
        schema: Dict[str, Any] = {"tables": []}

        for row in tables_result.rows:
            table = row[0]
            columns_result = await self.get_columns(table)
            schema["tables"].append(
                {
                    "name": table,
                    "type": row[1],
                    "columns": [
                        {
                            "name": col[0],
                            "type": col[1],
                            "nullable": col[2] == "YES",
                            "default": col[3],
                        }
                        for col in columns_result.rows
                    ],
                }
            )

        return schema

    def get_state(self) -> Dict[str, Any]:
        """Get backend state for persistence."""
        return {
            "config": {
                "host": self.config.host,
                "port": self.config.port,
                "database": self.config.database,
                "user": self.config.user,
                # Note: password not persisted for security
                "readonly": self.config.readonly,
            },
            "readonly": self.readonly,
        }


class MockDatabaseBackend:
    """
    In-memory mock database for testing without a real database.

    Supports basic SQL operations on in-memory tables.
    """

    def __init__(self, readonly: bool = False) -> None:
        """Initialize mock database backend."""
        self.readonly = readonly
        self._tables: Dict[str, Dict[str, Any]] = {}
        # table_name -> {"columns": [...], "rows": [...]}

    def add_table(
        self,
        name: str,
        columns: List[str],
        rows: Optional[List[List[Any]]] = None,
    ) -> None:
        """Add a table to the mock database."""
        self._tables[name] = {
            "columns": columns,
            "rows": rows or [],
        }

    async def connect(self) -> None:
        """Mock connect - no-op."""
        pass

    async def disconnect(self) -> None:
        """Mock disconnect - no-op."""
        pass

    async def execute(
        self,
        sql: str,
        params: Optional[List[Any]] = None,
        timeout: float = 30.0,
    ) -> QueryResult:
        """Execute SQL on mock database."""
        sql_upper = sql.strip().upper()

        # Check readonly
        if self.readonly and is_write_query(sql):
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error="Write queries are not allowed in readonly mode",
            )

        # Parse simple SELECT
        if sql_upper.startswith("SELECT"):
            return self._execute_select(sql)

        # Parse simple INSERT
        if sql_upper.startswith("INSERT"):
            return self._execute_insert(sql, params)

        return QueryResult(
            columns=[],
            rows=[],
            row_count=0,
            query=sql,
            error="Unsupported query type in mock database",
        )

    def _execute_select(self, sql: str) -> QueryResult:
        """Execute SELECT query."""
        sql_upper = sql.upper()

        # Parse FROM clause
        from_match = re.search(r"FROM\s+(\w+)", sql_upper)
        if not from_match:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error="Could not parse table name from SELECT",
            )

        table_name = from_match.group(1).lower()
        if table_name not in self._tables:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error=f"Table '{table_name}' not found",
            )

        table = self._tables[table_name]

        # Simple SELECT * support
        if "SELECT *" in sql_upper or "SELECT * " in sql_upper:
            return QueryResult(
                columns=table["columns"],
                rows=table["rows"],
                row_count=len(table["rows"]),
                query=sql,
            )

        # Parse specific columns
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", sql_upper)
        if select_match:
            col_str = select_match.group(1)
            col_names = [c.strip().lower() for c in col_str.split(",")]

            # Get column indices
            indices = []
            for col in col_names:
                if col in [c.lower() for c in table["columns"]]:
                    idx = [c.lower() for c in table["columns"]].index(col)
                    indices.append(idx)

            filtered_rows = [[row[i] for i in indices] for row in table["rows"]]

            return QueryResult(
                columns=col_names,
                rows=filtered_rows,
                row_count=len(filtered_rows),
                query=sql,
            )

        return QueryResult(
            columns=table["columns"],
            rows=table["rows"],
            row_count=len(table["rows"]),
            query=sql,
        )

    def _execute_insert(
        self, sql: str, params: Optional[List[Any]]
    ) -> QueryResult:
        """Execute INSERT query."""
        sql_upper = sql.upper()

        # Parse table name
        into_match = re.search(r"INTO\s+(\w+)", sql_upper)
        if not into_match:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error="Could not parse table name from INSERT",
            )

        table_name = into_match.group(1).lower()
        if table_name not in self._tables:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query=sql,
                error=f"Table '{table_name}' not found",
            )

        # Add row with params
        if params:
            self._tables[table_name]["rows"].append(params)

        return QueryResult(
            columns=[],
            rows=[],
            row_count=0,
            query=sql,
            affected_rows=1,
        )

    async def get_tables(self) -> QueryResult:
        """Get list of mock tables."""
        rows = [[name, "BASE TABLE"] for name in self._tables.keys()]
        return QueryResult(
            columns=["table_name", "table_type"],
            rows=rows,
            row_count=len(rows),
            query="SELECT table_name, table_type FROM information_schema.tables",
        )

    async def get_columns(self, table_name: str) -> QueryResult:
        """Get columns for a mock table."""
        if table_name not in self._tables:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                query="",
                error=f"Table '{table_name}' not found",
            )

        table = self._tables[table_name]
        rows = [
            [col, "text", "YES", None]
            for col in table["columns"]
        ]

        return QueryResult(
            columns=["column_name", "data_type", "is_nullable", "column_default"],
            rows=rows,
            row_count=len(rows),
            query=f"SELECT column info for {table_name}",
        )

    async def get_schema(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get mock database schema."""
        if table_name:
            if table_name not in self._tables:
                return {"error": f"Table '{table_name}' not found"}

            table = self._tables[table_name]
            return {
                "table": table_name,
                "columns": [
                    {"name": col, "type": "text", "nullable": True, "default": None}
                    for col in table["columns"]
                ],
            }

        return {
            "tables": [
                {
                    "name": name,
                    "type": "BASE TABLE",
                    "columns": [
                        {"name": col, "type": "text", "nullable": True, "default": None}
                        for col in table["columns"]
                    ],
                }
                for name, table in self._tables.items()
            ]
        }

    def get_state(self) -> Dict[str, Any]:
        """Get mock database state."""
        return {
            "tables": self._tables,
            "readonly": self.readonly,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load mock database state."""
        self._tables = state.get("tables", {})
        self.readonly = state.get("readonly", False)
