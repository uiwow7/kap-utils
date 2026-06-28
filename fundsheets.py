import kapApi, os, json

kapApi.setup(os.environ['KAP_KEY'])

# discl_raw = kapApi.disclosureDetailRaw(1598316)
# x = kapApi.kap_get('/api/vyk/lastDisclosureIndex')
x = kapApi.fundDisclosuresFromId('2501', '3750', 'FR', 'FR')
discs = []
CAP = 10
i = 0

# for r in x:
#     idx = r['disclosureIndex']
#     disc = kapApi.disclosureDetail(idx)
#     if 'Assets' in disc.df.columns:
#         discs.append(disc)
#         i += 1

#     if i == CAP: break

df = kapApi.combineDisclosures(x)

df.to_csv(f'fund_disc3.csv', index=False, encoding="utf-8")

# with open('detail2.json', 'w') as f:
#     json.dump(x, f, indent=2)
