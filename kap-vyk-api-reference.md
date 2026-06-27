# KAP VYK API — Reference Notes

**Product:** KAP Veri Yayın Servisleri (Data Dissemination Service)
**Portal OID:** `6765bc408e6d51715bccf5a5`
**Spec:** OpenAPI 3.0.3 · title `KAP VYK API` · version `0.0.1-apinizer-337-07a3583`
**Portal last-modified:** 05/06/2026

> **Source legend** — each fact below is tagged:
> `[spec]` confirmed from the OpenAPI document · `[portal]` from the portal product page · `[prior]` prior institutional knowledge, not (re)confirmed by the spec.

---

## 1. Access & environment

| Item | Value | Source |
|---|---|---|
| Base URL | `https://apigwdev.mkk.com.tr/api/vyk` | `[spec]` |
| OpenAPI download | `https://apigwdev.mkk.com.tr/api/vyk?openapi` | `[portal]` |
| Environment | **DEV gateway only** (`apigwdev`); no prod host advertised | `[spec]` |
| Auth | **HTTP Basic** — `Authorization: Basic base64(user:token)` (`basicAuth`, scheme `basic`) | `[spec]` |
| Declared scopes | `read`, `write` — decorative under Basic | `[spec]` |
| App approval | Auto-approve on registration (portal-level) | `[portal]` |
| API type | REST | `[portal]` |

**Access-tier caveats**

- The portal (`apiportal.mkk.com.tr`) is a JS-rendered SPA behind login — product detail pages are **not statically fetchable**; export the OpenAPI spec or copy content manually. `[prior]`
- Portal "auto-approve" is **not** the same as open network access. The company-list endpoint in particular sits behind a Borsa İstanbul data-distribution agreement + IP whitelisting. `[prior]`
- A bare `403` with no body/headers = edge-layer rejection (unregistered IP). A scoped permission denial returns a structured `VykErrorResponse`. `[prior]`
- There is an `AuthResponse {token}` schema but **no `/auth` or login path** in the spec — the token is provisioned out-of-band and used as the Basic password. `[spec]`
- Support contact for gated-API issues: `kapdestek@mkk.com.tr`. `[prior]`

---

## 2. Endpoints

All endpoints are `GET`. Every endpoint returns `VykErrorResponse` on `400` and `500`. `[spec]`

### Şirket Servisleri (Company)

| Path | Params | 200 schema | Notes |
|---|---|---|---|
| `/members` | — | `MemberInfo` | Full KAP member list. **Gated** (BIST agreement + IP whitelist `[prior]`). |
| `/memberSecurities` | — | `MemberSecuritiesResponse` | **IGS-only** by definition (işlem gören şirket — listed companies). |
| `/memberDetail/{id}` | `id` (path, **req**) | `CompanyDetailResponse` | |

### Bildirim Servisleri (Disclosure)

| Path | Params | 200 schema | Notes |
|---|---|---|---|
| `/lastDisclosureIndex` | — | `LastDisclosureIndexResponse` | Current cursor head. |
| `/disclosures` | `disclosureIndex` (query, **req**), `disclosureTypes` (query), `disclosureClass` (query), `companyId[]` (query) | `DisclosureInfoResponse` | **Index-based pagination, 50 records/page** from the given index. |
| `/disclosureDetail/{disclosureIndex}` | `disclosureIndex` (path, **req**), `fileType` (query, **req**, `html\|data`), `subReportList` (query) | `DisclosureByIdResponse` | `subReportList` omitted = all sub-reports; supplied = single report id. |
| `/downloadAttachment/{id}` | `id` (path, **req**) | `string` | `id` comes from `attachmentUrls` in the detail response. |
| `/caEventStatus` | `processRefId` (query, **req**) | `CAProcessStatus` | Corporate-action / rights-usage process status. |
| `/blockedDisclosures` | — | `BlockedBase` | Disclosures/attachments closed to access. |

### Fon Servisleri (Fund)

| Path | Params | 200 schema | Notes |
|---|---|---|---|
| `/funds` | `fundState[]` (query), `fundClass[]` (query), `fundType[]` (query) | `FundInfo` | All filters optional, array-typed. |
| `/fundDetail/{id}` | `id` (path, **req**) | `FundDetailResponse` | |

---

## 3. Core workflows

**Disclosure polling loop**

1. `GET /lastDisclosureIndex` → current head.
2. Walk `GET /disclosures?disclosureIndex=<cursor>` forward in pages of 50, advancing the cursor.
3. For each item of interest, `GET /disclosureDetail/{disclosureIndex}?fileType=data` for the structured form (use `fileType=html` for the rendered form).
4. For attachments, take each `attachmentUrls[].url`/id and call `GET /downloadAttachment/{id}`.

**Member / securities**

- `/members` for the universe; `/memberDetail/{id}` for one company; `/memberSecurities` for IGS companies' securities (ISIN-level).

---

## 4. Data model (22 schemas)

### Disclosure detail — the central envelope

`DisclosureByIdResponse` `[spec]`

```
blockedStatus, disclosureIndex,
senderId, senderTitle, senderExchCodes[],
behalfSenderId, behalfSenderTitle, behalfSenderExchCodes[],
behalfFundId, behalfFundCode, behalfFundTitle,
disclosureReason, disclosureDelayStatus, relatedDisclosureIndex,
disclosureType, disclosureClass,
subject (Subject), consolidation, year, period (Period),
relatedStocks[], summary (Summary), time, link,
attachmentUrls[], eventType, eventId,
htmlMessages[], flatData[], presentation[],
isBlocked, isBlockedDescriptionTr, isBlockedDescriptionEn
```

Supporting objects: `Subject{tr,en}`, `Summary{tr,en}`, `Period{tr,en}`, `RelatedStock{code}`, `AttachmentUrls{url,fileName}`, `HtmlMessages{id,tr,en}`, `FlatData{id,content}`, `Presentation{id,content}`.

### Company / member

- `MemberInfo` — `id, title, stockCode, memberType, kfifUrl`
- `CompanyInfo` — `id, memberType, sermayeSistemi, kayitliSermayeTavani(number), kstSonGecerlilikTarihi, sirketUnvan, mksMbrId`
- `MemberSecuritiesResponse` — `member (CompanyInfo), securities[]`
- `MemberSecurity` — `isin, isinDesc, borsaKodu, takasKodu, tertipGroup, capital(number), currentCapital(number), groupCode, groupCodeDesc, borsadaIslemeAcik(bool)`
- `CompanyDetailResponse` — `nameTr, nameEn, key, publishDateTime, value(object)`

### Fund

- `FundInfo` — `umbMemberOid, fundOid, fundId(number), fundName, fundCode, fundType, fundClass, fundExpiry, fundState, fundMemberOid, umbMemberTypes, fundMemberTypes, kapUrl, nonInactiveCount(number), fundCompanyId, fundCompanyTitle`
- `FundDetailResponse` — `nameTr, nameEn, key, publishDateTime, value(object), codeKey`

### Disclosure list / misc

- `DisclosureInfoResponse` — `disclosureIndex, disclosureType, disclosureClass, subReportIds[], title, companyId, fundId, fundCode, acceptedDataFileTypes[]`
- `LastDisclosureIndexResponse` — `lastDisclosureIndex`
- `CAProcessStatus` — `refId(number), status, statusReason, completeDate`
- `VykErrorResponse` — `code, message`
- `AuthResponse` — `token` (orphaned; see §1)
- `BlockedBase` — bare object, **no properties defined**

---

## 5. XBRL / financial-fact note

`fileType=data` on `/disclosureDetail` is the structured path; the financial content lands in `DisclosureByIdResponse.flatData[]` and `presentation[]`, where both `FlatData` and `Presentation` are `{id, content}`.

**`content` is typed as a bare `object` in the spec** — the XBRL-style internals (`ReportItem`, `ContextList`, `Values.Value[]`, `contextId`, `currency`, `rounding`) are **not described here**. The spec confirms the envelope only; the fact structure must come from live/sample payloads (which is what the existing parser was built against). `fileType=html` instead routes to `htmlMessages[]` (rendered, not parseable). `[spec]` + `[prior]`

---

## 6. Gotchas (important for codegen)

1. **All arrays have `items: {}` (empty schema).** Item models exist but are not wired in via `$ref`. As written, these properties are `array<untyped>` and naive codegen (openapi-generator / datamodel-codegen) will emit `List[Any]` / `list[object]`, silently dropping the models. Affected arrays and their **intended** item types (by name):

   | Property | Intended item type |
   |---|---|
   | `MemberSecuritiesResponse.securities` | `MemberSecurity` |
   | `DisclosureByIdResponse.attachmentUrls` | `AttachmentUrls` |
   | `DisclosureByIdResponse.relatedStocks` | `RelatedStock` |
   | `DisclosureByIdResponse.htmlMessages` | `HtmlMessages` |
   | `DisclosureByIdResponse.flatData` | `FlatData` |
   | `DisclosureByIdResponse.presentation` | `Presentation` |
   | `DisclosureInfoResponse.subReportIds` | string (likely) |
   | `DisclosureInfoResponse.acceptedDataFileTypes` | string (likely) |
   | `*.senderExchCodes`, `*.behalfSenderExchCodes` | string (likely) |

   **Fix:** mechanically patch each array's `items` to the matching `$ref` (or hand-write the models) **before** generating.

2. **Orphaned schemas** (0 `$ref`s, will not appear in generated models unless wired up): `MemberSecurity`, `AttachmentUrls`, `FlatData`, `HtmlMessages`, `Presentation`, `RelatedStock`, `AuthResponse`.

3. **Dev gateway only** — confirm a prod host before hardcoding.

4. **`BlockedBase` is an empty object** — `/blockedDisclosures` response shape is undescribed; inspect a real payload.

---

## 7. Next steps (planned)

- Patch the spec (`items.$ref` wiring per §6.1).
- Generate Pydantic models + a thin Basic-auth Python client, including the index-based `/disclosures` paginator.
- Decide whether `flatData[].content` stays a passthrough `dict` for the XBRL parser, or whether the `Values.Value[]` / `contextId` handling is folded into the client.
