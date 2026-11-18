"""
Analytics aggregation service for HydroAgent.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import AlertEvent, IrrigationPlan, SensorData
from src.services.irrigation_service import get_sensor_summary, get_zone_by_id, list_plans, list_zones


def _is_executed_plan(plan: IrrigationPlan) -> bool:
    return str(plan.status or "") in {"executing", "completed"} or str(plan.execution_status or "") in {"running", "stopped", "executed"}


def _is_pending_plan(plan: IrrigationPlan) -> bool:
    return str(plan.status or "") == "pending_approval"


def _is_approved_plan(plan: IrrigationPlan) -> bool:
    return str(plan.status or "") == "approved"


def _resolve_window(range_key: str) -> tuple[dt.datetime, str]:
    now = dt.datetime.utcnow()
    if range_key == "24h":
        return now - dt.timedelta(hours=24), "hour"
    if range_key == "30d":
        return now - dt.timedelta(days=30), "day"
    return now - dt.timedelta(days=7), "day"


def _bucket_label(timestamp: dt.datetime, granularity: str) -> str:
    return timestamp.strftime("%m-%d") if granularity == "day" else timestamp.strftime("%m-%d %H:00")


def get_zone_trend(db: Session, zone_id: str, range_key: str = "7d") -> dict:
    since, granularity = _resolve_window(range_key)
    zone = get_zone_by_id(db, zone_id)
    if not zone:
        raise ValueError(f"Zone not found: {zone_id}")
    labels: list[str] = []
    moisture_values: list[float | None] = []
    sensor_ids = [binding.sensor_id for binding in zone.sensor_bindings if binding.is_enabled]
    dialect = db.get_bind().dialect.name
    if granularity == "day":
        bucket = func.date(SensorData.timestamp)
    elif dialect == "postgresql":
        bucket = func.date_trunc("hour", SensorData.timestamp)
    elif dialect == "mysql":
        bucket = func.date_format(SensorData.timestamp, "%Y-%m-%d %H:00:00")
    else:
        bucket = func.strftime("%Y-%m-%d %H:00:00", SensorData.timestamp)
    rows = (
        db.query(bucket.label("bucket"), func.avg(SensorData.soil_moisture))
        .filter(SensorData.timestamp >= since, SensorData.sensor_id.in_(sensor_ids),
                SensorData.soil_moisture.between(0, 100))
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )
    for timestamp, average in rows:
        labels.append(_bucket_label(dt.datetime.fromisoformat(str(timestamp)), granularity))
        moisture_values.append(round(float(average), 2))

    if not labels:
        average = get_sensor_summary(db, zone).get("average", {})
        labels = [_bucket_label(dt.datetime.utcnow(), granularity)]
        value = average.get("soil_moisture")
        moisture_values = [round(float(value), 2) if value is not None else None]

    return {
        "zone_id": zone_id,
        "zone_name": zone.name,
        "range": range_key,
        "labels": labels,
        "soil_moisture": moisture_values,
        "threshold": [float(zone.soil_moisture_threshold if zone.soil_moisture_threshold is not None else 40.0) for _ in labels],
    }


def get_plan_funnel(db: Session, range_key: str = "7d") -> dict:
    since, _ = _resolve_window(range_key)
    plans = db.query(IrrigationPlan).filter(IrrigationPlan.created_at >= since).all()
    return {
        "range": range_key,
        "items": [
            {"stage": "generated", "count": len(plans)},
            {"stage": "pending", "count": sum(1 for plan in plans if _is_pending_plan(plan))},
            {"stage": "approved", "count": sum(1 for plan in plans if _is_approved_plan(plan))},
            {"stage": "executed", "count": sum(1 for plan in plans if _is_executed_plan(plan))},
            {"stage": "completed_or_rejected", "count": sum(1 for plan in plans if plan.status in {"completed", "rejected", "superseded", "cancelled"})},
        ],
    }


def get_alert_trend(db: Session, range_key: str = "7d") -> dict:
    since, granularity = _resolve_window(range_key)
    alerts = db.query(AlertEvent).filter(AlertEvent.created_at >= since).all()
    labels_map: dict[str, dict[str, int]] = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})
    for alert in alerts:
        labels_map[_bucket_label(alert.created_at, granularity)][alert.severity] += 1

    labels = sorted(labels_map.keys())
    if not labels:
        labels = [_bucket_label(dt.datetime.utcnow(), granularity)]
        labels_map[labels[0]]

    return {
        "range": range_key,
        "labels": labels,
        "series": {
            "high": [labels_map[label]["high"] for label in labels],
            "medium": [labels_map[label]["medium"] for label in labels],
            "low": [labels_map[label]["low"] for label in labels],
        },
    }


def get_analytics_overview(db: Session, range_key: str = "7d") -> dict:
    zones = list_zones(db)
    zone_health = []
    # Reading analytics must not trigger a weather-dependent alert evaluation.
    pending_alerts = db.query(AlertEvent).filter(AlertEvent.status.in_(["open", "acknowledged"])).all()
    plans = list_plans(db, limit=200)

    for zone in zones:
        summary = get_sensor_summary(db, zone)
        average = summary.get("average", {})
        moisture = average.get("soil_moisture") if summary.get("status") == "ok" else None
        threshold = float(zone.soil_moisture_threshold if zone.soil_moisture_threshold is not None else 40.0)
        actuator = next((item for item in zone.actuators if item.is_enabled), None)
        zone_health.append(
            {
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "soil_moisture": round(moisture, 2) if moisture is not None else None,
                "deficit": round(max(0.0, threshold - moisture), 2) if moisture is not None else None,
                "actuator_status": actuator.status if actuator else "unknown",
                "alert_count": sum(1 for alert in pending_alerts if alert.zone_id == zone.zone_id),
            }
        )

    primary_zone = zones[0].zone_id if zones else None
    soil_trend = get_zone_trend(db, primary_zone, range_key) if primary_zone else {"labels": [], "soil_moisture": [], "threshold": []}
    funnel = get_plan_funnel(db, range_key)
    alert_trend = get_alert_trend(db, range_key)

    return {
        "range": range_key,
        "kpis": {
            "zone_count": len(zones),
            "pending_plan_count": sum(1 for plan in plans if _is_pending_plan(plan)),
            "active_alert_count": sum(1 for alert in pending_alerts if alert.status in {"open", "acknowledged"}),
            "executed_plan_count": sum(1 for plan in plans if _is_executed_plan(plan)),
        },
        "soil_trend": soil_trend,
        "plan_funnel": funnel,
        "alert_trend": alert_trend,
        "zone_health": zone_health,
    }
