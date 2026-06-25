import requests, time, re, pandas as pd, json
from kapApi.disclosureParser import Disclosure
from kapApi.fundParser import Fund

BASE_URL: str = "https://kapdatafeed.kap.org.tr"
api_key: str = ''
token: str = ''
latest_index: int = -1

# region setup
def setup(apiKey: str) -> None:
    """Setup Kap API"""
    global api_key
    api_key = apiKey
    getToken()
    reloadLatestIndex()

def kap_get(path: str, query: dict = None, tries: int = 4):
    """GET a KAP endpoint with retries; raise on KAP error codes (ER/4xx/5xx)."""
    headers = None if token is None else {"Authorization": token}
    for k in range(1, tries + 1):
        try:
            resp = requests.get(BASE_URL + path, headers=headers, params=query, timeout=60)
        except requests.RequestException as e:
            print(f"   retry {k}/{tries}: {e}")
            time.sleep(2)
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

def companyDisclosuresFromId(companyId: str, disclosureClass: str = None, disclosureType: str = None, disclosureIndex: int = 538004):
    """Returns the disclosures for a company given a companyId"""
    disclosures = []
    current_index = disclosureIndex
    prev_index = -1
    while True:
        raw = disclosuresRaw(companyId=companyId, disclosureClass=disclosureClass, disclosureType=disclosureType, disclosureIndex=current_index)
        print(len(raw))
        if len(raw) == 0: break
        prev_index = current_index
        current_index = raw[-1]['disclosureIndex']
        print(current_index, latest_index, raw[-1])
        if prev_index == current_index: break
        disclosures.extend(raw)
        if int(current_index) >= int(latest_index): break

    with open('test.json', 'w') as f:
        json.dump(disclosures, f)

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