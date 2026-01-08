# Zenodo Communities Guide

This guide explains how to add the coastal-flood-modeling software to relevant Zenodo communities for increased visibility and discoverability.

## What Are Zenodo Communities?

Zenodo communities are curated collections of related research outputs. Benefits include:

- **Increased Discoverability**: Your software appears in community searches
- **Thematic Organization**: Groups similar research together
- **Quality Signal**: Community curation implies peer recognition
- **Networking**: Connect with researchers in your field
- **Citations**: More visibility leads to more citations

## Recommended Communities for Coastal Flood Modeling

### 🌊 Primary Communities (Highly Relevant)

#### 1. **Climate and Weather**
- **Community ID**: `climate`
- **URL**: https://zenodo.org/communities/climate/
- **Relevance**: ⭐⭐⭐⭐⭐ (Climate adaptation, sea level rise)
- **Size**: Large, active community
- **Acceptance**: Usually quick (1-7 days)

#### 2. **Earth System Science**
- **Community ID**: `earth-system-science`
- **URL**: https://zenodo.org/communities/earth-system-science/
- **Relevance**: ⭐⭐⭐⭐⭐ (Coastal processes, DEM analysis)
- **Size**: Medium, growing community
- **Acceptance**: Moderate review

#### 3. **Natural Hazards**
- **Community ID**: `natural-hazards`
- **URL**: https://zenodo.org/communities/natural-hazards/
- **Relevance**: ⭐⭐⭐⭐⭐ (Flood modeling, hazard assessment)
- **Size**: Medium, well-established
- **Acceptance**: May require description of hazard relevance

### 🗺️ Secondary Communities (Very Relevant)

#### 4. **GIS and Geospatial**
- **Community ID**: `gis` or `geospatial`
- **URL**: https://zenodo.org/communities/gis/
- **Relevance**: ⭐⭐⭐⭐ (Raster processing, spatial analysis)
- **Size**: Large community
- **Acceptance**: Generally accepts GIS tools

#### 5. **Open Source Geospatial**
- **Community ID**: `osgeo`
- **URL**: https://zenodo.org/communities/osgeo/
- **Relevance**: ⭐⭐⭐⭐ (Uses GDAL, open-source GIS)
- **Size**: Medium, OSGeo affiliated
- **Acceptance**: Requires open-source license (✓ MIT)

#### 6. **Coastal Research**
- **Community ID**: `coastal` or search "coastal"
- **URL**: Search on Zenodo for coastal communities
- **Relevance**: ⭐⭐⭐⭐⭐ (Directly related to coastal zones)
- **Size**: Varies by specific community
- **Acceptance**: Highly relevant, should be quick

### 🔬 Tertiary Communities (Relevant)

#### 7. **Hydrology**
- **Community ID**: `hydrology`
- **URL**: https://zenodo.org/communities/hydrology/
- **Relevance**: ⭐⭐⭐ (Hydrological connectivity, flooding)
- **Size**: Medium community
- **Acceptance**: Moderate

#### 8. **Remote Sensing**
- **Community ID**: `remote-sensing`
- **URL**: https://zenodo.org/communities/remote-sensing/
- **Relevance**: ⭐⭐⭐ (DEM processing, spatial data)
- **Size**: Large community
- **Acceptance**: May need to emphasize DEM aspect

#### 9. **Scientific Software**
- **Community ID**: `software` or `research-software`
- **URL**: https://zenodo.org/communities/software/
- **Relevance**: ⭐⭐⭐ (General scientific software)
- **Size**: Very large
- **Acceptance**: Usually accepts scientific tools

### 🇵🇹 Regional/National Communities

#### 10. **Portuguese Research**
- Search for Portugal-specific communities
- May be affiliated with Portuguese research institutions
- **Relevance**: ⭐⭐⭐⭐ (Geographic focus on Portugal)

#### 11. **European Geosciences Union (EGU)**
- **Community ID**: `egu`
- **URL**: https://zenodo.org/communities/egu/
- **Relevance**: ⭐⭐⭐ (European geoscience)
- **Size**: Large, prestigious
- **Acceptance**: May require EGU connection

### 🎓 Institutional/Programming Communities

#### 12. **Julia Programming Language**
- **Community ID**: `julia`
- **URL**: https://zenodo.org/communities/julia/
- **Relevance**: ⭐⭐⭐ (Julia implementation)
- **Size**: Growing community

#### 13. **Python Scientific Computing**
- Search for Python scientific communities
- **Relevance**: ⭐⭐⭐ (Python implementation)

---

## How to Add Your Software to Communities

### Method 1: When Creating a New Release (Recommended)

**Step 1: Create Your GitHub Release**
- This triggers Zenodo to archive your repository
- Wait for Zenodo to process (5-15 minutes)

**Step 2: Go to Your Zenodo Record**
1. Visit https://zenodo.org/account/settings/github/
2. Click on your repository name: `coastal-flood-modeling`
3. You'll see your uploaded record

**Step 3: Edit the Record**
1. Click the **"Edit"** button (orange button, top right)
2. Scroll down to the **"Communities"** section
3. You'll see a search box

**Step 4: Search and Add Communities**
1. Type a community name (e.g., "climate")
2. Click on the community in the dropdown
3. Click **"Add"** or press Enter
4. Repeat for each community (you can add multiple)

**Step 5: Save and Submit for Review**
1. Scroll to the bottom
2. Click **"Save"** (saves your changes)
3. Your submission is now pending community approval

**Step 6: Wait for Approval**
- Community curators review submissions
- Timeline: 1 day to 2 weeks (varies by community)
- You'll receive email notifications for approvals/rejections

---

### Method 2: For Existing Zenodo Records

If your software is already on Zenodo:

1. **Go to Your Record**: https://zenodo.org/search?q=coastal-flood-modeling
2. Click on your record
3. Click **"Edit"** (you must be logged in)
4. Follow steps 4-6 above
5. Note: You can edit records even after publication

---

## Tips for Successful Community Inclusion

### ✅ Do's

1. **Add a Detailed Description**
   - Explain how your software relates to the community
   - Highlight relevant features
   - Example: "This software implements morphological flooding algorithms for climate adaptation studies in coastal zones"

2. **Use Relevant Keywords**
   - Your `.zenodo.json` already has good keywords
   - Communities look at these when reviewing

3. **Choose Appropriate Communities**
   - Only submit to communities where your work is genuinely relevant
   - 5-10 communities is reasonable

4. **Keep Metadata Updated**
   - Ensure title, abstract, and keywords clearly describe your work
   - Good metadata increases acceptance chances

5. **Be Patient**
   - Some communities review weekly
   - Prestigious communities may be slower

### ❌ Don'ts

1. **Don't Spam Communities**
   - Avoid submitting to 50+ communities
   - Quality over quantity

2. **Don't Submit to Irrelevant Communities**
   - Example: Don't submit to "Particle Physics" for flood modeling
   - Curators will reject and it wastes everyone's time

3. **Don't Give Up After Rejection**
   - Some communities are highly selective
   - One rejection doesn't mean your work isn't valuable
   - Focus on communities where you fit best

---

## What Happens After Submission?

### Approval Process

1. **Pending Review**
   - Your record shows "Pending approval in X communities"
   - Community curators receive a notification

2. **Curator Review**
   - Curators check if your work fits the community scope
   - They review title, abstract, keywords, and metadata

3. **Approved ✓**
   - Your record appears in the community collection
   - You receive email notification
   - Your record page shows community badges

4. **Rejected ✗**
   - You receive email with reason (usually brief)
   - Common reasons:
     - Not relevant to community scope
     - Incomplete metadata
     - Duplicate submission
   - You can still submit to other communities

---

## Monitoring Your Community Memberships

### Check Current Memberships

1. Go to your Zenodo record
2. Look for "Communities" badges under the title
3. Each badge links to the community collection

### Remove from a Community

1. Edit your record
2. Go to "Communities" section
3. Click the "X" next to the community name
4. Save changes

---

## Creating Your Own Zenodo Community (Advanced)

If no suitable community exists, you can create one:

### Requirements
- Active Zenodo account
- Clear community scope and description
- Commitment to curate submissions

### Steps
1. Go to https://zenodo.org/communities/new
2. Fill in:
   - **ID**: Unique identifier (e.g., `coastal-modeling`)
   - **Title**: Display name
   - **Description**: Scope and purpose
   - **Curation Policy**: How you'll review submissions
   - **Page**: Optional markdown page
3. Submit for Zenodo staff approval
4. Once approved, you can invite submissions

### Example Community Ideas
- "Portuguese Coastal Research"
- "Flood Modeling Software"
- "Climate Adaptation Tools"

---

## Specific Recommendations for This Project

### Priority 1 (Submit Immediately)
1. ✅ Climate and Weather
2. ✅ Earth System Science
3. ✅ Natural Hazards
4. ✅ Coastal Research

### Priority 2 (Highly Relevant)
5. ✅ GIS and Geospatial
6. ✅ Open Source Geospatial (OSGeo)
7. ✅ Hydrology

### Priority 3 (Good Fit)
8. ✅ Remote Sensing
9. ✅ Scientific Software
10. ✅ Portuguese Research (if exists)

### Optional
- Julia community (if you want to highlight Julia implementation)
- Python community (for Python users)
- EGU (if you present at EGU conferences)

---

## Example Community Submission Message

If a community requires a message or description:

```
This software implements connected morphological flooding algorithms for
high-resolution coastal inundation modeling in Portuguese coastal zones.
It uses 50cm Digital Elevation Models to simulate flood extent under
various sea level rise scenarios, accounting for hydrological connectivity
and vertical datum conversions. The tool supports climate adaptation
planning and coastal hazard assessment.

Key features:
- Morphological reconstruction algorithm for hydrologically-connected flooding
- Dual Python and Julia implementations
- Support for large coastal regions via tiling
- Real-world area calculations with latitude correction
- Open-source (MIT License)

Relevant to this community because: [explain specific relevance to that community]
```

---

## Tracking Community Impact

### View Community Statistics

Once accepted, you can track:
- **Views**: How many people viewed your record via the community
- **Downloads**: Downloads attributed to community discovery
- **Citations**: Papers citing your work via community links

### Monitor via Zenodo Dashboard

1. Go to https://zenodo.org/account/settings/applications/
2. View statistics for each upload
3. See which communities drive the most traffic

---

## Community Networking Opportunities

### Engage with Communities

1. **Browse Community Collections**
   - See similar work
   - Discover potential collaborators

2. **Follow Community Announcements**
   - Some communities have mailing lists
   - Stay updated on related work

3. **Connect with Curators**
   - Curators are often field experts
   - Can provide feedback and networking

4. **Present at Related Conferences**
   - EGU, AGU, coastal conferences
   - Mention Zenodo archive in presentations

---

## Troubleshooting

### Can't Find a Community

**Solution**: Use Zenodo search
1. Go to https://zenodo.org/communities
2. Search for keywords (e.g., "coastal", "flood", "GIS")
3. Browse results for relevant communities

### Community Not Accepting

**Reasons**:
- Community may be closed/inactive
- May require institutional affiliation
- Scope may have changed

**Solution**:
- Read community description carefully
- Contact curators if unclear
- Choose alternative communities

### Submission Stuck in "Pending"

**Timeframe**:
- Some communities review weekly/monthly
- Academic holidays may delay reviews
- 2-4 weeks is normal for some communities

**Action**:
- Be patient
- If > 1 month, check if community is active
- Can contact Zenodo support: info@zenodo.org

---

## Summary Checklist

- [ ] Create first GitHub release (v1.0.0)
- [ ] Wait for Zenodo to process and assign DOI
- [ ] Edit Zenodo record to add communities
- [ ] Submit to 5-10 relevant communities:
  - [ ] Climate and Weather
  - [ ] Earth System Science
  - [ ] Natural Hazards
  - [ ] Coastal Research
  - [ ] GIS and Geospatial
  - [ ] Open Source Geospatial
  - [ ] Hydrology
  - [ ] Remote Sensing
  - [ ] Scientific Software
  - [ ] Portuguese Research (if exists)
- [ ] Wait for community approvals (1-14 days)
- [ ] Monitor community badges on your record
- [ ] Update README.md with community links (optional)

---

## Additional Resources

- **Zenodo Communities**: https://zenodo.org/communities
- **Community Guidelines**: https://help.zenodo.org/docs/deposit/describe-records/communities/
- **Zenodo Help**: https://help.zenodo.org/
- **Create Community**: https://zenodo.org/communities/new

---

**Last Updated**: 2026-01-08

Good luck with your community submissions! 🚀
