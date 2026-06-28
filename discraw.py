import kapApi, os, json

kapApi.setup(os.environ['KAP_KEY'])

x = kapApi.disclosureDetailRaw(953376)
# x = kapApi.kap_get('/api/vyk/lastDisclosureIndex')
# x = kapApi.fundDetail(4372)

# x.df.to_csv(f'fund3.csv', index=False, encoding="utf-8")

with open('detail3.json', 'w') as f:
    json.dump(x, f, indent=2)
