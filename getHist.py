import kapApi, os, pandas as pd
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

kapApi.setup(os.environ['KAP_KEY'])

# Cap the number of companies processed (handy for testing). Set to None for no cap.
cap = 5

# Number of concurrent HTTP requests. The work is network-bound, so raising this
# is the main speed knob; back it off if KAP starts throttling.
WORKERS = 16

# Which disclosures to pull per company. FR/FR = financial reports, the ones
# that parse into the wide period x line-item tables.
DISCLOSURE_CLASS = 'FR'
DISCLOSURE_TYPE = 'FR'

OUTPUT = 'all_companies.csv'


# /members lists some companies more than once (e.g. multiple member types);
# de-duplicate by id so we only fetch each company once.
members = kapApi.members()
seen: set = set()
unique_members = []
for m in members:
    mid = m.get('id')
    if mid in seen:
        continue
    seen.add(mid)
    unique_members.append(m)

if cap is not None:
    unique_members = unique_members[:cap]


# Stage A: list each company's FR disclosures. Pagination within one company is
# sequential (cursor-based), but companies are independent so we fan them out.
def list_disclosures(member):
    try:
        recs = kapApi.companyDisclosuresFromId(
            member['id'],
            disclosureClass=DISCLOSURE_CLASS,
            disclosureType=DISCLOSURE_TYPE,
        )
    except Exception as e:
        print(f"  list failed for {member.get('id')}: {e}")
        return member, []
    return member, recs


print(f"Listing disclosures for {len(unique_members)} companies...")
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    listed = list(ex.map(list_disclosures, unique_members))

# Flatten to all disclosure indices, remembering which member each belongs to.
member_by_index: dict = {}
indices: list = []
for member, recs in listed:
    for rec in recs:
        idx = rec['disclosureIndex']
        member_by_index[idx] = member
        indices.append(idx)

# Stage B: fetch AND parse every disclosure detail concurrently. The parser is
# thread-safe (it threads its facts list through the recursion), so each worker
# does the full fetch+parse and just hands back a finished Disclosure.
def fetch_and_parse(idx):
    return kapApi.Disclosure(kapApi.disclosureDetailRaw(idx))


print(f"Fetching {len(indices)} disclosure details with {WORKERS} workers...")
by_member: dict = defaultdict(list)  # member id -> list[Disclosure]
done = 0
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futures = {ex.submit(fetch_and_parse, idx): idx for idx in indices}
    for fut in as_completed(futures):
        idx = futures[fut]
        try:
            disc = fut.result()
        except Exception as e:
            print(f"  detail {idx} failed: {e}")
            continue
        done += 1
        if done % 50 == 0:
            print(f"  {done}/{len(indices)}")
        # Keep only balance sheets: reports whose parsed table has an 'Assets' column.
        if 'Assets' not in disc.df.columns:
            continue
        by_member[member_by_index[idx]['id']].append(disc)

# Stage C: combine per company, tag, then concatenate everything.
frames = []
for member, _ in listed:
    discs = by_member.get(member['id'])
    if not discs:
        continue
    df = kapApi.combineDisclosures(discs)
    if df.empty:
        continue
    df.insert(0, 'memberTitle', member.get('title'))
    df.insert(0, 'memberId', member.get('id'))
    frames.append(df)

if frames:
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined.to_csv(OUTPUT, index=False, encoding='utf-8')
    print(f"Wrote {OUTPUT}: {combined.shape[0]} rows x {combined.shape[1]} cols")
else:
    print("No data collected.")
