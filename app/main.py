from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import os, uuid, subprocess, pathlib, re
from typing import Optional, Tuple, List, Dict

app = FastAPI(title="MN ASR (Audio->Text)")

# ---- Config (env) ----
MODEL_SIZE = os.getenv("MODEL_SIZE", "medium")   # tiny/base/small/medium/large-v3
DEVICE = os.getenv("DEVICE", "cpu")              # cpu / cuda
COMPUTE = os.getenv("COMPUTE", "int8")           # cpu: int8/int8_float16, cuda: float16
BEAM_SIZE = int(os.getenv("BEAM_SIZE", "8"))     # чанар өснө, гэхдээ удааширна
BEST_OF = int(os.getenv("BEST_OF", "8"))

UPLOAD_DIR = pathlib.Path("uploads")
TMP_DIR = pathlib.Path("tmp")
UPLOAD_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

# ---- Mongolian guiding prompt ----
MN_PROMPT = (
    "Энэ бол монгол хэл дээрх подкаст. "
    "Кирилл үсгээр, зөв бичгийн дүрмээр, утга төгөлдөр өгүүлбэрээр хөрвүүл. "
    "Зөв үг сонголт хий: сэтгэл, магадлал, сонсох, зөвлөе гэх мэт."
)

# ---- Model lazy-load ----
_model: Optional[WhisperModel] = None

def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE)
    return _model

def run_ffmpeg_to_wav(input_path: str, wav_path: str) -> None:
    # Audio clean: highpass/lowpass + volume boost
    # (Сул бичлэг дээр volume=1.5 сайн. Хэт чанга бол 1.2 болгож бууруул.)
    audio_filter = os.getenv("AUDIO_FILTER", "highpass=f=80,lowpass=f=8000,volume=1.5")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-af", audio_filter,
        wav_path
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        err = (p.stderr or "")[:800]
        raise RuntimeError(f"ffmpeg failed: {err}")

def basic_mn_cleanup(text: str) -> str:
    """
    Rule-based жижиг засварууд.
    (ASR-ийн 'сонсох'->'сансах' зэрэг нийтлэг алдаануудыг жаахан засна)
    """
    if not text:
        return text

    # зай/цэг тэмдэг
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.!?…])", r"\1", text)
    text = re.sub(r"([,.!?…])([^\s])", r"\1 \2", text)

    # нийтлэг солилтууд (болгоомжтой)
    replacements = [
        ("сэдгэл", "сэтгэл"),
        ("сэдэх", "сэдэх"),  # placeholder
        ("маагдал", "магадлал"),
        ("сансах", "сонсох"),
        ("сансаха", "сонсох"),
        ("зүвлэй", "зөвлөе"),
        ("зүвлээ", "зөвлөе"),
        ("зүвлэй.", "зөвлөе."),
        ("үйдээ", "үедээ"),
        ("хүв", "хувь"),
        ("сангол", "сонголт"),
        ("сангал", "сонголт"),
        ("таахдар", "тавгүйдэх"),  # заримдаа буруу таардаг, гэхдээ утга дээрддэг тохиолдол бий
    ]
    for a, b in replacements:
        text = text.replace(a, b)

    return text

def transcribe_internal(
    wav_path: str,
    language: str,
    vad: bool,
) -> Tuple[Dict, List[Dict], str]:
    model = get_model()

    vad_parameters = dict(
        min_silence_duration_ms=int(os.getenv("VAD_MIN_SILENCE_MS", "700")),
        speech_pad_ms=int(os.getenv("VAD_SPEECH_PAD_MS", "250")),
    )

    segments, info = model.transcribe(
        wav_path,
        language=language,
        task="transcribe",
        vad_filter=vad,
        vad_parameters=vad_parameters,
        beam_size=BEAM_SIZE,
        best_of=BEST_OF,
        temperature=0.0,
        condition_on_previous_text=True,   # <= хамгийн чухал
        initial_prompt=MN_PROMPT if language == "mn" else None,
        no_speech_threshold=float(os.getenv("NO_SPEECH_THRESHOLD", "0.6")),
    )

    seg_list = []
    text_parts = []
    for s in segments:
        t = (s.text or "").strip()
        if t:
            seg_list.append({
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": t
            })
            text_parts.append(t)

    full_text = " ".join(text_parts).strip()
    meta = {
        "language": info.language,
        "duration": round(info.duration, 2),
    }
    return meta, seg_list, full_text

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Query("mn", description="mn / en гэх мэт"),
    vad: bool = Query(True, description="Silence таслах (VAD)"),
    keep_files: bool = Query(False, description="uploads/tmp файлуудыг үлдээх эсэх"),
):
    fid = uuid.uuid4().hex
    in_path = UPLOAD_DIR / f"{fid}_{file.filename}"
    wav_path = TMP_DIR / f"{fid}.wav"

    # save upload
    try:
        with open(in_path, "wb") as f:
            f.write(await file.read())
    except Exception as e:
        return JSONResponse({"error": f"save failed: {e}"}, status_code=500)

    # to wav
    try:
        run_ffmpeg_to_wav(str(in_path), str(wav_path))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # transcribe
    try:
        meta, seg_list, full_text = transcribe_internal(str(wav_path), language, vad)
    except Exception as e:
        return JSONResponse({"error": f"transcribe failed: {e}"}, status_code=500)

    # cleanup files
    if not keep_files:
        try:
            in_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        **meta,
        "text": full_text,
        "segments": seg_list
    }

@app.post("/transcribe_clean")
async def transcribe_clean(
    file: UploadFile = File(...),
    language: str = Query("mn", description="mn / en гэх мэт"),
    vad: bool = Query(True, description="Silence таслах (VAD)"),
):
    # эхлээд raw transcription
    raw = await transcribe(file=file, language=language, vad=vad, keep_files=False)
    if isinstance(raw, JSONResponse):
        return raw

    # зөвхөн mn дээр rule-based цэвэрлэгээ
    if language == "mn":
        raw["text_raw"] = raw["text"]
        raw["text"] = basic_mn_cleanup(raw["text"])
        # сегментүүдийг ч бас цэвэрлэж болно
        for s in raw.get("segments", []):
            s["text"] = basic_mn_cleanup(s.get("text", ""))

    return raw

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "compute": COMPUTE,
        "beam_size": BEAM_SIZE,
        "best_of": BEST_OF,
    }