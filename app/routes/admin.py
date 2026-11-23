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
.cheque-intro{color:#a7bad0;font-size:13px;margin:0 0 14px}
.cheque-panel{border:1px solid #27415f;background:rgba(8,16,28,.95);border-radius:14px;padding:16px}
.cheque-toolbar,.cheque-bottom{display:flex;justify-content:space-between;gap:14px;align-items:center}
.cheque-toolbar{margin-bottom:14px}.cheque-bottom{margin-top:14px}
.cheque-scroll{overflow-x:auto}.cheque-table{width:100%;border-collapse:collapse;text-align:left;min-width:750px}
.cheque-table th,.cheque-table td{padding:11px 9px;vertical-align:top;border-bottom:1px solid #233b55;font-size:13px}
.cheque-table th{color:#8fa9c8}.cheque-address summary{cursor:pointer;color:#9cbdff;font-weight:700}
.cheque-address div{margin-top:9px;white-space:pre-line;overflow-wrap:anywhere;color:#dce9fb}
.cheque-send{background:#1769ff;border:0;border-radius:8px;color:#fff;padding:9px 11px;font-weight:700;cursor:pointer}
.cheque-send:disabled{opacity:.45;cursor:not-allowed}
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

<div class="section-title">AFFILIATES</div>

<section class="grid">
  <div class="card">
    <div class="label">Registered Affiliates</div>
    <div id="affiliatesRegistered" class="value">—</div>
  </div>

  <div class="card">
    <div class="label">Total Referrals</div>
    <div id="affiliatesReferrals" class="value">—</div>
  </div>
</section>

<div class="section-title">AFFILIATE DETAILS</div>

<div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;text-align:left">
    <thead>
      <tr>
        <th>Affiliate</th>
        <th>Role</th>
        <th>Status</th>
        <th>Referrals</th>
        <th>Active</th>
        <th>Earned</th>
        <th>Available</th>
        <th>Pending</th>
      </tr>
    </thead>
    <tbody id="affiliatesTableBody">
      <tr>
        <td colspan="8">Loading affiliate data...</td>
      </tr>
    </tbody>
  </table>
</div>

<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:20px">
  <button id="affiliatesPrevious" class="logout" type="button">
    Previous
  </button>

  <span id="affiliatesPage">Page 1 of 1</span>

  <button id="affiliatesNext" class="logout" type="button">
    Next
  </button>
</div>

<div id="affiliatesStatus" class="status" role="status"></div>

<div class="section-title">AFFILIATE CHEQUES</div>
<div class="cheque-intro">First cheque: 7 days after the postal address is saved. Following cheques: monthly, when new commissions are available.</div>
<div class="cheque-panel">
  <div class="cheque-toolbar">
    <strong>Cheques to review</strong>
    <button id="chequesRefresh" class="logout" type="button">Refresh</button>
  </div>
  <div class="cheque-scroll">
    <table class="cheque-table">
      <thead><tr><th>Affiliate</th><th>Available</th><th>Due date</th><th>Mailing address</th><th>Action</th></tr></thead>
      <tbody id="chequesTableBody"><tr><td colspan="5">Loading...</td></tr></tbody>
    </table>
  </div>
  <div class="cheque-bottom">
    <button id="chequesPrevious" class="logout" type="button">Previous</button>
    <span id="chequesPage">Page 1 of 1</span>
    <button id="chequesNext" class="logout" type="button">Next</button>
  </div>
  <div id="chequesStatus" class="status" role="status"></div>
</div>
 
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

let affiliatesCurrentPage = 1;
let affiliatesTotalPages = 1;

async function loadAffiliates(page = 1) {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token) return;

  const status = document.getElementById("affiliatesStatus");
  const tbody = document.getElementById("affiliatesTableBody");
  const previous = document.getElementById("affiliatesPrevious");
  const next = document.getElementById("affiliatesNext");

  status.textContent = "Loading affiliates...";

  try {
    const response = await fetch(
      `/admin/affiliates/overview?page=${page}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json"
        },
        cache: "no-store"
      }
    );

    if (response.status === 401 || response.status === 403) {
      showLogin("Admin access required.");
      return;
    }

    if (!response.ok) {
      throw new Error("Unable to load affiliate information.");
    }

    const data = await response.json();

    if (!Array.isArray(data.affiliates)) {
      throw new Error("Invalid affiliate data.");
    }

    affiliatesCurrentPage = data.pagination.page;
    affiliatesTotalPages = data.pagination.total_pages;

    document.getElementById("affiliatesRegistered").textContent =
      data.summary.total_affiliates;

    document.getElementById("affiliatesReferrals").textContent =
      data.summary.total_referrals;

    tbody.replaceChildren();

    const money = (cents) =>
      new Intl.NumberFormat("en-CA", {
        style: "currency",
        currency: "CAD"
      }).format((Number(cents) || 0) / 100);

    if (data.affiliates.length === 0) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 8;
      cell.textContent = "No affiliates found.";
      cell.style.padding = "16px";
      row.appendChild(cell);
      tbody.appendChild(row);
    }

    data.affiliates.forEach((affiliate) => {
      const row = document.createElement("tr");

      const values = [
        affiliate.name,
        affiliate.role,
        affiliate.status,
        affiliate.total_referrals,
        affiliate.active_referrals,
        money(affiliate.commission_earned_cents),
        money(affiliate.available_cents),
        money(affiliate.pending_cents)
      ];

      values.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = String(value ?? "—");
        cell.style.padding = "12px 8px";
        cell.style.borderBottom = "1px solid #27415f";
        row.appendChild(cell);
      });

      tbody.appendChild(row);
    });

    document.getElementById("affiliatesPage").textContent =
      `Page ${affiliatesCurrentPage} of ${affiliatesTotalPages}`;

    previous.disabled = affiliatesCurrentPage <= 1;
    next.disabled = affiliatesCurrentPage >= affiliatesTotalPages;

    status.textContent = "Affiliate information updated.";

  } catch (error) {
    status.textContent = error.message;
  }
}

// CHEQUE MANAGEMENT — existing admin login and affiliate calculations are unchanged.
let chequesCurrentPage = 1;
let chequesTotalPages = 1;
let chequesBusy = false;
const chequeMoney = (cents) => new Intl.NumberFormat("en-CA", {
  style: "currency", currency: "CAD"
}).format((Number(cents) || 0) / 100);

function chequeCell(text) {
  const td = document.createElement("td");
  td.textContent = String(text ?? "—");
  return td;
}

async function loadCheques(page = 1) {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token || chequesBusy) return;
  chequesBusy = true;
  const body = document.getElementById("chequesTableBody");
  const status = document.getElementById("chequesStatus");
  status.textContent = "Loading cheques...";
  try {
    const response = await fetch(`/admin/affiliates/cheques?page=${page}`, {
      headers: {Authorization: `Bearer ${token}`, Accept: "application/json"},
      cache: "no-store"
    });
    if (response.status === 401 || response.status === 403) {
      showLogin("Admin access required."); return;
    }
    if (!response.ok) throw new Error("Unable to load cheque information.");
    const data = await response.json();
    if (!Array.isArray(data.cheques) || !data.pagination)
      throw new Error("Unexpected cheque response.");
    chequesCurrentPage = data.pagination.page;
    chequesTotalPages = data.pagination.total_pages;
    body.replaceChildren();
    if (data.cheques.length === 0) {
      const tr = document.createElement("tr");
      const td = chequeCell("No affiliates with unpaid available commissions and a saved mailing address.");
      td.colSpan = 5; tr.appendChild(td); body.appendChild(tr);
    }
    for (const item of data.cheques) {
      const row = document.createElement("tr");
      row.appendChild(chequeCell(item.name));
      row.appendChild(chequeCell(chequeMoney(item.available_cents)));
      const due = item.due_at
        ? new Date(item.due_at).toLocaleDateString("en-CA", {dateStyle:"medium",timeZone:"America/Toronto"})
        : "—";
      row.appendChild(chequeCell(due + (item.ready ? " — Ready" : " — Not due")));
      const addressTd = document.createElement("td");
      const details = document.createElement("details");
      details.className = "cheque-address";
      const summary = document.createElement("summary");
      summary.textContent = "View address";
      const address = document.createElement("div");
      const d = item.postal_address || {};
      address.textContent = [d.legal_name, d.address_line_1, d.address_line_2,
        [d.city,d.state_province,d.postal_code].filter(Boolean).join(", "),
        d.country_code, d.phone].filter(Boolean).join(" | ");
      details.append(summary,address);
      addressTd.appendChild(details);
      row.appendChild(addressTd);
      const actionTd = document.createElement("td");
      const sendButton = document.createElement("button");
      sendButton.type = "button";
      sendButton.className = "cheque-send";
      sendButton.textContent = item.ready ? "Mark cheque sent" : "Not due";
      sendButton.disabled = !item.ready;
      sendButton.addEventListener("click", () => markChequeSent(item));
      actionTd.appendChild(sendButton);
      row.appendChild(actionTd);
      body.appendChild(row);
    }
    document.getElementById("chequesPage").textContent =
      `Page ${chequesCurrentPage} of ${chequesTotalPages}`;
    document.getElementById("chequesPrevious").disabled = chequesCurrentPage <= 1;
    document.getElementById("chequesNext").disabled = chequesCurrentPage >= chequesTotalPages;
    status.textContent = `${data.summary.ready_count} cheques ready to send.`;
  } catch (error) {
    status.textContent = error.message || "Unable to load cheques.";
  } finally {
    chequesBusy = false;
  }
}

async function markChequeSent(item) {
  if (!item.ready) return;
  const prompt = `Confirm that you have ALREADY prepared and sent the cheque for ${item.name}, amount ${chequeMoney(item.available_cents)}? This records a payout and removes the amount from available commissions.`;
  if (!window.confirm(prompt)) return;
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token) { showLogin(); return; }
  const status = document.getElementById("chequesStatus");
  status.textContent = "Recording cheque...";
  try {
    const response = await fetch(`/admin/affiliates/cheques/${encodeURIComponent(item.affiliate_id)}/sent`, {
      method: "POST",
      headers: {Authorization: `Bearer ${token}`, Accept:"application/json"},
      cache: "no-store"
    });
    if (response.status === 401 || response.status === 403) {
      showLogin("Admin access required."); return;
    }
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(typeof result.detail === "string" ? result.detail : "Could not record cheque.");
    }
    await loadCheques(chequesCurrentPage);
    await loadAffiliates(affiliatesCurrentPage);
  } catch (error) {
    status.textContent = error.message || "Could not record cheque.";
  }
}

document.getElementById("chequesRefresh").addEventListener("click", () => loadCheques(chequesCurrentPage));
document.getElementById("chequesPrevious").addEventListener("click", () => {
  if (chequesCurrentPage > 1) loadCheques(chequesCurrentPage - 1);
});
document.getElementById("chequesNext").addEventListener("click", () => {
  if (chequesCurrentPage < chequesTotalPages) loadCheques(chequesCurrentPage + 1);
});

document.getElementById("affiliatesPrevious")
  .addEventListener("click", () => {
    if (affiliatesCurrentPage > 1) {
      loadAffiliates(affiliatesCurrentPage - 1);
    }
  });

document.getElementById("affiliatesNext")
  .addEventListener("click", () => {
    if (affiliatesCurrentPage < affiliatesTotalPages) {
      loadAffiliates(affiliatesCurrentPage + 1);
    }
  });

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
    
await loadAffiliates(1);
    await loadCheques(1);

  }catch(error){
    loginError.textContent=error.message||"Login failed";
  }
});
logoutButton.addEventListener("click",()=>showLogin());
loadMetrics();
loadAffiliates(1);
loadCheques(1);
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



# BLOQUE 13 — CONSULTA ADMINISTRATIVA DE AFILIADOS

@router.get("/affiliates/overview")
def get_admin_affiliates_overview(
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import case
    from app.models.affiliate import (
        AffiliateProfile,
        ReferralAttribution,
        ReferralStatus,
        AffiliateLedger,
        LedgerEntryType,
        LedgerStatus,
    )

    ensure_user_is_admin(current_user)

    if page < 1:
        raise HTTPException(
            status_code=400,
            detail="Page must be at least 1",
        )

    per_page = 20

    total_affiliates = (
        db.query(func.count(AffiliateProfile.id)).scalar()
        or 0
    )

    total_referrals = (
        db.query(func.count(ReferralAttribution.id)).scalar()
        or 0
    )

    profiles = (
        db.query(AffiliateProfile)
        .order_by(AffiliateProfile.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    profile_ids = [profile.id for profile in profiles]
    user_ids = [profile.user_id for profile in profiles]

    users = {
        user.id: user
        for user in db.query(User)
        .filter(User.id.in_(user_ids))
        .all()
    } if user_ids else {}

    referral_counts = {}

    if profile_ids:
        rows = (
            db.query(
                ReferralAttribution.referrer_profile_id,
                func.count(ReferralAttribution.id),
                func.sum(
                    case(
                        (
                            ReferralAttribution.status
                            == ReferralStatus.active,
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
            .filter(
                ReferralAttribution.referrer_profile_id.in_(
                    profile_ids
                )
            )
            .group_by(
                ReferralAttribution.referrer_profile_id
            )
            .all()
        )

        referral_counts = {
            row[0]: (
                int(row[1] or 0),
                int(row[2] or 0),
            )
            for row in rows
        }

    commission_counts = {}

    if profile_ids:
        rows = (
            db.query(
                AffiliateLedger.affiliate_profile_id,
                func.sum(
                    case(
                        (
                            AffiliateLedger.status.in_([
                                LedgerStatus.pending,
                                LedgerStatus.available,
                                LedgerStatus.paid,
                            ]),
                            AffiliateLedger.amount_cents,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            (
                                AffiliateLedger.status
                                == LedgerStatus.available
                            )
                            & AffiliateLedger.payout_id.is_(None),
                            AffiliateLedger.amount_cents,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            (
                                AffiliateLedger.status
                                == LedgerStatus.pending
                            )
                            & AffiliateLedger.payout_id.is_(None),
                            AffiliateLedger.amount_cents,
                        ),
                        else_=0,
                    )
                ),
            )
            .filter(
                AffiliateLedger.affiliate_profile_id.in_(
                    profile_ids
                ),
                AffiliateLedger.entry_type
                == LedgerEntryType.commission,
            )
            .group_by(AffiliateLedger.affiliate_profile_id)
            .all()
        )

        commission_counts = {
            row[0]: (
                int(row[1] or 0),
                int(row[2] or 0),
                int(row[3] or 0),
            )
            for row in rows
        }

    affiliates = []

    for profile in profiles:
        user = users.get(profile.user_id)
        role = profile.owner_type.value

        person = (
            user.barber if role == "barber"
            else user.client
        ) if user else None

        name = str(
            getattr(person, "name", "") or ""
        ).strip()

        if not name:
            name = user.email if user else "Unknown"

        total, active = referral_counts.get(
            profile.id,
            (0, 0),
        )

        earned, available, pending = (
            commission_counts.get(
                profile.id,
                (0, 0, 0),
            )
        )

        affiliates.append({
            "id": profile.id,
            "name": name,
            "role": role,
            "status": profile.status.value,
            "total_referrals": total,
            "active_referrals": active,
            "commission_earned_cents": earned,
            "available_cents": available,
            "pending_cents": pending,
        })

    return {
        "summary": {
            "total_affiliates": int(total_affiliates),
            "total_referrals": int(total_referrals),
        },
        "affiliates": affiliates,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_pages": max(
                1,
                (total_affiliates + per_page - 1)
                // per_page,
            ),
        },
    }

# CHEQUES — read-only eligibility view and explicit admin confirmation of mailing.
# The existing postal-address table, affiliate ledger and payout model are reused.

def _cheque_due_at(address_created_at, last_sent_at):
    """First cheque seven days after address registration; then monthly."""
    if last_sent_at is None:
        return address_created_at + timedelta(days=7)

    import calendar
    year = last_sent_at.year + (last_sent_at.month // 12)
    month = (last_sent_at.month % 12) + 1
    day = min(last_sent_at.day, calendar.monthrange(year, month)[1])
    return last_sent_at.replace(year=year, month=month, day=day)


def _cheque_utc(dt):
    return dt.isoformat(timespec="seconds") + "Z" if dt is not None else None


@router.get("/affiliates/cheques")
def get_admin_affiliate_cheques(
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.affiliate import (
        AffiliateChequeDelivery, AffiliateLedger, AffiliateProfile,
        AffiliatePayout, LedgerEntryType, LedgerStatus, PayoutStatus,
    )

    ensure_user_is_admin(current_user)
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be at least 1")

    # Batch queries: no separate query for every affiliate.
    addresses = db.query(AffiliateChequeDelivery).all()
    ids = [address.affiliate_profile_id for address in addresses]
    if not ids:
        from fastapi.responses import JSONResponse
        return JSONResponse(content={
            "summary": {"ready_count": 0},
            "cheques": [],
            "pagination": {"page": 1, "total_pages": 1, "per_page": 20},
        }, headers={"Cache-Control": "no-store"})

    profiles = {
        p.id: p for p in db.query(AffiliateProfile)
        .filter(AffiliateProfile.id.in_(ids)).all()
    }
    users = {
        u.id: u for u in db.query(User)
        .filter(User.id.in_([p.user_id for p in profiles.values()])).all()
    }
    available = dict(db.query(
        AffiliateLedger.affiliate_profile_id,
        func.coalesce(func.sum(AffiliateLedger.amount_cents), 0),
    ).filter(
        AffiliateLedger.affiliate_profile_id.in_(ids),
        AffiliateLedger.entry_type == LedgerEntryType.commission,
        AffiliateLedger.status == LedgerStatus.available,
        AffiliateLedger.payout_id.is_(None),
    ).group_by(AffiliateLedger.affiliate_profile_id).all())
    sent_dates = dict(db.query(
        AffiliatePayout.affiliate_profile_id,
        func.max(AffiliatePayout.paid_at),
    ).filter(
        AffiliatePayout.affiliate_profile_id.in_(ids),
        AffiliatePayout.status == PayoutStatus.paid,
        AffiliatePayout.paid_at.isnot(None),
    ).group_by(AffiliatePayout.affiliate_profile_id).all())

    now = datetime.utcnow()
    rows = []
    for address in addresses:
        profile = profiles.get(address.affiliate_profile_id)
        if profile is None:
            continue
        amount = int(available.get(profile.id, 0))
        if amount <= 0:
            continue
        last_sent = sent_dates.get(profile.id)
        due_at = _cheque_due_at(address.created_at, last_sent)
        # Initial cheque requires CA$50. Subsequent monthly cheques may
        # contain a smaller amount if new commission earnings exist.
        qualified = amount >= 5000 if last_sent is None else amount > 0
        ready = qualified and now >= due_at
        user = users.get(profile.user_id)
        person = (
            (user.barber if profile.owner_type.value == "barber" else user.client)
            if user is not None else None
        )
        name = str(getattr(person, "name", "") or "").strip()
        if not name:
            name = user.email if user is not None else "Unknown"
        rows.append({
            "affiliate_id": profile.id,
            "name": name,
            "available_cents": amount,
            "ready": ready,
            "due_at": _cheque_utc(due_at),
            "due_sort": due_at,
            "postal_address": {
                "legal_name": address.legal_name,
                "address_line_1": address.address_line_1,
                "address_line_2": address.address_line_2,
                "city": address.city,
                "state_province": address.state_province,
                "postal_code": address.postal_code,
                "country_code": address.country_code,
                "phone": address.phone,
            },
        })
    rows.sort(key=lambda r: (not r["ready"], r["due_sort"], r["affiliate_id"]))
    ready_count = sum(1 for row in rows if row["ready"])
    per_page = 20
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)
    chunk = rows[(page - 1) * per_page: page * per_page]
    for row in chunk:
        del row["due_sort"]

    from fastapi.responses import JSONResponse
    return JSONResponse(content={
        "summary": {"ready_count": ready_count},
        "cheques": chunk,
        "pagination": {"page": page, "total_pages": total_pages, "per_page": per_page},
    }, headers={"Cache-Control": "no-store"})


@router.post("/affiliates/cheques/{affiliate_id}/sent")
def mark_admin_affiliate_cheque_sent(
    affiliate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.affiliate import (
        AffiliateChequeDelivery, AffiliateLedger, AffiliateProfile,
        AffiliatePayout, LedgerEntryType, LedgerStatus, PayoutStatus,
    )

    ensure_user_is_admin(current_user)
    try:
        # Lock the profile to prevent two simultaneous cheque records.
        profile = db.query(AffiliateProfile).filter(
            AffiliateProfile.id == affiliate_id
        ).with_for_update().first()
        if profile is None:
            raise HTTPException(status_code=404, detail="Affiliate not found")

        address = db.query(AffiliateChequeDelivery).filter(
            AffiliateChequeDelivery.affiliate_profile_id == profile.id
        ).first()
        if address is None:
            raise HTTPException(status_code=409, detail="No mailing address saved")

        last_sent = db.query(func.max(AffiliatePayout.paid_at)).filter(
            AffiliatePayout.affiliate_profile_id == profile.id,
            AffiliatePayout.status == PayoutStatus.paid,
            AffiliatePayout.paid_at.isnot(None),
        ).scalar()
        now = datetime.utcnow()
        if now < _cheque_due_at(address.created_at, last_sent):
            raise HTTPException(status_code=409, detail="Cheque is not due yet")

        entries = db.query(AffiliateLedger).filter(
            AffiliateLedger.affiliate_profile_id == profile.id,
            AffiliateLedger.entry_type == LedgerEntryType.commission,
            AffiliateLedger.status == LedgerStatus.available,
            AffiliateLedger.payout_id.is_(None),
        ).order_by(AffiliateLedger.id).with_for_update().all()
        amount = sum(int(e.amount_cents) for e in entries)
        threshold = 5000 if last_sent is None else 1
        if amount < threshold:
            raise HTTPException(
                status_code=409,
                detail="Insufficient available commissions for this cheque",
            )

        # The admin must confirm that the cheque has actually been mailed.
        # This is a database record only; no physical mailing is performed.
        payout = AffiliatePayout(
            affiliate_profile_id=profile.id,
            amount_cents=amount,
            status=PayoutStatus.paid,
            external_reference="cheque_sent_by_admin",
            requested_at=now,
            paid_at=now,
        )
        db.add(payout)
        db.flush()
        for entry in entries:
            entry.payout_id = payout.id
            entry.status = LedgerStatus.paid
            entry.paid_at = now
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    from fastapi.responses import JSONResponse
    return JSONResponse(content={
        "recorded": True,
        "payout_id": payout.id,
        "amount_cents": amount,
        "sent_at": _cheque_utc(now),
    }, headers={"Cache-Control": "no-store"})
