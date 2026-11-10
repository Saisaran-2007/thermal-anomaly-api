from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import models
from .database import Base, engine
from .routes.assets import router as assets_router
from .routes.alerts import router as alerts_router
from .routes.inspections import router as inspections_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Thermal Anomaly Detection API", lifespan=lifespan)
app.include_router(assets_router)
app.include_router(inspections_router)
app.include_router(alerts_router)
