# Rebuild XLIFF Targets From Translation Results

## Use When

- approved translations need to be merged back into XLIFF
- you need updated XLIFF content for downstream CAT or QA workflows

## Inputs

- source file name
- original XLIFF content
- translation JSON containing `unitId` or `segNumber`

## Recommended MCP Tools

- `replace_xliff_targets`
- `diff_xliff_report`

## Workflow

1. Confirm the original XLIFF content is available.
2. Confirm the translation payload includes `aiResult` or `mtResult`.
3. Merge the translations back into the original XLIFF. Keep each source segment's inline tags in its translation: a translation whose tags differ is skipped, not written, unless `require_tags` is false. Tag order may change; tags the source does not have are escaped as text.
4. Report the replacement count.
5. Read `skipped_units` (each entry names the unit and one of `tags_mismatch`, `unit_not_found`, `empty_translation`, `duplicate_target`) and the `diff_report` returned by `replace_xliff_targets`, or call `diff_xliff_report` with the original and filled content, and call out every issue: differing unit count, ids, source bytes, unit attributes, target state, or inline tags.
6. Call out any unmatched or untranslated units.

## Expected Output

- updated XLIFF content
- replacement count
- diff report issues (tags, ids, count, state)
- unmatched unit summary if any
