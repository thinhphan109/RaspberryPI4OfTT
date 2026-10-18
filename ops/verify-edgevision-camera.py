"""On-Pi integration check: live JPEG, preview write policy, explicit capture."""
import base64
import json
from pathlib import Path
import time
import urllib.request

import cv2
import numpy as np

ROOT = Path.home() / "edgevision-camera/data"
URL = "http://127.0.0.1:18766"


def request(path, post=False):
    req = urllib.request.Request(URL + path, data=b"" if post else None)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def inventory():
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in ROOT.rglob("*") if p.is_file()}


status = request("/api/status")
assert status["camera"] == "configured" and status["robot"] == "disabled"
before = inventory()
sequences, timings = [], []
for _ in range(10):
    start = time.monotonic()
    frame = request("/api/preview?raw=1", post=True)
    image = cv2.imdecode(np.frombuffer(base64.b64decode(frame["jpeg_base64"]), np.uint8), cv2.IMREAD_COLOR)
    assert image is not None and image.shape[:2] == (480, 640)
    assert frame["preview_only"] and not frame["hardware_moved"]
    assert frame["quality"]["basis"] == "original_image"
    assert frame["quality"]["scope_xyxy"] == [0, 0, 640, 480]
    sequences.append(int(frame["device_sequence"]))
    timings.append(round((time.monotonic() - start) * 1000, 1))
assert len(set(sequences)) == 10 and sequences == sorted(sequences)
assert before == inventory(), "Preview modified persistent application data"
cropped = request("/api/preview?roi=0.1,0.1,0.9,0.9&min_box_area=400", post=True)
assert cropped["roi_xyxy"] == [64,48,576,432]
assert cropped["coordinate_frame"] == "full_original_image_pixels"
for detection in cropped["detections"]:
    x0, y0, x1, y1 = detection["xyxy"]
    assert 64 <= x0 <= x1 <= 576 and 48 <= y0 <= y1 <= 432
assert before == inventory(), "ROI preview modified persistent application data"
result = request("/api/analyze", post=True)
after = inventory()
new_files = sorted(set(after) - set(before))
assert sum(p.endswith("-raw.jpg") for p in new_files) == 1
assert sum(p.endswith("frames.jsonl") for p in new_files) == 1
assert result["source"] == "camera" and not result["hardware_moved"]
print(json.dumps({"preview_frames": 10, "sequences": sequences,
                  "mean_preview_ms": round(sum(timings) / len(timings), 1),
                  "preview_persistent_files_changed": 0,
                  "explicit_capture_files": new_files,
                  "detector": result["method"], "robot": status["robot"]}, ensure_ascii=False))
print(json.dumps({"quality_original": result["quality"], "detected_regions": len(result["detections"]),
                  "roi_quality": cropped["quality"]}, ensure_ascii=False))
