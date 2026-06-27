import kapApi, os
kapApi.setup(os.environ['KAP_KEY'])

# Start writing code here
if not os.path.exists('out'):
    os.mkdir('out')
recs = kapApi.companyDisclosuresFromId(866, disclosureClass="FR", disclosureType="FR")
disclosures = []

for i, rec in enumerate(recs):
    disclosure = kapApi.disclosureDetail(rec['disclosureIndex'])
    if 'Assets' in disclosure.df.columns:
      # disclosure.df.to_csv(f'out/{rec['disclosureIndex']}.csv', index=False, encoding="utf-8")
      disclosures.append(disclosure)

df = kapApi.combineDisclosures(disclosures)
df.to_csv('combined.csv', index=False, encoding="utf-8")