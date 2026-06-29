import kapApi, os, sys, glob, pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

kapApi.setup(os.environ['KAP_KEY'])

# Cap the number of companies processed THIS run (handy for testing). None = no cap.
cap = 5

# Concurrent HTTP requests used while fetching a single company's disclosures.
# Companies themselves are processed one at a time (see the main loop).
WORKERS = 3

# Seconds to wait between paginated listing calls within a company, to avoid
# bursting the feed. 0 disables it.
PAGE_PAUSE = 0.2

# Which disclosures to pull per company. FR/FR = financial reports, the ones
# that parse into the wide period x line-item tables.
DISCLOSURE_CLASS = 'FR'
DISCLOSURE_TYPE = 'FR'

OUTPUT = 'all_companies.csv'

# Directory holding one CSV per company. These persist across runs and are what
# makes resuming + the final combine possible.
OUTPUT_DIR = 'companies'


def fetch_and_parse(idx):
    """Fetch a disclosure detail and parse it into a Disclosure (thread-safe)."""
    return kapApi.Disclosure(kapApi.disclosureDetailRaw(idx))


def process_company(member):
    """Fetch ALL of one company's balance sheets, combine, and write its CSV.

    Returns the output path if a CSV was written, else None. Network failures on
    individual disclosures are logged and skipped so one bad report can't sink
    the whole company.
    """
    recs = kapApi.companyDisclosuresFromId(
        member['id'],
        disclosureClass=DISCLOSURE_CLASS,
        disclosureType=DISCLOSURE_TYPE,
        pause=PAGE_PAUSE,
    )
    indices = [rec['disclosureIndex'] for rec in recs]

    discs = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_and_parse, idx): idx for idx in indices}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                disc = fut.result()
            except Exception as e:
                print(f"    detail {idx} failed: {e}")
                continue
            # Keep only balance sheets: reports whose parsed table has 'Assets'.
            if 'Assets' in disc.df.columns:
                discs.append(disc)

    if not discs:
        return None

    df = kapApi.combineDisclosures(discs)
    if df.empty:
        return None
    df.insert(0, 'memberTitle', member.get('title'))
    df.insert(0, 'memberId', member.get('id'))

    path = os.path.join(OUTPUT_DIR, f"{member['id']}.csv")
    df.to_csv(path, index=False, encoding='utf-8')
    print(f"  wrote {path}: {df.shape[0]} rows")
    return path


def combine_csvs(output_dir, output):
    """Concatenate every per-company CSV into one file by streaming them from
    disk, so we never hold more than a single company's data in memory."""
    files = sorted(glob.glob(os.path.join(output_dir, '*.csv')))
    if not files:
        print("No per-company CSVs to combine.")
        return

    # Pass 1: union of columns, preserving the order they first appear.
    columns = []
    seen_cols = set()
    for f in files:
        for c in pd.read_csv(f, nrows=0).columns:
            if c not in seen_cols:
                seen_cols.add(c)
                columns.append(c)

    # Pass 2: append each file's rows (aligned to the full column set) one by one.
    rows = 0
    with open(output, 'w', encoding='utf-8', newline='') as out:
        for i, f in enumerate(files):
            df = pd.read_csv(f).reindex(columns=columns)
            df.to_csv(out, index=False, header=(i == 0))
            rows += len(df)
    print(f"Wrote {output}: {rows} rows x {len(columns)} cols from {len(files)} companies")


# /members lists some companies more than once (e.g. multiple member types);
# de-duplicate by id so we only handle each company once, keeping a stable order.
members = kapApi.members()
seen: set = set()
unique_members = []
for m in members:
    mid = m.get('id')
    if mid in seen:
        continue
    seen.add(mid)
    unique_members.append(m)

# Resume support: pass the last successfully processed company id as argv[1] and
# we continue with the NEXT company in the (stable) ordering.
resume_after = sys.argv[1] if len(sys.argv) > 1 else None
if resume_after is not None:
    ids = [m['id'] for m in unique_members]
    if resume_after in ids:
        start = ids.index(resume_after) + 1
        unique_members = unique_members[start:]
        print(f"Resuming after company {resume_after}: {len(unique_members)} companies left.")
    else:
        print(f"Resume id {resume_after} not found; starting from the beginning.")

if cap is not None:
    unique_members = unique_members[:cap]

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Main loop: one company fully fetched & written before moving to the next.
for i, member in enumerate(unique_members, 1):
    print(f"[{i}/{len(unique_members)}] {member.get('title')} ({member.get('id')})")
    try:
        process_company(member)
    except Exception as e:
        print(f"  company {member.get('id')} failed: {e}")
        print(f"  -> resume with: python getHist.py {unique_members[i - 2]['id']}"
              if i > 1 else "  -> resume from the beginning")
        raise
    # Last successfully processed id, so a crash/stop after this is resumable.
    print(f"  done. resume token: {member.get('id')}")

# Final step: stitch the per-company CSVs (this run's and any prior runs') together.
combine_csvs(OUTPUT_DIR, OUTPUT)
