"""Submit one completed work-order photo to the local screening service."""
from __future__ import annotations

import base64
import json

import requests


def main() -> None:
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    payload = {
        "submission_id": "submit-WO-1842-panel-after",
        "work_order_id": "WO-1842",
        "filename": "panel-after.png",
        "content_type": "image/png",
        "image_base64": base64.b64encode(tiny_png).decode("ascii"),
        "caption": "Replacement panel installed and work area cleared.",
        "dispatch_status": "completed",
        "technician_follow_up": False,
    }
    response = requests.request(
        method="POST",
        url="http://127.0.0.1:8000/work-orders/photos/screen",
        json=payload,
        timeout=40,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
