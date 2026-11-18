import concurrent.futures
import datetime as dt
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api import get_db as api_get_db, router
from src.database.models import Base, get_db
from src.routers.auth_router import router as auth_router
from src.routers.analytics_router import router as analytics_router
from src.services.auth_service import ensure_auth_seed
from src.services import irrigation_service as irrigation
from src.services.system_settings_service import ensure_system_settings


FORECAST = {"city": "北京", "forecast": [
    {"date": "2026-11-18", "dayweather": "晴", "daytemp": "22", "nighttemp": "12"},
]}
READING = {"data": {"soil_moisture": 12, "temperature": 22, "light_intensity": 500, "rainfall": 0}}


class TestWeatherCache(unittest.TestCase):
    def setUp(self):
        irrigation._weather_summary_cache.clear()

    def tearDown(self):
        irrigation._weather_summary_cache.clear()

    def test_cache_survives_sensor_ttl_without_changing_collection_time(self):
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", return_value=FORECAST) as fetch:
            first = irrigation.get_weather_summary("北京")
            irrigation._weather_summary_cache["北京"] = (dt.datetime.utcnow() - dt.timedelta(seconds=30), first)
            second = irrigation.get_weather_summary("北京")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first["collected_at"], second["collected_at"])

    def test_concurrent_refresh_is_coalesced(self):
        entered = threading.Event()
        release = threading.Event()

        def fetch(_):
            entered.set()
            self.assertTrue(release.wait(3))
            return FORECAST

        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", side_effect=fetch) as mock:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                leader = pool.submit(irrigation.get_weather_summary, "北京")
                self.assertTrue(entered.wait(3))
                followers = [pool.submit(irrigation.get_weather_summary, "北京") for _ in range(5)]
                release.set()
                results = [future.result(timeout=3) for future in [leader, *followers]]
        self.assertEqual(mock.call_count, 1)
        self.assertTrue(all(result == results[0] for result in results))
        self.assertFalse(irrigation._weather_inflight)

    def test_failure_does_not_fabricate_fair_weather_and_can_retry(self):
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", side_effect=RuntimeError("offline")):
            result = irrigation.get_weather_summary("北京")
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["rain_expected"])
        self.assertEqual(result["forecast_days"], [])
        self.assertFalse(irrigation._weather_inflight)
        irrigation._weather_summary_cache["北京"] = (dt.datetime.utcnow() - dt.timedelta(seconds=6), result)
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", return_value=FORECAST):
            self.assertEqual(irrigation.get_weather_summary("北京")["status"], "ok")

    def test_expired_forecast_is_marked_stale_on_failure(self):
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", return_value=FORECAST):
            original = irrigation.get_weather_summary("北京")
        irrigation._weather_summary_cache["北京"] = (dt.datetime.utcnow() - dt.timedelta(seconds=601), original)
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", side_effect=RuntimeError("offline")):
            result = irrigation.get_weather_summary("北京")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["collected_at"], original["collected_at"])
        self.assertIsNone(result["rain_expected"])

    def test_invalid_forecast_is_not_treated_as_no_rain(self):
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", return_value={"forecast": [{}]}):
            result = irrigation.get_weather_summary("北京")
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["rain_expected"])


class TestConsoleApi(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.directory.name}/test.db", connect_args={"check_same_thread": False})
        self.factory = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.factory()
        ensure_system_settings(self.db)
        irrigation.bootstrap_default_zones(self.db)
        ensure_auth_seed(self.db)
        irrigation._sensor_summary_cache.clear()
        irrigation._weather_summary_cache.clear()
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")
        self.app.include_router(auth_router, prefix="/api")
        self.app.include_router(analytics_router, prefix="/api")

        def session():
            with self.factory() as db:
                yield db

        self.app.dependency_overrides[get_db] = session
        self.app.dependency_overrides[api_get_db] = session
        self.client = TestClient(self.app)
        payload = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()
        self.headers = {"Authorization": "Bearer " + payload["token"]}
        self.sensor = patch.object(irrigation.DataCollectionModule, "get_data", return_value=READING)
        self.sensor.start()
        self.workspace = patch.object(irrigation, "WORKSPACE_ROOT", self.directory.name)
        self.workspace.start()

    def tearDown(self):
        self.workspace.stop()
        self.sensor.stop()
        self.client.close()
        self.db.close()
        self.engine.dispose()
        self.directory.cleanup()
        irrigation._sensor_summary_cache.clear()
        irrigation._weather_summary_cache.clear()

    def test_operations_and_sensor_display_never_call_weather(self):
        with patch.object(irrigation, "_get_weather_summary", side_effect=AssertionError("weather must not be read")):
            response = self.client.get("/api/operations", headers=self.headers)
            sensors = self.client.get("/api/sensors/current", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sensors.status_code, 200)
        self.assertEqual(response.json()["sensor_summaries"][0]["average"]["soil_moisture"], 12)
        self.assertNotIn("conversations", response.json())

    def test_sections_only_read_requested_data(self):
        with patch("src.services.operations_service.list_zones", side_effect=AssertionError("unneeded zones")):
            response = self.client.get("/api/operations?section=plans", headers=self.headers)
        self.assertEqual(response.json()["active_plans"], [])
        self.assertNotIn("zones", response.json())
        with patch("src.services.operations_service.list_open_plans", side_effect=AssertionError("unneeded plans")):
            response = self.client.get("/api/operations?section=zones", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("active_plans", response.json())
        self.assertEqual(self.client.get("/api/operations?section=bad", headers=self.headers).status_code, 422)

    def test_permission_failures_are_not_empty_success(self):
        self.assertEqual(self.client.get("/api/operations").status_code, 401)
        payload = self.client.post("/api/auth/login", json={"username": "viewer", "password": "viewer123"}).json()
        self.assertEqual(self.client.get("/api/operations", headers={"Authorization": "Bearer " + payload["token"]}).status_code, 403)

    def test_permission_revocation_is_not_cached_with_seed(self):
        from src.database.models import User
        from src.services.rbac_service import get_user_permission_keys, set_user_roles

        user = self.db.query(User).filter(User.username == "admin").one()
        self.assertIn("operations:view", get_user_permission_keys(self.db, user))
        set_user_roles(self.db, user, ["viewer"], assigned_by="test")
        self.assertNotIn("operations:view", get_user_permission_keys(self.db, user))
        self.assertEqual(self.client.get("/api/operations", headers=self.headers).status_code, 403)

    def test_missing_and_invalid_sensors_are_not_zero(self):
        for value in [None, float("nan"), -1, 101]:
            irrigation._sensor_summary_cache.clear()
            with patch.object(irrigation.DataCollectionModule, "get_data", return_value={"data": {**READING["data"], "soil_moisture": value}}):
                response = self.client.get("/api/operations?section=zones", headers=self.headers)
                sensors = self.client.get("/api/sensors/current", headers=self.headers)
            summary = response.json()["sensor_summaries"][0]
            self.assertEqual(summary["status"], "missing")
            self.assertIsNone(summary["average"]["soil_moisture"])
            self.assertIsNone(sensors.json()["average"]["soil_moisture"])

    def test_partial_failure_is_distinct_from_empty_list(self):
        with patch("src.services.operations_service.list_open_plans", side_effect=RuntimeError("database unavailable")):
            response = self.client.get("/api/operations", headers=self.headers)
            failed = self.client.get("/api/operations?section=plans", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("plans", response.json()["errors"])
        self.assertNotIn("active_plans", response.json())
        self.assertEqual(failed.status_code, 503)

    def test_slow_weather_does_not_block_health(self):
        entered = threading.Event()
        release = threading.Event()

        def slow(_):
            entered.set()
            self.assertTrue(release.wait(4))
            return FORECAST

        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", side_effect=slow):
            # A shared portal makes both requests use the same ASGI event loop.
            with TestClient(self.app) as client, concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                request = pool.submit(client.get, "/api/weather", headers=self.headers)
                try:
                    self.assertTrue(entered.wait(3))
                    started = time.perf_counter()
                    response = client.get("/api/health")
                    self.assertEqual(response.status_code, 200)
                    self.assertLess(time.perf_counter() - started, 0.5)
                finally:
                    release.set()
                self.assertEqual(request.result(timeout=3).status_code, 200)

    def test_unavailable_weather_holds_plan_and_blocks_approved_execution(self):
        zone = irrigation.list_zones(self.db)[0]
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", return_value=FORECAST):
            plan = irrigation.create_plan(self.db, zone.zone_id)
        irrigation.approve_plan(self.db, plan.plan_id, actor="tester")
        irrigation._weather_summary_cache.clear()
        with patch.object(irrigation.DataProcessingModule, "get_weather_by_city_name", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(ValueError, "Fresh weather"):
                irrigation.execute_plan(self.db, plan.plan_id, actor="tester")
            result = irrigation.generate_plan_result(self.db, irrigation.list_zones(self.db)[1].zone_id)
        self.assertEqual(result["suggestion"]["proposed_action"], "hold")
        self.assertEqual(plan.actuator.status, "idle")


if __name__ == "__main__":
    unittest.main()
