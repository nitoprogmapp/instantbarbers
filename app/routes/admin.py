from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database import get_db
from app.models.user import User, UserRole
from app.models.barber import Barber
from app.models.booking import Booking, BookingStatus
from app.routes.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])

BARBER_ONLINE_TIMEOUT_SECONDS = 90
LOCAL_TIMEZONE = ZoneInfo("America/Toronto")


def ensure_user_is_admin(current_user: User):
    role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>InstantBarbers Admin</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font-family:Arial,Helvetica,sans-serif;background:radial-gradient(circle at top,#0d2748 0%,#08111f 35%,#05080d 72%);color:#fff}
.page{width:min(1180px,calc(100% - 32px));margin:0 auto;padding:34px 0 50px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:28px}
.brand h1{margin:0;font-size:clamp(26px,4vw,42px);letter-spacing:-.8px}
.brand p{margin:7px 0 0;color:#8fa9c8;font-size:14px}
.logout{border:1px solid #1f67ff;background:transparent;color:#fff;border-radius:10px;padding:10px 16px;font-weight:700;cursor:pointer}
.section-title{margin:26px 0 13px;font-size:14px;letter-spacing:1.8px;color:#5fa0ff;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.card{min-height:164px;border:1px solid rgba(56,129,255,.30);background:linear-gradient(145deg,rgba(12,28,50,.96),rgba(8,16,28,.96));border-radius:18px;padding:24px;box-shadow:0 16px 40px rgba(0,0,0,.28);display:flex;flex-direction:column;justify-content:space-between}
.label{color:#a7bad0;font-size:15px;font-weight:700}
.value{font-size:clamp(42px,6vw,64px);line-height:1;font-weight:900;letter-spacing:-2px;color:#fff}
.online-dot{display:inline-block;width:9px;height:9px;border-radius:999px;background:#25dc7a;margin-right:8px;box-shadow:0 0 14px rgba(37,220,122,.8)}
.status{margin-top:22px;color:#6f88a6;font-size:12px;text-align:right}
.login-wrap{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(3,8,15,.92);backdrop-filter:blur(8px);z-index:10}
.login-card{width:min(430px,100%);border:1px solid rgba(56,129,255,.35);background:#08111f;border-radius:20px;padding:30px;box-shadow:0 25px 70px rgba(0,0,0,.55)}
.login-card h2{margin:0 0 6px;font-size:28px}
.login-card p{margin:0 0 24px;color:#8fa9c8}
.field{margin-bottom:15px}
label{display:block;margin-bottom:7px;color:#b7c6d8;font-size:13px;font-weight:700}
input{width:100%;padding:13px 14px;border-radius:10px;border:1px solid #27415f;background:#050b13;color:#fff;outline:none;font-size:15px}
.login-button{width:100%;margin-top:7px;padding:13px 16px;border:0;border-radius:10px;background:#1769ff;color:#fff;font-size:15px;font-weight:800;cursor:pointer}
.error{min-height:18px;margin-top:13px;color:#ff7474;font-size:13px}
.hidden{display:none!important}
@media(max-width:760px){.grid{grid-template-columns:1fr}.topbar{align-items:flex-start}.card{min-height:140px}}
</style>
</head>
<body>
<div id="loginWrap" class="login-wrap">
<form id="loginForm" class="login-card">
<h2>InstantBarbers Admin</h2>
<p>Private access</p>
<div class="field"><label for="email">Email</label><input id="email" type="email" autocomplete="username" required></div>
<div class="field"><label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required></div>
<button class="login-button" type="submit">Sign in</button>
<div id="loginError" class="error"></div>
</form>
</div>

<main class="page">
<div class="topbar">
<div class="brand"><h1>InstantBarbers Admin</h1><p>Private operational dashboard</p></div>
<button id="logoutButton" class="logout" type="button">Logout</button>
</div>

<div class="section-title">BARBERS</div>
<section class="grid">
<div class="card"><div class="label">Registered</div><div id="barbersRegistered" class="value">—</div></div>
<div class="card"><div class="label">Activated</div><div id="barbersActivated" class="value">—</div></div>
<div class="card"><div class="label"><span class="online-dot"></span>Online</div><div id="barbersOnline" class="value">—</div></div>
</section>

<div class="section-title">CUSTOMERS</div>
<section class="grid">
<div class="card"><div class="label">Registered</div><div id="clientsRegistered" class="value">—</div></div>
<div class="card"><div class="label">Activated</div><div id="clientsActivated" class="value">—</div></div>
<div class="card"><div class="label">Haircuts Today</div><div id="haircutsToday" class="value">—</div></div>
</section>
<div id="status" class="status"></div>
</main>

<script>
const TOKEN_KEY="instantbarbers_admin_token";
const loginWrap=document.getElementById("loginWrap");
const loginForm=document.getElementById("loginForm");
const loginError=document.getElementById("loginError");
const logoutButton=document.getElementById("logoutButton");
const statusText=document.getElementById("status");

function showLogin(message=""){
  sessionStorage.removeItem(TOKEN_KEY);
  loginError.textContent=message;
  loginWrap.classList.remove("hidden");
}
function hideLogin(){
  loginError.textContent="";
  loginWrap.classList.add("hidden");
}
async function loadMetrics(){
  const token=sessionStorage.getItem(TOKEN_KEY);
  if(!token){showLogin();return;}
  try{
    const response=await fetch("/admin/metrics",{headers:{"Authorization":`Bearer ${token}`}});
    if(response.status===401||response.status===403){showLogin("Admin access required.");return;}
    if(!response.ok) throw new Error("Could not load metrics");
    const data=await response.json();
    document.getElementById("barbersRegistered").textContent=data.barbers.registered;
    document.getElementById("barbersActivated").textContent=data.barbers.activated;
    document.getElementById("barbersOnline").textContent=data.barbers.online;
    document.getElementById("clientsRegistered").textContent=data.clients.registered;
    document.getElementById("clientsActivated").textContent=data.clients.activated;
    document.getElementById("haircutsToday").textContent=data.haircuts.completed_today;
    statusText.textContent="Updated: "+new Date().toLocaleTimeString();
    hideLogin();
  }catch(error){
    statusText.textContent="Unable to refresh dashboard.";
  }
}
loginForm.addEventListener("submit",async(event)=>{
  event.preventDefault();
  loginError.textContent="";
  const email=document.getElementById("email").value.trim();
  const password=document.getElementById("password").value;
  try{
    const response=await fetch("/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok||!data.access_token) throw new Error(data.detail||"Login failed");
    if(data.role!=="admin") throw new Error("Admin access required");
    sessionStorage.setItem(TOKEN_KEY,data.access_token);
    document.getElementById("password").value="";
    await loadMetrics();
  }catch(error){
    loginError.textContent=error.message||"Login failed";
  }
});
logoutButton.addEventListener("click",()=>showLogin());
loadMetrics();
setInterval(loadMetrics,5000);
</script>
</body>
</html>"""


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard():
    return HTMLResponse(content=ADMIN_HTML)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard_slash():
    return HTMLResponse(content=ADMIN_HTML)


@router.get("/metrics")
def get_admin_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_user_is_admin(current_user)

    registered_barbers = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.barber)
        .scalar()
        or 0
    )

    activated_barbers = (
        db.query(func.count(func.distinct(Booking.barber_id)))
        .filter(
            Booking.status == BookingStatus.completed,
            Booking.barber_id.isnot(None),
        )
        .scalar()
        or 0
    )

    online_cutoff = datetime.utcnow() - timedelta(seconds=BARBER_ONLINE_TIMEOUT_SECONDS)

    online_barbers = (
        db.query(func.count(Barber.id))
        .filter(
            Barber.active.is_(True),
            Barber.last_seen_at.isnot(None),
            Barber.last_seen_at >= online_cutoff,
        )
        .scalar()
        or 0
    )

    registered_clients = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.client)
        .scalar()
        or 0
    )

    activated_clients = (
        db.query(func.count(func.distinct(Booking.client_id)))
        .filter(
            Booking.status == BookingStatus.completed,
            Booking.client_id.isnot(None),
        )
        .scalar()
        or 0
    )

    now_local = datetime.now(LOCAL_TIMEZONE)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)

    haircuts_today = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.status == BookingStatus.completed,
            Booking.completed_at.isnot(None),
            Booking.completed_at >= start_utc,
            Booking.completed_at < end_utc,
        )
        .scalar()
        or 0
    )

    return {
        "barbers": {
            "registered": registered_barbers,
            "activated": activated_barbers,
            "online": online_barbers,
        },
        "clients": {
            "registered": registered_clients,
            "activated": activated_clients,
        },
        "haircuts": {
            "completed_today": haircuts_today,
        },
    }