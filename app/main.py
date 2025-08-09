from fastapi import FastAPI
from . import config
from .routers import public, private

app = FastAPI(
    title=config.API_TITLE,
    version=config.API_VERSION
)

# 注册路由
app.include_router(public.router)
app.include_router(private.router)

@app.get("/")
def root():
    return {"message": "Welcome to Coinone Proxy API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000,reload=True)
