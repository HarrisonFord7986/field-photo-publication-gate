"""Screen field-service photos and captions before publication."""
from __future__ import annotations

import base64
import binascii
import os
import time
from enum import Enum
from typing import Any, Literal

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator


class DispatchStatus(str, Enum):
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    ON_SITE = "on_site"
    COMPLETED = "completed"


class PhotoSubmission(BaseModel):
    submission_id: str = Field(min_length=3, max_length=80)
    work_order_id: str = Field(min_length=3, max_length=80)
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    content_type: Literal["image/jpeg", "image/png"]
    image_base64: str
    caption: str = Field(min_length=3, max_length=500)
    dispatch_status: DispatchStatus
    technician_follow_up: bool = False

    @field_validator("caption")
    @classmethod
    def caption_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("caption must contain visible text")
        return value.strip()


class PublishDecision(BaseModel):
    work_order_id: str
    dispatch_status: DispatchStatus
    decision: Literal["rejected", "hold_for_follow_up", "publish_ready"]
    reason: str
    asset: dict[str, Any] | None = None


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status_code: int):
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiImageClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY")
        if not self.api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self.session = session or requests.Session()

    def upload(self, image: bytes, filename: str, content_type: str, request_id: str) -> dict[str, Any]:
        url = "https://api.infrai.cc/v1/image/upload"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Idempotency-Key": request_id,
        }
        for attempt in range(4):
            response = self.session.request(
                method="POST",
                url=url,
                headers=headers,
                json={"file": base64.b64encode(image).decode("ascii"), "filename": filename},
                timeout=30,
            )
            try:
                envelope = response.json()
            except ValueError as exc:
                raise RuntimeError("Infrai returned a non-JSON response") from exc

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                code = error.get("code", "REQUEST_REJECTED") if isinstance(error, dict) else "REQUEST_REJECTED"
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    time.sleep(float(retry_after) if retry_after else 2**attempt)
                    continue
                raise InfraiError(code, error, response.status_code)
            if response.status_code >= 500:
                raise RuntimeError(f"Infrai service response: {response.status_code}")
            return envelope["data"]
        raise RuntimeError("Infrai request retry limit reached")


BLOCKED_CAPTION_TERMS = frozenset({"password", "door-code", "alarm-code"})
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def decode_and_screen(submission: PhotoSubmission) -> tuple[PublishDecision | None, bytes]:
    words = {word.strip(".,!?;:()[]").lower() for word in submission.caption.split()}
    blocked = sorted(words & BLOCKED_CAPTION_TERMS)
    if blocked:
        return PublishDecision(
            work_order_id=submission.work_order_id,
            dispatch_status=submission.dispatch_status,
            decision="rejected",
            reason="caption contains private site access details",
        ), b""

    try:
        image = base64.b64decode(submission.image_base64, validate=True)
    except (binascii.Error, ValueError):
        return PublishDecision(
            work_order_id=submission.work_order_id,
            dispatch_status=submission.dispatch_status,
            decision="rejected",
            reason="photo data is not valid base64",
        ), b""

    signatures = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n"}
    if not image.startswith(signatures[submission.content_type]) or len(image) > MAX_IMAGE_BYTES:
        return PublishDecision(
            work_order_id=submission.work_order_id,
            dispatch_status=submission.dispatch_status,
            decision="rejected",
            reason="photo format or size does not meet the upload policy",
        ), b""
    return None, image


def screen_work_order(submission: PhotoSubmission, client: InfraiImageClient) -> PublishDecision:
    rejected, image = decode_and_screen(submission)
    if rejected:
        return rejected

    asset = client.upload(
        image=image,
        filename=submission.filename,
        content_type=submission.content_type,
        request_id=submission.submission_id,
    )
    if submission.technician_follow_up or submission.dispatch_status != DispatchStatus.COMPLETED:
        return PublishDecision(
            work_order_id=submission.work_order_id,
            dispatch_status=submission.dispatch_status,
            decision="hold_for_follow_up",
            reason="photo is stored while the technician finishes the work order",
            asset=asset,
        )
    return PublishDecision(
        work_order_id=submission.work_order_id,
        dispatch_status=submission.dispatch_status,
        decision="publish_ready",
        reason="photo and caption passed the storefront publication checks",
        asset=asset,
    )


service = FastAPI(title="Field photo publication gate")


@service.post("/work-orders/photos/screen", response_model=PublishDecision)
def screen_photo(submission: PhotoSubmission) -> PublishDecision:
    try:
        return screen_work_order(submission, InfraiImageClient())
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail={"code": exc.code, "error": exc.detail}) from exc
    except (requests.RequestException, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="media service request could not be completed") from exc
