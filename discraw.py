import kapApi, os, json

kapApi.setup(os.environ['KAP_KEY'])

# discl_raw = kapApi.disclosureDetailRaw(1598316)
# x = kapApi.kap_get('/api/vyk/lastDisclosureIndex')
x = kapApi.fundDetail(4372)

x.df.to_csv(f'detail-test.csv', index=False, encoding="utf-8")

with open('fund-detail.json', 'w') as f:
    json.dump(x.data, f, indent=2)
