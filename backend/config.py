from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _resolve_data_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (BASE_DIR / path).resolve()


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"

DATA_DIR = _resolve_data_dir(os.getenv("DATA_DIR", "data"))
UPLOAD_DIR = DATA_DIR / "uploads"

CHUNK_SIZE = max(100, _env_int("CHUNK_SIZE", 500))
CHUNK_OVERLAP = max(0, _env_int("CHUNK_OVERLAP", 80))
CHUNK_OVERLAP = min(CHUNK_OVERLAP, CHUNK_SIZE // 2)

TOP_K = max(1, min(_env_int("TOP_K", 4), 10))
MAX_UPLOAD_MB = max(1, _env_int("MAX_UPLOAD_MB", 20))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

AGENT_MAX_STEPS = max(1, min(_env_int("AGENT_MAX_STEPS", 4), 8))
AGENT_TOOL_TIMEOUT = max(1, min(_env_int("AGENT_TOOL_TIMEOUT", 5), 30))
AGENT_MAX_CONTEXTS = max(4, min(_env_int("AGENT_MAX_CONTEXTS", 12), 24))

# LLM 模式：llm（默认）/ replay（回放录制）/ demo（兜底）
_FORCED_MODE = os.getenv("LLM_MODE", "").strip().lower()
LLM_MODE = _FORCED_MODE if _FORCED_MODE in {"llm", "replay", "demo"} else (
    "llm" if DEEPSEEK_API_KEY else "demo"
)

FORCE_DEMO = LLM_MODE == "demo"  # 兼容旧代码
DEMO_MODE = FORCE_DEMO

# --------------------------------------------------------------------------- #
# 项目定向测评
# --------------------------------------------------------------------------- #
ASSESSMENT_DB = DATA_DIR / "assessment.db"
ASSESSMENT_UPLOAD_DIR = DATA_DIR / "assessment_uploads"
CODE_UPLOAD_DIR = DATA_DIR / "assessment_code"

PRACTICE_ITEMS_PER_TAG = 3
PRACTICE_BATCH_SIZE = max(3, min(_env_int("PRACTICE_BATCH_SIZE", 8), 12))
PRACTICE_MIN_TOTAL = max(6, _env_int("PRACTICE_MIN_TOTAL", 20))
EXAM_QUESTION_COUNT = max(3, _env_int("EXAM_QUESTION_COUNT", 10))
EXAM_CANDIDATE_COUNT = max(EXAM_QUESTION_COUNT, _env_int("EXAM_CANDIDATE_COUNT", 22))
EXAM_MAX_REFILL_ROUNDS = 3
REVIEW_ITEMS_MIN = max(3, _env_int("REVIEW_ITEMS_MIN", 10))
INTERVIEW_MAX_ROUNDS = 3
INTERVIEW_MAX_FOLLOW_UPS = 2
DEDUP_OVERLAP_THRESHOLD = 0.6
PASS_EXAM_RATIO = 0.70
PASS_INTERVIEW_RATIO = 0.70
PASS_MIN_L2_COUNT = 5

CODE_MAX_BYTES = 200 * 1024
CODE_EXTENSIONS = {".vue", ".ts", ".js"}

FIXTURE_DIR = BASE_DIR.parent / "eval" / "fixtures"

FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ASSESSMENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CODE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
