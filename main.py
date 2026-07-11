from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import base64
import io
import os
import time
import traceback
import uuid

import jwt
from PIL import Image
from google import genai


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI()


# =========================================================
# CORS
# =========================================================

# Allow the grader's Cloudflare Worker to call the API.
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
async def add_headers(
    request: Request,
    call_next,
):
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = (
        time.perf_counter() - start_time
    )

    response.headers["X-Request-ID"] = (
        str(uuid.uuid4())
    )

    response.headers["X-Process-Time"] = (
        f"{process_time:.6f}"
    )

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
# STATISTICS API
# =========================================================

EMAIL = "23f3003526@ds.study.iitm.ac.in"


@app.get("/stats")
async def stats(
    values: str = Query(...)
):
    try:
        nums = [
            int(value.strip())
            for value in values.split(",")
        ]

        if len(nums) == 0:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        "At least one number "
                        "is required"
                    )
                },
            )

        return {
            "email": EMAIL,
            "count": len(nums),
            "sum": sum(nums),
            "min": min(nums),
            "max": max(nums),
            "mean": (
                sum(nums) / len(nums)
            ),
        }

    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    "All values must be integers"
                )
            },
        )


# =========================================================
# JWT VERIFICATION API
# =========================================================

ISSUER = "https://idp.exam.local"

AUDIENCE = (
    "tds-ww7kmemd.apps.exam.local"
)


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
async def verify(
    req: TokenRequest
):
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
            "email": payload.get(
                "email"
            ),
            "sub": payload.get(
                "sub"
            ),
            "aud": payload.get(
                "aud"
            ),
        }

    except jwt.PyJWTError:
        return JSONResponse(
            status_code=401,
            content={
                "valid": False
            },
        )


# =========================================================
# IMAGE QUESTION-ANSWERING API
# =========================================================

class ImageQuestionRequest(BaseModel):
    image_base64: str
    question: str


@app.post("/answer-image")
async def answer_image(
    req: ImageQuestionRequest
):
    try:

        # IMPORTANT:
        # This must match the environment-variable
        # name shown in your Render screenshot.
        api_key = os.getenv(
            "Gemini_API_Key"
        )

        # Print only whether the key exists.
        # Never print the actual API key.
        print(
            "Gemini key found:",
            bool(api_key),
            flush=True,
        )

        if not api_key:

            print(
                "ERROR: Render environment "
                "variable Gemini_API_Key "
                "was not found.",
                flush=True,
            )

            return JSONResponse(
                status_code=500,
                content={
                    "error": (
                        "Gemini API key "
                        "is not configured"
                    )
                },
            )

        # Create Gemini client.
        client = genai.Client(
            api_key=api_key
        )

        # Get base64 text.
        image_data = (
            req.image_base64.strip()
        )

        # Support data URLs such as:
        #
        # data:image/png;base64,
        # iVBORw0KGgo...
        if image_data.startswith(
            "data:"
        ):
            image_data = (
                image_data.split(
                    ",",
                    1,
                )[1]
            )

        # Remove spaces and line breaks
        # that may occur in base64 strings.
        image_data = "".join(
            image_data.split()
        )

        # Convert base64 text into bytes.
        image_bytes = (
            base64.b64decode(
                image_data
            )
        )

        # Open and validate the image.
        image = Image.open(
            io.BytesIO(
                image_bytes
            )
        )

        # Convert all image types to RGB.
        image = image.convert("RGB")

        prompt = f"""
Carefully inspect the supplied image.

Answer this question:

{req.question}

Output requirements:

1. Return only the final answer.
2. Do not provide an explanation.
3. Do not add a label or introduction.
4. If the answer is numeric, return only
   the number.
5. Do not include currency symbols.
6. Do not include units.
7. Do not include commas in numbers.
8. Perform any required calculations
   carefully.
9. The answer must be concise.
"""

        # Send both the question
        # and image to Gemini.
        response = (
            client.models.generate_content(
                model=(
                    "gemini-2.5-flash"
                ),
                contents=[
                    prompt,
                    image,
                ],
            )
        )

        answer = (
            response.text or ""
        ).strip()

        if not answer:

            print(
                "ERROR: Gemini returned "
                "an empty answer.",
                flush=True,
            )

            return JSONResponse(
                status_code=500,
                content={
                    "error": (
                        "The model returned "
                        "an empty answer"
                    )
                },
            )

        # Required response format:
        #
        # {"answer": "4089.35"}
        return {
            "answer": str(answer)
        }

    except Exception as error:

        print(
            "ANSWER-IMAGE ERROR:",
            type(error).__name__,
            str(error),
            flush=True,
        )

        # Print the complete error
        # in Render logs.
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(error)
            },
        )