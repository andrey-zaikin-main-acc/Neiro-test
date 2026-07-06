from fastapi import FastAPI
from app.api.routes import router
from app.db import init_db

app = FastAPI(title="KD AI Test Bench")


@app.on_event("startup")
def startup() -> None:
    init_db()


app.include_router(router)
