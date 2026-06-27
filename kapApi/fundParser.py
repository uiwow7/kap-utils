import pandas as pd


def _collect_facts(name, value, facts, row=0):
    """Flatten a fund field's value into (row, name, value) leaf facts.

    A value can be a scalar, ``None``, or a list of record dicts. Nested record
    sub-fields are exposed as ``name.subkey`` columns; each record in a list lands
    on its own row (like a fresh reporting period in ``detailToDataFrame``).
    Empty/None leaves are dropped so they don't create columns.
    """
    if value is None:
        return
    if isinstance(value, list):
        for i, rec in enumerate(value):
            _collect_facts(name, rec, facts, row=i)
    elif isinstance(value, dict):
        for subkey, subval in value.items():
            _collect_facts(f"{name}.{subkey}", subval, facts, row=row)
    else:
        sv = str(value).strip()
        if sv:
            facts.append({"row": row, "name": name, "value": value})


def fundToDataFrame(raw: list) -> pd.DataFrame:
    """Convert a fund detail into a wide table, mirroring ``detailToDataFrame``:
    one column per field ``nameEn`` (nested records expand to ``nameEn.subkey``),
    with the field value as the cell. Most fields occupy a single row; a field
    whose value is a list of several records spreads across that many rows.
    """
    facts = []
    for field in raw:
        _collect_facts(field["nameEn"], field.get("value"), facts)

    if not facts:
        return pd.DataFrame()

    # Preserve document order for the columns (pivot_table would otherwise sort).
    long = pd.DataFrame(facts)
    name_order = list(dict.fromkeys(long["name"].tolist()))

    wide = long.pivot_table(
        index="row",
        columns="name",
        values="value",
        aggfunc="last",
    )
    wide = wide.reindex(columns=name_order)
    wide.columns.name = None
    return wide.reset_index(drop=True)


class Fund:
    def __init__(self, raw: dict) -> None:
        self.df = fundToDataFrame(raw)
        self.data = raw
