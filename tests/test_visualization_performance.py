import datetime as dt
from unittest.mock import patch

from sqlalchemy import event

import test_console_performance as console_tests
from src.database.models import AlertEvent, IrrigationPlan, SensorData
from src.services import irrigation_service as irrigation
from src.services.analytics_service import get_zone_trend


class TestVisualizationPerformance(console_tests.TestConsoleApi):
    # Reuse the isolated database and authenticated client, without running the
    # parent test methods a second time in this suite.
    def test_screen_data_never_queries_weather_or_evaluates_alerts(self):
        with patch.object(irrigation, "_get_weather_summary", side_effect=AssertionError("weather must not be read")), \
             patch("src.services.alert_service.evaluate_alerts", side_effect=AssertionError("evaluation must not run")):
            summary = self.client.get("/api/visualization?section=summary", headers=self.headers)
            models = self.client.get("/api/visualization?section=models", headers=self.headers)
            overview = self.client.get("/api/analytics/overview?range=7d", headers=self.headers)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(models.status_code, 200)
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(summary.json()["city"], "北京")
        self.assertEqual(summary.json()["average_soil_moisture"], 12)
        self.assertEqual(models.json()["plans"], [])

    def test_viewer_can_read_metrics_but_not_model_evidence(self):
        self.assertEqual(self.client.get("/api/visualization").status_code, 401)
        payload = self.client.post("/api/auth/login", json={"username": "viewer", "password": "viewer123"}).json()
        headers = {"Authorization": "Bearer " + payload["token"]}
        self.assertEqual(self.client.get("/api/visualization", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/visualization?section=models", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/visualization?section=invalid", headers=self.headers).status_code, 422)

    def test_missing_readings_are_null_in_metrics_and_charts(self):
        with patch.object(irrigation.DataCollectionModule, "get_data", return_value={"data": {**console_tests.READING["data"], "soil_moisture": None}}):
            summary = self.client.get("/api/visualization", headers=self.headers)
            overview = self.client.get("/api/analytics/overview", headers=self.headers)
        self.assertIsNone(summary.json()["average_soil_moisture"])
        self.assertTrue(all(row["soil_moisture"] is None and row["deficit"] is None for row in overview.json()["zone_health"]))
        self.assertEqual(overview.json()["soil_trend"]["soil_moisture"], [None])

    def test_model_response_only_contains_display_evidence(self):
        zone = irrigation.list_zones(self.db)[0]
        self.db.add(IrrigationPlan(zone_id=zone.zone_id, evidence_summary={
            "ml_prediction": {"predicted_soil_moisture_24h": 25},
            "decision_model": {"recommended_action": "hold"},
            "sensor_summary": {"private_raw_payload": "do not send"},
        }))
        self.db.commit()
        response = self.client.get("/api/visualization?section=models", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        plan = response.json()["plans"][0]
        self.assertEqual(set(plan["evidence_summary"]), {"ml_prediction", "decision_model"})
        self.assertNotIn("workspace_path", plan)
        self.assertNotIn("approvals", plan)

    def test_metrics_include_all_pending_plans_and_stored_alerts(self):
        zone = irrigation.list_zones(self.db)[0]
        self.db.add_all([IrrigationPlan(zone_id=zone.zone_id, status="pending_approval") for _ in range(205)])
        self.db.add(AlertEvent(rule_key="test", severity="high", status="open", title="test", message="stored test alert", object_type="zone", object_id=zone.zone_id, zone_id=zone.zone_id))
        self.db.commit()
        response = self.client.get("/api/visualization", headers=self.headers).json()
        self.assertEqual(response["pending_plan_count"], 205)
        self.assertEqual(response["plan_count"], 205)
        self.assertEqual(response["active_alert_count"], 1)

    def test_trend_filters_and_aggregates_in_database(self):
        zone, other = irrigation.list_zones(self.db)[:2]
        sensor = zone.sensor_bindings[0].sensor_id
        other_sensor = other.sensor_bindings[0].sensor_id
        now = dt.datetime.utcnow().replace(minute=10, second=0, microsecond=0)
        self.db.add_all([
            SensorData(sensor_id=sensor, timestamp=now, soil_moisture=20),
            SensorData(sensor_id=sensor, timestamp=now + dt.timedelta(minutes=5), soil_moisture=40),
            SensorData(sensor_id=other_sensor, timestamp=now, soil_moisture=99),
            SensorData(sensor_id=sensor, timestamp=now, soil_moisture=None),
            SensorData(sensor_id=sensor, timestamp=now, soil_moisture=-1),
            SensorData(sensor_id=sensor, timestamp=now - dt.timedelta(days=40), soil_moisture=1),
        ])
        self.db.commit()
        statements = []

        def capture(connection, cursor, statement, parameters, context, many):
            if "sensordata" in statement.lower():
                statements.append(statement.lower())

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            with patch.object(irrigation, "_get_weather_summary", side_effect=AssertionError("weather must not be read")):
                hourly = get_zone_trend(self.db, zone.zone_id, "24h")
                daily = get_zone_trend(self.db, zone.zone_id, "7d")
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(hourly["soil_moisture"], [30])
        self.assertEqual(daily["soil_moisture"], [30])
        self.assertTrue(any("avg(" in statement and "sensor_id in" in statement and "group by" in statement for statement in statements))


# Keep only the fixture methods from the parent for discovery in this module.
for _name in list(vars(console_tests.TestConsoleApi)):
    if _name.startswith("test_"):
        setattr(TestVisualizationPerformance, _name, None)
