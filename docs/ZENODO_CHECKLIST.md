# Zenodo Setup Quick Checklist

Quick reference for setting up Zenodo DOI for coastal-flood-modeling.

## Pre-Setup (One Time)

- [ ] Create Zenodo account at https://zenodo.org/
- [ ] Sign in with GitHub account (recommended)
- [ ] Go to GitHub settings: https://zenodo.org/account/settings/github/
- [ ] Authorize Zenodo to access GitHub repositories
- [ ] Toggle **ON** the `coastal-flood-modeling` repository
- [ ] (Optional) Add your ORCID at https://orcid.org/
- [ ] (Optional) Update `.zenodo.json` with your affiliation and ORCID

## For Each Release

- [ ] Ensure `.zenodo.json` is updated and committed
- [ ] Create a git tag: `git tag -a v1.0.0 -m "Release message"`
- [ ] Push tag to GitHub: `git push origin v1.0.0`
- [ ] Create GitHub release with:
  - Tag version (e.g., v1.0.0)
  - Release title
  - Detailed description of changes
- [ ] Wait 5-15 minutes for Zenodo to process
- [ ] Check email for Zenodo confirmation
- [ ] Visit https://zenodo.org/account/settings/github/ to see your DOI
- [ ] Copy the DOI (e.g., 10.5281/zenodo.1234567)

## After First Release

- [ ] Update README.md DOI badge:
  ```markdown
  [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXX)
  ```
- [ ] Update CITATION.cff with DOI:
  ```yaml
  doi: "10.5281/zenodo.XXXXX"
  ```
- [ ] Commit and push these changes
- [ ] (Optional) Join relevant Zenodo communities

## Useful Links

- **Zenodo Main**: https://zenodo.org/
- **GitHub Settings**: https://zenodo.org/account/settings/github/
- **Your Records**: https://zenodo.org/account/settings/github/repository/randsley/coastal-flood-modeling
- **Full Guide**: See `docs/ZENODO_SETUP.md`

## Quick DOI Citation Format

```bibtex
@software{randsley2026coastal,
  author       = {Randsley, Nigel},
  title        = {Coastal Flood Simulation System},
  year         = 2026,
  publisher    = {Zenodo},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.XXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXX}
}
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No DOI after 30 min | Check if repository toggle is ON in Zenodo settings |
| Wrong metadata | Edit directly on Zenodo or create new release with fixed `.zenodo.json` |
| Need to update DOI | Cannot edit existing DOI - create new release version |

---

**See full guide**: `docs/ZENODO_SETUP.md`
