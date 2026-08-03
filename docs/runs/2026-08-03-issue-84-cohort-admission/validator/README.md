# #84 six-slot cohort manifest and validator gate

This sub-record freezes the six admitted slots after the approved T426893 and
T427224 addendum preflights. It is a manifest/validator gate only; no formal
M6 lane has started.

## Manifest

Manifest: `bench/m6/m6-qualification-v1.yaml`

- source SHA-256: `45e8ce551653542734b24ab5ae7f763383847fc9004360ff1ebabc10bbcff7b9`
- canonical SHA-256: `38e43f98f63c2b9a399d2bbc70969a077e016a6b70b1499435c30f9e975ec2f7`
- status: `frozen`
- slots: 6 (`H-01`..`H-03`, `P-01`..`P-03`)
- planned lanes: 36 (3 baseline + 3 candidate repetitions per slot)
- risk families: G-03, G-04, G-06, G-08
- replacement candidates: 7 (two historical, five prospective)
- replacement events: 3, all before the first formal invocation
- formal invocations started: 0

The prospective replacement ledger records exclusions for the original P-01,
P-02, P-03, T426527, and T419910. T425733, T426893, and T427224 consume ranks
3, 4, and 5 into the three prospective slots. The validator treats an earlier
rank already consumed by another slot as accounted for, while still requiring
all unavailable earlier ranks to have exclusion evidence.

## Exact validation commands

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.m6_cohort bench/m6/m6-qualification-v1.yaml \
  --repo-root .

/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest \
  -p no:cacheprovider -o addopts='' tests/bench/test_m6_cohort.py -q \
  --junitxml=validator/focused-junit.xml

/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/peter/projects/ai_verfication/.venv/bin/python -m pytest \
  -p no:cacheprovider -o addopts='' -q \
  --junitxml=validator/full-junit.xml

git diff --check
```

Results:

- manifest: `status=valid`; Draft 2020-12 schema, six slots, 36 lanes, four
  risk families, checksummed references, and replacement ledger all passed
- focused validator: 17 passed in 1.07s; shell wall 1.18s
- full repository suite: 696 passed in 17.93s; shell wall 18.03s
- `git diff --check`: exit 0

Artifacts:

| File | SHA-256 |
| --- | --- |
| `../selection-evidence.md` | `a4056ede3fa78f2a155b52a58a656adef5f2586b8d7ba3aa97c89d62d3ec3db5` |
| `manifest-validation.json` | `0b5e1ecac8e2ad161ef5d15805423a50e2f1218d5a74da93921d354889b1ad8b` |
| `focused-junit.xml` | `d6d0cb9ab0d17713eafdcb29fc4295b74c51a8e043be13f89b615ff56deb53f2` |
| `full-junit.xml` | `91651a8f7840fb9cb46abb712233be34435a6f1167903cee96ff1df2839f249a` |
| `focused-output.txt` | `ca8a2ea792081f3d084b5e89319df22b70bf175c47cf2143abdd64c4f0150ce1` |
| `full-output.txt` | `52a63172463673885918c57e1abe69a0e66510194f8c263eb8182dbe944fdb33` |

Code identities:

- `src/aiverify/bench/m6_cohort.py` SHA-256:
  `73f39938c8aa7e00df4421a30c14667c4477bac87a395442852e9404d5533548`
- `tests/bench/test_m6_cohort.py` SHA-256:
  `a623e3114cd76deddd194f5114025510f8e98cc6a6b635dd6782b461412d36b7`

No Android upstream checkout was changed by the manifest/validator work, and
no formal qualification lane or rate/confidence claim is authorized.
