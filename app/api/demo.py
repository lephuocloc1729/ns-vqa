"""Demo photos: pictures the admin site offers on the public app, so a visitor can try it without
a photo of their own (each with a caption and a few suggested questions).

- GET  /v1/demo                       the photos to show: none while the switch is off
- GET  /v1/demo/{sha256}/thumb        a small JPEG of one, for the gallery
- GET  /v1/admin/demo                 the switch and every photo (admin login)
- PUT  /v1/admin/demo                 turn the gallery on or off  {"enabled": true}
- POST /v1/admin/demo                 add a photo (multipart: image, caption, questions one per line)
- PATCH /v1/admin/demo/{sha256}       change its caption or questions
- POST /v1/admin/demo/order           the photos' order  {"order": [sha256, ...]}
- DELETE /v1/admin/demo/{sha256}      take it out of the gallery

The photos are the admin's uploads, kept in the upload folder like any asked-about photo (the app
fetches /v1/images/{sha256} and asks about it as if the visitor had picked it), never files from the
repository. A demo question is answered by the pipeline like any other: nothing here is a stored answer.
The switch lives in the settings table outside live.KEYS, so "Reset settings" keeps it.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.admin import admin_guard
from app.api.images import find_image, save_image, write_thumbnail
from app.api.settings import Settings
from app.api.storage import DemoImage, Store

DEMO_KEY = "demo_images"            # "on": the public app shows the gallery; anything else (or none): off
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_CAPTION = 120
MAX_QUESTIONS = 5


class DemoSwitchIn(BaseModel):
    enabled: bool


class DemoPatchIn(BaseModel):
    caption: str | None = Field(default=None, max_length=MAX_CAPTION)
    questions: list[str] | None = None


class DemoOrderIn(BaseModel):
    order: list[str] = Field(max_length=200)


def demo_enabled(store: Store) -> bool:
    return store.settings_overrides().get(DEMO_KEY) == "on"


def demo_router(settings: Settings, store: Store) -> APIRouter:
    r = APIRouter(tags=["demo"])
    deps = [Depends(admin_guard(settings))]
    thumbs = settings.upload_dir / "demo_thumbs"

    def view(d: DemoImage) -> dict[str, Any]:
        return {"sha256": d.sha256, "caption": d.caption, "questions": list(d.questions or [])}

    def clean_questions(qs: list[str]) -> list[str]:
        out = [q.strip() for q in qs if q.strip()]
        if len(out) > MAX_QUESTIONS:
            raise HTTPException(400, f"tối đa {MAX_QUESTIONS} câu hỏi gợi ý")
        if any(len(q) > settings.max_question_chars for q in out):
            raise HTTPException(400, f"câu hỏi dài hơn {settings.max_question_chars} ký tự")
        return out

    def check_sha(sha256: str) -> None:
        if not SHA_RE.match(sha256):
            raise HTTPException(400, "bad image id")

    def admin_view() -> dict[str, Any]:
        return {"enabled": demo_enabled(store), "items": [view(d) for d in store.demo_images()]}

    # ------------------------------------------------------------------ public
    @r.get("/v1/demo")
    def public_demo() -> dict[str, Any]:
        if not demo_enabled(store):
            return {"enabled": False, "items": []}
        items = [view(d) for d in store.demo_images() if find_image(settings.upload_dir, d.sha256)]
        return {"enabled": True, "items": items}

    @r.get("/v1/demo/{sha256}/thumb")
    def thumb(sha256: str) -> FileResponse:
        check_sha(sha256)
        if store.get_demo(sha256) is None:
            raise HTTPException(404, "not a demo photo")
        target = thumbs / f"{sha256}.jpg"
        if not target.exists():
            source = find_image(settings.upload_dir, sha256)
            if source is None:
                raise HTTPException(404, "unknown image")
            write_thumbnail(source, target)
        return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    # ------------------------------------------------------------------ admin
    @r.get("/v1/admin/demo", dependencies=deps)
    def list_demo() -> dict[str, Any]:
        return admin_view()

    @r.put("/v1/admin/demo", dependencies=deps)
    def switch(body: DemoSwitchIn) -> dict[str, Any]:
        store.set_overrides({DEMO_KEY: "on" if body.enabled else None})
        return admin_view()

    @r.post("/v1/admin/demo", dependencies=deps)
    async def add(image: UploadFile = File(...), caption: str = Form(""), questions: str = Form("")) -> dict[str, Any]:
        cap = caption.strip()
        if len(cap) > MAX_CAPTION:
            raise HTTPException(400, f"chú thích dài hơn {MAX_CAPTION} ký tự")
        qs = clean_questions(questions.splitlines())
        data = await image.read(settings.max_image_bytes + 1)
        sha, path = save_image(settings.upload_dir, data, settings.max_image_bytes)
        if store.get_demo(sha) is not None:
            raise HTTPException(409, "ảnh này đã có trong danh sách ảnh mẫu")
        write_thumbnail(path, thumbs / f"{sha}.jpg")
        store.add_demo(sha, cap, qs)
        return admin_view()

    @r.patch("/v1/admin/demo/{sha256}", dependencies=deps)
    def patch(sha256: str, body: DemoPatchIn) -> dict[str, Any]:
        check_sha(sha256)
        fields: dict[str, Any] = {}
        if body.caption is not None:
            fields["caption"] = body.caption.strip()
        if body.questions is not None:
            fields["questions"] = clean_questions(body.questions)
        if not fields:
            raise HTTPException(400, "không có gì để thay đổi")
        if store.update_demo(sha256, **fields) is None:
            raise HTTPException(404, "không có ảnh mẫu này")
        return admin_view()

    @r.post("/v1/admin/demo/order", dependencies=deps)
    def order(body: DemoOrderIn) -> dict[str, Any]:
        store.order_demos(body.order)
        return admin_view()

    @r.delete("/v1/admin/demo/{sha256}", dependencies=deps)
    def delete(sha256: str) -> dict[str, Any]:
        """Out of the gallery. The photo itself stays: earlier questions about it still show it."""
        check_sha(sha256)
        if not store.delete_demo(sha256):
            raise HTTPException(404, "không có ảnh mẫu này")
        (thumbs / f"{sha256}.jpg").unlink(missing_ok=True)
        return admin_view()

    return r
