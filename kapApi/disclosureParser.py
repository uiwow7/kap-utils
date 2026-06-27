import re, pandas as pd, os, json

def to_num(x):
    """Parse a number, falling back to European format (1.234.567,89 -> 1234567.89)."""
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    s2 = s.replace(".", "").replace(",", ".")
    try:
        return float(s2)
    except ValueError:
        return None


def get_labels(langs):
    out = {"tr": None, "en": None}
    if not isinstance(langs, dict):
        return out
    L = langs.get("lang")
    if L is None:
        return out
    if isinstance(L, dict):
        L = [L]
    for it in L:
        if isinstance(it, dict) and it.get("code") in ("tr", "en"):
            out[it["code"]] = it.get("value")
    return out


def context_map(content):
    if not isinstance(content, dict):
        return {}
    cl = content.get("ContextList")
    cl = cl.get("Context") if isinstance(cl, dict) else None
    if cl is None:
        return {}
    if isinstance(cl, dict):
        cl = [cl]
    out = {}
    for c in cl:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        p = c.get("Period") or {}
        if p.get("instant") is not None:
            period = p.get("instant")
        else:
            period = f"{p.get('startDate') or ''}..{p.get('endDate') or ''}"
        if cid is not None:
            out[cid] = period
    return out


NON_VALUE = {
    "name", "abstract", "isHypercubeItem", "isDimensionItem", "isMultiDimensional",
    "id", "key", "contextRef", "context", "unitRef", "decimals", "code",
}

facts = []


def handle_values(values_node, cur):
    """Handle a Values/Value structure where each Value carries its own
    contextId (the date), value, currency and rounding."""
    if not isinstance(values_node, dict):
        return
    vlist = values_node.get("Value")
    if vlist is None:
        return
    if isinstance(vlist, dict):      # a single Value
        vlist = [vlist]
    for rec in vlist:
        if not isinstance(rec, dict):
            continue
        raw = rec.get("value")
        if raw is None:
            continue
        sv = str(raw).strip()
        if not sv or not re.search(r"[0-9]", sv):
            continue
        num = to_num(sv)
        if num is None:
            continue
        cid = rec.get("contextId")
        facts.append({
            "name": cur.get("name"),
            "label_tr": cur.get("tr"),
            "label_en": cur.get("en"),
            "value_field": "value",
            "value_raw": sv,
            "value_num": num,
            "contextRef": cid,
            "period": cid,                  # <-- the date
            "currency": rec.get("currency"),
            "rounding": rec.get("rounding"),
        })


def handle_value(key, v, cur, cref, ctx):
    if v is None:
        return
    sv = str(v).strip()
    if not sv:
        return
    if key in NON_VALUE:
        return
    if re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}", sv):
        return
    num = to_num(sv)
    if num is None or not re.search(r"[0-9]", sv):
        return
    if cref is not None and cref in ctx:
        period = ctx[cref]
    elif key in ctx:
        period = ctx[key]
    elif re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}", key):
        period = key
    else:
        period = None
    facts.append({
        "name": cur.get("name"),
        "label_tr": cur.get("tr"),
        "label_en": cur.get("en"),
        "value_field": key,
        "value_raw": sv,
        "value_num": num,
        "contextRef": cref,
        "period": period,
        "currency": None,
        "rounding": None,
    })


def deep(node, ctx, cur=None, cref=None):
    if cur is None:
        cur = {"name": None, "tr": None, "en": None}
    if node is None:
        return

    if isinstance(node, dict):
        if node.get("name") is not None:
            labs = get_labels(node.get("langs"))
            cur = {"name": node.get("name"), "tr": labs["tr"], "en": labs["en"]}
        if node.get("contextRef") is not None:
            cref = node.get("contextRef")
        if node.get("context") is not None:
            cref = node.get("context")
        for key, child in node.items():
            if key in ("langs", "ContextList"):
                continue
            if key == "Values":                 # <-- new structure
                handle_values(child, cur)
                continue
            if isinstance(child, (dict, list)):
                deep(child, ctx, cur, cref)
            else:
                handle_value(key, child, cur, cref, ctx)
    elif isinstance(node, list):
        for child in node:
            if isinstance(child, (dict, list)):
                deep(child, ctx, cur, cref)
            else:
                handle_value("", child, cur, cref, ctx)
    else:
        handle_value("", node, cur, cref, ctx)


def detailToLongDataFrame(detail) -> pd.DataFrame:
    """Parse a disclosure detail into a long ('tidy') table where each row is a
    single fact: name, labels, the value and its reporting period/context."""
    global facts
    facts = []
    presentation = detail.get("presentation")
    if isinstance(presentation, dict) and (
        presentation.get("content") is not None or presentation.get("id") is not None
    ):
        pres = [presentation]
    elif isinstance(presentation, list):
        pres = presentation
    elif presentation is None:
        pres = []
    else:
        pres = [presentation]

    for p in pres:
        content = p.get("content") if isinstance(p, dict) else None
        ctx = context_map(content)
        if isinstance(content, dict):
            deep(content.get("ReportItem"), ctx)

    cols = ["name", "label_tr", "label_en", "value_field",
            "value_raw", "value_num", "contextRef", "period",
            "currency", "rounding"]
    return pd.DataFrame(facts, columns=cols)


def detailToDataFrame(detail) -> pd.DataFrame:
    """Parse a disclosure detail into a wide table: one column per ``name`` and
    one row per reporting ``period``, with ``value_num`` as the cell values.

    Column order follows the order the names first appear in the document, and
    row order follows the order the periods first appear. When the same
    name/period pair occurs more than once (e.g. dimensional facts in the
    statement of changes in equity) the last value encountered wins.
    """
    long = detailToLongDataFrame(detail)
    if long.empty:
        return pd.DataFrame()

    # Preserve document order for both axes (pivot_table would otherwise sort).
    name_order = list(dict.fromkeys(long["name"].tolist()))
    period_order = list(dict.fromkeys(long["period"].tolist()))

    wide = long.pivot_table(
        index="period",
        columns="name",
        values="value_num",
        aggfunc="last",
    )
    wide = wide.reindex(index=period_order, columns=name_order)
    wide.index.name = "period"
    wide.columns.name = None
    return wide.reset_index()


class Disclosure:
    def __init__(self, raw: dict):
        self.df = detailToDataFrame(raw)
        self.long_df = detailToLongDataFrame(raw)
        self.data = raw

    def save(self, fileType = 'csv'):
        """Saves to the standard location of '/out/SYMBOL_ID/DISCLOSUREINDEX.csv'"""
        if not os.path.exists('out'):
            os.mkdir('out')

        symbol = self.data['senderExchCodes'][0] or 'NUL'
        path = f'out/{symbol}_{self.data['senderId']}/{self.data['disclosureIndex']}.{fileType}'
        if fileType == 'csv':
            self.df.to_csv(path, index=False, encoding='utf-8')
        elif fileType == 'json':
            with open(path, 'w') as f:
                json.dump(self.data, f)