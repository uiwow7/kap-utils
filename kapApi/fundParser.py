import pandas as pd, json

def fundToDataFrame(raw: dict) -> pd.DataFrame:
    cols = ['key', 'nameTr', 'nameEn', 'time', 'value']
    facts = []
    for field in raw:
        facts.append([
            field['key'],
            field['nameTr'],
            field['nameEn'],
            field['publishDateTime'],
            json.dumps(field['value'])
        ])

    return pd.DataFrame(facts, columns=cols)

class Fund:
    def __init__(self, raw: dict) -> None:
        self.df = fundToDataFrame(raw)
        self.data = raw