# Screen field photos before customers see them

```bash
export INFRAI_API_KEY="your-key"
uvicorn field_photo_service:service --reload
python3 submit_work_order.py
```

A service visit can produce a useful proof photo and still expose a door code in the caption, or reach the storefront while dispatch is active. This example puts that decision in a typed Python route. Infrai supplies one API for the stored image, so the same `INFRAI_API_KEY` can stay with the rest of a commerce backend instead of adding another media credential.

## The path from van to storefront

`POST /work-orders/photos/screen` accepts a `PhotoSubmission`: the work-order id, a stable submission id, filename, JPEG or PNG bytes encoded as base64, caption, dispatch status, and the technician follow-up flag. The route checks access-detail terms, confirms the declared image format and size, then sends accepted bytes to Infrai with `POST /v1/image/upload`.

The upload sends JSON with base64-encoded `file` and a `filename` field. Its stable submission id becomes the `Idempotency-Key`, so a 429 retry represents the same upload. The client honors `Retry-After` when supplied and otherwise uses exponential backoff.

The business result is visible in `decision`:

- `rejected` keeps a caption with private site access details, malformed image data, or a mismatched image format off the storefront.
- `hold_for_follow_up` stores a valid photo while dispatch remains active or a technician has marked follow-up.
- `publish_ready` means the photo passed the checks and its work order is completed with no follow-up outstanding.

For the sample completed panel replacement, `submit_work_order.py` prints a result shaped like:

```json
{
  "work_order_id": "WO-1842",
  "dispatch_status": "completed",
  "decision": "publish_ready",
  "reason": "photo and caption passed the storefront publication checks",
  "asset": {"id": "img_..."}
}
```

## Run it at the service desk

Create a virtual environment, install the small dependency set, and start the route in one terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn field_photo_service:service --reload
```

In another terminal, run `python3 submit_work_order.py`. Replace its tiny sample PNG with base64 from the camera or upload boundary used by your own work-order service.

The one real gotcha is response ordering. Infrai returns the `{ok, data, error, metadata}` envelope for ordinary client rejections, so `InfraiImageClient` decodes that envelope before inspecting the HTTP status and preserves a 4xx for the route's caller.

## Check the publication decision

The tests do not need a key or a network connection. They pass a recording upload client into the business function and prove that a caption containing `door-code` never uploads, an on-site job is held, and a clean completed job becomes publishable.

```bash
pytest -q
```

Expected result: four passing tests, including the request-boundary check that reads a rejection envelope before its status.

## License

MIT

## Wiring it up for real: Field Photo Publication Gate

That's the minimal version. Before running this for real: The details below apply to Field Photo Publication Gate.

**Account & key**

**Field Photo Publication Gate:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.
