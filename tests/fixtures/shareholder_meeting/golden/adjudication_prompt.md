# Shareholder-meeting golden adjudication prompt

Review the complete external and internal KIND HTML pair for one receipt. Treat those
two byte-for-byte files as the only source of truth. Do not use a parser's current
output as the answer and do not infer a person, organization, role, action, outcome,
or transaction that the selected source fields do not state explicitly.

Record:

1. the disclosure mode and phase;
2. the important agenda boundaries and result polarity;
3. explicitly named people and organizations;
4. positive entity relationships, including their direction and decisive attributes;
5. negative boundaries that must not become entities or relationships; and
6. any disagreement between the source reading and the current deterministic parser.

Apply the shareholder-meeting contract's phase safety rules. A notice may describe a
candidate or agenda subject but must not assert an active election, removal, or
resignation. A result may assert those active facts only for a passed agenda. Preserve
shareholder-proposal and stock-option-grant agendas, but do not extract proposers or
individual stock-option beneficiaries as entities or relationships. Electronic-voting
instructions remain source text only; do not extract voting managers or named system
providers. Do not entityize unnamed roles, compensation-limit phrases, generic merger
parties, dates, group suffixes, or negated/cancelled actions.

Return a concise case decision with positive labels, negative boundaries, rationale,
disagreements, and resolution. A reviewer must approve the stored decision before it
becomes a golden assertion. The resulting fixture is executed without any runtime LLM
or network dependency.
