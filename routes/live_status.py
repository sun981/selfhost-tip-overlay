"""GET /api/live-status — OBS WebSocket, cached 3s, fail-closed."""
from fastapi import APIRouter
from app import obs_client

router = APIRouter()


@router.get("/api/live-status")
async def live_status():
    live = await obs_client.get_live_status()
    return {"live": live}
