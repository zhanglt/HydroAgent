"""Read only the data needed by the operations console."""
import datetime as dt
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.services.irrigation_service import get_sensor_summary, list_open_plans, list_zones

logger = logging.getLogger(__name__)


def get_operations_data(db: Session, section: str = "all") -> dict:
    result = {"errors": {}}
    successes = 0
    if section in {"all", "zones"}:
        try:
            zones = list_zones(db)
            result["zones"] = [zone.to_dict() for zone in zones]
            result["sensor_summaries"] = []
            for zone in zones:
                try:
                    summary = get_sensor_summary(db, zone)
                except Exception:
                    db.rollback()
                    logger.exception("Sensor summary unavailable")
                    summary = {"status": "missing", "average": {}}
                result["sensor_summaries"].append({
                    "zone_id": zone.zone_id,
                    "average": {key: summary.get("average", {}).get(key) for key in
                                ("soil_moisture", "temperature", "light_intensity", "rainfall")},
                    "status": summary["status"],
                    "collected_at": summary.get("timestamp"),
                })
            successes += 1
        except Exception:
            db.rollback()
            logger.exception("Operations zones unavailable")
            result.pop("zones", None)
            result.pop("sensor_summaries", None)
            result["errors"]["zones"] = "分区数据暂时不可用"
    if section in {"all", "plans"}:
        try:
            result["active_plans"] = [plan.to_dict() for plan in list_open_plans(db)]
            successes += 1
        except Exception:
            db.rollback()
            logger.exception("Operations plans unavailable")
            result["errors"]["plans"] = "活跃计划暂时不可用"
    if not successes:
        raise HTTPException(status_code=503, detail=result["errors"])
    result["timestamp"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return result
