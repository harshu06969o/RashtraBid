"""Central path constants — dynamic relative paths using pathlib."""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = APP_DIR.parent
DATA_DIR = BACKEND_ROOT / "data"
SAMPLE_DOCS_DIR = DATA_DIR / "sample_docs"
TENDER_DOCS_DIR = DATA_DIR / "tender_docs"
BIDDER_DOCS_DIR = DATA_DIR / "bidder_docs"
UPLOADS_DIR = DATA_DIR / "uploads"
PIPELINE_DIR = APP_DIR / "pipeline"

for _dir in (SAMPLE_DOCS_DIR, TENDER_DOCS_DIR, BIDDER_DOCS_DIR, UPLOADS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
