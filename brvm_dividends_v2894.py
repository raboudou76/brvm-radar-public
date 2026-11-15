"""BRVM Radar V2.8.9.4 — lecture prudente d'avis PDF BRVM, sans écriture financière."""
import io
import re
from urllib.parse import urlparse
import requests
import pandas as pd
import streamlit as st

MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PAGES = 12
USER_AGENT = {"User-Agent": "Mozilla/5.0 (BRVM Radar research; document audit)"}

def _official_pdf_url(url):
    p = urlparse(str(url))
    return p.scheme == "https" and p.hostname in {"www.brvm.org", "brvm.org"} and p.path.lower().endswith(".pdf")

@st.cache_data(ttl=3600, show_spinner=False)
def download_official_pdf(url):
    if not _official_pdf_url(url):
        raise ValueError("Seuls les liens PDF directs HTTPS du domaine BRVM sont acceptés.")
    with requests.get(url, headers=USER_AGENT, timeout=(10, 35), stream=True, allow_redirects=True) as response:
        response.raise_for_status()
        if not _official_pdf_url(response.url):
            raise ValueError("La redirection quitte un PDF direct du domaine BRVM.")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ValueError("PDF supérieur à 12 Mo : téléchargement interrompu.")
            chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        raise ValueError("La réponse ne contient pas un PDF valide.")
    return data

def _ocr_image(img, lang, psm, timeout):
    import pytesseract
    return pytesseract.image_to_string(img, lang=lang, config=f"--oem 1 --psm {psm}", timeout=timeout)


def extract_pdf_pages(data, max_pages=3):
    """Fast native extraction; bounded multi-pass OCR with per-page diagnostics.

    Never use a catalog description as OCR output. A failed page stays empty.
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Dépendance OCR manquante : vérifier PyMuPDF, Pillow, pytesseract") from exc
    doc = fitz.open(stream=data, filetype="pdf")
    pages, methods, diagnostics = [], [], []
    try:
        if doc.is_encrypted:
            raise ValueError("PDF chiffré non pris en charge")
        langs = pytesseract.get_languages(config="")
        lang = "fra" if "fra" in langs else "eng"
        if lang not in langs:
            raise RuntimeError("Aucune langue OCR disponible : vérifier packages.txt")
        for i in range(min(len(doc), max_pages, MAX_PAGES)):
            page = doc[i]
            native = page.get_text("text")
            if len(re.sub(r"\s+", "", native)) >= 35:
                pages.append(native)
                methods.append("Texte natif")
                diagnostics.append(f"Page {i+1} : texte natif ({len(native)} caractères)")
                continue
            # 1.3x instead of 2.4x: ~70% fewer pixels than the previous version.
            # Limit long-side dimensions to protect small Streamlit instances.
            pix = page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3), alpha=False, colorspace=fitz.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            img.thumbnail((1500, 1900))
            attempts = [(img, 6, 12, "OCR rapide"),
                        (ImageOps.autocontrast(img), 11, 12, "OCR alternatif")]
            best = ""
            log = []
            for image, psm, seconds, label in attempts:
                try:
                    raw = _ocr_image(image, lang, psm, seconds)
                    log.append(f"{label} : {len(raw.strip())} caractères")
                    if len(raw.strip()) > len(best.strip()):
                        best = raw
                    if len(re.sub(r"\s+", "", raw)) >= 60:
                        break
                except RuntimeError as exc:
                    log.append(f"{label} : délai dépassé ou erreur ({str(exc)[:90]})")
                except Exception as exc:
                    log.append(f"{label} : échec ({type(exc).__name__}: {str(exc)[:80]})")
            pages.append(best)
            methods.append(f"OCR {lang}" if best.strip() else "OCR sans résultat")
            diagnostics.append(f"Page {i+1} ({img.width}×{img.height}) : " + "; ".join(log))
        if len(doc) > min(max_pages, MAX_PAGES):
            diagnostics.append(f"{len(doc)} pages au total ; {min(max_pages, MAX_PAGES)} analysées")
        return pages, methods, diagnostics
    finally:
        doc.close()

def _number(raw):
    s = re.sub(r"[\s\u00a0\u202f]", "", raw)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = float(s)
        return v if 0 < v < 1_000_000 else None
    except ValueError:
        return None

def analyze_notice(pages, url, methods=None, diagnostics=None):
    """Produce documentary candidates, never infer NET from an unqualified amount."""
    full = "\n".join(pages)
    compact = re.sub(r"\s+", " ", full)
    year_matches = re.findall(r"(?:exercice|au titre de l.exercice)\s*(?:social\s*)?(20\d{2})", compact, re.I)
    date_matches = re.findall(r"\b(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-]20\d{2}\b", compact)
    amount_pattern = re.compile(
        r"(?:dividende|montant\s+(?:du\s+)?dividende)[^.;\n]{0,160}?"
        r"(\d[\d\s\u00a0\u202f.,]{0,18})\s*(?:FCFA|F\s*CFA|XOF|francs?\s*CFA)\s*(?:par\s+action|/\s*action)?",
        re.I)
    candidates = []
    for page_number, page in enumerate(pages, 1):
        normalized = re.sub(r"\s+", " ", page)
        for m in amount_pattern.finditer(normalized):
            amount = _number(m.group(1))
            if amount is None:
                continue
            context = normalized[max(0, m.start()-110):min(len(normalized), m.end()+110)]
            # A tax rate, total payout or nominal capital is not a dividend per share.
            per_share = bool(re.search(r"(?:par\s+action|/\s*action|actionnaire)", context, re.I))
            if not per_share:
                continue
            before = normalized[max(0, m.start()-85):m.end()]
            if re.search(r"(?:dividende\s+net|net\s+par\s+action|net\s+d.imp[oô]t)", before, re.I):
                kind = "NET_EXPLICITE"
            elif re.search(r"(?:dividende\s+brut|brut\s+par\s+action)", before, re.I):
                kind = "BRUT_EXPLICITE"
            else:
                kind = "NON_QUALIFIE"
            candidates.append({"Page PDF": page_number, "Montant FCFA/action": amount,
                               "Qualification": kind, "Extrait à contrôler": context[:240],
                               "Source": url, "Statut": "À confirmer sur le PDF original"})
    # Different amounts and contradictory labels are intentionally not reconciled.
    return {"Exercices candidats": sorted(set(year_matches)),
            "Dates candidates": sorted(set(date_matches)),
            "Pages lues": len(pages), "Méthodes": methods or [],
            "Diagnostics": diagnostics or [], "Aperçu OCR": full[:4000],
            "Texte disponible": bool(compact.strip()),
            "Montants candidats": pd.DataFrame(candidates)}

def notice_label(item, i, total):
    values = [str(item.get(k) or "") for k in
              ("Contexte", "Contexte officiel", "Titre", "Publication", "Libellé", "Document", "Société")]
    title = next((x for x in values if x.strip() and x.strip().lower() not in ("télécharger", "telecharger")), "")
    if not title:
        title = str(item.get("URL officielle", "")).split("/")[-1].replace("-", " ")
    title = re.sub(r"\s+", " ", title).strip()
    return f"{title[:110]} · {i+1}/{total}"


def render_dividend_pdf_audit():
    st.markdown("#### 2 bis. Lecture OCR optimisée — V2.8.9.4")
    st.caption("Extraction expérimentale, en lecture seule. Aucun dividende, IRVM ou nombre d'actions n'est modifié automatiquement.")
    from brvm_sync_v289 import discover_dividend_documents
    try:
        docs = discover_dividend_documents()
    except Exception as exc:
        st.warning(f"Catalogue indisponible : {exc}")
        return
    pdfs = [d for d in docs if _official_pdf_url(d.get("URL officielle", ""))]
    st.metric("PDF directs candidats", len(pdfs))
    if not pdfs:
        st.info("Aucun PDF direct détecté. Les pages HTML indirectes ne sont pas interprétées comme PDF.")
        return
    choice = st.selectbox("Avis BRVM à analyser", range(len(pdfs)),
        format_func=lambda i: notice_label(pdfs[i], i, len(pdfs)),
        key="v2892_notice_choice")
    item = pdfs[choice]
    url = item["URL officielle"]
    st.link_button("Consulter le PDF officiel", url)
    max_pages = st.selectbox("Pages à examiner", [1, 2, 3, 5], index=0, key="v2894_pages")
    if st.button("Lire et analyser cet avis PDF", key="v2894_read_pdf"):
        try:
            with st.spinner("Lecture du document officiel…"):
                data = download_official_pdf(url)
                pages, methods, diagnostics = extract_pdf_pages(data, max_pages=max_pages)
                result = analyze_notice(pages, url, methods, diagnostics)
            st.session_state["v2894_last_result"] = (url, result)
        except Exception as exc:
            st.error(f"Extraction non concluante : {exc}")
    saved = st.session_state.get("v2894_last_result")
    if not saved or saved[0] != url:
        return
    result = saved[1]
    st.caption(f"Pages lues : {result['Pages lues']} · Exercices détectés : {', '.join(result['Exercices candidats']) or 'non déterminés'}")
    st.caption("Méthode de lecture : " + ", ".join(result.get("Méthodes", [])))
    st.caption(f"Dates candidates : {', '.join(result['Dates candidates']) or 'non déterminées'}")
    with st.expander("Diagnostic technique OCR", expanded=False):
        for line in result.get("Diagnostics", []):
            st.text(line)
    with st.expander("Diagnostic — extrait du texte réellement lu (OCR ou natif)"):
        st.text(result.get("Aperçu OCR", "") or "Aucun texte détecté")
    if not result["Texte disponible"]:
        st.warning("Aucun texte extrait. Consulter le diagnostic technique : OCR indisponible, délai dépassé ou image illisible.")
    candidates = result["Montants candidats"]
    if candidates.empty:
        st.warning("Aucun montant par action suffisamment explicite détecté. Consulter l'avis original.")
        return
    st.dataframe(candidates, hide_index=True, use_container_width=True)
    st.download_button("Exporter les candidats audités (CSV)",
        candidates.to_csv(index=False, sep=";").encode("utf-8-sig"),
        "brvm_v2894_dividendes_a_verifier.csv", "text/csv")
    st.warning("Les montants ci-dessus ne sont PAS validés. En particulier NON_QUALIFIE ne signifie ni brut ni net. Aucun préremplissage automatique avant contrôle documentaire.")
