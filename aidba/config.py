"""Configuration loader - converts YAML dicts to Pydantic objects."""
from pathlib import Path
from typing import Literal, List
import yaml
from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    name: str
    type: Literal["sqlserver", "mysql", "postgresql"]
    host: str
    port: int = 1433
    database: str = "master"
    username: str = ""
    password: str = ""
    enabled: bool = True


class AppConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    data_dir: Path = Path("./data")


class MonitoringConfig(BaseModel):
    critical_interval_seconds: int = 10
    secondary_interval_seconds: int = 60
    slow_query_threshold_ms: int = 500
    max_overhead_percent: float = 2.0


class LLMConfig(BaseModel):
    provider: Literal["ollama", "mock"] = "mock"
    base_url: str = "http://localhost:11434"
    model: str = "deepseek-coder:6.7b"
    timeout_seconds: int = 120
    temperature: float = 0.1


class ApprovalConfig(BaseModel):
    auto_approve_safe: bool = False
    rollback_on_p99_regression_pct: float = 10.0


class StorageConfig(BaseModel):
    metrics_retention_days: int = 7
    audit_retention_days: int = 365


class RootConfig(BaseModel):
    app: AppConfig = AppConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    llm: LLMConfig = LLMConfig()
    approval: ApprovalConfig = ApprovalConfig()
    storage: StorageConfig = StorageConfig()
    databases: List[DatabaseConfig] = Field(default_factory=list)


def load_config(path):
    """Load and validate config.yaml - converts dicts to Pydantic objects."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    
    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    
    if not raw:
        raise ValueError(f"Config file {path} is empty")
    
    # Ensure data_dir is a Path
    raw.setdefault("app", {})
    raw["app"]["data_dir"] = Path(raw["app"].get("data_dir", "./data"))
    
    # Ensure databases is a list
    if raw.get("databases") is None:
        raw["databases"] = []
    
    # Pydantic will automatically convert dicts to DatabaseConfig objects
    config = RootConfig(**raw)
    
    print(f"[AIDBA] Config loaded: {len(config.databases)} database(s)", flush=True)
    for db in config.databases:
        # db is now a DatabaseConfig OBJECT, not a dict!
        print(f"[AIDBA]   - {db.name} ({db.type}) at {db.host}:{db.port}/{db.database}", flush=True)
    
    return config
