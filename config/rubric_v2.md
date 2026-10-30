# Importance rubric v2 (frozen until after the eval)

Single source for the ranker prompt, the coverage-check scores and the relabel queue.

**Principle:** the score is the competitive impact on JFrog, not the size of the improvement or how dramatic the headline is. The item's type sets the default; substantive content can raise it (a patch fixing an actively exploited critical flaw is 3–4, not 1). Keywords never raise a score by themselves. Uncertainty doesn't raise a score: an unverifiable gap is not a 4.

| Score | Competitor | Industry | Shown in |
| --- | --- | --- | --- |
| 5 | Strategic move at significant scale against a JFrog core product (Artifactory, Xray, Curation) or its positioning; a material acquisition | A market-changing event (rare) | Brief |
| 4 | Material competitive change backed by evidence: a capability-level gap opened or closed, or a business/security event with direct competitive impact | A major event in JFrog's market: a broad supply-chain attack on a package or AI-tooling ecosystem, new regulation | Brief |
| 3 | Relevant development without a proven material change: improves an existing capability, a sub-feature, a partnership, a customer win, a security event with indirect impact | A relevant vulnerability or incident of limited scope | Brief |
| 2 | No new event, but intelligence value: marketing, opinion, listicle, buyer's guide that reveals positioning or strategy | Commentary and research | Competitor profile |
| 1 | A routine operational event: patch release, version support, maintenance, deprecation of a minor feature, a default/config change | — | Competitor timeline |
| Noise | Not relevant, or no intelligence value: stock chatter, VC-firm "Nexus", review-site pages, generic SEO content | same | Log only |

**Capability vs sub-feature (the 3-vs-4 line):** a capability is something a buyer's comparison checklist would list (secrets detection, reachability/contextual analysis, package firewall/curation, MCP registry). Management views, scan-frequency controls, performance, an extra integration or language are sub-features → 3, judged at capability level even when it's unknown whether JFrog has the exact sub-feature. Preview/beta lowers a step, except for a move against a JFrog core capability. GA of an existing preview = 3 by default.

**Anchors:**
- Amazon ECR replication backfill = 3 (improves an existing capability)
- GitHub package firewall, public preview = 5 (head-on vs a JFrog core product at GitHub's distribution scale; preview doesn't lower a core-capability move)
- "5 Best SCA Tools" vendor listicle = 2
- Cloudsmith Mumbai storage region = 3 (real product event, extends market reach)
- GitHub Enterprise includes Copilot = 3 (indirect impact, not proven; the platform-bundling trend belongs in insights)
- GitLab patch release 19.5.3 = 1
- GitLab vs SonarQube review-site page = Noise

Labels are base scores. The JFrog-mention bonus, snippet cap and tie-breaks are ranker-layer adjustments, not part of labels.
