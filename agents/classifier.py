from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import json
import re


class DocumentClassifier:
    """
    Classifica il documento usando un LLM e ne estrae i dati chiave.
    Restituisce un dizionario strutturato con tipo + dati.
    """

    def __init__(self, api_key: str):
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=api_key,
            temperature=0
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Sei un assistente specializzato in documenti immobiliari italiani.

Ricevi il testo di un documento e devi:
1. Classificare il tipo di documento
2. Estrarre i dati chiave

Tipi di documento ammessi:
- visura_catastale
- planimetria
- ape
- atto_provenienza
- conformita_impianti
- agibilita
- documento_identita
- preliminare
- visura_ipotecaria
- altro

Rispondi SOLO in JSON valido con questa struttura:
{{
    "tipo": "tipo_documento",
    "dati_estratti": {{}},
    "confidence": 0-100,
    "note": "eventuali note"
}}

Per ogni tipo di documento estrai i dati specifici:

VISURA_CATASTALE:
- foglio
- particella
- subalterno
- indirizzo
- proprietario
- codice_fiscale_proprietario

APE:
- classe_energetica (A4, A3, A2, A1, B, C, D, E, F, G)
- data_emissione (formato YYYY-MM-DD)
- data_scadenza (formato YYYY-MM-DD)
- indirizzo

DOCUMENTO_IDENTITA:
- nome
- cognome
- codice_fiscale
- data_nascita (formato YYYY-MM-DD)
- data_scadenza (formato YYYY-MM-DD)
- numero_documento

Per gli altri tipi estrai i dati che ritieni rilevanti.
Se non riesci a estrarre un dato, lascia il campo come null.
NON inventare dati."""),
            ("user", "Classifica questo documento:\n\n{testo}")
        ])

        self.chain = self.prompt | self.llm

    def classify(self, testo: str) -> dict:
        """
        Classifica il documento.
        Restituisce un dizionario con tipo, dati_estratti, confidence.
        """
        if not testo or len(testo.strip()) < 20:
            return {
                "tipo": "altro",
                "dati_estratti": {},
                "confidence": 0,
                "note": "Testo troppo corto per la classificazione"
            }

        testo_troncato = testo[:5000] if len(testo) > 5000 else testo

        try:
            response = self.chain.invoke({"testo": testo_troncato})
            content = response.content.strip()

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group()

            result = json.loads(content)

            if "tipo" not in result:
                result["tipo"] = "altro"
            if "dati_estratti" not in result:
                result["dati_estratti"] = {}
            if "confidence" not in result:
                result["confidence"] = 50

            return result

        except json.JSONDecodeError as e:
            return {
                "tipo": "altro",
                "dati_estratti": {},
                "confidence": 0,
                "note": f"Errore parsing JSON: {str(e)}"
            }
        except Exception as e:
            return {
                "tipo": "altro",
                "dati_estratti": {},
                "confidence": 0,
                "note": f"Errore classificazione: {str(e)}"
            }