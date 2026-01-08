# Zenodo Integration Guide

This guide explains how to set up Zenodo archiving for the coastal-flood-modeling repository to get a citable DOI.

## What is Zenodo?

[Zenodo](https://zenodo.org/) is a research data repository developed by CERN that:
- Provides permanent DOIs (Digital Object Identifiers) for research outputs
- Ensures long-term preservation of software and data (50+ year commitment)
- Makes your work citable in academic publications
- Integrates seamlessly with GitHub for automated archiving
- Is free and open-access

## Benefits for This Project

1. **Citability**: Researchers can cite specific versions of the software
2. **Preservation**: Code is preserved even if GitHub goes down
3. **Versioning**: Each GitHub release gets a unique DOI
4. **Discoverability**: Listed in Zenodo's search and connected to research communities
5. **Academic Recognition**: Software contributions count as research outputs

## Setup Instructions

### Step 1: Create Zenodo Account

1. Go to https://zenodo.org/
2. Click "Sign Up" (or "Log in" if you have an account)
3. **Recommended**: Sign up using your GitHub account for easier integration
4. Alternatively: Use your institutional email (e.g., university email)
5. Complete your profile with ORCID if available

### Step 2: Enable GitHub Integration

1. Log into Zenodo at https://zenodo.org/
2. Click your username → "GitHub" in the dropdown menu
3. You'll be redirected to authorize Zenodo to access your GitHub repositories
4. Click "Authorize application"
5. You'll see a list of your GitHub repositories

### Step 3: Enable Repository Archiving

1. In the Zenodo-GitHub settings page, find `randsley/coastal-flood-modeling`
2. Toggle the switch to **ON** (it will turn green)
3. This tells Zenodo to watch this repository for new releases

### Step 4: Create Your First GitHub Release

Zenodo only archives **releases**, not regular commits.

#### Option A: Using GitHub Web Interface

1. Go to https://github.com/randsley/coastal-flood-modeling
2. Click "Releases" on the right sidebar
3. Click "Create a new release"
4. Fill in the release form:
   - **Tag version**: `v1.0.0` (semantic versioning)
   - **Release title**: `v1.0.0 - Initial Release with Python/Julia Feature Parity`
   - **Description**:
     ```markdown
     ## What's New

     - Python implementation with full feature parity to Julia version
     - GeoTIFF output for QGIS/ArcGIS integration
     - Pixel-perfect HTML maps with Leaflet.js
     - Tiling support for large coastal regions (>50 km)
     - Comprehensive documentation and examples

     ## Features

     - Connected morphological flooding algorithm
     - Dual Python and Julia implementations
     - Support for Portuguese DGT 50cm DEMs
     - Vertical datum conversion (Cascais 1938 ↔ Hydrographic Zero)
     - Real-world area calculations (latitude-corrected)

     ## Files

     - `Simul_corrected.py` - Main Python implementation
     - `Simul_tiled.py` - Python tiled processing for large areas
     - `simul_flood.jl` - Julia implementation
     - `simul_flood_tiled.jl` - Julia tiled processing
     - `makeVRT.py` - DEM preprocessing

     See README.md for installation and usage instructions.
     ```
   - **Attach binaries**: None needed (source code is automatically included)
5. Click "Publish release"

#### Option B: Using Git Command Line

```bash
# Tag the current commit
git tag -a v1.0.0 -m "Initial release with Python/Julia feature parity"

# Push the tag to GitHub
git push origin v1.0.0
```

Then create the release on GitHub web interface as above.

### Step 5: Wait for Zenodo Processing

1. After creating the release, Zenodo will automatically:
   - Detect the new release via webhook
   - Download a snapshot of your repository
   - Create a new DOI
   - Archive the release permanently
2. This usually takes **5-15 minutes**
3. You'll receive an email from Zenodo when complete

### Step 6: Get Your DOI

1. Go to https://zenodo.org/account/settings/github/
2. Find your repository in the list
3. Click on the DOI badge (or the repository name)
4. You'll see your record page with:
   - **DOI**: Something like `10.5281/zenodo.1234567`
   - **Citation**: Pre-formatted citation in multiple styles
   - **Metadata**: Pulled from `.zenodo.json`

### Step 7: Update Repository with DOI

Once you have your DOI, update the README badge:

**Current (placeholder):**
```markdown
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.XXXXX-blue)](https://github.com/randsley/coastal-flood-modeling)
```

**Updated (with real DOI):**
```markdown
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.1234567.svg)](https://doi.org/10.5281/zenodo.1234567)
```

Replace `1234567` with your actual Zenodo record number.

## Metadata Configuration

The `.zenodo.json` file in the repository root controls how Zenodo displays your work.

### Key Fields to Customize

```json
{
  "creators": [
    {
      "name": "Randsley, Nigel",
      "affiliation": "Your Institution Here",  // Add your affiliation
      "orcid": "0000-0000-0000-0000"           // Add your ORCID if available
    }
  ]
}
```

### Optional: Add Funding Information

If this work was funded, add grant details:

```json
{
  "grants": [
    {
      "id": "grant-id",
      "title": "Grant Title",
      "funder": "Funding Agency Name"
    }
  ]
}
```

### Optional: Link to Publications

If you publish a paper using this software:

```json
{
  "related_identifiers": [
    {
      "identifier": "10.xxxx/journal.paper.doi",
      "relation": "isSupplementTo",
      "scheme": "doi"
    }
  ]
}
```

## Version Management Strategy

### Semantic Versioning

Use [semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes (e.g., v2.0.0 - complete rewrite)
- **MINOR**: New features (e.g., v1.1.0 - added new visualization)
- **PATCH**: Bug fixes (e.g., v1.0.1 - fixed calculation error)

### When to Create New Releases

Create a new release when:
- ✅ Significant new features are added
- ✅ Important bug fixes are made
- ✅ API changes that users should know about
- ✅ Before publishing a paper using the code
- ✅ Annually, even if changes are minor (for citation purposes)

Don't create releases for:
- ❌ Documentation-only updates
- ❌ Minor typo fixes
- ❌ Work-in-progress features

### Concept DOI vs Version DOI

Zenodo provides two types of DOIs:

1. **Concept DOI**: `10.5281/zenodo.1234567`
   - Points to **all versions** of your software
   - Use this in papers to cite the software generally
   - Always resolves to the latest version

2. **Version-specific DOI**: `10.5281/zenodo.1234568`
   - Points to a **specific release** (e.g., v1.0.0)
   - Use this for exact reproducibility
   - Each release gets its own DOI

## Citation Examples

Once your DOI is active, users can cite your work:

### In Papers (APA Style)
```
Randsley, N. (2026). Coastal Flood Simulation System for Portuguese Coastal Zones (Version 1.0.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.1234567
```

### In Papers (BibTeX)
```bibtex
@software{randsley2026coastal,
  author       = {Randsley, Nigel},
  title        = {Coastal Flood Simulation System for Portuguese Coastal Zones},
  month        = jan,
  year         = 2026,
  publisher    = {Zenodo},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.1234567},
  url          = {https://doi.org/10.5281/zenodo.1234567}
}
```

### In Code/README
```markdown
This research used the Coastal Flood Simulation System (Randsley, 2026) available at https://doi.org/10.5281/zenodo.1234567
```

## Zenodo Communities

Adding your software to relevant Zenodo communities significantly increases discoverability and citations.

### 🎯 Top Recommended Communities for This Project:
1. **Climate and Weather** - Climate adaptation, sea level rise
2. **Earth System Science** - Coastal processes, DEM analysis
3. **Natural Hazards** - Flood modeling, hazard assessment
4. **Coastal Research** - Directly related to coastal zones
5. **GIS and Geospatial** - Raster processing, spatial analysis
6. **Open Source Geospatial (OSGeo)** - Uses GDAL, open-source GIS
7. **Hydrology** - Hydrological connectivity, flooding

### 📖 Complete Communities Guide

For detailed instructions on:
- How to submit to communities
- List of 13+ relevant communities
- Tips for successful acceptance
- Community networking opportunities

**See**: [`docs/ZENODO_COMMUNITIES.md`](ZENODO_COMMUNITIES.md)

### Quick Steps to Join Communities

1. Go to your Zenodo record
2. Click "Edit"
3. Scroll to "Communities"
4. Search and add communities (can add multiple)
5. Save and wait for curator approval (1-14 days)

## ORCID Integration

If you don't have an ORCID:
1. Register at https://orcid.org/ (free)
2. ORCID is a unique identifier for researchers
3. Helps disambiguate you from others with similar names
4. Many journals now require ORCID for submissions
5. Add it to `.zenodo.json` for automatic linking

## Troubleshooting

### DOI Not Generated After Release

- Check Zenodo GitHub settings: Is the toggle ON?
- Verify the release is tagged (not just a draft)
- Wait 15-30 minutes; GitHub webhooks can be delayed
- Check Zenodo's status page: https://status.zenodo.org/

### Metadata Not Showing Correctly

- Ensure `.zenodo.json` is in the repository **before** creating the release
- JSON must be valid (use https://jsonlint.com/ to check)
- If metadata is wrong, you can edit it on Zenodo after publication

### Want to Update an Existing DOI

- You **cannot** change an archived release (that's the point!)
- Instead: Create a new release (e.g., v1.0.1) with corrected metadata
- Zenodo will create a new version-specific DOI
- The concept DOI will link to all versions

## Maintenance Checklist

- [ ] Create Zenodo account
- [ ] Enable GitHub integration
- [ ] Toggle repository archiving ON
- [ ] Customize `.zenodo.json` with your information
- [ ] Create v1.0.0 release on GitHub
- [ ] Wait for Zenodo to process (~15 minutes)
- [ ] Update README.md with real DOI badge
- [ ] Add DOI to CITATION.cff
- [ ] Commit and push changes
- [ ] (Optional) Join relevant Zenodo communities
- [ ] (Optional) Add ORCID to your profile

## Additional Resources

- **Zenodo FAQ**: https://help.zenodo.org/
- **GitHub-Zenodo Integration**: https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content
- **Semantic Versioning**: https://semver.org/
- **Citation File Format (CFF)**: https://citation-file-format.github.io/
- **ORCID**: https://orcid.org/

## Questions?

If you encounter issues:
1. Check Zenodo's documentation: https://help.zenodo.org/
2. Contact Zenodo support: info@zenodo.org
3. Ask on Zenodo's community forum: https://github.com/zenodo/zenodo/discussions

---

**Last Updated**: 2026-01-08
