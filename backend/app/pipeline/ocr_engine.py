import cv2
import pytesseract
import pdfplumber
import pymupdf
import numpy as np

# Tesseract path configuration (to be adjusted based on OS/Docker)
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

class OCREngine:
    def __init__(self):
        pass

    def extract_from_digital_pdf(self, file_path: str) -> str:
        """Extract text from a digital PDF using PyMuPDF and pdfplumber."""
        text_content = ""
        try:
            # First pass: Fast extraction using PyMuPDF
            doc = pymupdf.open(file_path)
            for page in doc:
                text_content += page.get_text()
            
            # Second pass: Table extraction using pdfplumber if needed
            # (In production, we'd merge structured table data with text)
            return text_content.strip()
        except Exception as e:
            print(f"Error in digital extraction: {e}")
            return ""

    def extract_from_image(self, image_path: str) -> str:
        """Extract text from an image/scanned document using OpenCV and Tesseract."""
        try:
            # 1. Load image using OpenCV
            image = cv2.imread(image_path)
            
            # 2. Preprocessing for better OCR
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # Thresholding
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            # Noise removal
            kernel = np.ones((1, 1), np.uint8)
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            
            # 3. Perform OCR
            custom_config = r'--oem 3 --psm 6'
            extracted_text = pytesseract.image_to_string(opening, config=custom_config)
            
            return extracted_text.strip()
        except Exception as e:
            print(f"Error in OCR extraction: {e}")
            return ""

    def process_document(self, file_path: str, is_scanned: bool = False) -> str:
        """Main entry point to route the document to the right extraction pipeline."""
        if is_scanned or file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            return self.extract_from_image(file_path)
        elif file_path.lower().endswith('.pdf'):
            return self.extract_from_digital_pdf(file_path)
        else:
            raise ValueError("Unsupported file format")

# Example Usage
if __name__ == "__main__":
    engine = OCREngine()
    # print(engine.process_document("sample.pdf"))
