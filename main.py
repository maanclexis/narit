"""NARIT Legal Graph — root entrypoint."""

from api.main import app
from api.contribute import router as contribute_router

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
