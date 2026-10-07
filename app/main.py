from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.routes.auth import router as auth_router
from app.routes.bookings import router as bookings_router
from app.routes.payments import router as payments_router
from app.routes.square_oauth import router as square_oauth_router
from app.routes.square_payments import router as square_payments_router
from app.routes.square_webhooks import router as square_webhooks_router
from app.routes.reviews import router as reviews_router
from app.routes.barbers import router as barbers_router
from app.routes.clients import router as clients_router
from app.routes.stripe_webhooks import router as stripe_webhooks_router
from app.routes.admin import router as admin_router
from app.database import engine, Base
from app.models import user, barber, service, booking, review, payment_connection, payment_attempt
from app.models import square_webhook
from app.routes.square_token_refresh import start_maintenance, stop_maintenance

app = FastAPI(title="InstantBarber API", version="1.0.0",
              swagger_ui_parameters={"persistAuthorization": True})
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
        "https://instantbarbers.com", "https://www.instantbarbers.com",
        "https://ec257e2f-ca81-45a9-aedc-c16de05edb86.app-preview.com",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(bookings_router)
app.include_router(payments_router)
app.include_router(square_oauth_router)
app.include_router(square_payments_router)
app.include_router(square_webhooks_router)
app.include_router(reviews_router)
app.include_router(barbers_router)
app.include_router(clients_router)
app.include_router(stripe_webhooks_router)
app.include_router(admin_router)

@app.on_event("startup")
def on_startup():
    print("Starting InstantBarber API...")
    try:
        Base.metadata.create_all(bind=engine)
        print("Database connected and tables ready")
        start_maintenance(app)
        print("Square OAuth automatic maintenance started")
    except Exception as e:
        print("Database connection failed:", str(e))

@app.on_event("shutdown")
def on_shutdown():
    stop_maintenance(app)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "InstantBarber API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
