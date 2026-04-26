from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.auth import router as auth_router
from app.routes.bookings import router as bookings_router
from app.routes.payments import router as payments_router
from app.routes.reviews import router as reviews_router
from app.routes.barbers import router as barbers_router
from app.routes.clients import router as clients_router

from app.database import engine, Base
from app.models import user, barber, service, booking, review

app = FastAPI(
    title="InstantBarber API",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True}
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "https://instantbarbers.com",
        "https://www.instantbarbers.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(bookings_router)
app.include_router(payments_router)
app.include_router(reviews_router)
app.include_router(barbers_router)
app.include_router(clients_router)

# 🔥 FIX PROFESIONAL (startup controlado)
@app.on_event("startup")
def on_startup():
    print("🚀 Starting InstantBarber API...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database connected and tables ready")
    except Exception as e:
        print("❌ Database connection failed:", str(e))

# Health check (clave para Render)
@app.get("/")
def read_root():
    return {"status": "ok", "message": "InstantBarber API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
