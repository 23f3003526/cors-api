from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
import time
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import jwt

EMAIL = "23f3003526@ds.study.iitm.ac.in"
ALLOWED_ORIGIN = "https://dash-e51i9s.example.com"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_headers(request: Request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Process-Time"] = f"{time.perf_counter()-start:.6f}"

    return response


@app.get("/stats")
async def stats(values: str = Query(...)):
    nums = [int(x.strip()) for x in values.split(",")]

    return {
        "email": EMAIL,
        "count": len(nums),
        "sum": sum(nums),
        "min": min(nums),
        "max": max(nums),
        "mean": sum(nums) / len(nums)
    }
ISSUER = "https://idp.exam.local"
AUDIENCE = "tds-ww7kmemd.apps.exam.local"

PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2okOHspNjgA+2rTLbeuY
cxiP/hG8C6Sb9iwg3yiLAA4HCnpITcbWCSelbvbYGuc3EbNy4xFyf5Cbj5DHJMID
EkryOgyd2giIIIBOUBj8S63uGcnRpOBh9NFatfNwheKuzsPuVNldu6A9cNteNpXc
WyJjG2axVfmq7i6SuKr1JoWYG7xTTAvKPujSl4OtsQfO3h5NepzdfXpr28oNnzfW
ed+zclR6BcmNNo/WVfJ4xyCLSf0BCOgdTgW6PdaChd1l9VDetJZVEgC5tkyvXsfI
SI6iyrYbKR0NEBSqq4XkadEjsCs4LlgniT7GlkL9Mce3b0wGLs9/7ZIX
dQIDAQAB
-----END PUBLIC KEY-----"""

class TokenRequest(BaseModel):
    token: str

@app.post("/verify")
async def verify(req: TokenRequest):
    try:
        payload = jwt.decode(
            req.token,
            PUBLIC_KEY,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
        )

        return {
            "valid": True,
            "email": payload.get("email"),
            "sub": payload.get("sub"),
            "aud": payload.get("aud"),
        }

    except Exception as e:
     return JSONResponse(
        status_code=401,
        content={
            "valid": False,
            "error": type(e).__name__,
            "message": str(e),
        },
     )  
    
import os
import yaml
from dotenv import load_dotenv
from fastapi import Query

load_dotenv()


def to_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes", "on")


@app.get("/effective-config")
async def effective_config(set: list[str] = Query(default=[])):
    # defaults
    cfg = {
        "port": 8000,
        "workers": 1,
        "debug": False,
        "log_level": "info",
        "api_key": "default-secret-000",
    }

    # yaml
    if os.path.exists("config.development.yaml"):
        with open("config.development.yaml") as f:
            cfg.update(yaml.safe_load(f))

    # .env
    if os.getenv("APP_PORT"):
        cfg["port"] = os.getenv("APP_PORT")

    if os.getenv("NUM_WORKERS"):
        cfg["workers"] = os.getenv("NUM_WORKERS")

    if os.getenv("APP_API_KEY"):
        cfg["api_key"] = os.getenv("APP_API_KEY")

    # OS env (higher precedence)
    if os.getenv("APP_PORT"):
        cfg["port"] = os.getenv("APP_PORT")

    if os.getenv("APP_WORKERS"):
        cfg["workers"] = os.getenv("APP_WORKERS")

    if os.getenv("APP_DEBUG"):
        cfg["debug"] = os.getenv("APP_DEBUG")

    if os.getenv("APP_LOG_LEVEL"):
        cfg["log_level"] = os.getenv("APP_LOG_LEVEL")

    if os.getenv("APP_API_KEY"):
        cfg["api_key"] = os.getenv("APP_API_KEY")

    # CLI overrides
    for item in set:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        cfg[k] = v

    # Type coercion
    cfg["port"] = int(cfg["port"])
    cfg["workers"] = int(cfg["workers"])
    cfg["debug"] = to_bool(cfg["debug"])
    cfg["log_level"] = str(cfg["log_level"])

    # Secret masking
    cfg["api_key"] = "****"

    return cfg    