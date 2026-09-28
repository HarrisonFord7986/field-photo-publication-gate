import base64

from field_photo_service import DispatchStatus, InfraiImageClient, PhotoSubmission, screen_work_order


class RecordingClient:
    def __init__(self):
        self.calls = []

    def upload(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "img_work_order_1842"}


def submission(**changes):
    values = {
        "submission_id": "submit-1842",
        "work_order_id": "WO-1842",
        "filename": "panel.png",
        "content_type": "image/png",
        "image_base64": base64.b64encode(b"\x89PNG\r\n\x1a\nphoto").decode("ascii"),
        "caption": "Replacement panel installed and area cleared.",
        "dispatch_status": DispatchStatus.COMPLETED,
        "technician_follow_up": False,
    }
    values.update(changes)
    return PhotoSubmission(**values)


def test_private_access_caption_is_rejected_before_upload():
    client = RecordingClient()
    result = screen_work_order(submission(caption="Panel is beside the door-code keypad."), client)
    assert result.decision == "rejected"
    assert client.calls == []


def test_on_site_photo_is_stored_and_held_for_technician():
    client = RecordingClient()
    result = screen_work_order(submission(dispatch_status="on_site"), client)
    assert result.decision == "hold_for_follow_up"
    assert result.asset == {"id": "img_work_order_1842"}
    assert client.calls[0]["request_id"] == "submit-1842"


def test_completed_work_order_photo_is_ready_to_publish():
    result = screen_work_order(submission(), RecordingClient())
    assert result.decision == "publish_ready"


class EnvelopeResponse:
    status_code = 400
    headers = {}

    @staticmethod
    def json():
        return {"ok": False, "data": None, "error": {"code": "BAD_PHOTO"}, "metadata": {}}


class EnvelopeSession:
    def request(self, **kwargs):
        return EnvelopeResponse()


def test_client_decodes_rejection_envelope_before_http_status():
    client = InfraiImageClient(api_key="test-key", session=EnvelopeSession())
    try:
        client.upload(b"photo", "panel.png", "image/png", "submit-1842")
    except Exception as exc:
        assert exc.status_code == 400
        assert exc.code == "BAD_PHOTO"
    else:
        raise AssertionError("expected the rejection envelope to raise")


def test_upload_sends_base64_json():
    class CaptureSession:
        def request(self, **kwargs):
            self.kwargs = kwargs
            return EnvelopeResponse()

    session = CaptureSession()
    client = InfraiImageClient(api_key="test-key", session=session)
    try:
        client.upload(b"\x89PNG", "panel.png", "image/png", "submit-1842")
    except Exception:
        pass
    assert session.kwargs["json"] == {"file": "iVBORw==", "filename": "panel.png"}
    assert "files" not in session.kwargs
    assert session.kwargs["headers"]["Idempotency-Key"] == "submit-1842"
