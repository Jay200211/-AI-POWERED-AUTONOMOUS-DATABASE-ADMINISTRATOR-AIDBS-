"""Database manager - converts configs to dicts and connects."""
import logging
import traceback

log = logging.getLogger("aidba.db")


class DatabaseManager:
    def __init__(self, configs):
        self.connectors = {}
        
        if not configs:
            print("[AIDBA] No databases in config", flush=True)
            return
        
        if not isinstance(configs, list):
            print(f"[AIDBA] configs is {type(configs).__name__}, not list", flush=True)
            return
        
        print(f"[AIDBA] Loading {len(configs)} database(s)...", flush=True)
        
        for idx, c in enumerate(configs):
            try:
                # CRITICAL: Convert Pydantic to dict
                if hasattr(c, "model_dump"):
                    cfg = c.model_dump()
                elif hasattr(c, "dict"):
                    cfg = c.dict()
                elif isinstance(c, dict):
                    cfg = c
                else:
                    print(f"[AIDBA] [{idx}] Unknown type: {type(c).__name__}", flush=True)
                    continue
                
                if not cfg.get("enabled", True):
                    print(f"[AIDBA] [{idx}] Disabled: {cfg.get('name')}", flush=True)
                    continue
                
                name = cfg.get("name", f"db_{idx}")
                db_type = cfg.get("type", "").lower()
                host = cfg.get("host", "")
                port = cfg.get("port", 1433)
                
                print(f"[AIDBA] [{idx+1}] Connecting {db_type}: {name} at {host}:{port}", flush=True)
                
                if db_type == "sqlserver":
                    from .sqlserver import SqlServerConnector
                    self.connectors[name] = SqlServerConnector(cfg).connect()
                elif db_type == "mysql":
                    from .mysql import MySQLConnector
                    self.connectors[name] = MySQLConnector(cfg).connect()
                elif db_type == "postgresql":
                    from .postgresql import PostgresConnector
                    self.connectors[name] = PostgresConnector(cfg).connect()
                else:
                    print(f"[AIDBA] [{idx+1}] Unknown type: {db_type}", flush=True)
                    continue
                
                print(f"[AIDBA] [{idx+1}] CONNECTED: {name}", flush=True)
                
            except Exception as e:
                print(f"[AIDBA] [{idx+1}] ERROR: {e}", flush=True)
                traceback.print_exc()
        
        print(f"[AIDBA] Final databases: {list(self.connectors.keys())}", flush=True)

    def list(self):
        return list(self.connectors.keys())

    def get(self, name):
        return self.connectors.get(name)

    def health_all(self):
        result = {}
        for name, conn in self.connectors.items():
            try:
                result[name] = conn.health_check()
            except Exception as e:
                result[name] = {"ok": False, "error": str(e)}
        return result

    def close(self):
        for conn in self.connectors.values():
            try:
                conn.disconnect()
            except Exception:
                pass
