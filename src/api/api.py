import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.configs.config import logger
from src.routers import admin, chat, client, payment, provider, user , casemanager
from src.authentication.auth_middleware import AuthMiddleware

logger.log_info("Server started!")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Attach authentication middleware; exempt public endpoints
app.add_middleware(
    AuthMiddleware,
    exempt_paths=[
        "/"
        # "/health",           # health sub-app
        # "/images",           # static mounts
        # "/avatars",
        # "/adbanner",
        # "/brochure",
        # "/a",
        # "/resume",
        # "/users/login",      # login endpoint
        # "/users/forgot-password",
        # "/users/verify-otp",
        # "/users/reset-password",
        # "/users/email-validation",
        # "/users/send-otp",
        # "/users/contact-us",
        # "/users/avatar",     # optional: if you want avatars public
    ],
    allow_docs=True,
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMAGE_DIR = os.path.join(BASE_DIR, "hfe_images")
AVATAR_DIR = os.path.join(BASE_DIR, "avatars")
ADBANNER_PATH = os.path.join(BASE_DIR, "adbanner")
BROCHURE = os.path.join(BASE_DIR, "brochure")
ATTACHMENT = os.path.join(BASE_DIR, "attachments")
RESUME = os.path.join(BASE_DIR, "resume")
IMPORT_PROVIDER = os.path.join(BASE_DIR,"import_provider")

# Ensure directories exist
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(IMPORT_PROVIDER, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(ADBANNER_PATH, exist_ok=True)
os.makedirs(BROCHURE, exist_ok=True)
os.makedirs(ATTACHMENT, exist_ok=True)
os.makedirs(RESUME, exist_ok=True)

# Serve static files
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")
app.mount("/avatars", StaticFiles(directory=AVATAR_DIR), name="avatars")
app.mount("/adbanner", StaticFiles(directory=ADBANNER_PATH), name="adbanner")
app.mount("/brochure", StaticFiles(directory=BROCHURE), name="brochure")
app.mount("/a", StaticFiles(directory=ATTACHMENT), name="a")
app.mount("/resume", StaticFiles(directory=RESUME), name="resume")

healthcheck_app = FastAPI(
    title="Fast api healthcheck app",
    description="API for healthchecks",
)


@healthcheck_app.get("/")
def health_home():
    return {"message": "Hello from Fast app! V1"}


app.mount("/health", healthcheck_app)


app.include_router(user.router)
app.include_router(chat.router)
app.include_router(casemanager.router)
app.include_router(admin.router)
app.include_router(provider.router)
app.include_router(client.router)
app.include_router(payment.router)
# app.include_router(notification.router)
