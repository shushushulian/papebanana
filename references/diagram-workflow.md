# Diagram workflow

## Retriever role

Select references that teach the target's visual structure. Prioritize the same
communicative intent—pipeline, architecture, detailed module, control loop, hierarchy,
or comparison—over superficial topic similarity. Prefer a same-domain example when its
structure is also useful.

## Planner role

Transform the methodology and caption into a precise, self-contained visual
specification. Learn composition patterns from the selected references without
copying their scientific content.

The specification must define:

1. canvas orientation, reading order, and major zones;
2. every required module, input, intermediate state, output, and loss;
3. exact labels derived from the source;
4. every connection, direction, branch, merge, feedback loop, and line meaning;
5. visual hierarchy, container nesting, shapes, colors, icons, typography, and spacing;
6. what must not appear, especially unsupported claims and a figure title.

Choose a compact organizing metaphor when helpful: pipeline, layered stack, branching
tree, hub-and-spoke, map, or control loop. The metaphor guides layout only and must not
alter the method.

## Stylist role

Preserve all semantic content and graph structure. Improve only hierarchy, grouping,
color harmony, typography, whitespace, and connector clarity. Simplify verbose labels
only when their meaning remains exact. Avoid decorative complexity that competes with
the science.

## Visualizer role

Render a publication-ready scientific diagram on a white or very light background.
Do not include a figure title. Keep labels legible at manuscript size. Use consistent
geometry and make the primary reading path immediately visible.

## Critic role

Compare the rendered image with the methodology, caption, and current specification.
Check:

- factual fidelity and completeness;
- hallucinated or omitted components;
- arrow direction, branching, and feedback logic;
- typos, malformed symbols, and ambiguous labels;
- examples, equations, and tensor dimensions;
- readability, whitespace, alignment, and visual hierarchy;
- redundant legends or title text.

Return “No changes needed.” only when no material correction is warranted. Otherwise
produce a targeted correction list and a complete revised specification.

