"""
Announcement endpoints for the High School Management System API
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _parse_date(date_str: Optional[str], field_name: str) -> Optional[date]:
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must use YYYY-MM-DD format") from exc


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc.get("_id")),
        "message": doc.get("message", ""),
        "start_date": doc.get("start_date"),
        "expires_at": doc.get("expires_at"),
        "created_by": doc.get("created_by", ""),
        "updated_at": doc.get("updated_at")
    }


def _is_active(doc: Dict[str, Any], today_str: str) -> bool:
    start_date = doc.get("start_date")
    expires_at = doc.get("expires_at")

    if not expires_at:
        return False

    if start_date and start_date > today_str:
        return False

    return expires_at >= today_str


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return only active announcements for public display."""
    today_str = datetime.now(timezone.utc).date().isoformat()
    query = {
        "expires_at": {"$gte": today_str},
        "$or": [
            {"start_date": None},
            {"start_date": {"$exists": False}},
            {"start_date": {"$lte": today_str}}
        ]
    }

    docs = announcements_collection.find(query).sort("expires_at", 1)
    return [_serialize_announcement(doc) for doc in docs if _is_active(doc, today_str)]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements_for_management(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Return all announcements for authenticated teachers."""
    _require_teacher(teacher_username)

    docs = announcements_collection.find({}).sort([("expires_at", 1), ("updated_at", -1)])
    return [_serialize_announcement(doc) for doc in docs]


@router.post("/manage", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    expires_at: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement (teachers only)."""
    teacher = _require_teacher(teacher_username)

    cleaned_message = message.strip()
    if not cleaned_message:
        raise HTTPException(status_code=400, detail="Announcement message is required")
    if len(cleaned_message) > 240:
        raise HTTPException(status_code=400, detail="Announcement message must be 240 characters or fewer")

    parsed_start = _parse_date(start_date, "start_date")
    parsed_expires = _parse_date(expires_at, "expires_at")
    if parsed_expires is None:
        raise HTTPException(status_code=400, detail="expires_at is required")

    if parsed_start and parsed_start > parsed_expires:
        raise HTTPException(status_code=400, detail="start_date cannot be after expires_at")

    now_iso = datetime.now(timezone.utc).isoformat()
    document = {
        "message": cleaned_message,
        "start_date": parsed_start.isoformat() if parsed_start else None,
        "expires_at": parsed_expires.isoformat(),
        "created_by": teacher["username"],
        "updated_at": now_iso
    }

    result = announcements_collection.insert_one(document)
    document["_id"] = result.inserted_id

    return {"message": "Announcement created", "announcement": _serialize_announcement(document)}


@router.put("/manage/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: str,
    expires_at: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement (teachers only)."""
    _require_teacher(teacher_username)

    cleaned_message = message.strip()
    if not cleaned_message:
        raise HTTPException(status_code=400, detail="Announcement message is required")
    if len(cleaned_message) > 240:
        raise HTTPException(status_code=400, detail="Announcement message must be 240 characters or fewer")

    parsed_start = _parse_date(start_date, "start_date")
    parsed_expires = _parse_date(expires_at, "expires_at")
    if parsed_expires is None:
        raise HTTPException(status_code=400, detail="expires_at is required")

    if parsed_start and parsed_start > parsed_expires:
        raise HTTPException(status_code=400, detail="start_date cannot be after expires_at")

    try:
        object_id = ObjectId(announcement_id)
        query = {"_id": object_id}
    except Exception:
        query = {"_id": announcement_id}

    update_data = {
        "message": cleaned_message,
        "start_date": parsed_start.isoformat() if parsed_start else None,
        "expires_at": parsed_expires.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    result = announcements_collection.update_one(query, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated_doc = announcements_collection.find_one(query)
    if not updated_doc:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement updated", "announcement": _serialize_announcement(updated_doc)}


@router.delete("/manage/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Delete an announcement (teachers only)."""
    _require_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
        query = {"_id": object_id}
    except Exception:
        query = {"_id": announcement_id}

    result = announcements_collection.delete_one(query)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
