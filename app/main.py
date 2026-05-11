from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio, os, uvicorn

from app.config import settings
from app.core.bybit import BybitClient
from app.engine.engine import TradingEngine
from app.utils.logger import get_logger

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 NEXUS-7 iniciando...")
    client = BybitClient()
    engine = TradingEngine(client)
    app.state.client = client
    app.state.engine = engine
    asyncio.create_task(engine.run())
    log.info("✅ NEXUS-7 online")
    yield
    engine.stop()
    await client.close()


app = FastAPI(title="NEXUS-7", version="4.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root():
    return {"status": "online", "version": "4.0.0", "bot": "NEXUS-7"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/status")
async def status(request=None):
    if hasattr(app.state, "engine"):
        return app.state.engine.status()
    return {"running": False}


@app.get("/api/balance")
async def balance():
    try:
        b = await app.state.client.get_balance()
        return {"balance_usdt": b, "ok": b >= 0}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/stop")
async def stop():
    if hasattr(app.state, "engine"):
        app.state.engine.stop()
    return {"message": "Bot pausado"}


@app.post("/api/start")
async def start():
    if hasattr(app.state, "engine"):
        asyncio.create_task(app.state.engine.run())
    return {"message": "Bot iniciado"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
