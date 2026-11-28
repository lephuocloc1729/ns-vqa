"""The admin site's API: /v1/admin/... (docs/plans/admin-page.md).

Every endpoint checks the admin login itself (HTTP basic auth, VQA_ADMIN_USER / VQA_ADMIN_PASSWORD),
even though the web server also asks for it on admin.<domain> and hides /v1/admin on the public
site. Without VQA_ADMIN_PASSWORD every endpoint answers 404.

It reads stored answers and feedback and changes live settings and site accounts (create, reset the
password, turn on or off, delete; a deleted account's questions keep its name). The pipeline
never reads anything written here except the live settings (app/api/live.py).
"""

from __future__ import annotations

import base64
import csv
import hmac
import io
import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api import accounts as acc
from app.api import gpu as gpu_mod
from app.api import live as live_mod
from app.api.settings import Settings
from app.api.storage import Store, Turn

VN = timezone(timedelta(hours=7))        # days on the dashboard are Vietnam days
SECONDS_BUCKETS = [5, 10, 15, 20, 30, 45, 60, 90, 120]


# ---------------------------------------------------------------------- helpers
def _naive_utc(d: datetime) -> datetime:
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _aware(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def day_range(since: date | None, until: date | None) -> tuple[datetime | None, datetime | None]:
    """Vietnam calendar days [since, until] as naive UTC bounds (the stored times are UTC)."""
    a = _naive_utc(datetime.combine(since, datetime.min.time(), VN)) if since else None
    b = _naive_utc(datetime.combine(until + timedelta(days=1), datetime.min.time(), VN)) if until else None
    return a, b


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def latest_feedback(t: Turn) -> dict[str, Any]:
    """The latest thumb, and whether any feedback corrected the answer or left a note."""
    thumb = None
    for f in t.feedback or []:
        if f.thumb:
            thumb = f.thumb
    corrected = [f.corrected_answer for f in t.feedback or [] if f.corrected_answer]
    notes = [f.note for f in t.feedback or [] if f.note]
    return {"thumb": thumb, "corrected_answer": corrected[-1] if corrected else None,
            "note": notes[-1] if notes else None}


def route_of(t: Turn) -> str:
    """rules | rag | rag_cache | fallback (Claude) | not_decided | error | running."""
    if t.status != "done":
        return t.status
    if t.answered_by == "fallback":
        if "rag" in (t.basis or []):
            fb = (t.stages or {}).get("fallback") or {}
            return "rag_cache" if fb.get("cache_hit") else "rag"
        return "fallback"
    return t.answered_by or "none"


def summary(t: Turn) -> dict[str, Any]:
    fb = latest_feedback(t)
    return {"turn_id": t.id, "session_id": t.session_id, "created_at": _aware(t.created_at).isoformat(),
            "account": t.account, "question": t.question, "understood_as": t.understood_as,
            "image_sha256": t.image_sha256,
            "status": t.status, "verdict": t.verdict, "route": route_of(t),
            "answer": t.answer_text, "seconds": t.seconds, "cost_usd": t.cost_usd, "error": t.error,
            **fb}


def first_on_photo(turns: list[Turn]) -> set[str]:
    """Ids of turns that were the first question ever asked on their photo (turns sorted by time)."""
    seen: set[str] = set()
    out: set[str] = set()
    for t in turns:
        if t.image_sha256 not in seen:
            seen.add(t.image_sha256)
            out.add(t.id)
    return out


# ---------------------------------------------------------------------- request bodies
class SettingsIn(BaseModel):
    answer_fallback: str | None = None
    rag_url: str | None = None
    rag_cache: bool | None = None
    spend_limit: float | None = None
    followup: bool | None = None


class AccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    note: str | None = Field(default=None, max_length=200)


class GpuIn(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int


class SiteLoginIn(BaseModel):
    required: bool


class AccountPatch(BaseModel):
    enabled: bool | None = None
    note: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------------- the router
def admin_guard(settings: Settings) -> Callable[[Request], None]:
    """A FastAPI dependency that lets only the admin login through (404 without VQA_ADMIN_PASSWORD)."""
    def require_admin(request: Request) -> None:
        if not settings.admin_password:
            raise HTTPException(404, "Not Found")
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                ok = (hmac.compare_digest(user.encode(), settings.admin_user.encode())
                      and hmac.compare_digest(pw.encode(), settings.admin_password.encode()))
            except (ValueError, UnicodeDecodeError):
                ok = False
        if not ok:
            raise HTTPException(401, "cần đăng nhập quản trị", headers={"WWW-Authenticate": 'Basic realm="SignCite admin"'})
    return require_admin


def admin_router(settings: Settings, store: Store, live_now: Callable[[], live_mod.Live],
                 runner: Any, rag_cache_folder: Callable[[], Any],
                 rag_health: Callable[[str], tuple[bool, str]] | None = None) -> APIRouter:
    r = APIRouter(prefix="/v1/admin", tags=["admin"])

    require_admin = admin_guard(settings)

    def check_rag(url: str) -> tuple[bool, str]:
        if rag_health is not None:
            return rag_health(url)
        try:
            res = httpx.get(url.rstrip("/") + "/health", timeout=4.0)
            if res.status_code == 200 and "ok" in res.text:
                return True, "ok"
            return False, f"HTTP {res.status_code}"
        except httpx.HTTPError as e:
            return False, type(e).__name__

    def sync_site_users() -> None:
        sync_users(settings, store)

    def spend() -> dict[str, Any]:
        guard = getattr(runner.pipeline, "guard", None) if runner.loaded else None
        if guard is None:
            return {"spent": None, "limit": live_now().spend_limit, "loaded": runner.loaded}
        return {"spent": round(guard.spent, 4), "limit": guard.limit, "loaded": True}

    deps = [Depends(require_admin)]

    # ------------------------------------------------------------------ data
    @r.get("/overview", dependencies=deps)
    def overview(since: date | None = None, until: date | None = None) -> dict[str, Any]:
        a, b = day_range(since, until)
        turns = store.turns_between(a, b)
        firsts = first_on_photo(store.turns_between(None, b)) if turns else set()
        done = [t for t in turns if t.status == "done"]
        routes = Counter(route_of(t) for t in turns)
        secs = [t.seconds for t in done if t.seconds is not None]
        fbs = [latest_feedback(t) for t in turns]
        up = sum(f["thumb"] == "up" for f in fbs)
        down = sum(f["thumb"] == "down" for f in fbs)
        per_day: dict[str, dict[str, Any]] = defaultdict(lambda: {"questions": 0, "rules": 0, "rag": 0, "rag_cache": 0,
                                                                  "fallback": 0, "not_decided": 0, "error": 0,
                                                                  "cost_usd": 0.0})
        for t in turns:
            d = per_day[_aware(t.created_at).astimezone(VN).date().isoformat()]
            d["questions"] += 1
            rt = route_of(t)
            if rt in d:
                d[rt] += 1
            d["cost_usd"] += t.cost_usd or 0.0
        hist = [0] * (len(SECONDS_BUCKETS) + 1)
        for x in secs:
            hist[next((i for i, lim in enumerate(SECONDS_BUCKETS) if x <= lim), len(SECONDS_BUCKETS))] += 1
        first_secs = [t.seconds for t in done if t.id in firsts and t.seconds is not None]
        seen_secs = [t.seconds for t in done if t.id not in firsts and t.seconds is not None]
        return {
            "range": {"since": since.isoformat() if since else None, "until": until.isoformat() if until else None},
            "questions": len(turns), "conversations": len({t.session_id for t in turns}),
            "accounts": len({t.account for t in turns if t.account}), "photos": len({t.image_sha256 for t in turns}),
            "routes": dict(routes),
            "verdicts": dict(Counter(t.verdict or "none" for t in done)),
            "feedback": {"rated": up + down, "up": up, "down": down, "up_share": up / (up + down) if up + down else None,
                         "corrected": sum(bool(f["corrected_answer"]) for f in fbs)},
            "seconds": {"n": len(secs), "p50": pct(secs, 0.5), "p90": pct(secs, 0.9), "p95": pct(secs, 0.95),
                        "first_on_photo_p50": pct(first_secs, 0.5), "first_on_photo_n": len(first_secs),
                        "seen_before_p50": pct(seen_secs, 0.5), "seen_before_n": len(seen_secs),
                        "buckets": SECONDS_BUCKETS, "histogram": hist},
            "cost_usd": {"total": round(sum(t.cost_usd or 0.0 for t in turns), 4),
                         "per_answer": (sum(t.cost_usd or 0.0 for t in done) / len(done)) if done else None},
            "per_day": [{"day": k, **v} for k, v in sorted(per_day.items())],
            "spend": spend(),
        }

    @r.get("/turns", dependencies=deps)
    def turns(since: date | None = None, until: date | None = None, route: str | None = None,
              verdict: str | None = None, rating: str | None = None, account: str | None = None,
              q: str | None = Query(default=None, max_length=100),
              limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
        a, b = day_range(since, until)
        rows = [summary(t) for t in reversed(store.turns_between(a, b))]
        if route:
            rows = [x for x in rows if x["route"] == route]
        if verdict:
            rows = [x for x in rows if (x["verdict"] or "none") == verdict]
        if account:
            rows = [x for x in rows if (x["account"] or "") == account]
        if rating == "up":
            rows = [x for x in rows if x["thumb"] == "up"]
        elif rating == "down":
            rows = [x for x in rows if x["thumb"] == "down"]
        elif rating == "corrected":
            rows = [x for x in rows if x["corrected_answer"]]
        elif rating == "none":
            rows = [x for x in rows if not x["thumb"] and not x["corrected_answer"]]
        if q:
            ql = q.lower()
            rows = [x for x in rows if ql in (x["question"] or "").lower() or ql in (x["answer"] or "").lower()]
        return {"total": len(rows), "items": rows[offset:offset + limit]}

    CSV_COLUMNS = ["created_at", "account", "question", "answer", "route", "verdict", "seconds", "cost_usd",
                   "thumb", "corrected_answer", "note", "status", "error", "turn_id", "session_id", "image_sha256"]

    def csv_response(rows: list[dict[str, Any]], name: str) -> Response:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        # a BOM so spreadsheet apps read the Vietnamese text as UTF-8
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @r.get("/turns.csv", dependencies=deps)
    def turns_csv(since: date | None = None, until: date | None = None, route: str | None = None,
                  verdict: str | None = None, rating: str | None = None, account: str | None = None,
                  q: str | None = Query(default=None, max_length=100)) -> Response:
        page = turns(since, until, route, verdict, rating, account, q, limit=500, offset=0)
        rows = page["items"]
        if page["total"] > len(rows):        # the CSV has every row, not just the first page
            rows = turns(since, until, route, verdict, rating, account, q, limit=page["total"], offset=0)["items"]
        return csv_response(rows, f"signcite-cau-hoi-{since or 'all'}-{until or 'all'}.csv")

    @r.get("/feedback.csv", dependencies=deps)
    def feedback_csv(since: date | None = None, until: date | None = None) -> Response:
        return csv_response(feedback_inbox(since, until)["items"], f"signcite-phan-hoi-{since or 'all'}-{until or 'all'}.csv")

    @r.get("/feedback", dependencies=deps)
    def feedback_inbox(since: date | None = None, until: date | None = None) -> dict[str, Any]:
        a, b = day_range(since, until)
        rows = [summary(t) for t in reversed(store.turns_between(a, b))]
        rows = [x for x in rows if x["thumb"] == "down" or x["corrected_answer"] or x["note"]]
        return {"total": len(rows), "items": rows}

    # ------------------------------------------------------------------ live settings
    def settings_view() -> dict[str, Any]:
        over = store.settings_overrides()
        now = live_now()
        reachable, detail = check_rag(now.rag_url)
        try:
            from app.api.rag_cache import RagAnswerCache
            entries = len(RagAnswerCache(rag_cache_folder()).entries())
        except Exception:
            entries = None
        return {"live": now.as_dict(), "defaults": live_mod.defaults(settings).as_dict(),
                "overridden": sorted(k for k in over if k in live_mod.KEYS),
                "fixed": {"answer_slots": runner.slots, "profile": settings.profile},
                "rag": {"url": now.rag_url, "reachable": reachable, "detail": detail},
                "rag_cache_entries": entries, "spend": spend()}

    @r.get("/settings", dependencies=deps)
    def get_settings() -> dict[str, Any]:
        return settings_view()

    @r.put("/settings", dependencies=deps)
    def put_settings(body: SettingsIn) -> dict[str, Any]:
        given = body.model_dump(exclude_none=True)
        if not given:
            raise HTTPException(400, "không có gì để thay đổi")
        values: dict[str, str | None] = {}
        try:
            for k, v in given.items():
                values[k] = live_mod.to_text(k, live_mod.parse(k, live_mod.to_text(k, v)))
        except ValueError as e:
            raise HTTPException(400, str(e))
        current = live_now()
        mode = values.get("answer_fallback", current.answer_fallback)
        url = values.get("rag_url", current.rag_url)
        if mode == "rag":
            ok, detail = check_rag(url)
            if not ok:
                raise HTTPException(409, f"RAG không trả lời tại {url} ({detail}); chưa đổi cách trả lời dự phòng")
        store.set_overrides(values)
        return settings_view()

    @r.post("/settings/reset", dependencies=deps)
    def reset_settings() -> dict[str, Any]:
        store.set_overrides({k: None for k in live_mod.KEYS})
        return settings_view()

    # ------------------------------------------------------------------ the GPU connection
    def gpu_view() -> dict[str, Any]:
        if settings.gpu_dir is None:
            return {"enabled": False}
        s = gpu_mod.status(settings.gpu_dir)
        reachable, detail = check_rag(settings.gpu_rag_url) if s["state"] == "connected" else (False, s["state"])
        now = live_now()
        return {"enabled": True, **s, "rag_url": settings.gpu_rag_url,
                "rag": {"reachable": reachable, "detail": detail},
                "rag_in_use": now.answer_fallback == "rag" and now.rag_url == settings.gpu_rag_url}

    def need_gpu() -> Path:
        if settings.gpu_dir is None:
            raise HTTPException(409, "máy chủ này chưa bật điều khiển GPU (VQA_GPU_DIR)")
        return settings.gpu_dir

    @r.get("/gpu", dependencies=deps)
    def gpu_status() -> dict[str, Any]:
        return gpu_view()

    @r.post("/gpu/connect", dependencies=deps)
    def gpu_connect(body: GpuIn) -> dict[str, Any]:
        folder = need_gpu()
        try:
            gpu_mod.set_target(folder, body.host, body.port)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return gpu_view()

    @r.post("/gpu/disconnect", dependencies=deps)
    def gpu_disconnect() -> dict[str, Any]:
        folder = need_gpu()
        now = live_now()
        if now.answer_fallback == "rag" and now.rag_url == settings.gpu_rag_url:
            store.set_overrides({"answer_fallback": "off"})     # first stop sending questions to it
        gpu_mod.clear_target(folder)
        return gpu_view()

    @r.post("/rag-cache/clear", dependencies=deps)
    def clear_rag_cache() -> dict[str, Any]:
        from app.api.rag_cache import RagAnswerCache
        return {"removed": RagAnswerCache(rag_cache_folder()).clear()}

    # ------------------------------------------------------------------ site accounts
    def account_view(a: Any, usage: dict[str, tuple[int, datetime | None]]) -> dict[str, Any]:
        n, last = usage.get(a.name, (0, None))
        return {"name": a.name, "enabled": a.enabled, "note": a.note,
                "created_at": _aware(a.created_at).isoformat(),
                "password_set_at": _aware(a.password_set_at).isoformat(),
                "questions": n, "last_question_at": _aware(last).isoformat() if last else None}

    def reserved(name: str) -> bool:
        return name in {settings.admin_user.lower(), settings.site_shared_user.lower()}

    @r.get("/accounts", dependencies=deps)
    def list_accounts() -> dict[str, Any]:
        usage = store.account_usage()
        return {"enabled": settings.site_users_file is not None,
                "shared_account": settings.site_shared_user or None,
                "login_required": login_required(store),
                "items": [account_view(a, usage) for a in store.accounts()]}

    @r.put("/site-login", dependencies=deps)
    def set_site_login(body: SiteLoginIn) -> dict[str, Any]:
        """Turn the public site's login on or off for everyone (off: anyone with the address can ask)."""
        if settings.site_users_file is None:
            raise HTTPException(409, "máy chủ này chưa bật tài khoản riêng (VQA_SITE_USERS_FILE)")
        store.set_overrides({SITE_LOGIN_KEY: None if body.required else "off"})
        sync_site_users()
        return {"login_required": login_required(store)}

    @r.post("/accounts", dependencies=deps)
    def create_account(body: AccountIn) -> dict[str, Any]:
        if settings.site_users_file is None:
            raise HTTPException(409, "máy chủ này chưa bật tài khoản riêng (VQA_SITE_USERS_FILE)")
        name = body.name.strip().lower()
        if not acc.valid_name(name):
            raise HTTPException(400, "tên: 2–32 ký tự, chữ thường không dấu, số, '.', '_' hoặc '-'")
        if reserved(name) or store.get_account(name) is not None:
            raise HTTPException(409, f"tên {name} đã được dùng")
        password = acc.new_password()
        store.add_account(name, acc.apr1(password), body.note)
        sync_site_users()
        return {"name": name, "password": password}

    @r.post("/accounts/{name}/reset", dependencies=deps)
    def reset_password(name: str) -> dict[str, Any]:
        password = acc.new_password()
        a = store.update_account(name, password_hash=acc.apr1(password),
                                 password_set_at=datetime.now(timezone.utc))
        if a is None:
            raise HTTPException(404, "không có tài khoản này")
        sync_site_users()
        return {"name": name, "password": password}

    @r.patch("/accounts/{name}", dependencies=deps)
    def patch_account(name: str, body: AccountPatch) -> dict[str, Any]:
        fields = body.model_dump(exclude_none=True)
        if not fields:
            raise HTTPException(400, "không có gì để thay đổi")
        a = store.update_account(name, **fields)
        if a is None:
            raise HTTPException(404, "không có tài khoản này")
        sync_site_users()
        return account_view(a, store.account_usage())

    @r.delete("/accounts/{name}", dependencies=deps)
    def delete_account(name: str) -> dict[str, Any]:
        if not store.delete_account(name):
            raise HTTPException(404, "không có tài khoản này")
        sync_site_users()                 # the login stops working at once
        return {"name": name, "deleted": True}

    @r.get("/me", dependencies=deps)
    def me() -> dict[str, Any]:
        return {"admin": settings.admin_user}

    return r


SITE_LOGIN_KEY = "site_login"          # in the settings table, outside live.KEYS: "Reset settings" keeps it
OPEN_FLAG = "site_open"                # next to the password file; nginx skips the login while it exists


def login_required(store: Store) -> bool:
    return store.settings_overrides().get(SITE_LOGIN_KEY) != "off"


def sync_users(settings: Settings, store: Store) -> None:
    """Write the web server's password file (the shared .env login and every enabled account) and
    the open-site flag (docker/nginx/40-basic-auth.sh checks it on each request)."""
    if settings.site_users_file is None:
        return
    flag = Path(settings.site_users_file).parent / OPEN_FLAG
    if login_required(store):
        flag.unlink(missing_ok=True)
    else:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("the public site's login is off (admin console, Accounts)\n", encoding="utf-8")
        os.chmod(flag, 0o644)
    entries: list[tuple[str, str]] = []
    if settings.site_shared_user and settings.site_shared_password:
        entries.append((settings.site_shared_user, acc.apr1(settings.site_shared_password)))
    entries += [(a.name, a.password_hash) for a in store.accounts() if a.enabled]
    acc.write_htpasswd(settings.site_users_file, entries)

