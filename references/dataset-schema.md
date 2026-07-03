# PaperBananaBench reference schema

## Dataset root

Accept either the `PaperBananaBench` directory itself or its parent:

```text
PaperBananaBench/
├── diagram/
│   ├── ref.json
│   └── images/
└── plot/
    ├── ref.json
    └── images/
```

`test.json` contains evaluation targets and ground-truth images. Never mix it into
retrieval.

## Required reference fields

| Field | Diagram | Plot | Runtime use |
|---|---|---|---|
| `id` | Unique string | Unique string | Retrieval result and manifest |
| `content` | Relevant methodology text | Structured raw numeric data | Text retrieval and Planner context |
| `visual_intent` | Figure caption | Chart type, title, and visual intent | Weighted retrieval and Planner context |
| `path_to_gt_image` | Relative image path | Relative image path | Multimodal reranking |

Optional fields such as `category`, `split`, `difficulty`, `original_category`,
`additional_info`, and `gt_code` are metadata. `category` receives a small retrieval
weight. The native workflow does not execute `gt_code`.

## Adding domain references

Add each image under the matching `images/` directory and add one record to
`ref.json`. Prefer the method subsection directly related to the figure instead of the
entire paper. Use a unique domain-prefixed ID and a caption that clearly states the
figure type and scientific purpose.

The local retriever scans the complete file; appended entries are not subject to the
original project's first-200 limit.

