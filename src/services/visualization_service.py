"""Weather-independent data for the visualization screen."""
import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import AlertEvent, IrrigationLog, IrrigationPlan
from src.services.irrigation_service import get_sensor_summary, list_zones


def get_visualization_summary(db: Session, include_log: bool = False) -> dict:
    zones = list_zones(db)
    moisture = []
    running_count = 0
    for zone in zones:
        summary = get_sensor_summary(db, zone)
        value = summary.get("average", {}).get("soil_moisture")
        if summary.get("status") == "ok" and value is not None:
            moisture.append(value)
        running_count += sum(actuator.status == "running" for actuator in zone.actuators)
    counts = dict(db.query(IrrigationPlan.status, func.count(IrrigationPlan.id)).group_by(IrrigationPlan.status).all())
    last_log = db.query(IrrigationLog.created_at).order_by(IrrigationLog.created_at.desc()).first() if include_log else None
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "version": "5.0.0",
        "average_soil_moisture": round(sum(moisture) / len(moisture), 2) if moisture else None,
        "city": zones[0].location if zones else None,
        "zone_count": len(zones),
        "running_actuator_count": running_count,
        "irrigation_status": "running" if running_count else "stopped",
        "plan_count": sum(counts.values()),
        "pending_plan_count": counts.get("pending_approval", 0),
        "active_alert_count": db.query(AlertEvent).filter(AlertEvent.status.in_(["open", "acknowledged"])).count(),
        "last_irrigation_at": last_log[0].replace(tzinfo=dt.timezone.utc).isoformat() if last_log and last_log[0] else None,
    }


def get_visualization_models(db: Session) -> dict:
    rows = (
        db.query(IrrigationPlan)
        .order_by(IrrigationPlan.created_at.desc(), IrrigationPlan.id.desc())
        .limit(20).all()
    )
    return {"plans": [{
        "plan_id": plan.plan_id,
        "zone_id": plan.zone_id,
        "zone_name": plan.zone.name if plan.zone else None,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "evidence_summary": {key: (plan.evidence_summary or {}).get(key) for key in ("ml_prediction", "decision_model")},
    } for plan in rows]}
