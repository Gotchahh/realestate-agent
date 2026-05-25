import pdfplumber
from pdf2image import convert_from_path
import pytesseract
from pathlib import Path


class DocumentIngestion:
    """
    Estrae il testo da un PDF.
    Prima prova con pdfplumber (testo digitale).
    Se il PDF è scansionato (immagine), usa OCR con Tesseract.
    """

    def __init__(self, ocr_confidence_threshold: float = 60.0):
        self.ocr_confidence_threshold = ocr_confidence_threshold

    def extract_text(self, pdf_path: str) -> dict:
        """
        Estrae il testo da un PDF.
        Restituisce un dizionario con:
        - testo: il contenuto estratto
        - metodo: "digital" o "ocr"
        - confidence: affidabilità dell'estrazione (0-100)
        - numero_pagine: quante pagine ha il PDF
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"File non trovato: {pdf_path}")

        testo_digitale, num_pagine = self._extract_digital(pdf_path)

        if testo_digitale and len(testo_digitale.strip()) > 50:
            return {
                "testo": testo_digitale,
                "metodo": "digital",
                "confidence": 100.0,
                "numero_pagine": num_pagine
            }

        testo_ocr, confidence = self._extract_ocr(pdf_path)

        return {
            "testo": testo_ocr,
            "metodo": "ocr",
            "confidence": confidence,
            "numero_pagine": num_pagine
        }

    def _extract_digital(self, pdf_path: str) -> tuple[str, int]:
        """Estrae testo da PDF digitali con pdfplumber"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                num_pagine = len(pdf.pages)
                testi = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        testi.append(page_text)
                return "\n\n".join(testi), num_pagine
        except Exception as e:
            return "", 0

    def _extract_ocr(self, pdf_path: str) -> tuple[str, float]:
        """Estrae testo da PDF scansionati con OCR"""
        try:
            images = convert_from_path(pdf_path)
            testi = []
            confidence_totale = 0
            num_pages = 0

            for image in images:
                ocr_data = pytesseract.image_to_data(
                    image,
                    lang="ita",
                    output_type=pytesseract.Output.DICT
                )

                page_text = " ".join([w for w in ocr_data["text"] if w.strip()])
                testi.append(page_text)

                confidences = [int(c) for c in ocr_data["conf"] if int(c) > 0]
                if confidences:
                    confidence_totale += sum(confidences) / len(confidences)
                    num_pages += 1

            avg_confidence = confidence_totale / num_pages if num_pages > 0 else 0
            return "\n\n".join(testi), avg_confidence

        except Exception as e:
            return "", 0.0