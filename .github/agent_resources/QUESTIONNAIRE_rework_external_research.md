# Rework Research Questionnaire — Synapse

## Exact Current Technology Stack (Source-of-Truth Header)

### Backend / Bot / Data
- Python `>=3.12`
- discord.py `>=2.6.4`
- FastAPI `>=0.115.0`
- Uvicorn `>=0.34.0`
- SQLAlchemy `>=2.0.46`
- psycopg2-binary `>=2.9.11`
- Alembic `>=1.18.4`
- PyJWT `>=2.10.0`
- httpx `>=0.28.0`
- python-multipart `>=0.0.22`
- PostgreSQL `16` (`postgres:16-alpine` in Docker Compose)

### Frontend
- Svelte `^5.28.0`
- SvelteKit `^2.20.0`
- @sveltejs/adapter-node `^5.2.0`
- Vite `^6.3.0`
- TypeScript `^5.7.0`
- Tailwind CSS `^3.4.17`
- Chart.js `^4.4.9`

### Dev Quality Tooling
- pytest `>=9.0.2`
- Ruff `>=0.15.0`
- mypy `>=1.19.1`

### Runtime Topology (Docker Compose)
- `db` (PostgreSQL)
- `bot` (discord event collector/processor)
- `api` (FastAPI)
- `dashboard` (SvelteKit Node adapter)

---

## How to Use This Questionnaire

- Answer what you know now.
- Mark unknowns as `UNKNOWN`.
- For each uncertain answer, attach a source link or screenshot path if possible.
- If two answers conflict, prefer the one from official Discord docs or direct gateway behavior tests.

---

## Section 1 — Non-Negotiables (Must Know Without Doubt)

1. What exact categories of Discord events must be captured even if we never reward them?
2. What data fields are forbidden to persist (privacy, policy, legal, institutional rules)?
3. What is the required retention period for raw observed telemetry?
4. Is telemetry immutable in practice (append-only + no in-place edits), yes or no?
5. What is the acceptable convergence window for config/rule changes (e.g., seconds/minutes)?
6. Is eventual consistency acceptable for rewards and projections? If yes, what max delay is acceptable?
7. Which admin roles are allowed to create/modify reward rules vs. deploy schema/config changes?
8. What is the minimum anti-gaming baseline that must always remain active, even with custom rules?
9. Which decisions must be explainable/auditable to admins after the fact?
10. What is the rollback requirement for rules (point-in-time restore, version rollback, both)?
11. Are there data export/deletion obligations (e.g., for members leaving a guild)?
12. What is the worst-case tolerated data loss window (if any) for observed telemetry?
13. Must reward outcomes be replay-deterministic from event history + rule snapshots?
14. Are we allowed to rely on eventual recomputation, or must user-facing counters be instantly accurate?
15. Which environments matter most for this migration: local dev, single-server self-host, managed cloud?

---

## Section 2 — Discord Event Surface & Availability

16. Which Discord event families are currently exposed by discord.py for your target use cases?
17. For each desired event family, what fields are available at gateway time vs requiring REST fetch?
18. Do poll events expose enough structure to classify creation/votes/close reliably?
19. Are gift keyboard interactions visible in gateway events as actionable data?
20. Are sticker usages exposed uniformly across message contexts?
21. Can we reliably distinguish pasted image vs uploaded file vs link-embed?
22. How are forum post creation and forum reply represented differently in event payloads?
23. What is the reliable signal for “reply chain depth” in forum/thread contexts?
24. Are message edit and message delete events required in telemetry scope?
25. Do we need to capture reaction remove events for intent modeling, not just reaction add?
26. Do mentions need typed breakdown (user/role/channel/everyone/here)?
27. Is attachment MIME type always available and trustworthy from payloads?
28. Which voice state transitions are essential (join/leave/move/mute/deafen/stream/video)?
29. Should we capture presence/status events, or explicitly exclude as noise/privacy risk?
30. Which moderation/admin events should be captured in observed telemetry?
31. Which events are too noisy to capture by default but should remain toggleable?
32. Which interactions are currently impossible to capture with your chosen gateway intents?
33. What privileged intents are guaranteed enabled in your guild(s)?
34. If intents are disabled, what degraded capture behavior is acceptable?
35. Are crossposted announcements and webhooks in scope for telemetry?
36. Are bot-authored messages excluded, included, or classified separately?
37. Should interactions from integrations/automations be tracked distinctly from human users?
38. How should deleted users/messages/channels be represented in immutable history?
39. What timezone standard should timestamps use for all telemetry (UTC assumed?)
40. Should message content itself ever be stored, or only derived feature metadata?

---

## Section 3 — Observed Telemetry Model (Event Envelope)

41. What are mandatory envelope fields for every event (actor, subject, container, etc.)?
42. What schema versioning strategy should govern envelope evolution?
43. Should raw Discord payload fragments be stored alongside normalized fields?
44. Which IDs must remain native snowflakes vs string-normalized?
45. How do we represent unknown/missing fields without corrupting downstream logic?
46. What are required idempotency keys per event category?
47. How do we handle duplicate delivery from gateway reconnect scenarios?
48. How do we classify causal relationships (e.g., reaction targets message author)?
49. Should envelope include precomputed content features or defer to projection time?
50. Which fields belong in top-level columns vs JSON payload for queryability?
51. What indexing strategy is required for expected query patterns?
52. Which partitions (by date/guild/type) are required for long-term scalability?
53. Is schema migration frequency expected to be high? How strict is migration safety?
54. What’s the acceptable complexity limit for envelope (avoid turning into unbounded blob)?
55. Should we include rule-evaluation correlation IDs in event records?
56. Must envelopes include data provenance (gateway vs API fetch vs synthetic inference)?
57. Do we need integrity checksums/hashes for event records?
58. How should we model redactions without mutating original rows?
59. Is there a requirement for tenant isolation at DB level for multi-guild hosting?
60. Should event ordering guarantees be strict per channel/user/guild, or eventual only?

---

## Section 4 — Rule Firewall (Core Semantics)

61. What boolean grammar is required at launch (AND/OR/NOT/group nesting depth)?
62. Do we need “first match wins,” “accumulate all matches,” or both modes?
63. How should rule precedence be defined (priority number, scope specificity, recency)?
64. Must rule evaluation be deterministic with a complete trace of matched clauses?
65. Which action types are required at v1 (flat award, multiplier, fixed bonus, caps)?
66. Can multiple actions stack (flat + multiplier + fixed), and in what order?
67. Should rule actions support floors/ceilings and clamping behavior?
68. Do we need conditional cooldowns scoped by actor/channel/rule?
69. Must rules support channel type, category, channel ID, thread/forum subtype scopes?
70. Must rules support content feature predicates (has_url, has_code_block, attachments)?
71. Must rules support intent predicates (post, reply, reaction, mention, etc.)?
72. Do we need count-window predicates (e.g., replies in 24h) at launch?
73. Should rules allow user cohort predicates (role-based, tenure-based, trust-level)?
74. Are negative rewards/penalties allowed or disallowed?
75. Do we need simulation mode before publishing a rule set?
76. Do we need dry-run impact estimates before publishing changes?
77. Must rules be versioned and timestamped with actor identity?
78. Is rollback required at single-rule granularity or whole-ruleset snapshots?
79. Should archived/deactivated rules remain queryable/auditable forever?
80. Are rule side effects allowed beyond rewards (e.g., achievements triggers, alerts)?
81. Do we need global fallback default rule set if no custom rule matches?
82. Should admins be prevented from authoring impossible/conflicting rules?
83. How much validation should be static (save-time) vs runtime (evaluation-time)?
84. Do we need language-level restrictions to prevent “rule explosion” performance hits?
85. Is rule authoring intended for power users only, or guided for non-technical admins?

---

## Section 5 — Anti-Gaming & Abuse Resistance

86. Which abuse patterns are highest priority in your guild context?
87. What false-positive rate is acceptable for anti-gaming controls?
88. Should anti-gaming be hard baseline before rules, or configurable by admins?
89. Which anti-gaming controls are non-bypassable by custom rules?
90. What windows matter most (per minute/hour/day/week)?
91. Should reciprocal interaction loops be detected (A rewards B repeatedly)?
92. Should reply-chain farming be capped, and by what policy?
93. Should reaction farms be weighted by unique participants and account age?
94. Do we need trust scoring for users/channels to modulate rewards?
95. Should anti-gaming actions be transparent to admins and/or users?
96. Should anti-gaming suppress reward silently or log explicit reason codes?
97. Do we need quarantined event queues for suspicious interactions?
98. How should anti-gaming interact with manual awards and admin overrides?
99. Should anti-gaming be globally tunable or policy-profile based per guild?
100. What metrics define anti-gaming effectiveness after launch?

---

## Section 6 — Derived Projections (XP/Gold/Levels/Achievements)

101. Which derived entities must be replayable from telemetry + rules?
102. Which projections require near-real-time updates vs batch updates?
103. What acceptable staleness window per projection type?
104. Should projection recomputation be full replay or incremental snapshots?
105. How should projection checkpoints be versioned across rule changes?
106. What invariants must hold during replay (no double grants, deterministic ordering)?
107. Should achievements be event-sourced or state-sourced at evaluation time?
108. Is `max_earners` hard limit required immediately?
109. Should achievements support hidden/revealed states with audit trail?
110. Do season boundaries reset all projection counters or only selected ones?
111. What happens to historical leaderboards when rules change mid-season?
112. Should projection corrections be visible to admins (drift logs)?
113. Is eventual correction acceptable if displayed values are temporarily stale?
114. Must user-facing pages show “last updated” freshness indicator?
115. How should manual backfills interact with live ingestion to avoid race conditions?

---

## Section 7 — Performance, Scale, and SLOs

116. What are realistic expected event rates (avg/peak) per guild?
117. What write throughput must Postgres sustain at current and 12-month horizon?
118. What query latency targets matter for admin pages vs public pages?
119. How many guilds/tenants must one deployment support initially?
120. Do you need horizontal bot workers or single process is acceptable now?
121. What’s acceptable lag for cache invalidation propagation?
122. What batch sizes are acceptable for retention/backfill/reconciliation jobs?
123. Should heavy analytics run in OLTP DB or separate warehouse later?
124. Do we need partitioning now or later milestone trigger?
125. What are storage growth estimates for 30/90/365 day retention?
126. What is acceptable cost envelope for storage + compute?
127. What monitoring thresholds should trigger autoscaling or alerts?
128. How much downtime is acceptable for migrations and replays?
129. Is online migration required or short maintenance windows acceptable?
130. Do we need read replicas before rule firewall launch?

---

## Section 8 — Consistency, Concurrency, and Reliability

131. Which operations require strict transactional consistency?
132. Which flows can be eventually consistent with bounded delay?
133. How should duplicate event handling be guaranteed across reconnects/restarts?
134. What are expected failure modes: DB down, Discord outage, API timeout, partial writes?
135. Which retries must have hard caps and jitter policies?
136. Which operations should fail fast vs queue for later retry?
137. Is out-of-order event arrival acceptable, and how corrected?
138. Should projection updates be idempotent by design key?
139. How should long-running reconciliation coexist with live writes?
140. Do we need dead-letter queues for failed processing?
141. What operational runbook should exist for replay after incident?
142. Which correctness checks run continuously vs on-demand?
143. Is exactly-once processing required or at-least-once with idempotency acceptable?
144. What are alerting requirements for listener health and queue lag?
145. How to detect silent partial-failure states in capture pipeline?

---

## Section 9 — Privacy, Compliance, and Governance

146. What data classifications apply to Discord-derived fields (sensitive/public)?
147. Are you subject to FERPA/GDPR/CCPA/internal institutional policies?
148. What are member notification/consent requirements for telemetry capture?
149. Do you need per-field retention limits (e.g., delete payload details sooner)?
150. Should members be able to request data export/deletion?
151. Are minors involved, requiring stricter retention or visibility limits?
152. Which admin actions require immutable audit records?
153. How long must admin audit logs be retained?
154. Who can access raw telemetry vs derived summaries?
155. Do we need row-level security for multi-admin organizations?
156. Are there legal requirements around automated decision transparency?
157. Should anti-gaming flags be considered sensitive and role-restricted?
158. Are external processors/services allowed for media or analytics?
159. Should IP/user-agent be stored in admin logs, and for how long?
160. What incident response process is required for data mishandling?

---

## Section 10 — UI/UX for Rule Authoring and Explainability

161. Who is the primary admin persona (technical, semi-technical, non-technical)?
162. What complexity can UI expose without overwhelming admins?
163. Is visual rule-builder required, JSON editor optional, or both?
164. Should UI provide templates/presets for common guild policies?
165. Do you need side-by-side “before vs after” reward impact preview?
166. Should UI show real examples from telemetry that matched a rule?
167. How should conflicting rules be explained in UI?
168. Do you want linting/warnings for risky rules before publish?
169. Should UI support staging rules before activation?
170. Is approval workflow needed (draft -> review -> publish)?
171. Should every publish generate a changelog entry automatically?
172. How should rollback be presented to non-technical admins?
173. Which pages need freshness indicators due to eventual consistency?
174. How much explainability detail should end users see vs admins only?
175. Do you need “why no reward was given” traceability in user profile views?

---

## Section 11 — Data Operations & Migration Strategy

176. What historical data must be preserved through migration?
177. What can be dropped without business harm?
178. Is one-time backfill enough, or repeated replay expected during rollout?
179. Do we need dual-write period (old + new models) during transition?
180. What is cutover success definition (metrics + correctness checks)?
181. Which migrations are reversible vs one-way accepted?
182. What downtime window is acceptable for schema migration?
183. Should we seed baseline default rules to mirror current behavior exactly?
184. How do we validate parity between old reward outcomes and new evaluator?
185. What acceptance dataset should be used for parity testing?
186. Which legacy tables/columns will be deprecated and when?
187. What archival strategy for deprecated data/models?
188. How should rollout be phased by feature area (capture first, then rules, then UI)?
189. What are rollback triggers during migration?
190. Who signs off each migration phase (technical + product owner)?

---

## Section 12 — Testing, Verification, and Observability

191. What must be unit-tested vs integration-tested vs replay-tested?
192. Do we need golden datasets for deterministic rule evaluation tests?
193. What contract tests are required between dashboard and API rule schemas?
194. Should we add synthetic load tests before enabling broad capture?
195. What key telemetry metrics should be in dashboards (ingest rate, lag, duplicates)?
196. What event loss detection mechanism is required?
197. How will you verify no reward drift after rule changes?
198. Which alerts are critical (capture stopped, queue lag, replay failures)?
199. Do we need distributed tracing IDs across bot/api/projection flows?
200. How should admin-facing logs distinguish capture errors vs rule errors?
201. Which health endpoints are required and what must each report?
202. What should be included in post-deploy verification checklist?
203. Do we need canary guild rollout before global rollout?
204. What minimum monitoring window before declaring a phase stable?
205. What evidence constitutes “ready for next phase” in the tracker?

---

## Section 13 — Strategic Product Questions

206. What differentiates Synapse from simpler bots in one sentence?
207. Which 3 capabilities must be undeniably better after rework?
208. What should remain intentionally simple despite architecture flexibility?
209. What should admins never be allowed to customize?
210. Where is the line between platform flexibility and unsafe complexity?
211. What is the first “wow” workflow for your student club after migration?
212. What do you want admins to do in 5 minutes on day 1?
213. What do you want power admins to do in 30 minutes on day 30?
214. What failure would make this migration feel not worth it?
215. What proof would make you confident the strategy succeeded?

---

## Section 14 — External Research Requests (Bring Back Evidence)

Please gather references/examples for:

216. Discord gateway/event coverage matrix for target interaction types.
217. Best practices for event-envelope schema versioning in Postgres JSONB systems.
218. Rule engine patterns for deterministic evaluation + explainability.
219. Anti-gaming heuristics for community systems (forum/reply/reaction abuse).
220. Replayable projection architectures (event sourcing style) in Python/Postgres stacks.
221. Partitioning + retention strategies for append-only telemetry tables in Postgres 16.
222. Practical eventual-consistency UX patterns (freshness indicators, user trust).
223. Migration playbooks for moving from hardcoded logic to rules DSL.
224. Auditable rule lifecycle design (draft/publish/version/rollback).
225. Data minimization/privacy patterns for community telemetry platforms.

---

## Fast-Start Response Template (Optional)

Use this lightweight format to answer quickly:

- **Q#**: 
- **Answer**:
- **Confidence**: High / Medium / Low
- **Source**:
- **Notes / Follow-up Needed**:
