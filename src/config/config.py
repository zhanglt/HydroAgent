"""
配置管理模块 - 负责加载和提供配置信息
"""
import copy
import os
import tempfile
import yaml
from dotenv import load_dotenv

from src.security import mask_secret

class Config:
    """
    配置管理类，从环境变量、YAML文件等加载配置。
    """
    def __init__(self, config_file_path=None, env_file_path=None):
        """
        初始化配置管理器。
        :param config_file_path: YAML配置文件路径 (可选)
        :param env_file_path: 环境变量文件路径 (可选, 默认为根目录下的.env)
        """
        # 加载环境变量
        if env_file_path:
            load_dotenv(env_file_path)
        else:
            load_dotenv()  # 默认加载根目录下的.env文件
            
        # 优先加载 config.yaml
        config_path = config_file_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../config.yaml')
        self.CONFIG_PATH = os.path.abspath(config_path)
        self._config_from_yaml = {}
        if os.path.exists(self.CONFIG_PATH):
            with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                self._config_from_yaml = yaml.safe_load(f) or {}
        
        # 数据库配置 - 优先从环境变量读取
        self.DB_HOST = os.getenv('DB_HOST') or self._config_from_yaml.get('database', {}).get('host', 'localhost')
        self.DB_PORT = int(os.getenv('DB_PORT') or self._config_from_yaml.get('database', {}).get('port', 5432))
        self.DB_NAME = os.getenv('DB_NAME') or self._config_from_yaml.get('database', {}).get('name', 'irrigation_db')
        self.DB_USER = os.getenv('DB_USER') or self._config_from_yaml.get('database', {}).get('user', 'postgres')
        self.DB_PASSWORD = os.getenv('DB_PASSWORD') or self._config_from_yaml.get('database', {}).get('password', 'postgres')
        self.DB_TYPE = os.getenv('DB_TYPE') or self._config_from_yaml.get('database', {}).get('type', 'sqlite')
        
        # API密钥
        self.WEATHER_API_KEY = os.getenv("WEATHER_API_KEY") or self._get_from_yaml("apis.weather_api_key", "")
        self.API_SERVICE_URL = os.getenv("API_SERVICE_URL") or self._get_from_yaml(
            "apis.weather_service_url", "https://api.open-meteo.com/v1/forecast")
        self.PROXY = str(self._config_from_yaml.get("proxy") or "").strip()
        
        # 传感器配置
        self.SENSOR_IDS = os.getenv("SENSOR_IDS") and os.getenv("SENSOR_IDS").split(",") or self._get_from_yaml("sensors.ids", ["sensor_001", "sensor_002"])
        self.LEGACY_COLLECTION_INTERVAL_MINUTES = int(self._get_from_yaml("sensors.collection_interval_minutes", 5))
        
        # 灌溉策略（仅作为历史 YAML 回填值，运行期业务配置改由数据库托管）
        self.LEGACY_DEFAULT_SOIL_MOISTURE_THRESHOLD = float(
            self._get_from_yaml("irrigation_strategy.soil_moisture_threshold", 30.0)
        )
        self.LEGACY_DEFAULT_DURATION_MINUTES = int(
            self._get_from_yaml("irrigation_strategy.default_duration_minutes", 30)
        )
        self.IRRIGATION_STRATEGY = {
            "soil_moisture_threshold": self.LEGACY_DEFAULT_SOIL_MOISTURE_THRESHOLD,
            "default_duration_minutes": self.LEGACY_DEFAULT_DURATION_MINUTES,
        }
        
        # 模型配置
        self.MODEL_PATH = os.getenv("MODEL_PATH") or self._get_from_yaml("ml_model.path", None)
        self.MODEL_INPUT_SIZE = int(os.getenv("MODEL_INPUT_SIZE") or self._get_from_yaml("ml_model.input_size", 6))
        self.MODEL_HIDDEN_SIZE = int(os.getenv("MODEL_HIDDEN_SIZE") or self._get_from_yaml("ml_model.hidden_size", 50))
        # 报警配置（仅作为历史 YAML 回填值，运行期业务配置改由数据库托管）
        self.LEGACY_ALARM_THRESHOLD = float(self._get_from_yaml("alarm.soil_moisture_threshold", 25.0))
        self.LEGACY_ALARM_ENABLED = bool(self._get_from_yaml("alarm.enabled", True))
        self.ALARM_THRESHOLD_SOIL_MOISTURE = self.LEGACY_ALARM_THRESHOLD
        self.ALARM_ENABLED = self.LEGACY_ALARM_ENABLED
        
        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL") or self._get_from_yaml("logging.level", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE") or self._get_from_yaml("logging.file", "irrigation_system.log")
        
        self._load_model_settings()
        self.LEGACY_KNOWLEDGE_TOP_K = int(self._get_from_yaml('knowledge_base.top_k', 4))
        self.LEGACY_KNOWLEDGE_CHUNK_SIZE = int(self._get_from_yaml('knowledge_base.chunk_size', 1200))
        self.LEGACY_KNOWLEDGE_CHUNK_OVERLAP = int(self._get_from_yaml('knowledge_base.chunk_overlap', 180))
        self.KNOWLEDGE_TOP_K = self.LEGACY_KNOWLEDGE_TOP_K
        self.KNOWLEDGE_CHUNK_SIZE = self.LEGACY_KNOWLEDGE_CHUNK_SIZE
        self.KNOWLEDGE_CHUNK_OVERLAP = self.LEGACY_KNOWLEDGE_CHUNK_OVERLAP
        self.DATA_COLLECTION_INTERVAL_MINUTES = self.LEGACY_COLLECTION_INTERVAL_MINUTES
        
        # FastAPI 服务配置
        self.APP_HOST = os.getenv('APP_HOST') or self._get_from_yaml('app.host', '0.0.0.0')
        self.APP_PORT = int(os.getenv('APP_PORT') or self._get_from_yaml('app.port', 7860))
        self.FRONTEND_ORIGINS = self._parse_origins(
            os.getenv('FRONTEND_ORIGINS'),
            self._get_from_yaml('app.frontend_origins', ['http://localhost:3000'])
        )
        
        # MCP Server 路径
        self.MCP_SERVER_PATH = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '../mcp_server.py'
        )
        self.sync_yaml_to_environment()

        # 演示模式：禁止注册新用户，仅保留唯一管理员账号
        self.DEMO_MODE = os.getenv('DEMO_MODE', '').strip().lower() == 'true'
    
    def _get_from_yaml(self, path, default=None):
        """
        从嵌套的YAML配置中提取值
        :param path: 以点分隔的配置路径 (例如 "database.host")
        :param default: 如果找不到值，返回的默认值
        :return: 配置值或默认值
        """
        keys = path.split('.')
        value = self._config_from_yaml
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    # Ignore values exported by this loader when resolving a different provider.
    _synced_environment = {}

    def _resolve_secret(self, *, env_key, yaml_key, fallback=None):
        env_value = os.getenv(env_key)
        if env_value and env_value != self._synced_environment.get(env_key):
            return env_value
        return self._get_from_yaml(yaml_key) or fallback

    def _select_provider(self, section, supported, default):
        entries = self._config_from_yaml.get(section)
        if entries is None:
            return default, None
        if not isinstance(entries, dict):
            raise ValueError(f"{section} must be a mapping")
        selected = entries.get("provider")
        if selected is None:
            selected = next((name for name, value in entries.items()
                             if name in supported and isinstance(value, dict)
                             and value.get("model_name" if section == "llm_model" else "embedding_model_name")), default)
        if selected not in supported:
            raise ValueError(f"Unsupported {section} provider: {selected}")
        block = entries.get(selected) or {}
        if not isinstance(block, dict):
            raise ValueError(f"{section}.{selected} must be a mapping")
        return selected, block

    def _load_model_settings(self):
        self.LLM_PROVIDER, llm = self._select_provider("llm_model", {"openai", "minimax"}, "openai")
        prefix = self.LLM_PROVIDER
        if llm is None:
            llm = self._config_from_yaml
            root = ""
        else:
            root = f"llm_model.{prefix}."
        self.MODEL_NAME = llm.get("model_name") or ("MiniMax-M2.5" if prefix == "minimax" else "gpt-4o")
        # Retain the legacy OPENAI_* attributes as aliases for the active chat provider.
        self.OPENAI_API_KEY = self._resolve_secret(env_key=f"{prefix.upper()}_API_KEY", yaml_key=f"{root}{prefix}_api_key")
        self.OPENAI_BASE_URL = llm.get(f"{prefix}_base_url") or (
            "https://api.minimax.io/v1" if prefix == "minimax" else "https://api.openai.com/v1")
        self.OPENAI_WIRE_API = self._validate_openai_wire_api(
            llm.get(f"{prefix}_wire_api") or ("chat_completions" if prefix == "minimax" else "auto"))
        self.EMBEDDING_PROVIDER, embedding = self._select_provider(
            "embedding_model", {"openai", "ollama", "ollam"}, "openai")
        self._embedding_yaml_provider = self.EMBEDDING_PROVIDER
        if self.EMBEDDING_PROVIDER == "ollam":
            self.EMBEDDING_PROVIDER = "ollama"
        embedding_root = "" if embedding is None else f"embedding_model.{self._embedding_yaml_provider}."
        if embedding is None:
            embedding = self._config_from_yaml
        self.EMBEDDING_MODEL_NAME = embedding.get("embedding_model_name") or (
            "bge-m3:latest" if self.EMBEDDING_PROVIDER == "ollama" else "text-embedding-3-small")
        self.EMBEDDING_BASE_URL = str(embedding.get("embedding_base_url") or "").strip() or (
            "http://127.0.0.1:11434" if self.EMBEDDING_PROVIDER == "ollama" else None)
        self.EMBEDDING_API_KEY = self._resolve_secret(
            env_key="EMBEDDING_API_KEY", yaml_key=f"{embedding_root}embedding_api_key",
            fallback=self.OPENAI_API_KEY if self.EMBEDDING_PROVIDER == "openai" else None)

    def _model_setting_path(self, key):
        if key.startswith("embedding_"):
            if "embedding_model" in self._config_from_yaml:
                return f"embedding_model.{self._embedding_yaml_provider}.{key}"
        elif "llm_model" in self._config_from_yaml:
            field = key.replace("openai_", f"{self.LLM_PROVIDER}_", 1)
            return f"llm_model.{self.LLM_PROVIDER}.{field}"
        return key

    def _set_in_yaml(self, path, value):
        """按点路径写入嵌套 YAML 配置。"""
        keys = path.split('.')
        target = self._config_from_yaml
        for key in keys[:-1]:
            if not isinstance(target.get(key), dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    def _delete_in_yaml(self, path):
        keys = path.split('.')
        target = self._config_from_yaml
        for key in keys[:-1]:
            if not isinstance(target, dict) or key not in target:
                return
            target = target[key]
        if isinstance(target, dict):
            target.pop(keys[-1], None)

    def _serialize_secret_status(self, value):
        masked = mask_secret(value)
        return {
            "configured": bool(masked),
            "masked_value": masked,
        }

    def _write_yaml(self):
        """将当前 YAML 配置持久化回 config.yaml。"""
        config_dir = os.path.dirname(self.CONFIG_PATH) or "."
        os.makedirs(config_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config_dir, delete=False) as file:
            yaml.safe_dump(self._config_from_yaml, file, allow_unicode=True, sort_keys=False)
            temp_path = file.name
        os.replace(temp_path, self.CONFIG_PATH)

    def sync_yaml_to_environment(self):
        """将 YAML 托管的模型/密钥配置同步到进程环境变量，兼容依赖 env 的库。"""
        env_mapping = {
            f"{self.LLM_PROVIDER.upper()}_API_KEY": self.OPENAI_API_KEY,
            "EMBEDDING_API_KEY": self.EMBEDDING_API_KEY,
            "EMBEDDING_BASE_URL": self.EMBEDDING_BASE_URL or self.OPENAI_BASE_URL,
            "OPENAI_BASE_URL": self.OPENAI_BASE_URL,
            "MODEL_NAME": self.MODEL_NAME,
            "EMBEDDING_MODEL_NAME": self.EMBEDDING_MODEL_NAME,
        }
        for key, value in env_mapping.items():
            if key.endswith("_API_KEY") and os.getenv(key) and os.getenv(key) != self._synced_environment.get(key):
                continue
            normalized = str(value or "").strip()
            self._synced_environment[key] = normalized
            if normalized:
                os.environ[key] = normalized
            else:
                os.environ.pop(key, None)

    def get_yaml_settings(self):
        """返回由 YAML 托管的模型与环境配置快照。"""
        return {
            "llm_provider": self.LLM_PROVIDER,
            "embedding_provider": self.EMBEDDING_PROVIDER,
            "model_name": self.MODEL_NAME,
            "embedding_model_name": self.EMBEDDING_MODEL_NAME,
            "embedding_base_url": self.EMBEDDING_BASE_URL,
            "openai_base_url": self.OPENAI_BASE_URL,
            "openai_wire_api": self.OPENAI_WIRE_API,
            "openai_api_key_status": self._serialize_secret_status(self.OPENAI_API_KEY),
            "embedding_api_key_status": self._serialize_secret_status(self.EMBEDDING_API_KEY),
            "db_type": self.DB_TYPE,
            "config_source": self.CONFIG_PATH,
        }

    def get_runtime_settings(self):
        """兼容旧调用；现仅返回 YAML 托管字段。"""
        return self.get_yaml_settings()

    def update_yaml_settings(self, updates):
        """将前端结构化设置映射回 config.yaml，并同步刷新运行时配置。"""
        if updates.get("openai_wire_api") is not None:
            self._validate_openai_wire_api(updates["openai_wire_api"])
        # Validate the complete candidate before persisting any change.
        candidate = copy.copy(self)
        candidate._config_from_yaml = copy.deepcopy(self._config_from_yaml)
        for field, section, supported in (
            ("llm_provider", "llm_model", {"openai", "minimax"}),
            ("embedding_provider", "embedding_model", {"openai", "ollama", "ollam"}),
        ):
            if updates.get(field) is not None:
                provider = updates[field]
                if provider not in supported:
                    raise ValueError(f"Unsupported {field}: {provider}")
                # Preserve legacy settings when first enabling provider selection.
                if section not in candidate._config_from_yaml:
                    keys = (["model_name", "openai_base_url", "openai_wire_api", "openai_api_key"]
                            if section == "llm_model" else
                            ["embedding_model_name", "embedding_base_url", "embedding_api_key"])
                    candidate._config_from_yaml[section] = {"openai": {
                        key: candidate._config_from_yaml[key] for key in keys if key in candidate._config_from_yaml}}
                if provider == "ollama" and "ollam" in candidate._config_from_yaml[section] and "ollama" not in candidate._config_from_yaml[section]:
                    provider = "ollam"
                candidate._set_in_yaml(f"{section}.provider", provider)
        candidate._load_model_settings()
        for key in ("model_name", "embedding_model_name", "embedding_base_url", "openai_base_url",
                    "openai_wire_api", "openai_api_key", "embedding_api_key"):
            if key not in updates or updates[key] is None:
                continue
            path = candidate._model_setting_path(key)
            value = str(updates[key]).strip()
            if key.endswith("api_key") and not value:
                candidate._delete_in_yaml(path)
            else:
                candidate._set_in_yaml(path, value)
        candidate._load_model_settings()
        candidate._write_yaml()
        self.__dict__.update(candidate.__dict__)
        self.sync_yaml_to_environment()

        return self.get_yaml_settings()

    @staticmethod
    def _validate_openai_wire_api(value):
        if value not in {"auto", "responses", "chat_completions"}:
            raise ValueError("openai_wire_api must be auto, responses, or chat_completions")
        return value

    def update_runtime_settings(self, updates):
        """兼容旧调用；现仅更新 YAML 托管字段。"""
        return self.update_yaml_settings(updates)

    def get_db_uri(self):
        """
        返回数据库连接URI字符串。
        根据 DB_TYPE 动态生成，支持 sqlite (默认), mysql, postgresql。
        """
        db_type = self.DB_TYPE.lower()
        if db_type == "postgresql":
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        elif db_type == "mysql":
            return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        else:
            # 默认 SQLite —— 零配置启动
            db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), f'../../{self.DB_NAME}.db'
            )
            return f"sqlite:///{os.path.abspath(db_path)}"

    def _parse_origins(self, origins, default):
        """将环境变量或配置中的前端域名解析为列表。"""
        if isinstance(origins, str):
            return [origin.strip() for origin in origins.split(',') if origin.strip()]
        if isinstance(origins, list):
            return origins
        return default

# 全局配置实例 - 单例模式
config = Config()
