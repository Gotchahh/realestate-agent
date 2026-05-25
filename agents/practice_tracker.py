from datetime import datetime, timedelta
from typing import Optional
from models.schemas import Pratica, DocumentoBase, TipoDocumento, StatoPratica


class PracticeTracker:
    """
    Gestisce lo stato delle pratiche immobiliari.
    Tiene traccia di documenti ricevuti, mancanti, e scadenze.
    """

    def __init__(self):
        self.pratiche: dict[str, Pratica] = {}

    def crea_pratica(self, pratica_id: str, indirizzo: str, venditore: str = None, acquirente: str = None) -> Pratica:
        """Crea una nuova pratica immobiliare"""
        if pratica_id in self.pratiche:
            raise ValueError(f"Pratica {pratica_id} già esistente")

        pratica = Pratica(
            id=pratica_id,
            indirizzo_immobile=indirizzo,
            venditore=venditore,
            acquirente=acquirente
        )
        self.pratiche[pratica_id] = pratica
        return pratica

    def get_pratica(self, pratica_id: str) -> Optional[Pratica]:
        """Restituisce una pratica per ID"""
        return self.pratiche.get(pratica_id)

    def lista_pratiche(self) -> list[Pratica]:
        """Restituisce tutte le pratiche"""
        return list(self.pratiche.values())

    def aggiungi_documento(self, pratica_id: str, documento: DocumentoBase) -> dict:
        """
        Aggiunge un documento a una pratica.
        Aggiorna lo stato della pratica.
        Restituisce un report di cosa è cambiato.
        """
        pratica = self.pratiche.get(pratica_id)
        if not pratica:
            raise ValueError(f"Pratica {pratica_id} non trovata")

        documento.pratica_id = pratica_id
        pratica.documenti_ricevuti.append(documento)

        completamento = pratica.percentuale_completamento()
        mancanti = pratica.documenti_mancanti()

        if completamento >= 100:
            pratica.stato = StatoPratica.COMPLETA
        elif completamento > 0:
            pratica.stato = StatoPratica.IN_LAVORAZIONE

        return {
            "documento_aggiunto": documento.tipo.value,
            "completamento": completamento,
            "documenti_mancanti": [m.value for m in mancanti],
            "stato_pratica": pratica.stato.value
        }

    def documenti_in_scadenza(self, pratica_id: str, giorni: int = 90) -> list[dict]:
        """
        Trova documenti che scadranno entro N giorni.
        Utile per APE, documenti d'identità, ecc.
        """
        pratica = self.pratiche.get(pratica_id)
        if not pratica:
            return []

        scadenze = []
        limite = datetime.now() + timedelta(days=giorni)

        for doc in pratica.documenti_ricevuti:
            data_scadenza = doc.dati_estratti.get("data_scadenza")
            if data_scadenza:
                try:
                    scadenza = datetime.fromisoformat(data_scadenza)
                    if scadenza < limite:
                        giorni_residui = (scadenza - datetime.now()).days
                        scadenze.append({
                            "tipo_documento": doc.tipo.value,
                            "nome_file": doc.nome_file,
                            "data_scadenza": data_scadenza,
                            "giorni_residui": giorni_residui,
                            "urgente": giorni_residui < 30
                        })
                except (ValueError, TypeError):
                    pass

        return sorted(scadenze, key=lambda x: x["giorni_residui"])

    def report_pratica(self, pratica_id: str) -> dict:
        """Genera un report completo dello stato della pratica"""
        pratica = self.pratiche.get(pratica_id)
        if not pratica:
            return {}

        return {
            "id": pratica.id,
            "indirizzo": pratica.indirizzo_immobile,
            "venditore": pratica.venditore,
            "acquirente": pratica.acquirente,
            "stato": pratica.stato.value,
            "completamento": pratica.percentuale_completamento(),
            "documenti_ricevuti": [
                {
                    "tipo": d.tipo.value,
                    "nome_file": d.nome_file,
                    "data_ricezione": d.data_ricezione.isoformat(),
                    "dati_estratti": d.dati_estratti
                }
                for d in pratica.documenti_ricevuti
            ],
            "documenti_mancanti": [m.value for m in pratica.documenti_mancanti()],
            "documenti_in_scadenza": self.documenti_in_scadenza(pratica_id)
        }