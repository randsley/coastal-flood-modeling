---
name: Feature Request
about: Suggest a new feature or enhancement
title: '[FEATURE] '
labels: enhancement
assignees: ''
---

## Feature Description

A clear and concise description of the feature you'd like to see.

## Problem or Use Case

What problem does this feature solve? What use case does it support?

**Example:** "I'm trying to analyze sea level rise impacts across multiple time periods, but currently..."

## Proposed Solution

How should this feature work? Include examples if possible.

```julia
# Example of how the feature might be used
results = run_multi_scenario_analysis(
    vrt_path,
    scenarios = [
        (tide=3.8, surge=0.6, slr=0.5),
        (tide=3.8, surge=0.6, slr=1.0),
        (tide=3.8, surge=0.6, slr=1.5)
    ]
)
```

## Alternatives Considered

What other approaches or solutions have you considered?

## Implementation Details

If you have technical suggestions about how this could be implemented.

## Scientific Background

For algorithm or methodology changes:
- Research papers or references
- Similar implementations in other tools
- Validation data or benchmarks

## Benefits

Who would benefit from this feature? How would it improve the project?

## Additional Context

Add any other context, screenshots, mockups, or examples.

## Willing to Contribute?

- [ ] I would be willing to implement this feature
- [ ] I would be willing to help test this feature
- [ ] I can provide validation data for this feature
