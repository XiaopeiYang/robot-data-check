---
name: verify-finding
description: Verify a suspected data problem before calling it a defect. Use whenever a query, a check or the viewer shows something that looks wrong in a dataset, and always before writing a finding into docs/README or drafting an upstream issue.
---

# Verify a finding

A pattern in the data is not a defect until its cause is known. Many "problems" are
by design (e.g. failed DROID episodes carry no language annotation). Getting this wrong
in public costs more credibility than missing a finding.

Work through the steps in order and record the outcome in
`docs/findings/<dataset>.md` (one section per finding, use the template at the end).

## 1. Quantify

- How many episodes / frames are affected, out of how many? Give a percentage.
- Which dataset revision (commit sha) and which episode range?
- Write the query so anyone can re-run it against the `frames` / `episodes` / `tasks` views.

## 2. Cross-tabulate against labels

Before suspecting a bug, check whether the pattern lines up with something the dataset
already labels:

- `is_episode_successful` (or the dataset's success flag)
- site / operator columns (`building`, `collector_id`, ...)
- episode length, task, date / file chunk

If the pattern is (almost) entirely explained by a label, it is probably by design.
Compare with the dataset's own documentation (paper, dataset card, website).

Worked example: 20.9% of DROID episodes 0–999 have an empty task. Cross-tab: 163/164
failed episodes vs 46/836 successful ones. **By design**, not a defect. But DROID's docs
do not state the annotation policy, so the log says "inferred from labels" until a source
confirms it. Do not cite documentation you have not actually read.

## 3. Trace the source

For converted datasets, the defect can live in three places. Check them in this order
and cite file + line:

1. The conversion script (e.g. `huggingface/lerobot` `examples/port_datasets/port_droid.py`).
   Check the version on `main` and, if possible, the version used to produce the
   published revision.
2. The original source data (RLDS / raw files): does the problem already exist there?
3. The LeRobot writer / format itself.

Worked example: DROID `date == collector_id` in 1000/1000 episodes, but the current
script maps `date` from `m["date"]` correctly. Source unknown until the raw RLDS metadata
is checked. **Unconfirmed.**

## 4. Classify

Exactly one of:

- **defect**: cause located (file + line, or proven in the source data), not intended
- **by design**: explained by a label or documented behaviour; note what users should
  know ("failed episodes have no language annotation")
- **unconfirmed**: pattern is real, cause not yet located; list the next step
- **no issue found**: the suspected problem was checked for and is absent (worth
  logging: it tells readers what was ruled out)

Never write "bug" or "broken" for anything that is not a confirmed defect.

## 5. Before reporting upstream

- [ ] Status is **defect**
- [ ] For conversion findings: the original source data was checked, so the report can
      say where the problem starts ("the field exists in the source, line N maps it wrongly")
- [ ] Reproducible query + dataset revision included
- [ ] Right recipient: conversion script → LeRobot repo; source data → dataset authors;
      Hub copy only → the dataset's Hub discussion tab
- [ ] Impact stated in numbers, without exaggeration; suggested fix if known
- [ ] The user has read and approved the text (Claude never files issues on its own)

## Template

```markdown
### <short title>

- **Status:** defect | by design | unconfirmed | no issue found
- **Observed:** <what, how many, out of how many> (revision `<sha8>`, episodes <range>)
- **Query:**
  ```sql
  ...
  ```
- **Evidence:** <cross-tabs, code references with file:line, docs>
- **Meaning for users:** <what someone training on this data should know>
- **Next step:** <for unconfirmed / defect>
```
