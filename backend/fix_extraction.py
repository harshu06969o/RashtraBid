"""Re-extract text from uploaded tender PDF and save to DB."""
import pymupdf, sys
sys.path.insert(0, ".")
# pyrefly: ignore [missing-import]
from app.database import SessionLocal
from app import models

db = SessionLocal()
doc = db.query(models.TenderDocument).filter_by(id=1).first()
stored_len = len(doc.extracted_text or "")
print(f"DB stored: filename={doc.filename}, pages={doc.page_count}, text_len={stored_len}")
print(f"File path: {doc.file_path}")

pdf = pymupdf.open(doc.file_path)
text = ""
for page in pdf:
    text += page.get_text()

print(f"Actual text length: {len(text)}")
print(f"Preview:\n{text[:400]}")

doc.extracted_text = text
doc.extraction_method = "PYMUPDF"
db.commit()
print("\n[OK] Text saved to database.")
db.close()
