# Plot workflow

## Retriever role

Prioritize references with the same statistical intent and chart family. Match
multi-panel structure, variable roles, uncertainty encoding, grouping, and scale before
matching the application domain.

## Planner role

Convert the raw data and visual intent into a complete plot specification. Explicitly
enumerate:

1. every value or observation that must be plotted;
2. x, y, color, marker, size, facet, and grouping mappings;
3. chart type and subplot layout;
4. axis labels, units, ranges, scales, ticks, and ordering;
5. uncertainty, baselines, annotations, legends, and titles;
6. figure dimensions and publication constraints.

Never infer missing measurements. Preserve numeric precision and category order.

## Stylist role

Improve accessibility and presentation without changing data. Use colorblind-safe
palettes, markers or hatches where useful, restrained grids, legible typography, and
compact legends. Avoid 3D decoration unless depth is a real data dimension.

## Visualizer role

Write deterministic Matplotlib code using inline data only. Create at least one Figure.
Do not read or write files, access the network, launch processes, call `show()`, or call
`savefig()`; the guarded renderer owns output.

## Critic role

Compare the plot against the exact source data and specification. Verify every
coordinate, aggregation, denominator, error bar, ordering, label, unit, scale, legend,
and annotation. Also check clipping, overlap, contrast, and print readability.

Return “No changes needed.” only when both numerical and visual checks pass. Otherwise
provide a complete revised specification before regenerating code.

