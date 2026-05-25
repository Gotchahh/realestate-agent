import re
from datetime import datetime, timedelta
from models.schemas import RisultatoValidazione, TipoDocumento


class OutputValidator:
    """
    LAYER 2 — Validazione dell'output dell'LLM.
    Controlla che i dati estratti abbiano senso e siano coerenti.
    Blocca allucinazioni e classificazioni assurde.
    """

    def validate(self, classification_result: dict, contesto_pratica: dict = None) -> RisultatoValidazione:
        """
        Valida il risultato della classificazione.
        Opzionalmente verifica coerenza con altri documenti della pratica.
        """
        problemi = []
        avvisi = []
        richiede_revisione = False

        tipo = classification_result.get("tipo", "")
        dati = classification_result.get("dati_estratti", {})
        confidence = classification_result.get("confidence", 0)

        tipi_validi = [t.value for t in TipoDocumento]
        if tipo not in tipi_validi:
            problemi.append(f"Tipo documento non valido: {tipo}")
            return RisultatoValidazione(
                valido=False,
                problemi=problemi,
                richiede_revisione_umana=True
            )

        if confidence < 30:
            problemi.append(f"Confidence troppo bassa: {confidence}%. Classificazione inaffidabile.")
            richiede_revisione = True
        elif confidence < 60:
            avvisi.append(f"Confidence media: {confidence}%. Verificare manualmente.")

        if tipo == TipoDocumento.VISURA_CATASTALE.value:
            self._valida_visura(dati, problemi, avvisi)
        elif tipo == TipoDocumento.APE.value:
            self._valida_ape(dati, problemi, avvisi)
        elif tipo == TipoDocumento.DOCUMENTO_IDENTITA.value:
            self._valida_identita(dati, problemi, avvisi)

        if contesto_pratica:
            self._valida_coerenza_pratica(tipo, dati, contesto_pratica, problemi, avvisi)

        if problemi and not richiede_revisione:
            richiede_revisione = True

        return RisultatoValidazione(
            valido=len(problemi) == 0,
            problemi=problemi,
            avvisi=avvisi,
            richiede_revisione_umana=richiede_revisione
        )

    def _valida_visura(self, dati: dict, problemi: list, avvisi: list):
        """Validazioni specifiche per visura catastale"""
        cf = dati.get("codice_fiscale_proprietario")
        if cf and not self._cf_valido(cf):
            problemi.append(f"Codice fiscale non valido: {cf}")

        foglio = dati.get("foglio")
        if foglio and not str(foglio).isdigit():
            avvisi.append(f"Foglio catastale sospetto: {foglio}")

        if not dati.get("proprietario"):
            avvisi.append("Proprietario non identificato nella visura")

    def _valida_ape(self, dati: dict, problemi: list, avvisi: list):
        """Validazioni specifiche per APE"""
        classe = dati.get("classe_energetica", "").upper() if dati.get("classe_energetica") else ""
        classi_valide = ["A4", "A3", "A2", "A1", "B", "C", "D", "E", "F", "G"]
        if classe and classe not in classi_valide:
            problemi.append(f"Classe energetica non valida: {classe}")

        data_scadenza = dati.get("data_scadenza")
        if data_scadenza:
            try:
                scadenza = datetime.fromisoformat(data_scadenza)
                if scadenza < datetime.now():
                    problemi.append(f"APE scaduto in data {data_scadenza}")
                elif scadenza < datetime.now() + timedelta(days=90):
                    avvisi.append(f"APE in scadenza il {data_scadenza}")
            except (ValueError, TypeError):
                avvisi.append(f"Data scadenza APE non parsabile: {data_scadenza}")

        data_emissione = dati.get("data_emissione")
        if data_emissione:
            try:
                emissione = datetime.fromisoformat(data_emissione)
                if emissione > datetime.now():
                    problemi.append(f"APE con data emissione futura: {data_emissione}")
            except (ValueError, TypeError):
                pass

    def _valida_identita(self, dati: dict, problemi: list, avvisi: list):
        """Validazioni specifiche per documento d'identità"""
        cf = dati.get("codice_fiscale")
        if cf and not self._cf_valido(cf):
            problemi.append(f"Codice fiscale non valido: {cf}")

        data_scadenza = dati.get("data_scadenza")
        if data_scadenza:
            try:
                scadenza = datetime.fromisoformat(data_scadenza)
                if scadenza < datetime.now():
                    problemi.append(f"Documento d'identità scaduto in data {data_scadenza}")
                elif scadenza < datetime.now() + timedelta(days=60):
                    avvisi.append(f"Documento d'identità in scadenza il {data_scadenza}")
            except (ValueError, TypeError):
                avvisi.append(f"Data scadenza non parsabile: {data_scadenza}")

    def _valida_coerenza_pratica(self, tipo: str, dati: dict, contesto: dict, problemi: list, avvisi: list):
        """
        Verifica che il documento sia coerente con gli altri della stessa pratica.
        Esempio: l'indirizzo nella visura deve corrispondere all'indirizzo dell'APE.
        """
        indirizzo_pratica = contesto.get("indirizzo_immobile", "").lower().strip()
        indirizzo_doc = dati.get("indirizzo", "").lower().strip()

        if indirizzo_pratica and indirizzo_doc:
            if not self._indirizzi_compatibili(indirizzo_pratica, indirizzo_doc):
                problemi.append(
                    f"Indirizzo nel documento ({indirizzo_doc}) "
                    f"non corrisponde all'indirizzo della pratica ({indirizzo_pratica})"
                )

        if tipo == TipoDocumento.VISURA_CATASTALE.value:
            proprietario_doc = dati.get("proprietario", "").lower().strip()
            venditore_pratica = contesto.get("venditore", "").lower().strip()

            if proprietario_doc and venditore_pratica:
                if proprietario_doc not in venditore_pratica and venditore_pratica not in proprietario_doc:
                    avvisi.append(
                        f"Proprietario nella visura ({proprietario_doc}) "
                        f"non corrisponde al venditore della pratica ({venditore_pratica})"
                    )

    def _cf_valido(self, cf: str) -> bool:
        """Controllo base sul formato del codice fiscale"""
        if not cf or len(cf) != 16:
            return False
        pattern = r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$"
        return bool(re.match(pattern, cf.upper()))

    def _indirizzi_compatibili(self, ind1: str, ind2: str) -> bool:
        """
        Controllo euristico — gli indirizzi sembrano riferirsi allo stesso luogo?
        Confronta parole chiave (via, numero, città).
        """
        words1 = set(re.findall(r"\w+", ind1.lower()))
        words2 = set(re.findall(r"\w+", ind2.lower()))

        words1 -= {"via", "viale", "corso", "piazza", "vicolo"}
        words2 -= {"via", "viale", "corso", "piazza", "vicolo"}

        if not words1 or not words2:
            return True

        intersection = words1 & words2
        smaller = min(len(words1), len(words2))
        return len(intersection) / smaller >= 0.5