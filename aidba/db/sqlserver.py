"""SQL Server connector using pyodbc - completely bulletproof."""
import logging
import pandas as pd
from .base import BaseConnector

log = logging.getLogger("aidba.db.sqlserver")

try:
    import pyodbc  # type: ignore
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False
    pyodbc = None


def _find_driver():
    """Find the best available SQL Server ODBC driver."""
    if not HAS_PYODBC:
        return None
    try:
        drivers = pyodbc.drivers()
    except Exception:
        return None
    for preferred in [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server",
    ]:
        if preferred in drivers:
            return preferred
    for d in drivers:
        if "SQL Server" in d:
            return d
    return None


def _build_connection_string(host, port, database, username, password, driver):
    """Build pyodbc connection string - handles named instances."""
    if "\\" in host or "/" in host:
        server = host  # Named instance like JAYENDRA\SQLEXPRESS
    else:
        server = f"{host},{port}"

    if username and password:
        cs = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"UID={username};PWD={password};"
        )
    else:
        cs = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"Trusted_Connection=yes;"
        )

    if "18" in driver or "17" in driver:
        cs += "TrustServerCertificate=yes;"
    cs += "Connection Timeout=10;"
    return cs


class SqlServerConnector(BaseConnector):
    """SQL Server connector - bulletproof version."""

    dialect = "tsql"

    def __init__(self, cfg=None):
        """Initialize - cfg can be dict or Pydantic model."""
        super().__init__(cfg)  # This sets self.cfg safely via base class
        self._driver = None
        self._conn = None

    def connect(self):
        """Establish SQL Server connection."""
        if not HAS_PYODBC:
            raise RuntimeError("pyodbc not installed. Run: pip install pyodbc")
        
        self._driver = _find_driver()
        if not self._driver:
            raise RuntimeError("No SQL Server ODBC driver found. Install ODBC Driver 17.")
        
        # Use get_cfg helper to safely access config values
        cs = _build_connection_string(
            host=self.get_cfg("host", "localhost"),
            port=self.get_cfg("port", 1433),
            database=self.get_cfg("database", "master"),
            username=self.get_cfg("username", ""),
            password=self.get_cfg("password", ""),
            driver=self._driver,
        )
        
        log.info(f"Connecting to SQL Server: {self.get_cfg('host')}:{self.get_cfg('port')}/{self.get_cfg('database')}")
        print(f"[AIDBA] SQL Server: connecting to {self.get_cfg('host')}...", flush=True)
        
        self._conn = pyodbc.connect(cs, autocommit=True, timeout=10)
        return self

    def disconnect(self):
        """Close the connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def execute(self, sql, params=None):
        """Execute a SQL query. Returns list of dicts."""
        if not self._conn:
            raise RuntimeError("Not connected to database")
        cur = self._conn.cursor()
        try:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            if cur.description:
                cols = [c[0] for c in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                return rows
            return []
        finally:
            cur.close()

    def health_check(self):
        """Check SQL Server health."""
        if not HAS_PYODBC:
            return {"ok": False, "error": "pyodbc not installed"}
        try:
            if not self._conn:
                self.connect()
            row = self.execute("SELECT @@VERSION AS v, DB_NAME() AS db")
            if not row:
                return {"ok": False, "error": "No data returned"}
            return {
                "ok": True,
                "version": str(row[0].get("v", ""))[:100],
                "current_db": str(row[0].get("db", "")),
                "driver": self._driver or "unknown"
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_schemas(self):
        """Get list of schemas (databases)."""
        if not self._conn:
            return []
        try:
            rows = self.execute(
                "SELECT name FROM sys.databases WHERE state = 0 ORDER BY name"
            )
            return [r["name"] for r in rows]
        except Exception as e:
            log.warning(f"get_schemas failed: {e}")
            return []

    def get_tables(self, schema):
        """Get list of BASE TABLES in a schema."""
        if not self._conn:
            return []
        try:
            sql = """
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = ? AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """
            cur = self._conn.cursor()
            cur.execute(sql, (schema,))
            tables = [row[0] for row in cur.fetchall()]
            cur.close()
            return tables
        except Exception as e:
            log.warning(f"get_tables failed for schema '{schema}': {e}")
            return []

    def explain_query(self, sql):
        """Get execution plan."""
        if not self._conn:
            return "Not connected"
        try:
            rows = self.execute(f"SET SHOWPLAN_ALL ON; {sql}; SET SHOWPLAN_ALL OFF;")
            return "\n".join(str(r) for r in rows)
        except Exception as e:
            return f"Error: {e}"

    def collect_slow_queries(self, threshold_ms):
        """Collect slow queries from sys.dm_exec_query_stats."""
        if not self._conn:
            return pd.DataFrame()
        try:
            sql = f"""
            SELECT TOP 20
                qs.execution_count AS exec_count,
                (qs.total_elapsed_time/qs.execution_count)/1000 AS avg_ms,
                qs.total_elapsed_time/1000 AS total_ms,
                SUBSTRING(qt.text, 1, 4000) AS query_text,
                CAST(qs.query_hash AS VARCHAR(64)) AS query_hash
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
            WHERE (qs.total_elapsed_time/qs.execution_count)/1000 > {int(threshold_ms)}
            ORDER BY avg_ms DESC
            """
            return pd.read_sql(sql, self._conn)
        except Exception as e:
            log.warning(f"collect_slow_queries failed: {e}")
            return pd.DataFrame()
