"""CasaAgent — assistente documentale AI per agenzie immobiliari italiane."""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime
from typing import Optional

import streamlit as st
from pydantic import ValidationError

from agents.classifier import DocumentClassifier
from agents.ingestion import DocumentIngestion
from agents.practice_tracker import PracticeTracker
from models.schemas import (
    APE,
    DocumentoBase,
    DocumentoIdentita,
    Pratica,
    RisultatoValidazione,
    StatoPratica,
    TipoDocumento,
    Visura,
)
from validators.input_validator import InputValidator
from validators.output_validator import OutputValidator


TITOLI_TIPO: dict[str, str] = {
    TipoDocumento.VISURA_CATASTALE.value: "Visura catastale",
    TipoDocumento.PLANIMETRIA.value: "Planimetria",
    TipoDocumento.APE.value: "APE — Attestato Prestazione Energetica",
    TipoDocumento.ATTO_PROVENIENZA.value: "Atto di provenienza",
    TipoDocumento.CONFORMITA_IMPIANTI.value: "Conformità impianti",
    TipoDocumento.AGIBILITA.value: "Agibilità",
    TipoDocumento.DOCUMENTO_IDENTITA.value: "Documento d'identità",
    TipoDocumento.PRELIMINARE.value: "Preliminare di vendita",
    TipoDocumento.VISURA_IPOTECARIA.value: "Visura ipotecaria",
    TipoDocumento.ALTRO.value: "Altro",
}

BADGE_STATO: dict[str, str] = {
    StatoPratica.APERTA.value: "🟦 Aperta",
    StatoPratica.IN_LAVORAZIONE.value: "🟨 In lavorazione",
    StatoPratica.COMPLETA.value: "🟩 Completa",
    StatoPratica.BLOCCATA.value: "🟥 Bloccata",
}


@st.cache_resource
def init_pipeline() -> tuple[DocumentIngestion, DocumentClassifier, InputValidator, OutputValidator]:
    api_key = st.secrets.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        st.error(
            "GROQ_API_KEY mancante. Configurala in `.streamlit/secrets.toml` "
            "o come variabile d'ambiente."
        )
        st.stop()
    return (
        DocumentIngestion(),
        DocumentClassifier(api_key=api_key),
        InputValidator(),
        OutputValidator(),
    )


def init_session_state() -> None:
    if "tracker" not in st.session_state:
        st.session_state["tracker"] = PracticeTracker()
    if "pratica_id_attiva" not in st.session_state:
        st.session_state["pratica_id_attiva"] = None


def _salva_temp(uploaded_file) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(uploaded_file.getbuffer())
    tmp.close()
    return tmp.name


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _costruisci_documento(classification: dict, nome_file: str) -> tuple[DocumentoBase, Optional[str]]:
    """Mappa l'output del classifier su uno schema Pydantic concreto.
    Ritorna (documento, errore_di_validazione_opzionale)."""
    tipo_raw = classification.get("tipo", TipoDocumento.ALTRO.value)
    dati = classification.get("dati_estratti") or {}
    note = classification.get("note")

    try:
        tipo_enum = TipoDocumento(tipo_raw)
    except ValueError:
        tipo_enum = TipoDocumento.ALTRO

    common = {
        "nome_file": nome_file,
        "dati_estratti": dati,
        "note": note,
    }

    try:
        if tipo_enum == TipoDocumento.VISURA_CATASTALE:
            return Visura(
                **common,
                foglio=dati.get("foglio"),
                particella=dati.get("particella"),
                subalterno=dati.get("subalterno"),
                indirizzo=dati.get("indirizzo"),
                proprietario=dati.get("proprietario"),
                codice_fiscale_proprietario=dati.get("codice_fiscale_proprietario"),
            ), None
        if tipo_enum == TipoDocumento.APE:
            return APE(
                **common,
                classe_energetica=dati.get("classe_energetica"),
                data_emissione=_parse_date(dati.get("data_emissione")),
                data_scadenza=_parse_date(dati.get("data_scadenza")),
                indirizzo=dati.get("indirizzo"),
            ), None
        if tipo_enum == TipoDocumento.DOCUMENTO_IDENTITA:
            return DocumentoIdentita(
                **common,
                nome=dati.get("nome"),
                cognome=dati.get("cognome"),
                codice_fiscale=dati.get("codice_fiscale"),
                data_nascita=_parse_date(dati.get("data_nascita")),
                data_scadenza=_parse_date(dati.get("data_scadenza")),
                numero_documento=dati.get("numero_documento"),
            ), None
        return DocumentoBase(tipo=tipo_enum, **common), None
    except ValidationError as exc:
        return DocumentoBase(tipo=tipo_enum, **common), str(exc)


def _mostra_validazione(risultato: RisultatoValidazione, label: str) -> None:
    if risultato.valido and not risultato.avvisi:
        st.success(f"{label}: nessun problema rilevato.")
        return
    if risultato.problemi:
        st.error(f"**{label} — problemi bloccanti:**\n" + "\n".join(f"- {p}" for p in risultato.problemi))
    if risultato.avvisi:
        st.warning(f"**{label} — avvisi:**\n" + "\n".join(f"- {a}" for a in risultato.avvisi))
    if risultato.richiede_revisione_umana:
        st.info("Si consiglia revisione umana di questo documento.")


def render_sidebar(tracker: PracticeTracker) -> Optional[Pratica]:
    st.sidebar.title("📁 Pratiche")

    with st.sidebar.expander("➕ Nuova pratica", expanded=not tracker.lista_pratiche()):
        with st.form("nuova_pratica", clear_on_submit=True):
            indirizzo = st.text_input("Indirizzo immobile *", placeholder="Via Roma 10, Milano")
            venditore = st.text_input("Venditore", placeholder="Mario Rossi")
            acquirente = st.text_input("Acquirente", placeholder="Lucia Bianchi")
            submit = st.form_submit_button("Crea pratica", type="primary")
            if submit:
                if not indirizzo.strip():
                    st.error("L'indirizzo è obbligatorio.")
                else:
                    nuovo_id = uuid.uuid4().hex[:8]
                    tracker.crea_pratica(
                        pratica_id=nuovo_id,
                        indirizzo=indirizzo.strip(),
                        venditore=venditore.strip() or None,
                        acquirente=acquirente.strip() or None,
                    )
                    st.session_state["pratica_id_attiva"] = nuovo_id
                    st.success(f"Pratica creata: {nuovo_id}")
                    st.rerun()

    pratiche = tracker.lista_pratiche()
    if not pratiche:
        st.sidebar.info("Nessuna pratica ancora. Creane una qui sopra per iniziare.")
        return None

    opzioni = {p.id: f"{p.indirizzo_immobile} — {p.id}" for p in pratiche}
    ids = list(opzioni.keys())
    default_index = ids.index(st.session_state["pratica_id_attiva"]) if st.session_state["pratica_id_attiva"] in ids else 0

    selected = st.sidebar.selectbox(
        "Pratica attiva",
        options=ids,
        index=default_index,
        format_func=lambda x: opzioni[x],
    )
    st.session_state["pratica_id_attiva"] = selected
    pratica = tracker.get_pratica(selected)

    if pratica:
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Stato:** {BADGE_STATO.get(pratica.stato.value, pratica.stato.value)}")
        st.sidebar.progress(
            pratica.percentuale_completamento() / 100,
            text=f"Completamento {pratica.percentuale_completamento():.0f}%",
        )
        if pratica.venditore:
            st.sidebar.caption(f"Venditore: {pratica.venditore}")
        if pratica.acquirente:
            st.sidebar.caption(f"Acquirente: {pratica.acquirente}")

    return pratica


def render_tab_upload(
    tracker: PracticeTracker,
    pratica: Pratica,
    ingestion: DocumentIngestion,
    classifier: DocumentClassifier,
    input_validator: InputValidator,
    output_validator: OutputValidator,
) -> None:
    st.subheader(f"📥 Carica documento per pratica `{pratica.id}`")
    st.caption(f"Immobile: **{pratica.indirizzo_immobile}**")

    uploaded = st.file_uploader("PDF da processare", type=["pdf"], accept_multiple_files=False)
    if not uploaded:
        return

    if not st.button("🚀 Processa documento", type="primary"):
        return

    temp_path: Optional[str] = None
    try:
        with st.status("Elaborazione in corso...", expanded=True) as status:
            st.write("📄 Salvataggio file temporaneo")
            temp_path = _salva_temp(uploaded)

            st.write("🔍 Estrazione testo (pdfplumber / OCR)")
            ingestion_res = ingestion.extract_text(temp_path)
            st.caption(
                f"Metodo: **{ingestion_res['metodo']}** · "
                f"Confidence: **{ingestion_res['confidence']:.1f}%** · "
                f"Pagine: **{ingestion_res['numero_pagine']}**"
            )

            st.write("🛡️ Layer 1 — validazione input")
            input_res = input_validator.validate(ingestion_res, temp_path)
            if not input_res.valido:
                status.update(label="Documento rifiutato", state="error")
                _mostra_validazione(input_res, "Input Validator")
                return

            st.write("🤖 Classificazione LLM (Groq · llama-3.3-70b)")
            classification = classifier.classify(ingestion_res["testo"])

            st.write("🛡️ Layer 2 — validazione output")
            contesto = tracker.report_pratica(pratica.id)
            output_res = output_validator.validate(classification, contesto_pratica=contesto)

            st.write("📂 Registrazione nella pratica")
            documento, errore_pydantic = _costruisci_documento(classification, uploaded.name)
            report = tracker.aggiungi_documento(pratica.id, documento)

            status.update(label="Elaborazione completata", state="complete")

        st.markdown("---")
        st.subheader("📊 Risultato")

        col1, col2, col3 = st.columns(3)
        col1.metric("Tipo", TITOLI_TIPO.get(classification.get("tipo", ""), classification.get("tipo", "?")))
        col2.metric("Confidence LLM", f"{classification.get('confidence', 0)}%")
        col3.metric("Completamento pratica", f"{report['completamento']:.0f}%")

        with st.expander("Dati estratti", expanded=True):
            st.json(classification.get("dati_estratti", {}))
            if classification.get("note"):
                st.caption(f"Note: {classification['note']}")

        _mostra_validazione(input_res, "Input Validator")
        _mostra_validazione(output_res, "Output Validator")
        if errore_pydantic:
            st.warning(
                "Alcuni campi non sono passati la validazione Pydantic e sono stati salvati "
                f"come dati grezzi:\n```\n{errore_pydantic}\n```"
            )

    except Exception as exc:
        st.error(f"Errore durante l'elaborazione: {exc}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def render_tab_dashboard(tracker: PracticeTracker, pratica: Pratica) -> None:
    st.subheader(f"📈 Dashboard — pratica `{pratica.id}`")

    col1, col2, col3 = st.columns(3)
    col1.metric("Completamento", f"{pratica.percentuale_completamento():.0f}%")
    col2.metric("Stato", BADGE_STATO.get(pratica.stato.value, pratica.stato.value))
    col3.metric("Documenti ricevuti", len(pratica.documenti_ricevuti))

    st.markdown("---")
    st.markdown("### ✅ Checklist documenti")
    tipi_ricevuti = {d.tipo.value for d in pratica.documenti_ricevuti}
    checklist_rows = [
        {
            "Documento": TITOLI_TIPO.get(t.value, t.value),
            "Stato": "✅ Ricevuto" if t.value in tipi_ricevuti else "⬜ Mancante",
        }
        for t in pratica.documenti_richiesti
    ]
    st.dataframe(checklist_rows, use_container_width=True, hide_index=True)

    st.markdown("### 📄 Documenti ricevuti")
    if pratica.documenti_ricevuti:
        rows = [
            {
                "Tipo": TITOLI_TIPO.get(d.tipo.value, d.tipo.value),
                "File": d.nome_file,
                "Ricevuto il": d.data_ricezione.strftime("%d/%m/%Y %H:%M"),
            }
            for d in pratica.documenti_ricevuti
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Nessun documento ancora caricato.")

    st.markdown("### ⏰ Documenti in scadenza (prossimi 90 giorni)")
    scadenze = tracker.documenti_in_scadenza(pratica.id, giorni=90)
    if not scadenze:
        st.success("Nessun documento in scadenza nei prossimi 90 giorni.")
    else:
        for s in scadenze:
            badge = "🔴 URGENTE" if s["urgente"] else "🟡"
            st.markdown(
                f"{badge} **{TITOLI_TIPO.get(s['tipo_documento'], s['tipo_documento'])}** "
                f"({s['nome_file']}) — scade il {s['data_scadenza']} "
                f"({s['giorni_residui']} giorni)"
            )


def main() -> None:
    st.set_page_config(page_title="CasaAgent", page_icon="🏠", layout="wide")
    st.title("🏠 CasaAgent")
    st.caption("Assistente documentale AI per agenzie immobiliari italiane")

    init_session_state()
    ingestion, classifier, input_validator, output_validator = init_pipeline()
    tracker: PracticeTracker = st.session_state["tracker"]

    pratica = render_sidebar(tracker)

    if pratica is None:
        st.info("👈 Crea o seleziona una pratica nella sidebar per iniziare.")
        st.markdown(
            "**CasaAgent** classifica automaticamente i documenti di una pratica immobiliare "
            "(visure, APE, planimetrie, documenti d'identità, ecc.), valida i dati estratti e "
            "tiene traccia di completamento e scadenze."
        )
        return

    tab_upload, tab_dashboard = st.tabs(["📥 Carica documento", "📊 Dashboard pratica"])
    with tab_upload:
        render_tab_upload(
            tracker, pratica, ingestion, classifier, input_validator, output_validator
        )
    with tab_dashboard:
        render_tab_dashboard(tracker, pratica)


if __name__ == "__main__":
    main()
