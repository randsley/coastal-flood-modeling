# Contributing to Coastal Flood Simulation System

Thank you for your interest in contributing to this coastal flood modeling project! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Submitting Changes](#submitting-changes)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Enhancements](#suggesting-enhancements)

## Code of Conduct

This project is committed to providing a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

## How Can I Contribute?

### Types of Contributions Welcome

- **Bug fixes**: Corrections to existing code
- **Documentation improvements**: Clarifications, examples, corrections
- **Performance optimizations**: Faster algorithms, memory efficiency
- **New features**: Additional flood modeling capabilities
- **Test cases**: Validation with real-world scenarios
- **Algorithm improvements**: Better morphological reconstruction methods
- **Data processing enhancements**: Support for additional DEM formats

### Areas of Focus

1. **Algorithm Development**
   - Morphological flooding improvements
   - Alternative hydrological connectivity methods
   - Performance optimizations for large regions

2. **Data Processing**
   - Support for additional DEM sources
   - Vertical datum conversion utilities
   - Automated data validation

3. **Visualization**
   - Enhanced HTML map outputs
   - Interactive 3D visualization
   - Time-series animation for SLR scenarios

4. **Documentation**
   - Use case examples
   - Scientific validation studies
   - Tutorial notebooks

## Development Setup

### Prerequisites

**Julia (1.10+):**
```julia
using Pkg
Pkg.add(["Rasters", "ArchGDAL", "ImageMorphology", "Statistics"])
Pkg.add(["FileIO", "ImageIO", "ColorTypes"])  # For HTML maps
Pkg.add("GLMakie")  # Optional: for plotting
```

**Python (3.8+):**
```bash
pip install rasterio numpy folium shapely scikit-image gdal
```

### Getting Started

1. **Fork the repository** on GitHub

2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/coastal-flood-modeling.git
   cd coastal-flood-modeling
   ```

3. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Set up test data** (optional):
   - Download sample DEM tiles from [DGT](https://www.dgterritorio.gov.pt/)
   - Place in `DEM/` directory
   - Run `python makeVRT.py` to create VRT files

## Coding Standards

### Julia Code Style

Follow [Julia Style Guide](https://docs.julialang.org/en/v1/manual/style-guide/):

- Use 4 spaces for indentation (no tabs)
- Function names: lowercase with underscores (`run_simulation_on_vrt`)
- Variable names: lowercase with underscores (`flood_threshold`)
- Constants: UPPERCASE (`DATUM_OFFSET`)
- Maximum line length: 92 characters
- Add docstrings to public functions

**Example:**
```julia
"""
    calculate_flood_threshold(tide_zh, surge, slr, datum_offset)

Calculate flood elevation threshold relative to DEM datum.

# Arguments
- `tide_zh`: Tide level relative to Hydrographic Zero (m)
- `surge`: Storm surge height (m)
- `slr`: Sea level rise (m)
- `datum_offset`: Offset between DEM datum and ZH (m)

# Returns
- Flood threshold elevation in DEM datum (m)
"""
function calculate_flood_threshold(tide_zh, surge, slr, datum_offset)
    return (tide_zh + surge + slr) - datum_offset
end
```

### Python Code Style

Follow [PEP 8](https://pep8.org/):

- Use 4 spaces for indentation
- Function names: lowercase with underscores
- Maximum line length: 88 characters (Black formatter compatible)
- Add type hints where helpful
- Include docstrings for functions

**Example:**
```python
def calculate_flood_threshold(
    tide_zh: float,
    surge: float,
    slr: float,
    datum_offset: float
) -> float:
    """
    Calculate flood elevation threshold relative to DEM datum.

    Args:
        tide_zh: Tide level relative to Hydrographic Zero (m)
        surge: Storm surge height (m)
        slr: Sea level rise (m)
        datum_offset: Offset between DEM datum and ZH (m)

    Returns:
        Flood threshold elevation in DEM datum (m)
    """
    return (tide_zh + surge + slr) - datum_offset
```

### General Guidelines

1. **Comments**: Explain *why*, not *what*
   - Good: `# Use erosion to ensure hydrological connectivity`
   - Bad: `# Set seed[1:-1, 1:-1] to max elevation`

2. **Variable Naming**: Use descriptive names
   - Good: `flood_threshold`, `pixel_area_m2`
   - Bad: `th`, `area`, `x`

3. **Magic Numbers**: Define constants
   - Good: `DATUM_OFFSET = 2.00  # Cascais to ZH offset (m)`
   - Bad: `threshold = (tide + surge) - 2.0`

4. **Error Handling**: Provide informative messages
   ```julia
   if !isfile(vrt_path)
       error("VRT file not found: $vrt_path. Run makeVRT.py first.")
   end
   ```

## Submitting Changes

### Pull Request Process

1. **Update your fork:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make your changes:**
   - Write clear, focused commits
   - Include tests if applicable
   - Update documentation as needed

3. **Test your changes:**
   - Run existing examples to ensure no regressions
   - Test with sample DEM data if possible
   - Verify HTML/GeoTIFF outputs

4. **Commit with descriptive messages:**
   ```bash
   git commit -m "Add support for NOAA DEM format

   - Implement reader for NOAA coastal relief model
   - Add vertical datum conversion for NAVD88
   - Update documentation with NOAA example

   Fixes #123"
   ```

5. **Push to your fork:**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create Pull Request:**
   - Go to the original repository on GitHub
   - Click "New Pull Request"
   - Select your feature branch
   - Fill out the PR template (see below)

### Pull Request Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing functionality)
- [ ] Documentation update

## Testing
How has this been tested?
- [ ] Tested with sample DEM data
- [ ] Verified HTML output renders correctly
- [ ] Checked GeoTIFF in QGIS
- [ ] Ran tiled processing for large region

## Checklist
- [ ] My code follows the style guidelines
- [ ] I have commented my code where needed
- [ ] I have updated the documentation
- [ ] My changes generate no new warnings
- [ ] I have tested with both Julia and Python (if applicable)

## Screenshots (if applicable)
Add screenshots of HTML maps or QGIS visualizations.
```

## Reporting Bugs

### Before Submitting a Bug Report

- Check existing issues to avoid duplicates
- Verify you're using the latest version
- Test with minimal example if possible

### Bug Report Template

**Title:** Clear, descriptive title

**Description:**
- What you expected to happen
- What actually happened
- Steps to reproduce

**Environment:**
```
- OS: [e.g., macOS 14.0, Ubuntu 22.04]
- Julia version: [e.g., 1.10.0]
- Python version: [e.g., 3.11.5]
- Rasters.jl version: [from Pkg.status()]
- rasterio version: [from pip list]
```

**Sample Code:**
```julia
# Minimal reproducible example
bounds = (-8.70, 40.95, -8.60, 41.03)
result = run_simulation_on_vrt("test.vrt", 3.8, 0.6, 1.13, bounds)
# Error occurs here...
```

**Error Message:**
```
Full error traceback
```

**Data:**
- DEM source: [e.g., DGT 50cm tiles]
- Bounding box: [coordinates]
- File size: [if relevant]

## Suggesting Enhancements

### Enhancement Proposal Template

**Title:** Feature: [Clear description]

**Motivation:**
Why is this enhancement needed? What problem does it solve?

**Proposed Solution:**
How should this work? Include code examples if possible.

**Alternatives Considered:**
What other approaches did you think about?

**Additional Context:**
- Links to research papers
- Examples from other tools
- Screenshots or mockups

## Scientific Contributions

### Validation Studies

If you have validation data (observed flood extents, tide gauge data, etc.):

1. Document your data sources clearly
2. Include methodology for comparison
3. Provide quantitative metrics (e.g., F1 score, area overlap)
4. Consider adding to a `validation/` directory

### Algorithm Improvements

For morphological reconstruction or flooding algorithm changes:

1. Explain the scientific basis
2. Provide before/after comparisons
3. Include performance benchmarks
4. Reference relevant literature

### Datum Conversions

For new coastal regions or vertical datum offsets:

1. Document the datum relationship clearly
2. Cite official sources (tide gauge data, geodetic surveys)
3. Include uncertainty estimates
4. Add to documentation with geographic applicability

## Questions?

If you have questions about contributing:

- Open a GitHub Discussion
- Check existing Issues and PRs for similar topics
- Contact: nigel.randsley@protonmail.com

## Recognition

All contributors will be acknowledged in the project. Significant contributions may be recognized in:
- CONTRIBUTORS.md file
- Academic papers using this software
- Release notes

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to better coastal flood modeling!**
