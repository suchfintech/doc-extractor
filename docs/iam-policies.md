# IAM policies — consumer-role boundary

## 1. What this doc is

`doc-extractor` reads from `s3://golden-mountain-storage` (raw source
documents) and reads + writes `s3://golden-mountain-analysis` (extraction
outputs). The analysis bucket has two functionally-distinct prefixes that
look identical at the IAM level but carry very different sensitivity:

| Prefix                            | Purpose                            | Consumer access |
|-----------------------------------|------------------------------------|-----------------|
| `s3://.../<doc>.md`               | Canonical extracted Markdown       | **Allow** (this is the product) |
| `s3://.../corrections/<doc>.md`   | Human override layer (Story 6.1)   | **Allow** (consumers prefer this over canonical) |
| `s3://.../disagreements/<key>.json` | Forensic queue: raw model responses + verifier audit (Story 3.9 / Decision 1) | **Deny** |

The disagreements prefix exists so a human reviewer can replay the exact
provider conversation that produced a low-confidence extraction. Each
entry inlines `primary_raw_response_text` and `verifier_raw_response_text`
verbatim — these are model outputs that may include partial PII (names,
account numbers, DOBs visible on the source image) before
post-processing.

**Consumer roles must not see this prefix.** Reviewers run with elevated
credentials; consumer pipelines (cny-flow loader, compliance daemon, the
Kei chatbot) must be denied even read access so an accidental log-leak or
prompt-injection cannot exfiltrate raw model output.

## 2. The Deny rule

Attach this statement to every consumer role's IAM policy. It pairs with
whatever `Allow s3:GetObject` rule the role already has on the analysis
bucket — explicit `Deny` overrides any `Allow`, so the broader access
stays intact for the canonical / corrections paths.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::golden-mountain-analysis/disagreements/*"
    }
  ]
}
```

If the role also has any list-level access, deny those too:

```json
{
  "Effect": "Deny",
  "Action": ["s3:ListBucket"],
  "Resource": "arn:aws:s3:::golden-mountain-analysis",
  "Condition": {
    "StringLike": {"s3:prefix": ["disagreements/*", "disagreements"]}
  }
}
```

The list-deny is optional but cheap — it prevents enumeration of which
documents had disagreements (which is itself a weak signal).

## 3. Which consumer roles need this rule

The following roles read from the analysis bucket and **must** carry the
Deny statement:

- **`cny-flow-loader`** — the merlin cny-flow ingest pipeline that reads
  extracted PaymentReceipt frontmatter to build the daily transaction
  graph.
- **`daily-report-runtime`** — the merlin compliance-daemon CronJob role
  on the neptune-pipeline cluster that generates the per-customer
  daily-summary reports.
- **`kei-chatbot`** *(post-rebuild)* — the Slack-attached chat agent that
  answers analyst questions over the corpus. Currently being rebuilt;
  the new role must include the Deny statement from day one.
- **Any future Slack-callable agent skill** — same reasoning. If you are
  adding a new role that touches `golden-mountain-analysis`, default to
  including this Deny unless you have an explicit human-reviewer-only
  use case.

The roles that **may** read `disagreements/*`:

- The reviewer's personal IAM user (Yang).
- A future dedicated `disagreement-reviewer` role, if/when forensic
  review is automated (currently human-only).
- The CI runner's eval role, **only** for test fixtures under a
  `tests/` subprefix if that arrangement is ever introduced — not the
  case today.

## 4. Cross-reference

The disagreements forensic-payload model is defined in the architecture
under **Decision 1 — Disagreement-Queue Location & Forensic Payload**
(`_bmad-output/planning-artifacts/architecture.md` §Decision 1). That
decision establishes:

- `disagreements/<source_key>.json` is the path layout.
- Raw responses are inlined (not stored separately) because v1 has only
  human-review consumers.
- The forensic payload is durable (S3 versioning) and never overwritten.

This IAM doc is the **consumer-side enforcement** of that decision — the
storage layer captures the data, and the IAM layer ensures only
authorised eyes can read it.

See also: NFR9 (bucket access scoping) and Story 3.9 (the
`record_disagreement` writer that produces these files).

## 5. Implementation TODO

The actual policy file lives in the `homelab` infra repo, not here. This
doc is the design record; the operational rollout is tracked separately:

- [ ] Land the `Deny` statement in
      `homelab/clusters/neptune/iam/<role>.policy.json` (or equivalent
      path for whichever IAM tooling owns each role) for each of the
      consumer roles in §3.
- [ ] Confirm the deny applies via an explicit test: assume the role
      and run `aws s3 cp s3://golden-mountain-analysis/disagreements/<some-real-key>.json -`
      — it must return `AccessDenied`, not the JSON body.
- [ ] Add the same explicit test to the role's CI lint so a future
      role-policy edit can't silently regress.
- [ ] Once Kei is rebuilt, ensure the new chatbot role inherits the Deny
      from a shared base policy rather than having it added ad-hoc.
