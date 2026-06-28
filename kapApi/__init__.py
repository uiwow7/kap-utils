import requests, time, re, pandas as pd, json
from requests.adapters import HTTPAdapter
from kapApi.disclosureParser import Disclosure
from kapApi.fundParser import Fund

BASE_URL: str = "https://kapdatafeed.kap.org.tr"
api_key: str = ''
token: str = ''
latest_index: int = -1

# Per-request timeout (seconds). Short so a throttled/hung call fails fast and
# we back off, instead of blocking for a minute before retrying.
REQUEST_TIMEOUT: float = 15

# Shared session: reuses TCP/TLS connections across the thread pool instead of
# doing a fresh handshake on every call. The pool is sized generously so many
# concurrent workers don't contend for a single connection.
session = requests.Session()
_adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32)
session.mount("https://", _adapter)
session.mount("http://", _adapter)

# region setup
def setup(apiKey: str) -> None:
    """Setup Kap API"""
    global api_key
    api_key = apiKey
    getToken()
    reloadLatestIndex()

def kap_get(path: str, query: dict = None, tries: int = 4):
    """GET a KAP endpoint with retries; raise on KAP error codes (ER/4xx/5xx).

    Retries on network errors and on throttling/5xx responses with exponential
    backoff, so when KAP starts rate-limiting we ease off rather than hammer it.
    """
    headers = None if token is None else {"Authorization": token}
    for k in range(1, tries + 1):
        try:
            resp = session.get(
                BASE_URL + path, headers=headers, params=query, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as e:
            if k == tries:
                raise RuntimeError(f"Network failed: {e}")
            backoff = 2 ** (k - 1)        # 1s, 2s, 4s, ...
            print(f"   retry {k}/{tries} ({e}); backing off {backoff}s")
            time.sleep(backoff)
            continue

        # Retry transient throttling / server errors instead of failing hard.
        if resp.status_code in (429, 500, 502, 503, 504):
            if k == tries:
                raise RuntimeError(f"KAP HTTP {resp.status_code} after {tries} tries")
            backoff = 2 ** (k - 1)
            print(f"   retry {k}/{tries} (HTTP {resp.status_code}); backing off {backoff}s")
            time.sleep(backoff)
            continue

        try:
            out = resp.json()
        except ValueError:
            out = resp.text
        if isinstance(out, dict):
            code = out.get("code")
            if isinstance(code, str) and re.match(r"^(ER|4|5)", code):
                raise RuntimeError(f"KAP {code}: {out.get('message') or ''}")
        return out
    raise RuntimeError("Network failed.")

def getToken() -> None:
    """Generates a token for the KAP API"""
    global token
    tok_resp = kap_get("/auth/generateToken", {"apiKey": api_key})
    if isinstance(tok_resp, dict):
        tok = tok_resp.get("token") or tok_resp.get("data")
    elif isinstance(tok_resp, str):
        tok = tok_resp
    else:
        tok = None
    if not tok:
        raise RuntimeError("No token.")
    
    token = tok

def reloadLatestIndex() -> None:
    global latest_index
    resp = kap_get('/api/vyk/lastDisclosureIndex')
    latest_index = resp['lastDisclosureIndex']

#endregion

#region companies

def members():
    """Returns the result of the /members endpoint"""
    return kap_get('/api/vyk/members')

def getCompanyId(companySymbol: str) -> str:
    """Returns the company id for a given company symbol"""
    url = f"https://www.kap.org.tr/tr/api/member/filter/{companySymbol.upper()}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    r.raise_for_status()
    return r.json()[0]["companyCode"]

def companyFinancialReports(companySymbol: str) -> list[Disclosure]:
    """Retrieves all financial reports"""
    res: list[Disclosure] = []
    disclosures = companyDisclosures(companySymbol, 'FR', 'FR')
    for disclosure in disclosures:
        disc: Disclosure = disclosureDetail(disclosure['disclosureIndex'])
        res.append(disc)

    return res

def funds():
    """Returns the result of the /funds endpoint"""
    return kap_get('/api/vyk/funds')

def fundDetailRaw(fundID: int):
    return kap_get(f'/api/vyk/fundDetail/{fundID}')

def fundDetail(fundID: int) -> Fund:
    return Fund(fundDetailRaw(fundID))

#endregion

# region disclosures

def disclosuresRaw(disclosureIndex: int = 538004, disclosureClass: str = None, disclosureType: str = None, companyId: str = None):
    """Returns the result of the /disclosures endpoint"""
    return kap_get('/api/vyk/disclosures', {
        'disclosureIndex': disclosureIndex,
        'disclosureClass': disclosureClass,
        'disclosureType': disclosureType,
        'companyId': companyId
    })

def companyDisclosuresFromId(
    companyId: str,
    disclosureClass: str = None,
    disclosureType: str = None,
    disclosureIndex: int = 538004,
    pause: float = 0.0,
) -> list[dict]:
    """
    Fetch ALL disclosures for one company, paging FORWARD from `disclosureIndex`.

    /api/vyk/disclosures returns up to 50 records per call, ordered by
    disclosureIndex ascending, starting at the index you pass (inclusive).
    We walk forward by setting the next cursor to (max index on the page + 1)
    and stop when a page comes back short (< page_size) or empty.

    disclosureIndex starts at 538004 = the first KAP 4.0 disclosure. Records in
    84196-538004 are pre-4.0 and are NOT served here, so the default 538004
    means "from the very beginning of available history" (oldest -> newest).
    """
    disclosures: list[dict] = []
    seen: set[int] = set()
    cursor = int(disclosureIndex)

    while True:
        try:
            page = disclosuresRaw(
                companyId=companyId,
                disclosureClass=disclosureClass,
                disclosureType=disclosureType,
                disclosureIndex=cursor,
            )
        except RuntimeError as e:
            # ER005 "Bildirim bulunamadı" = no disclosures at/after the cursor.
            # This is how the feed signals end-of-data, so stop cleanly.
            if "ER005" in str(e):
                break
            raise
        if not page:
            break  # nothing left ahead for this company

        new_in_page = 0
        for rec in page:
            idx = int(rec["disclosureIndex"])
            if idx not in seen:
                seen.add(idx)
                disclosures.append(rec)
                new_in_page += 1

        last_idx = max(int(r["disclosureIndex"]) for r in page)

        # guard against a server that ignores the cursor (prevents infinite loops).
        # NOTE: do NOT stop on a short page — this feed returns matches within a
        # scan window, so pages are routinely < page_size yet more data follows.
        # The only real end-of-data signal is ER005 (handled above).
        if last_idx < cursor or new_in_page == 0:
            break

        cursor = last_idx + 1          # +1 avoids re-fetching the boundary record

        # belt-and-braces: stop once we pass the global newest index
        if latest_index and int(latest_index) > 0 and cursor > int(latest_index):
            break

        if pause:
            time.sleep(pause)

    return disclosures

def fundDisclosuresFromId(companyId: int, fundId: int, disclosureClass: str = None, disclosureType: str = None, disclosureIndex: int = 538004) -> list[Disclosure]:
    """Returns all disclosures associated with a fundId"""
    recs = companyDisclosuresFromId(companyId, disclosureClass, disclosureType, disclosureIndex)
    disclosures = []
    for rec in recs:
        if rec.get('fundId') == fundId:
            disclosures.append(disclosureDetail(rec['disclosureIndex']))

    return disclosures


def companyDisclosures(companySymbol: str, disclosureClass: str = None, disclosureType: str = None):
    """Returns a disclosures object given a company symbol"""
    companyId: str = getCompanyId(companySymbol)
    return companyDisclosuresFromId(companyId, disclosureClass, disclosureType)

def disclosureDetailRaw(disclosureIndex: int, fileType: str = 'data', subReportList: str = None):
    """Returns the raw output of the disclosureDetail API endpoint"""
    return kap_get(f'/api/vyk/disclosureDetail/{disclosureIndex}', {
        'fileType': fileType, 
        'subReportList': subReportList
    })

def disclosureDetail(disclosureIndex: int, fileType: str = 'data', subReportList: str = None) -> Disclosure:
    """Returns a Disclosure object containing parsed data from the disclosure detail"""
    detail = disclosureDetailRaw(disclosureIndex, fileType, subReportList)
    return Disclosure(detail)

def combineDisclosures(disclosures: list[Disclosure]) -> pd.DataFrame:
    """Combine a list of Disclosures into a single DataFrame.

    Each Disclosure's wide table (one row per reporting period, one column per
    line-item name) contributes its rows, tagged with the source
    `disclosureIndex` and company `symbol` for provenance. Columns are the union
    of all names seen across the disclosures, preserving first-appearance order;
    a line item missing from a given disclosure is left as NaN for its rows.    
    """
    frames: list[pd.DataFrame] = []
    for disc in disclosures:
        df = disc.df
        if df is None or df.empty:
            continue
        data = disc.data or {}
        codes = data.get('senderExchCodes') or []
        meta = pd.DataFrame({
            'disclosureIndex': data.get('disclosureIndex'),
            'symbol': codes[0] if codes else None,
        }, index=df.index)
        frames.append(pd.concat([meta, df], axis=1))

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True, sort=False)

#endregion


### Member types:
# IGS   (İşlem Gören Şirket)            -> Traded Company (listed/trading on the exchange)
# IGMS  (İşlem Görmeyen Şirket)         -> Non-Traded Company (KAP-registered, not listed)
# YK    (Yatırım Kuruluşu)              -> Investment Firm
# PYS   (Portföy Yönetim Şirketi)       -> Portfolio Management Company
# DDK   (Düzenleyici Denetleyici Kurum) -> Regulatory & Supervisory Authority
# FK    (Fon Kurucu - Temsilci)         -> Fund Founder / Representative
# BDK   (Bağımsız Denetim Kuruluşu)     -> Independent Audit Firm
# DCS   (Derecelendirme Şirketi)        -> Rating Agency
# DS    (Değerlendirme Şirketi)         -> Valuation / Appraisal Company

### Fund types:
# SYF  (Şemsiye Yatırım Fonu)                          -> Umbrella Investment Fund (legal wrapper; individual sub-funds are issued under it)
# KGF  (Koruma Amaçlı / Garantili Şemsiye Yatırım Fonu) -> Capital-Protected / Guaranteed Umbrella Fund
# EYF  (Emeklilik Yatırım Fonu)                        -> Pension Investment Fund (private pension system / BES)
# OKS  (OKS Emeklilik Yatırım Fonu)                    -> Auto-Enrollment Pension Investment Fund (OKS = Otomatik Katılım Sistemi)
# YYF  (Yabancı Yatırım Fonu)                          -> Foreign Investment Fund (foreign-domiciled fund offered in Türkiye)
# BYF  (Borsa Yatırım Fonu)                            -> Exchange-Traded Fund (ETF)
# VFF  (Varlık Finansman Fonları)                      -> Asset Finance Fund (asset-backed securitization vehicle)
# KFF  (Konut Finansman Fonları)                       -> Housing Finance Fund (mortgage-backed securitization vehicle)
# GMF  (Gayrimenkul Yatırım Fonları)                   -> Real Estate Investment Fund
# GSF  (Girişim Sermayesi Yatırım Fonu)                -> Venture Capital Investment Fund
# PFF  (Proje Finansman Fonu)                          -> Project Finance Fund