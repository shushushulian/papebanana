---
name: paperbanana-codex
description: Create publication-ready academic mechanism diagrams and quantitative plots from method text, captions, or structured data using a locally installed PaperBananaBench reference set. Use for algorithm frameworks, model architectures, scientific pipelines, experiment charts, reference-driven figure planning, and iterative figure critique. Prefer Codex-native reasoning and image generation; use Gemini/OpenRouter only when the user explicitly requests their configured API.
---

# PaperBanana Codex

Use PaperBananaBench as retrieval-only few-shot context. Do not train or fine-tune a
model. Read only `ref.json`; never use `test.json` as a reference source.

## Resume an interrupted native render

Before dataset validation, retrieval, or planning, detect whether the user explicitly
asks to continue or retry the previous native render without changing its source,
caption, or task. If so, read the latest matching checkpoint:

```powershell
python "<SKILL_ROOT>/scripts/run_artifacts.py" resume `
  --base-dir paperbanana_outputs `
  --task diagram `
  --backend native
```

When the command returns a JSON object:

1. Reuse its `output_dir`, `selected_references`, `final_description`, parameters, and
   exact `render_prompt`.
2. Call image generation immediately with that `render_prompt`.
3. Do not validate the dataset, retrieve references, inspect reference images, rerun
   Planner or Stylist, or rewrite the render prompt.
4. If image generation fails again, keep `.paperbanana-state.json` unchanged and
   report the failure. Never delete the checkpoint or retrieval file after a failed
   render.
5. If generation succeeds, continue with Critic inspection and normal manifest
   creation. A successful manifest removes the consumed checkpoint.

When the command returns `null`, explain that no resumable render exists and continue
as a new run. Never resume a checkpoint when the user supplies changed source content,
caption, task, or explicitly asks for new references.

## Resolve the request

1. Treat the skill directory containing this file as `SKILL_ROOT`.
2. Resolve the task:
   - Use `diagram` for algorithms, mechanisms, architectures, workflows, and systems.
   - Use `plot` for numeric experiment results and statistical charts.
3. Accept source text inline or from a local file. Infer a concise caption when absent.
4. Default to one candidate and three Critic rounds. Cap candidates at three and stop
   early when the Critic finds no material change.
5. Default to `backend=native`.
6. Use `backend=api` only when the user explicitly says to use their API. A configured
   key alone is never consent.

## Configure and validate data

Resolve the dataset path in this order: the current request, the
`PAPERBANANA_BENCH_ROOT` environment variable, then the saved user configuration.

When no path is configured, ask for it and run:

```powershell
python "<SKILL_ROOT>/scripts/configure.py" --dataset-root "<PaperBananaBench>"
```

Validate only the requested task before generation:

```powershell
python "<SKILL_ROOT>/scripts/validate_dataset.py" --task diagram
```

Stop on structural errors. Warn and continue when individual reference images are
missing.

For a new native run, create its durable run directory before retrieval:

```powershell
python "<SKILL_ROOT>/scripts/run_artifacts.py" prepare
```

## Retrieve references

Create a compact English retrieval query containing the domain, intended figure type,
major components, and relationships. Retrieve 20 candidates from the complete
task-specific `ref.json`:

```powershell
python "<SKILL_ROOT>/scripts/retrieve_references.py" `
  --task diagram `
  --query "<retrieval query>" `
  --limit 20 `
  --output "<run-dir>/retrieval.json"
```

Read the candidate JSON. Inspect up to eight leading images with the local image-view
capability, then rerank by:

1. visual structure and communicative intent;
2. semantic/domain relevance;
3. layout and style usefulness.

Keep five references or fewer when fewer are valid. Use their text and images only as
context; do not copy labels or scientific claims unsupported by the target source.

## Plan and style

Read the task-specific workflow and style guide:

- Diagram: `references/diagram-workflow.md` and `references/diagram-style.md`
- Plot: `references/plot-workflow.md` and `references/plot-style.md`

Perform the roles in order:

1. **Planner:** convert the source and caption into a complete figure specification.
2. **Stylist:** improve visual presentation without changing semantics or values.
3. **Visualizer:** render the image.
4. **Critic:** compare the image against the source, caption, and specification.

Keep the final specification in memory and prepare the exact render prompt before
calling image generation.

## Checkpoint a native render

Immediately before the first native image-generation call, save the source hash,
selected reference IDs, final specification, parameters, and exact render prompt:

```powershell
python "<SKILL_ROOT>/scripts/run_artifacts.py" checkpoint `
  --output-dir "<run-dir>" `
  --task diagram `
  --backend native `
  --source-file "<temporary-source-file>" `
  --caption "<caption>" `
  --description-file "<temporary-description-file>" `
  --render-prompt-file "<temporary-render-prompt-file>" `
  --references-file "<temporary-selected-reference-ids-json>" `
  --parameters-file "<temporary-parameters-json>"
```

Verify that `<run-dir>/.paperbanana-state.json` exists before calling image generation.
The checkpoint may contain the render prompt but stores only a hash of the original
source text. Delete temporary source, description, prompt, and parameter files after
the checkpoint is verified. Keep the checkpoint and `retrieval.json` until the final
manifest succeeds.

## Render a diagram

Require the Codex image-generation capability. If it is unavailable, explain that
native diagram rendering cannot proceed. Do not silently use an external API.

1. Call image generation with the exact checkpointed render prompt. Do not pass
   reference images as source images for a new figure.
2. Inspect the generated image.
3. Critique factual fidelity, missing modules, arrow direction, text correctness,
   readability, and aesthetics.
4. If a material correction is needed, edit the current image using it as the
   referenced image and a precise correction prompt.
5. Repeat for at most three Critic rounds; retain the last valid image when an edit
   fails.
6. Copy the selected image to `<run-dir>/final.png`.

## Render a plot

Generate Python code with inline source data only. Do not generate code that reads
files, accesses the network, launches processes, calls `show()`, or calls `savefig()`.

Check the isolated Plot runtime:

```powershell
python "<SKILL_ROOT>/scripts/setup_runtime.py" --mode plot --check
```

If missing, show the following command and wait for approval before running it:

```powershell
python "<SKILL_ROOT>/scripts/setup_runtime.py" --mode plot --install
```

Use the Python path printed by that command to render through the guarded subprocess:

```powershell
"<plot-runtime-python>" "<SKILL_ROOT>/scripts/safe_plot.py" `
  --code "<temporary-plot.py>" `
  --output "<run-dir>/final.png" `
  --code-output "<run-dir>/plot.py"
```

Inspect the plot. Verify every numeric value, mapping, axis, legend, uncertainty
encoding, and annotation. Revise and rerender at most three times. Keep the last valid
render when a revision fails.

## Use the optional API backend

Only after explicit user consent, check the isolated API runtime:

```powershell
python "<SKILL_ROOT>/scripts/setup_runtime.py" --mode api --check
```

If missing, show the following command and wait for approval:

```powershell
python "<SKILL_ROOT>/scripts/setup_runtime.py" --mode api --install
```

Then use the printed Python path to run:

```powershell
"<api-runtime-python>" "<SKILL_ROOT>/scripts/api_pipeline.py" `
  --confirm-api `
  --task diagram `
  --source-file "<source-file>" `
  --caption "<caption>"
```

API configuration defaults to
`$CODEX_HOME/paperbanana/configs/model_config.yaml`; allow
`PAPERBANANA_MODEL_CONFIG` or `--model-config` to override it.

Never print, copy, or store API keys.

## Save outputs

Default outputs:

- Diagram: `final.png`, `run.json`
- Plot: `final.png`, `plot.py`, `run.json`

Write the manifest with `scripts/run_artifacts.py manifest`. Include the task, backend,
caption, selected reference IDs, final specification, parameters, warnings, and output
filenames. The script stores only a source hash, not the source text or credentials.
After the manifest succeeds, delete `retrieval.json`, temporary source copies,
intermediate descriptions, failed images, and temporary Plot code. Never perform this
cleanup after a failed image-generation call.
