import kapApi, os, json, shutil

kapApi.setup(os.environ['KAP_KEY'])

members = kapApi.members()
CAP = 1

shutil.rmtree('out')
os.mkdir('out')

# for i, member in enumerate(members):
#     if 'IGS' not in member['memberType']: continue
#     reports = kapApi.companyFinancialReports(member['stockCode'])
#     os.mkdir(f'out/{i}_{member['stockCode']}_{member['id']}')

#     for j, df in enumerate(reports):
#         if 'Assets' in df['name'].values:
#             df.to_csv(f'out/{i}_{member['stockCode']}_{member['id']}/report_{j}.csv', index=False, encoding="utf-8")

#     if i >= CAP: break

member = {
    'id': '866',
    'stockCode': 'ASELS'
}
i = 1

reports = kapApi.companyFinancialReports(member['stockCode'])
os.mkdir(f'out/{i}_{member['stockCode']}_{member['id']}')

for j, disclosure in enumerate(reports):
#     # if 'Assets' in df['name'].values:
    disclosure.df.to_csv(f'out/{i}_{member['stockCode']}_{member['id']}/{disclosure.data['disclosureIndex']}.csv', index=False, encoding="utf-8")

# print(kapApi.kap_get('/api/vyk/latestDisclosureIndex'))