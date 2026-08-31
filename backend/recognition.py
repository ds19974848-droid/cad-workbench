from pathlib import Path
from typing import Dict, Any
import subprocess
import uuid
import cv2
import numpy as np
import pytesseract

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from . import semantic

router = APIRouter()

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / "recognition"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INSKAPE_CMD = "inkscape"


def _preprocess_image_bytes(data: bytes) -> Path:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.bilateralFilter(gray, 9, 75, 75)
    th = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 15, 6)
    th = 255 - th
    out_pre = OUTPUT_DIR / f"preproc_{uuid.uuid4().hex}.png"
    cv2.imwrite(str(out_pre), th)
    return out_pre


def _raster_to_svg(preproc_path: Path) -> Path:
    svg_out = preproc_path.with_suffix('.svg')
    try:
        subprocess.check_call([INSKAPE_CMD, str(preproc_path), '--export-plain-svg', str(svg_out)])
    except Exception:
        try:
            subprocess.check_call([INSKAPE_CMD, '--export-plain-svg', str(svg_out), str(preproc_path)])
        except Exception as e:
            raise RuntimeError(f"Inkscape vectorization failed: {e}")
    return svg_out


def _run_ocr_on_image(preproc_path: Path) -> Dict[str, Any]:
    img = cv2.imread(str(preproc_path), cv2.IMREAD_GRAYSCALE)
    custom_oem_psm_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.-OxmM\u00F8'
    try:
        data = pytesseract.image_to_data(img, config=custom_oem_psm_config, output_type=pytesseract.Output.DICT)
    except Exception as e:
        raise RuntimeError(f"Tesseract OCR failed: {e}")
    results = []
    n = len(data['text'])
    for i in range(n):
        txt = data['text'][i].strip()
        if txt == '':
            continue
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        conf = int(data.get('conf', [])[i]) if 'conf' in data and len(data.get('conf', []))>i else -1
        results.append({"text": txt, "bbox": [int(x), int(y), int(x+w), int(y+h)], "conf": conf})
    return {"ocr_raw": results}


@router.post("/upload_and_detect")
async def upload_and_detect(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        preproc = _preprocess_image_bytes(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preprocessing failed: {e}")

    svg_path = None
    try:
        svg_path = _raster_to_svg(preproc)
    except Exception as e:
        # Log but continue
        svg_path = None

    try:
        ocr = _run_ocr_on_image(preproc)
    except Exception as e:
        ocr = {"error": str(e)}

    candidates = []
    try:
        # call semantic parser to extract geometry and match OCR numbers to dimensions
        candidates = semantic.extract_candidates(preproc, svg_path, ocr.get('ocr_raw', []))
    except Exception as e:
        candidates = [{"error": f"semantic extraction failed: {e}"}]

    resp = {
        "uploaded": str(preproc),
        "svg": str(svg_path) if svg_path else None,
        "ocr": ocr,
        "candidates": candidates
    }
    return JSONResponse(resp)
