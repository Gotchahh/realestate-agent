from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TipoDocumento(str, Enum):
    VISURA_CATASTALE = "visura_catastale"
    PLANIMETRIA = "planimetria"
    APE = "ape"
    ATTO_PROVENIENZA = "atto_provenienza"
    CONFORMITA_IMPIANTI = "conformita_impianti"
    AGIBILITA = "agibilita"
    DOCUMENTO_IDENTITA = "documento_identita"
    PRELIMINARE = "preliminare"
    VISURA_IPOTECARIA = "visura_ipotecaria"
    ALTRO = "altro"


class StatoPratica(str, Enum):
    APERTA = "aperta"
    IN_LAVORAZIONE = "in_lavorazione"
    COMPLETA = "completa"
    BLOCCATA = "bloccata"


class DocumentoBase(BaseModel):
    """Schema base per ogni documento processato"""
    tipo: TipoDocumento
    nome_file: str
    data_ricezione: datetime = Field(default_factory=datetime.now)
    pratica_id: Optional[str] = None
    dati_estratti: dict = Field(default_factory=dict)
    note: Optional[str] = None


class Visura(DocumentoBase):
    """Schema per visura catastale"""
    tipo: TipoDocumento = TipoDocumento.VISURA_CATASTALE
    foglio: Optional[str] = None
    particella: Optional[str] = None
    subalterno: Optional[str] = None
    indirizzo: Optional[str] = None
    proprietario: Optional[str] = None
    codice_fiscale_proprietario: Optional[str] = None

    @field_validator("codice_fiscale_proprietario")
    @classmethod
    def valida_codice_fiscale(cls, v):
        if v and len(v) != 16:
            raise ValueError("Codice fiscale deve avere 16 caratteri")
        return v


class APE(DocumentoBase):
    """Schema per Attestato Prestazione Energetica"""
    tipo: TipoDocumento = TipoDocumento.APE
    classe_energetica: Optional[str] = None
    data_emissione: Optional[datetime] = None
    data_scadenza: Optional[datetime] = None
    indirizzo: Optional[str] = None

    @field_validator("classe_energetica")
    @classmethod
    def valida_classe(cls, v):
        if v and v.upper() not in ["A4", "A3", "A2", "A1", "B", "C", "D", "E", "F", "G"]:
            raise ValueError(f"Classe energetica non valida: {v}")
        return v.upper() if v else v


class DocumentoIdentita(DocumentoBase):
    """Schema per documento d'identità"""
    tipo: TipoDocumento = TipoDocumento.DOCUMENTO_IDENTITA
    nome: Optional[str] = None
    cognome: Optional[str] = None
    codice_fiscale: Optional[str] = None
    data_nascita: Optional[datetime] = None
    data_scadenza: Optional[datetime] = None
    numero_documento: Optional[str] = None

    @field_validator("codice_fiscale")
    @classmethod
    def valida_cf(cls, v):
        if v and len(v) != 16:
            raise ValueError("Codice fiscale deve avere 16 caratteri")
        return v.upper() if v else v


class Pratica(BaseModel):
    """Schema per una pratica immobiliare"""
    id: str
    indirizzo_immobile: str
    venditore: Optional[str] = None
    acquirente: Optional[str] = None
    data_apertura: datetime = Field(default_factory=datetime.now)
    stato: StatoPratica = StatoPratica.APERTA
    documenti_ricevuti: List[DocumentoBase] = Field(default_factory=list)

    documenti_richiesti: List[TipoDocumento] = Field(default_factory=lambda: [
        TipoDocumento.ATTO_PROVENIENZA,
        TipoDocumento.VISURA_CATASTALE,
        TipoDocumento.PLANIMETRIA,
        TipoDocumento.VISURA_IPOTECARIA,
        TipoDocumento.APE,
        TipoDocumento.AGIBILITA,
        TipoDocumento.CONFORMITA_IMPIANTI,
        TipoDocumento.DOCUMENTO_IDENTITA,
        TipoDocumento.PRELIMINARE,
    ])

    def percentuale_completamento(self) -> float:
        if not self.documenti_richiesti:
            return 100.0
        tipi_ricevuti = {d.tipo for d in self.documenti_ricevuti}
        completati = sum(1 for t in self.documenti_richiesti if t in tipi_ricevuti)
        return (completati / len(self.documenti_richiesti)) * 100

    def documenti_mancanti(self) -> List[TipoDocumento]:
        tipi_ricevuti = {d.tipo for d in self.documenti_ricevuti}
        return [t for t in self.documenti_richiesti if t not in tipi_ricevuti]


class RisultatoValidazione(BaseModel):
    """Schema per il risultato della validazione"""
    valido: bool
    problemi: List[str] = Field(default_factory=list)
    avvisi: List[str] = Field(default_factory=list)
    richiede_revisione_umana: bool = False