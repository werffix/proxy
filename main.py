# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import logging

import config
from core.proxy_generator import generate_secret, validate_secret, build_link
from db.database import init_db, get_user, create_or_update_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MTProto Proxy Web")
templates = Jinja2Templates(directory="web/templates")
app.mount("/static", StaticFiles(directory="web/static"), name="static")


class ProxyRequest(BaseModel):
    user_id: int = Field(..., ge=1, le=2**31)
    admin_token: str | None = None  # Опциональная защита от спама


class ProxyResponse(BaseModel):
    success: bool
    proxy_link: str | None = None
    secret: str | None = None


@app.on_event("startup")
async def on_startup():
    await init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/proxy", response_model=ProxyResponse)
async def issue_proxy(req: ProxyRequest):
    # 🔐 Опциональная защита: если задан ADMIN_TOKEN — проверяем
    if config.ADMIN_TOKEN and req.admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    try:
        secret = generate_secret(req.user_id)
        if not validate_secret(secret):
            raise ValueError("Generated secret is invalid")
        
        # Сохраняем в БД (для статистики/управления)
        await create_or_update_user(req.user_id, secret)
        
        return ProxyResponse(
            success=True,
            proxy_link=build_link(secret),
            secret=secret
        )
    except Exception as e:
        logger.error(f"Proxy generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok"}
