# JFrog capability sheet

What JFrog sells on each head-to-head axis, from official JFrog pages, as of 30 Oct 2026. Use it to decide the 3-vs-4 line: does a competitor's move close a gap, open one, or just improve something both already have? Anything not confirmed is marked unverified.

**Naming changes:** JFrog AI Catalog is now "JFrog AI Security"; "MCP Gateway" is now "Agent Guard"; JFrog Pipelines (its own CI) reached end of life on 1 May 2026.

## Scoring rule

| Score | Competitor | Industry |
| --- | --- | --- |
| 5 | Strategic move at significant scale against Artifactory, Xray or Curation, or a material acquisition | Market-changing event (rare) |
| 4 | Material change with evidence: gains a capability listed below for the first time (closes) or one JFrog lacks (opens); or a business/security event with direct impact | Major event in JFrog's market: broad supply-chain attack on a package or AI-tooling ecosystem, new regulation |
| 3 | Improves an existing capability or adds a sub-feature, partnership, customer win, security event with indirect impact | Relevant vulnerability or incident of limited scope |
| 2 | No new event, but intelligence value: marketing, opinion, listicle that reveals positioning | Commentary, research |
| 1 | Routine operational event: patch release, version support, maintenance, small change | — |
| Noise | Not relevant, or no intelligence value | same |

Type sets the default; content can raise it (a patch fixing an actively exploited critical flaw is 3–4). Rubric v2, frozen until after the eval (D29).

**Capability or sub-feature?** A capability has its own named line in the table below (secrets detection, Contextual Analysis, Curation, MCP Registry). Ask: would a buyer's comparison checklist list it? Is it GA, or only preview/beta (preview lowers a step unless it's a core capability)? Don't leave a label provisional because a JFrog sub-feature is unknown: judge at capability level. Example: Snyk adds a secrets inventory and scan-frequency controls → 3 (both already offer secrets detection; inventory and frequency are management sub-features).

## Capabilities by axis

**Last verified:** every entry below was checked against its source on 30 Oct 2026. **Availability status** as stated by JFrog: Zero-Touch Remediation GA (Sept 2026); Skills repositories beta; Xray, AI Catalog, Advanced Security and AppTrust federation planned (no date); Pipelines end of life (May 2026); Agent Guard covered MCP servers only as of Jul 2026, with skills and plugins "coming". Where no status is given, the source didn't state GA or beta. Labels are judged at capability level; a sub-feature-level baseline maintained by product experts is future work.

| Axis | What JFrog offers | Tier / add-on |
| --- | --- | --- |
| Deployment | SaaS (direct or AWS/Azure/GCP marketplaces), self-hosted, hybrid. Platform Federation links sites peer-to-peer (Projects and Curation federation today; Xray, AI Catalog, Advanced Security, AppTrust federation planned). Federated repositories for every package type except Terraform backend. Distribution to Edge nodes, air-gapped supported | SaaS and self-hosted core; HA and federation from Enterprise X; multi-site federation and Distribution Enterprise+ |
| Package coverage | 62 package types in one universal repository manager: Docker, OCI, Helm, Maven, npm, PyPI, uv, Go, Cargo, Conan, NuGet, Terraform, OpenTofu, Generic, WASM. AI types: Hugging Face, ML repositories, Nvidia, Skills (beta), Agent Plugins, APM, Claude, Cursor/Kiro/VS Code extensions, JetBrains plugins. APM Registry (Sept 2026) for prompts, skills and MCP servers | Core in every tier; some AI types need the security bundles |
| Security scanning | Xray: SCA and licenses across \~15 languages plus Docker/OCI, Helm and ML models, incl. malicious packages and models. Advanced Security: Contextual Analysis (is the CVE actually applicable), secrets detection, IaC scanning, SAST, Smart Remediation / AutoPR. Runtime: is vulnerable code loaded in memory. Zero-Touch Remediation (GA Sept 2026): automatic patches via partners (Chainguard, Broadcom, Echo, IBM/Red Hat, Moderne, TuxCare, Seal). Frogbot opens fix PRs on GitHub | Xray not in cloud Pro, included from Pro X / Enterprise X; Advanced Security paid add-on (Enterprise X+); Runtime Impact Enterprise+ |
| Curation / gating | "Package firewall": blocks malicious, vulnerable, license-violating and immature packages (default 14-day hold), serves the next compliant version, waivers, full audit log. Also covers Hugging Face and NVIDIA NIM models, IDE extensions, agents via JFrog's MCP server. Curation Federation across sites. Traffic Controller (Sept 2026) blocks direct registry calls at the network layer with Cloudflare, Netskope, Zscaler | Enterprise X and up, and the security bundles; full ecosystem list unverified |
| AI & MCP | MCP Registry (Mar 2026): approved MCP servers for Claude Code, Cursor, VS Code. Agent Guard: agents reach only approved MCP servers; IDE hook blocks bypasses; device lock via Jamf/Intune/Kandji; skills and plugins "coming" as of Jul 2026. AI asset and Skills scanning (Sept 2026). Shadow AI detection. Agent Plugin (Claude Code, Cursor, Codex, Copilot, Kiro), Agent Package Resolution, Agent Plugins Registry. JFrog ML: model serving, feature store, Hugging Face remotes, NIM allow-list | AI Security in Ultimate Security (Enterprise+); MLOps bundles separate; Agent Guard pricing unverified |
| CI/CD integration | No own CI since Pipelines ended (May 2026). Integrations: GitHub Actions (setup-jfrog-cli, OIDC), Jenkins, GitLab templates, Azure DevOps, Bitbucket, Bamboo. Build-info. Release Bundles v2 with signed promotion and Xray gates. AppTrust: signed evidence, policy-as-code (Rego), EU CRA / DORA / NIST SSDF / CERT-In packs, Prompt-to-Release Traceability | Build-info and plugins core; Distribution and AppTrust Enterprise+ |
| Pricing model | Cloud: Pro $50/mo promo ($150 list, 25 GB), Enterprise X from $950/mo (125 GB), Enterprise+ custom; overage $1.25–$0.33/GB. Self-hosted: Pro X from $27k/yr, Enterprise X from $51k/yr, Enterprise+ custom. Security bundles: Unified, Ultimate (Enterprise+). Free tier: 5 users, 2 GB storage, 5 GB transfer, basic NVD scanning | Pricing taken from the French page (English one unreachable); last bundle details may be missing |

## Worked examples

| Hypothetical announcement | Verdict | JFrog reference point |
| --- | --- | --- |
| GitHub adds a package firewall blocking malicious npm/PyPI at install | Closes gap | Curation |
| Amazon ECR adds replication backfill | Incremental | Federated repos, Platform Federation, Edge |
| Snyk adds reachability for Python | Incremental, or closes gap if new to Snyk | Advanced Security Contextual Analysis |
| Sonatype adds an MCP server registry with allow-lists | Closes gap | MCP Registry and Agent Guard |
| A competitor scans agent skills/plugins with LLM checks | Closes gap | Skills Scanning (Sept 2026) |
| GitLab ships built-in CI with signed promotion | Opens gap (CI only) | JFrog has no own CI since Pipelines ended |
| Automatic backported CVE patches without version bumps | Closes gap | Zero-Touch Remediation |
| Ready-made EU CRA / DORA policy packs | Closes gap | AppTrust compliance frameworks |
| Native Hugging Face proxy and caching | Incremental | Hugging Face repositories + Curation |
| A permanent free tier with 10 GB and SCA | Opens gap (pricing) | JFrog free tier: 2 GB, basic scanning |

## Sources

- [Pricing (French page)](https://jfrog.com/fr/pricing/) · [Start free](https://jfrog.com/start-free/cloud)
- [Platform Federation blog](https://jfrog.com/blog/platform-federation-syncs-multisite-development) · [Federated package types](https://docs.jfrog.com/artifactory/docs/federated-repository-supported-package-types) · [Edge nodes](https://docs.jfrog.com/setup/docs/complete-the-sdlc-release-bundles-edge-nodes-build-integration)
- [Supported package types](https://docs.jfrog.com/artifactory/docs/supported-package-types)
- [Xray supported technologies](https://docs.jfrog.com/security/docs/supported-technologies-catalog) · [Advanced Security](https://docs.jfrog.com/security/docs/advanced-security) · [DevOps-native security](https://jfrog.com/devops-native-security/) · [Zero-Touch Remediation](https://jfrog.com/press-room/jfrog-introduces-zero-touch-remediation-to-its-self-healing-software-supply-chain-broadening-its-footprint-through-secure-open-source-partnerships/) · [Frogbot / GitHub](https://jfrog.com/blog/jfrog-github-integration-technical-details)
- [Curation](https://jfrog.com/curation/) · [Block malicious packages](https://docs.jfrog.com/security/docs/part-3-block-malicious-packages)
- [MCP Registry (BusinessWire)](https://www.businesswire.com/news/home/20260318132919/en/) · [Agent Guard](https://jfrog.com/blog/agent-guard-control-ai-assets-before-they-become-shadow-ai/) · [AI Security](https://jfrog.com/ai-catalog/) · [swampUP 2026 press](https://jfrog.com/ja/press-room/jfrog-embeds-security-into-the-agentic-workforce/) · [swampUP recap](https://jfrog.com/blog/swampup-2026-recap-single-source-of-truth-agentic-software-supply-chain/) · [JFrog ML release notes](https://docs.jfrog.com/releases/docs/jfrog-ml-release-notes-2026)
- [Pipelines end of life](https://docs.jfrog.com/releases/docs/pipeline-deprecation-end-of-life) · [Jenkins plugin](https://docs.jfrog.com/integrations/docs/jenkins-jfrog-plugin) · [AppTrust](https://jfrog.com/apptrust/)
