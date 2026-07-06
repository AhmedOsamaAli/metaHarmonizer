# `backend/vendor/`

Pre-built wheels we install instead of fetching from git, so
`pip install -r requirements.txt` works on every OS without a special path.

## `metaharmonizer-0.4.0-py3-none-any.whl`

Built from [`shbrief/MetaHarmonizer`](https://github.com/shbrief/MetaHarmonizer)
`main` (v0.4.0, src-layout refactor, PR #81), with only the `src/` package tree
checked out.

**Why not `pip install git+...`**: several files under `examples/data/` and
`data/corpus/` have `:` in their names (e.g.
`disease_corpus_from_NCIT:C3262.csv`), which NTFS forbids. A full git checkout
therefore fails on Windows. We check out only `src/` + `pyproject.toml` +
`README.md` (all the build needs) and build the wheel from that.

**FAISS**: engine >=0.4.0 no longer bundles `faiss-cpu` (libomp clash with
torch on macOS). `backend/requirements.txt` installs it separately
(`faiss-cpu>=1.11.0`); on macOS use conda-forge. The ontology path
(`OntoMapEngine`) needs FAISS; `SchemaMapEngine` does not.

## Rebuilding after a version bump

When upstream ships a new commit you want to pin (src-layout, >=0.4.0):

```powershell
# 1. Sparse-clone only the package source (avoids the ':' corpus filenames)
$bd = "$env:TEMP\mh_build"
Remove-Item $bd -Recurse -Force -ErrorAction SilentlyContinue
git clone --no-checkout --depth 1 https://github.com/shbrief/MetaHarmonizer.git $bd
cd $bd
git checkout HEAD -- src pyproject.toml README.md   # only what the build needs

# 2. Build the wheel
backend\.venv\Scripts\python.exe -m pip wheel . --no-deps -w "$env:TEMP\mh_wheel"

# 3. Drop the new wheel in this directory, remove the old one
Move-Item "$env:TEMP\mh_wheel\metaharmonizer-*-py3-none-any.whl" backend\vendor\ -Force

# 4. Update the wheel path + version in backend/requirements.txt, commit, push
```

Linux/macOS: same flow with `bash` and `git`.
