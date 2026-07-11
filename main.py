from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import base64
import io
import os
import time
import uuid

import jwt
from PIL import Image
from google import genai


# =========================================================
# APP SETUP
# =========================================================

app = FastAPI()


# =========================================================
# CORS
# =========================================================

# Allows the image grader and other browser clients
# to send cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# RESPONSE HEADERS
# =========================================================

@app.middleware("http")
async def add_headers(request: Request, call_next):
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = time.perf_counter() - start_time

    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Process-Time"] = f"{process_time:.6f}"

    return response


# =========================================================
# HOME ENDPOINT
# =========================================================

@app.get("/")
async def home():
    return {
        "status": "running",
        "available_endpoints": [
            "GET /stats",
            "POST /verify",
            "POST /answer-image",
        ],
    }


# =========================================================
# STATS API
# =========================================================

EMAIL = "23f3003526@ds.study.iitm.ac.in"


@app.get("/stats")
async def stats(values: str = Query(...)):
    try:
        nums = [
            int(value.strip())
            for value in values.split(",")
        ]

        if not nums:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "At least one number is required"
                },
            )

        return {
            "email": EMAIL,
            "count": len(nums),
            "sum": sum(nums),
            "min": min(nums),
            "max": max(nums),
            "mean": sum(nums) / len(nums),
        }

    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "error": "All values must be integers"
            },
        )


# =========================================================
# JWT VERIFICATION API
# =========================================================

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
            key=PUBLIC_KEY,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={
                "require": [
                    "exp",
                    "iss",
                    "aud",
                ]
            },
        )

        return {
            "valid": True,
            "email": payload.get("email"),
            "sub": payload.get("sub"),
            "aud": payload.get("aud"),
        }

    except jwt.PyJWTError:
        return JSONResponse(
            status_code=401,
            content={
                "valid": False
            },
        )


# =========================================================
# MULTIMODAL IMAGE QUESTION-ANSWERING API
# =========================================================

class ImageQuestionRequest(BaseModel):
    image_base64: str
    question: str


@app.post("/answer-image")
async def answer_image(
    req: ImageQuestionRequest
):
    try:
        # Read the Gemini API key from Render.
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            return JSONResponse(
                status_code=500,
                content={
                    "error": (
                        "GEMINI_API_KEY is not configured"
                    )
                },
            )

        client = genai.Client(
            api_key=api_key
        )

        image_data = req.image_base64.strip()

        # Supports data URLs such as:
        # data:image/png;base64,iVBORw0KGgo...
        if image_data.startswith("data:"):
            image_data = image_data.split(
                ",",
                1,
            )[1]

        # Decode the base64 image.
        image_bytes = base64.b64decode(
            image_data
        )

        # Convert the decoded bytes into an image.
        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        prompt = f"""
Analyze the supplied image carefully.

Question:
{req.question}

Return only the final answer.

Rules:
- Do not provide an explanation.
- Do not include labels or introductory text.
- If the answer is numeric, return only the number.
- Do not include currency symbols.
- Do not include commas in numeric answers.
- Do not include measurement units.
- Perform any required arithmetic carefully.
- The response must be concise.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                prompt,
                image,
            ],
        )

        answer = (
            response.text or ""
        ).strip()

        return {
            "answer": str(answer)
        }

    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": str(error)
            },
        )