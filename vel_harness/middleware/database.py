"""
Database Middleware

Provides SQL execution tools with safety controls.
"""

from typing import Any, Dict, List, Optional, Union

from vel import ToolSpec

from vel_harness.backends.database import (
    DatabaseBackend,
    DatabaseConfig,
    MockDatabaseBackend,
    QueryResult,
    is_write_query,
)
from vel_harness.middleware.base import BaseMiddleware


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware providing SQL execution tools.

    Provides tools:
    - sql_query: Execute SQL queries
    - list_tables: Get available tables
    - describe_table: Get table schema

    Safety features:
    - Readonly mode blocks write queries
    - Query timeout protection
    - Result truncation for large datasets
    """

    def __init__(
        self,
        backend: Optional[Union[DatabaseBackend, MockDatabaseBackend]] = None,
        config: Optional[DatabaseConfig] = None,
        readonly: bool = True,
        max_rows: int = 100,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize database middleware.

        Args:
            backend: Database backend instance (creates MockDatabaseBackend if None)
            config: Database config (used if backend is None)
            readonly: If True, block write queries (default True for safety)
            max_rows: Maximum rows to return from queries
            timeout: Query timeout in seconds
        """
        if backend is not None:
            self._backend = backend
        elif config is not None:
            self._backend = DatabaseBackend(config=config, readonly=readonly)
        else:
            # Use mock backend for testing
            self._backend = MockDatabaseBackend(readonly=readonly)

        self._readonly = readonly
        self._max_rows = max_rows
        self._timeout = timeout
        self._connected = False

    @property
    def backend(self) -> Union[DatabaseBackend, MockDatabaseBackend]:
        """Get the database backend."""
        return self._backend

    async def connect(self) -> None:
        """Connect to the database."""
        await self._backend.connect()
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from the database."""
        await self._backend.disconnect()
        self._connected = False

    def get_tools(self) -> List[ToolSpec]:
        """Return database tools."""
        return [
            ToolSpec.from_function(
                self._sql_query,
                name="sql_query",
                description=(
                    "Execute a SQL query against the database. "
                    "Returns results as a formatted table. "
                    f"{'Write queries (INSERT, UPDATE, DELETE) are blocked.' if self._readonly else 'Write queries are allowed.'}"
                ),
                category="database",
            ),
            ToolSpec.from_function(
                self._list_tables,
                name="list_tables",
                description="List all tables in the database with their types.",
                category="database",
            ),
            ToolSpec.from_function(
                self._describe_table,
                name="describe_table",
                description=(
                    "Get the schema of a specific table including column names, "
                    "types, and constraints."
                ),
                category="database",
            ),
        ]

    def get_system_prompt_segment(self) -> str:
        """Return system prompt describing database capabilities."""
        return f"""## Database Access

You have access to a SQL database for querying data.

**Available Tools:**
- `sql_query(query, params?)`: Execute SQL query
- `list_tables()`: Show available tables
- `describe_table(table_name)`: Show table schema

**Configuration:**
- Mode: {'read-only' if self._readonly else 'read-write'}
- Max rows returned: {self._max_rows}
- Query timeout: {self._timeout}s

**Usage Notes:**
- Use parameterized queries with $1, $2, etc. for values
- Always explore the schema before writing queries
- Results are truncated to {self._max_rows} rows
{'- Write operations (INSERT, UPDATE, DELETE) are BLOCKED' if self._readonly else '- Write operations are allowed - use caution'}
"""

    async def _sql_query(
        self,
        query: str,
        params: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a SQL query.

        Args:
            query: SQL query to execute (use $1, $2 for parameters)
            params: Optional list of parameter values

        Returns:
            Dict with query results or error
        """
        # Ensure connected
        if not self._connected:
            await self.connect()

        result = await self._backend.execute(
            query,
            params=params,
            timeout=self._timeout,
        )

        if result.error:
            return {"error": result.error, "query": query}

        # Truncate results if needed
        rows = result.rows[:self._max_rows]
        truncated = len(result.rows) > self._max_rows

        return {
            "columns": result.columns,
            "rows": rows,
            "row_count": len(rows),
            "total_rows": result.row_count,
            "truncated": truncated,
            "affected_rows": result.affected_rows,
            "query": query,
        }

    async def _list_tables(self) -> Dict[str, Any]:
        """
        List all tables in the database.

        Returns:
            Dict with table names and types
        """
        if not self._connected:
            await self.connect()

        result = await self._backend.get_tables()

        if result.error:
            return {"error": result.error}

        return {
            "tables": [
                {"name": row[0], "type": row[1]}
                for row in result.rows
            ]
        }

    async def _describe_table(self, table_name: str) -> Dict[str, Any]:
        """
        Get schema information for a table.

        Args:
            table_name: Name of the table to describe

        Returns:
            Dict with column information
        """
        if not self._connected:
            await self.connect()

        schema = await self._backend.get_schema(table_name)
        return schema

    def get_state(self) -> Dict[str, Any]:
        """Get middleware state."""
        return {
            "readonly": self._readonly,
            "max_rows": self._max_rows,
            "timeout": self._timeout,
            "connected": self._connected,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load middleware state."""
        self._readonly = state.get("readonly", self._readonly)
        self._max_rows = state.get("max_rows", self._max_rows)
        self._timeout = state.get("timeout", self._timeout)
        # Note: connection state not restored - requires reconnect
