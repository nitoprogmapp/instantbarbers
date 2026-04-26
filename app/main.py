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

app.include_router(auth_router, prefix="/auth", tags=["Auth"])

# ✔ Bookings limpio
app.include_router(bookings_router)

# ✔ Payments limpio
app.include_router(payments_router)

# ✔ Reviews limpio
app.include_router(reviews_router)

# ✅ Barbers limpio
app.include_router(barbers_router)

# 🔴 Clients queda igual por ahora
app.include_router(clients_router)
Base.metadata.create_all(bind=engine)

@app.get("/")
def read_root():
    return {"message": "InstantBarber API is running"}

