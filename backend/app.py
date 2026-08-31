from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
import os, uuid, subprocess
from fastapi.middleware.cors import CORSMiddleware

# Import the CadQuery model builder
from cad_models.ljt06 import build_part
from cadquery import exporters

app = FastAPI(title="CAD Workbench API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'output'))
os.makedirs(OUTPUT, exist_ok=True)

class ModelParams(BaseModel):
    base_length: float = 224.0
    base_width: float = 90.0
    base_thickness: float = 10.0
    big_cyl_outer_dia: float = 56.0
    big_cyl_inner_dia: float = 35.0
    web_thickness: float = 28.0
    web_width: float = 72.0
    web_center_z: float = 140.0
    lower_cyl_outer: float = 28.0
    lower_cyl_inner: float = 10.0

@app.post("/generate_model")
async def generate_model(params: ModelParams):
    jobid = uuid.uuid4().hex
    step_name = f"ljt06_{jobid}.step"
    stl_name  = f"ljt06_{jobid}.stl"
    step_path = os.path.join(OUTPUT, step_name)
    stl_path  = os.path.join(OUTPUT, stl_name)

    # Build CadQuery part
    try:
        part = build_part(params.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model build failed: {e}")

    # Export STEP & STL
    try:
        exporters.export(part, step_path)
        exporters.export(part, stl_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    return {"jobid": jobid, "step": step_path, "stl": stl_path}

@app.post("/upload_and_detect")
async def upload_and_detect(file: UploadFile = File(...)):
    # Save uploaded file and return a placeholder SVG + candidate params
    ext = os.path.splitext(file.filename)[1].lower()
    out = os.path.join(OUTPUT, f"upload_{uuid.uuid4().hex}{ext}")
    with open(out, "wb") as f:
        f.write(await file.read())

    # Placeholder behavior: return saved path and a simple candidate params set (to be replaced by OCR/vec pipeline)
    candidates = [
        {"name": "base_length", "value": 224.0, "confidence": 0.7},
        {"name": "base_width", "value": 90.0, "confidence": 0.7},
        {"name": "big_cyl_outer_dia", "value": 56.0, "confidence": 0.8},
        {"name": "big_cyl_inner_dia", "value": 35.0, "confidence": 0.8}
    ]

    # For frontend demo we return the uploaded file path (client can fetch via static server) and candidates
    return {"uploaded": out, "candidates": candidates}

@app.post("/open_nx")
async def open_nx(step_path: str):
    if not os.path.exists(step_path):
        raise HTTPException(status_code=404, detail="STEP file not found")
    try:
        # try os.startfile
        os.startfile(step_path)
        return {"status": "opened", "method": "startfile", "path": step_path}
    except Exception:
        # fallback to explicit NX exe if configured
        NX_EXE = r"D:\Program Files\Siemens\NX 12.0\NXBIN\ugraf.exe"
        try:
            subprocess.Popen([NX_EXE, "-nx", step_path])
            return {"status": "opened", "method": "nx_exec", "path": step_path}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to open NX: {e}")
