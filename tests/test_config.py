"""
配置管理模块的测试
"""
import os
import unittest
import tempfile
import yaml
from src.config import Config

class TestConfig(unittest.TestCase):
    """测试配置管理模块"""
    
    def setUp(self):
        """测试前准备工作"""
        # 创建测试用的临时YAML配置文件
        self.config_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
        yaml_content = {
            "database": {
                "host": "test-db-host",
                "port": 5678,
                "name": "test-db-name",
                "user": "test-db-user",
                "password": "test-db-password",
                "type": "postgresql"
            },
            "model_name": "yaml-model",
            "embedding_model_name": "yaml-embedding-model",
            "openai_base_url": "https://yaml.example.com/v1",
            "apis": {
                "weather_api_key": "test-api-key",
                "weather_service_url": "http://test-api.example.com"
            },
            "sensors": {
                "ids": ["test-sensor-001", "test-sensor-002"],
                "collection_interval_minutes": 10
            }
        }
        yaml.dump(yaml_content, self.config_file)
        self.config_file.close()
        
        # 备份当前环境变量
        self.original_env = os.environ.copy()
        
        # 设置测试环境变量
        os.environ["DB_HOST"] = "env-db-host"
        os.environ["WEATHER_API_KEY"] = "env-api-key"
        os.environ["MODEL_NAME"] = "env-model-should-not-win"
    
    def tearDown(self):
        """测试后清理工作"""
        # 删除临时文件
        os.unlink(self.config_file.name)
        
        # 恢复原始环境变量
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_config_load_from_yaml(self):
        """测试从YAML文件加载配置"""
        config = Config(config_file_path=self.config_file.name)
        
        # 验证从YAML加载的配置
        self.assertEqual(config.DB_HOST, "env-db-host")  # 环境变量优先
        self.assertEqual(config.DB_PORT, 5678)  # 从YAML加载
        self.assertEqual(config.DB_NAME, "test-db-name")
        self.assertEqual(config.SENSOR_IDS, ["test-sensor-001", "test-sensor-002"])
    
    def test_config_priority(self):
        """测试配置加载优先级：环境变量 > YAML > 默认值"""
        config = Config(config_file_path=self.config_file.name)
        
        # 环境变量优先
        self.assertEqual(config.WEATHER_API_KEY, "env-api-key")
        
        # 删除环境变量，应该回退到YAML值
        del os.environ["WEATHER_API_KEY"]
        del os.environ["DB_HOST"]
        config = Config(config_file_path=self.config_file.name)
        self.assertEqual(config.WEATHER_API_KEY, "test-api-key")
        self.assertEqual(config.DB_HOST, "test-db-host")
        
        # 如果YAML中也没有，应该使用默认值
        test_config = {
            "database": {"host": "yaml-host"}
        }
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as minimal_config:
            yaml.dump(test_config, minimal_config)
        
        config = Config(config_file_path=minimal_config.name)
        self.assertEqual(config.DB_HOST, "yaml-host")  # 从YAML加载
        self.assertEqual(config.DB_PORT, 5432)  # 使用默认值
        
        os.unlink(minimal_config.name)
    
    def test_get_db_uri(self):
        """测试数据库URI生成"""
        os.environ["DB_TYPE"] = "postgresql"
        config = Config(config_file_path=self.config_file.name)
        expected_uri = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        self.assertEqual(config.get_db_uri(), expected_uri)
        # 测试其他数据库类型
        os.environ["DB_TYPE"] = "mysql"
        config = Config(config_file_path=self.config_file.name)
        expected_uri = f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        self.assertEqual(config.get_db_uri(), expected_uri)

    def test_secret_settings_are_masked_in_runtime_snapshot(self):
        """测试敏感配置仅以掩码状态暴露给前端，YAML 中存明文。"""
        config = Config(config_file_path=self.config_file.name)
        config.update_runtime_settings({
            "openai_api_key": "sk-secret-demo",
            "embedding_api_key": "sk-embed-demo",
        })

        runtime = config.get_runtime_settings()
        self.assertTrue(runtime["openai_api_key_status"]["configured"])
        self.assertTrue(runtime["embedding_api_key_status"]["configured"])
        self.assertNotIn("sk-secret-demo", str(runtime))
        self.assertNotIn("sk-embed-demo", str(runtime))

        # 验证 YAML 中存的是明文 key，而非加密字段
        self.assertIn("openai_api_key", config._config_from_yaml)
        self.assertNotIn("openai_api_key_encrypted", config._config_from_yaml)
        self.assertEqual(config._config_from_yaml["openai_api_key"], "sk-secret-demo")

    def test_yaml_managed_model_settings_override_custom_env(self):
        """YAML 托管的模型配置应优先于同名环境变量。"""
        config = Config(config_file_path=self.config_file.name)

        self.assertEqual(config.MODEL_NAME, "yaml-model")
        self.assertEqual(config.EMBEDDING_MODEL_NAME, "yaml-embedding-model")
        self.assertEqual(config.OPENAI_BASE_URL, "https://yaml.example.com/v1")
        self.assertEqual(os.environ["MODEL_NAME"], "yaml-model")
        self.assertEqual(os.environ["EMBEDDING_MODEL_NAME"], "yaml-embedding-model")
        self.assertEqual(os.environ["OPENAI_BASE_URL"], "https://yaml.example.com/v1")

    def test_wire_api_roundtrip_preserves_other_configuration(self):
        config = Config(config_file_path=self.config_file.name)
        self.assertEqual(config.OPENAI_WIRE_API, "auto")
        before = dict(config._config_from_yaml)
        snapshot = config.update_yaml_settings({"openai_wire_api": "responses"})
        self.assertEqual(snapshot["openai_wire_api"], "responses")
        loaded = Config(config_file_path=self.config_file.name)
        self.assertEqual(loaded.OPENAI_WIRE_API, "responses")
        self.assertEqual({k: v for k, v in loaded._config_from_yaml.items() if k != "openai_wire_api"}, before)

    def test_invalid_wire_api_is_rejected_before_writing(self):
        config = Config(config_file_path=self.config_file.name)
        with open(self.config_file.name) as source:
            before = source.read()
        with self.assertRaises(ValueError):
            config.update_yaml_settings({"openai_wire_api": "invalid", "model_name": "changed"})
        with open(self.config_file.name) as source:
            self.assertEqual(source.read(), before)

    def test_weather_proxy_loads_from_yaml_and_defaults_to_empty(self):
        self.assertEqual(Config(config_file_path=self.config_file.name).PROXY, "")
        with open(self.config_file.name) as source:
            payload = yaml.safe_load(source)
        payload["proxy"] = "http://10.0.0.8:30000"
        with open(self.config_file.name, "w") as target:
            yaml.safe_dump(payload, target)
        self.assertEqual(Config(config_file_path=self.config_file.name).PROXY, payload["proxy"])

    def test_embedding_url_roundtrip_and_fallback(self):
        config = Config(config_file_path=self.config_file.name)
        self.assertIsNone(config.EMBEDDING_BASE_URL)
        self.assertEqual(os.environ["EMBEDDING_BASE_URL"], config.OPENAI_BASE_URL)
        original_chat = config.OPENAI_BASE_URL
        snapshot = config.update_yaml_settings({"embedding_base_url": "https://embedding.example/v1"})
        self.assertEqual(snapshot["embedding_base_url"], "https://embedding.example/v1")
        self.assertEqual(config.OPENAI_BASE_URL, original_chat)
        loaded = Config(config_file_path=self.config_file.name)
        self.assertEqual(loaded.EMBEDDING_BASE_URL, "https://embedding.example/v1")
        self.assertEqual(os.environ["EMBEDDING_BASE_URL"], loaded.EMBEDDING_BASE_URL)
        loaded.update_yaml_settings({"openai_base_url": "https://new-chat.example/v1"})
        self.assertEqual(loaded.EMBEDDING_BASE_URL, "https://embedding.example/v1")
        loaded.update_yaml_settings({"embedding_base_url": ""})
        self.assertIsNone(loaded.EMBEDDING_BASE_URL)
        self.assertEqual(os.environ["EMBEDDING_BASE_URL"], "https://new-chat.example/v1")

if __name__ == "__main__":
    unittest.main()
