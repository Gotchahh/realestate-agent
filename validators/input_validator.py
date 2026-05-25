import hashlib
from pathlib import Path
from models.schemas import RisultatoValidazione


class InputValidator:
    """
    LAYER 1 — Validazione dell'input.
    Controlla che il documento sia leggibile, non duplicato, e processabile.
    Blocca spazzatura prima che arrivi all'LLM (risparmio tempo e costi).
    """

    def __init__(self, ocr_threshold: float = 60.0):
        self.ocr_threshold = ocr_threshold
        self.hash_documenti_processati = set()

    def validate(self, ingestion_result: dict, file_path: str) -> RisultatoValidazione:
        """
        Valida l'output dell'ingestion.
        Restituisce un RisultatoValidazione.
        """
        problemi = []
        avvisi = []
        richiede_revisione = False

        testo = ingestion_result.get("testo", "")
        confidence = ingestion_result.get("confidence", 0)
        metodo = ingestion_result.get("metodo", "")
        num_pagine = ingestion_result.get("numero_pagine", 0)

        if not testo or len(testo.strip()) < 20:
            problemi.append("Documento illeggibile o vuoto")
            return RisultatoValidazione(
                valido=False,
                problemi=problemi,
                richiede_revisione_umana=True
            )

        if metodo == "ocr" and confidence < self.ocr_threshold:
            problemi.append(
                f"OCR confidence troppo bassa ({confidence:.1f}%). "
                f"Documento probabilmente scansionato male. "
                f"Richiedere una versione di qualità migliore."
            )
            richiede_revisione = True

        if metodo == "ocr" and confidence < 80 and confidence >= self.ocr_threshold:
            avvisi.append(
                f"OCR confidence media ({confidence:.1f}%). "
                f"Verificare manualmente i dati estratti."
            )

        if num_pagine == 0:
            problemi.append("Impossibile leggere le pagine del documento")
            return RisultatoValidazione(
                valido=False,
                problemi=problemi,
                richiede_revisione_umana=True
            )

        hash_doc = self._calcola_hash(file_path)
        if hash_doc in self.hash_documenti_processati:
            problemi.append("Documento duplicato — già processato in precedenza")
            return RisultatoValidazione(
                valido=False,
                problemi=problemi,
                richiede_revisione_umana=False
            )

        if not self._sembra_documento_immobiliare(testo):
            avvisi.append(
                "Il documento non sembra essere un documento immobiliare. "
                "Verificare se è pertinente alla pratica."
            )
            richiede_revisione = True

        if not problemi:
            self.hash_documenti_processati.add(hash_doc)

        return RisultatoValidazione(
            valido=len(problemi) == 0,
            problemi=problemi,
            avvisi=avvisi,
            richiede_revisione_umana=richiede_revisione
        )

    def _calcola_hash(self, file_path: str) -> str:
        """Calcola hash MD5 del file per detection di duplicati"""
        path = Path(file_path)
        if not path.exists():
            return ""

        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _sembra_documento_immobiliare(self, testo: str) -> bool:
        """
        Controllo euristico — il documento contiene parole tipiche di documenti immobiliari?
        """
        parole_chiave = [
            "catasto", "catastale", "foglio", "particella", "subalterno",
            "immobile", "abitazione", "appartamento", "fabbricato",
            "energetica", "energetico", "ape", "rogito", "notaio",
            "compravendita", "atto", "planimetria", "agibilità",
            "conformità", "impianto", "ipoteca", "preliminare",
            "venditore", "acquirente", "proprietario", "intestatario"
        ]

        testo_lower = testo.lower()
        match = sum(1 for p in parole_chiave if p in testo_lower)
        return match >= 2