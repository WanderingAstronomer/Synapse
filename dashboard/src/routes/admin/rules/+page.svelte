<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		type RewardRuleRow,
		type RuleSnapshotRow,
		type RuleTaxonomy,
		type RuleDryRunResult,
		type RuleEvaluationRow,
		type ProjectionStatusResponse,
		type RulePredicate,
		type RuleOutcome,
	} from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';

	// ---------------------------------------------------------------------------
	// Zone tabs
	// ---------------------------------------------------------------------------
	type Zone = 'canvas' | 'lab' | 'taxonomy' | 'projections';
	const ZONE_LABELS: Record<Zone, string> = {
		canvas: 'Rule Canvas',
		lab: 'Laboratory',
		taxonomy: 'Taxonomy',
		projections: 'Projections',
	};
	let activeZone = $state<Zone>('canvas');
	let loading = $state(true);

	// ---------------------------------------------------------------------------
	// Zone A — Rule Canvas state
	// ---------------------------------------------------------------------------
	let rules = $state<RewardRuleRow[]>([]);
	let snapshots = $state<RuleSnapshotRow[]>([]);
	let taxonomy = $state<RuleTaxonomy | null>(null);

	// Editor state
	let showEditor = $state(false);
	let editingRule = $state<RewardRuleRow | null>(null);
	let formName = $state('');
	let formPriority = $state(50);
	let formIsActive = $state(true);
	let formPredicates = $state<RulePredicate[]>([]);
	let formOutcomes = $state<RuleOutcome[]>([]);
	let saving = $state(false);
	let searchQuery = $state('');

	// Delete confirm
	let confirmDeleteId = $state<number | null>(null);

	// ---------------------------------------------------------------------------
	// Zone B — Laboratory state
	// ---------------------------------------------------------------------------
	let labEventType = $state('MESSAGE');
	let labUserId = $state('');
	let labChannelId = $state('');
	let labContext = $state<Record<string, number>>({
		messages_today: 10,
		reactions_today: 5,
		voice_minutes_today: 0,
		user_level: 1,
		user_xp: 0,
	});
	let labResult = $state<RuleDryRunResult | null>(null);
	let labRunning = $state(false);
	let labRuleIds = $state<number[]>([]);

	// ---------------------------------------------------------------------------
	// Zone C — Taxonomy state (served from taxonomy endpoint)
	// ---------------------------------------------------------------------------

	// ---------------------------------------------------------------------------
	// Zone D — Projections state
	// ---------------------------------------------------------------------------
	let projectionStatus = $state<ProjectionStatusResponse | null>(null);
	let evaluations = $state<RuleEvaluationRow[]>([]);
	let evalPage = $state(1);
	let evalTotal = $state(0);

	// ---------------------------------------------------------------------------
	// Data loading
	// ---------------------------------------------------------------------------
	async function load() {
		try {
			const [rulesRes, snapshotsRes, taxonomyRes] = await Promise.all([
				api.admin.getRules(),
				api.admin.getSnapshots(),
				api.admin.getTaxonomy(),
			]);
			rules = rulesRes.rules;
			snapshots = snapshotsRes.snapshots;
			taxonomy = taxonomyRes;
		} catch (e: any) {
			flash.error(e.message || 'Failed to load rules data');
		} finally {
			loading = false;
		}
	}

	async function loadProjections() {
		try {
			const [statusRes, evalsRes] = await Promise.all([
				api.admin.getProjectionStatus(),
				api.admin.getEvaluations({ page: evalPage, page_size: 25 }),
			]);
			projectionStatus = statusRes;
			evaluations = evalsRes.evaluations;
			evalTotal = evalsRes.total;
		} catch (e: any) {
			flash.error(e.message || 'Failed to load projections');
		}
	}

	onMount(() => { load(); });

	// Auto-load projections when switching to that tab
	$effect(() => {
		if (activeZone === 'projections') {
			loadProjections();
		}
	});

	// ---------------------------------------------------------------------------
	// Zone A — Rule Canvas actions
	// ---------------------------------------------------------------------------
	function openNewRule() {
		editingRule = null;
		formName = '';
		formPriority = 50;
		formIsActive = true;
		formPredicates = [];
		formOutcomes = [];
		showEditor = true;
	}

	function openEditRule(rule: RewardRuleRow) {
		editingRule = rule;
		formName = rule.name;
		formPriority = rule.priority;
		formIsActive = rule.is_active;
		formPredicates = [...rule.predicates.map(p => ({ ...p }))];
		formOutcomes = [...rule.outcomes.map(o => ({
			...o,
			scaling: o.scaling ? { ...o.scaling } : undefined,
		}))];
		showEditor = true;
	}

	function addPredicate() {
		formPredicates = [...formPredicates, { field: 'event_type', op: '==', value: 'MESSAGE' }];
	}

	function removePredicate(idx: number) {
		formPredicates = formPredicates.filter((_, i) => i !== idx);
	}

	function addOutcome() {
		formOutcomes = [...formOutcomes, { type: 'xp', base_value: 10 }];
	}

	function removeOutcome(idx: number) {
		formOutcomes = formOutcomes.filter((_, i) => i !== idx);
	}

	async function saveRule() {
		saving = true;
		try {
			if (editingRule) {
				await api.admin.updateRule(editingRule.id, {
					name: formName,
					priority: formPriority,
					is_active: formIsActive,
					predicates: formPredicates,
					outcomes: formOutcomes,
				});
				flash.success('Rule updated');
			} else {
				await api.admin.createRule({
					name: formName,
					priority: formPriority,
					is_active: formIsActive,
					predicates: formPredicates,
					outcomes: formOutcomes,
				});
				flash.success('Rule created');
			}
			showEditor = false;
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Failed to save rule');
		} finally {
			saving = false;
		}
	}

	async function deleteRule(id: number) {
		try {
			await api.admin.deleteRule(id);
			flash.success('Rule deleted');
			confirmDeleteId = null;
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Failed to delete rule');
		}
	}

	async function toggleRule(rule: RewardRuleRow) {
		try {
			await api.admin.updateRule(rule.id, { is_active: !rule.is_active });
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Failed to toggle rule');
		}
	}

	async function publishSnapshot() {
		try {
			await api.admin.publishSnapshot();
			flash.success('Snapshot published');
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Failed to publish snapshot');
		}
	}

	// ---------------------------------------------------------------------------
	// Zone B — Laboratory actions
	// ---------------------------------------------------------------------------
	async function runSimulation() {
		labRunning = true;
		labResult = null;
		try {
			const parsedUserId = labUserId.trim()
				? Number.parseInt(labUserId.trim(), 10)
				: undefined;
			if (parsedUserId !== undefined && Number.isNaN(parsedUserId)) {
				flash.warning('User ID must be numeric');
				return;
			}

			const parsedChannelId = labChannelId.trim()
				? Number.parseInt(labChannelId.trim(), 10)
				: undefined;
			if (parsedChannelId !== undefined && Number.isNaN(parsedChannelId)) {
				flash.warning('Channel ID must be numeric');
				return;
			}

			const result = await api.admin.testRule({
				event_type: labEventType,
				user_id: parsedUserId,
				channel_id: parsedChannelId,
				context: labContext,
				rule_ids: labRuleIds.length > 0 ? labRuleIds : undefined,
			});
			labResult = result;
		} catch (e: any) {
			flash.error(e.message || 'Simulation failed');
		} finally {
			labRunning = false;
		}
	}

	function createRuleForEventType(eventType: string) {
		openNewRule();
		formPredicates = [{ field: 'event_type', op: '==', value: eventType }];
		formName = `Rule for ${eventType}`;
		activeZone = 'canvas';
	}

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------
	let filteredRules = $derived(
		searchQuery
			? rules.filter(r => r.name.toLowerCase().includes(searchQuery.toLowerCase()))
			: rules
	);

	function outcomeLabel(o: RuleOutcome): string {
		if (o.type === 'achievement') return `Achievement: ${o.template_name || o.template_id || '?'}`;
		const base = `${o.type.toUpperCase()} ${o.base_value ?? 0}`;
		if (o.scaling) return `${base} (${o.scaling.curve} on ${o.scaling.variable})`;
		return base;
	}

	function predicateLabel(p: RulePredicate): string {
		return `${p.field} ${p.op} ${JSON.stringify(p.value)}`;
	}

	// Sparkline generator for scaling curve preview
	function sparklinePath(curve: string, variable: string, factor: number = 1, base: number = 10, thresholds: Record<string,number> = {}): string {
		const points: number[] = [];
		for (let n = 1; n <= 50; n++) {
			let y = 0;
			if (curve === 'linear') y = n * factor;
			else if (curve === 'logarithmic') y = Math.log(Math.max(1, n)) / Math.log(base) * factor;
			else if (curve === 'exponential') y = Math.pow(n, factor);
			else if (curve === 'step') {
				let mult = 1;
				for (const [t, m] of Object.entries(thresholds).sort((a,b) => parseInt(a[0]) - parseInt(b[0]))) {
					if (n >= parseInt(t)) mult = m;
				}
				y = mult;
			}
			points.push(y);
		}
		const maxY = Math.max(...points, 1);
		return points.map((y, i) => `${(i / 49) * 120},${40 - (y / maxY) * 36}`).join(' ');
	}
</script>

<svelte:head>
	<title>Rule Engine — Synapse Admin</title>
</svelte:head>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold text-white">Rule Engine</h1>
			<p class="text-sm text-surface-400 mt-1">Build, test, and monitor reward rules</p>
		</div>
	</div>

	<!-- Zone Tabs -->
	<div class="flex gap-1 border-b border-surface-400/20 pb-px">
		{#each Object.entries(ZONE_LABELS) as [zone, label]}
			<button
				class="px-4 py-2 text-sm font-medium rounded-t-lg transition-colors
					{activeZone === zone ? 'bg-surface-300/30 text-brand-400 border-b-2 border-brand-400' : 'text-surface-400 hover:text-white hover:bg-surface-400/10'}"
				onclick={() => activeZone = zone as Zone}
			>{label}</button>
		{/each}
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-20">
			<div class="animate-spin h-8 w-8 border-2 border-brand-400 border-t-transparent rounded-full"></div>
		</div>

	<!-- ================================================================ -->
	<!-- ZONE A — Rule Canvas                                             -->
	<!-- ================================================================ -->
	{:else if activeZone === 'canvas'}
		<div class="space-y-4">
			<!-- Toolbar -->
			<div class="flex items-center gap-3 flex-wrap">
				<input
					type="text"
					class="input flex-1 min-w-[200px]"
					placeholder="Search rules..."
					bind:value={searchQuery}
				/>
				<button class="btn-primary" onclick={openNewRule}>+ New Rule</button>
				<button
					class="btn-secondary"
					onclick={publishSnapshot}
					title="Snapshot current active rules"
				>Publish Snapshot</button>
			</div>

			<!-- Rules Table -->
			{#if filteredRules.length === 0}
				<EmptyState
					title="No rules found"
					description={searchQuery ? 'No rules match your search' : 'No reward rules yet'}
				/>
			{:else}
				<div class="space-y-2">
					{#each filteredRules as rule (rule.id)}
						<div class="card p-4 flex items-start gap-4">
							<!-- Toggle -->
							<button
								class="mt-1 w-10 h-5 rounded-full transition-colors {rule.is_active ? 'bg-green-500' : 'bg-surface-400/40'}"
								onclick={() => toggleRule(rule)}
								title={rule.is_active ? 'Active — click to disable' : 'Disabled — click to enable'}
							>
								<div class="w-4 h-4 rounded-full bg-white transition-transform {rule.is_active ? 'translate-x-5' : 'translate-x-0.5'}"></div>
							</button>

							<!-- Main content -->
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<span class="font-semibold text-white">{rule.name}</span>
									<span class="text-xs px-2 py-0.5 rounded bg-surface-300/40 text-surface-400">
										Priority {rule.priority}
									</span>
									{#if !rule.is_active}
										<span class="text-xs px-2 py-0.5 rounded bg-red-500/20 text-red-400">Disabled</span>
									{/if}
								</div>

								<!-- Predicates -->
								{#if rule.predicates.length > 0}
									<div class="mt-1 flex flex-wrap gap-1">
										{#each rule.predicates as pred}
											<span class="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
												{predicateLabel(pred)}
											</span>
										{/each}
									</div>
								{:else}
									<span class="text-xs text-surface-400 mt-1">Catch-all (no predicates)</span>
								{/if}

								<!-- Outcomes -->
								<div class="mt-1 flex flex-wrap gap-1">
									{#each rule.outcomes as outcome}
										<span class="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20">
											{outcomeLabel(outcome)}
										</span>
										{#if outcome.scaling}
											<svg class="inline-block ml-1" width="60" height="20" viewBox="0 0 120 40">
												<polyline
													points={sparklinePath(outcome.scaling.curve, outcome.scaling.variable, outcome.scaling.factor, outcome.scaling.base, outcome.scaling.thresholds)}
													fill="none" stroke="#7c3aed" stroke-width="2"
												/>
											</svg>
										{/if}
									{/each}
								</div>
							</div>

							<!-- Actions -->
							<div class="flex gap-2 shrink-0">
								<button class="btn-secondary text-sm px-3 py-1" onclick={() => openEditRule(rule)}>Edit</button>
								<button class="text-sm px-3 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20" onclick={() => confirmDeleteId = rule.id}>Delete</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			<!-- Snapshot History -->
			{#if snapshots.length > 0}
				<div class="mt-6">
					<h3 class="text-lg font-semibold text-white mb-3">Snapshot History</h3>
					<div class="space-y-1">
						{#each snapshots as snap (snap.id)}
							<div class="card p-3 flex items-center gap-3 text-sm">
								<span class="font-mono text-brand-400">v{snap.version}</span>
								<span class="text-surface-400">{snap.rules_count} rules</span>
								{#if snap.is_active}
									<span class="px-2 py-0.5 rounded bg-green-500/20 text-green-400 text-xs">Active</span>
								{/if}
								<span class="text-surface-400 ml-auto">{snap.published_at ? new Date(snap.published_at).toLocaleString() : ''}</span>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<!-- Rule Editor Modal -->
		{#if showEditor}
			<div class="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 flex items-start justify-center pt-10 overflow-y-auto">
				<div class="card p-6 w-full max-w-2xl mx-4 my-8 space-y-4">
					<h2 class="text-xl font-bold text-white">{editingRule ? 'Edit Rule' : 'New Rule'}</h2>

					<!-- Name & Priority -->
					<div class="grid grid-cols-2 gap-4">
						<div>
							<label class="label" for="rule-form-name">Name</label>
							<input id="rule-form-name" type="text" class="input w-full" bind:value={formName} placeholder="e.g. Bonus for long messages" />
						</div>
						<div>
							<label class="label" for="rule-form-priority">Priority</label>
							<input id="rule-form-priority" type="number" class="input w-full" bind:value={formPriority} min="1" max="1000" />
							<p class="text-xs text-zinc-500 mt-1">Range: 1–1000. Higher values are evaluated first.</p>
						</div>
					</div>

					<label class="flex items-center gap-2 text-sm text-surface-300">
						<input type="checkbox" bind:checked={formIsActive} class="accent-brand-400" />
						Active
					</label>

					<!-- Predicates -->
					<div>
						<div class="flex items-center justify-between mb-2">
							<h3 class="text-sm font-semibold text-white flex items-center gap-1">
								Predicates (Conditions)
								{#if formPredicates.length > 0}
									<span class="group relative cursor-help text-zinc-400 hover:text-zinc-200">
										<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
										</svg>
										<div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-surface-100 border border-surface-300 rounded shadow-xl text-xs text-zinc-300 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
											Predicates define when this rule applies. All predicates must match for the rule to trigger.
										</div>
									</span>
								{/if}
							</h3>
							{#if formPredicates.length > 0}
								<button class="text-xs text-brand-400 hover:text-brand-300" onclick={addPredicate}>+ Add Predicate</button>
							{/if}
						</div>
						{#if formPredicates.length === 0}
							<div class="bg-surface-200/50 border border-surface-300 rounded-lg p-4 text-center">
								<p class="text-sm text-zinc-300 mb-1">No predicates configured</p>
								<p class="text-xs text-zinc-500 mb-3">Without predicates, this rule acts as a catch-all and will apply to every event.</p>
								<button class="btn-secondary text-xs py-1.5" onclick={addPredicate}>+ Add your first predicate</button>
							</div>
						{/if}
						{#each formPredicates as pred, idx}
							<div class="flex gap-2 items-center mb-2">
								<select class="input flex-1" bind:value={pred.field}>
									{#if taxonomy}
										{#each taxonomy.predicate_fields as f}
											<option value={f.field}>{f.label}</option>
										{/each}
									{/if}
								</select>
								<select class="input w-28" bind:value={pred.op}>
									{#if taxonomy}
										{#each taxonomy.operators as op}
											<option value={op.op}>{op.label}</option>
										{/each}
									{/if}
								</select>
								{#if pred.field === 'event_type'}
									<select class="input flex-1" bind:value={pred.value}>
										{#if taxonomy}
											{#each taxonomy.interaction_types as t}
												<option value={t.value}>{t.label}</option>
											{/each}
										{/if}
									</select>
								{:else}
									<input type="text" class="input flex-1" bind:value={pred.value} placeholder="Value" />
								{/if}
								<button class="text-red-400 hover:text-red-300 text-sm" onclick={() => removePredicate(idx)}>✕</button>
							</div>
						{/each}
					</div>

					<!-- Outcomes -->
					<div>
						<div class="flex items-center justify-between mb-2">
							<h3 class="text-sm font-semibold text-white">Outcomes (Rewards)</h3>
							<button class="text-xs text-brand-400 hover:text-brand-300" onclick={addOutcome}>+ Add Outcome</button>
						</div>
						{#if formOutcomes.length === 0}
							<p class="text-xs text-surface-400">No outcomes defined yet</p>
						{/if}
						{#each formOutcomes as outcome, idx}
							<div class="card p-3 mb-2 space-y-2">
								<div class="flex gap-2 items-center">
									<select class="input w-32" bind:value={outcome.type}>
										<option value="xp">XP</option>
										<option value="gold">Gold</option>
										<option value="achievement">Achievement</option>
									</select>
									{#if outcome.type === 'achievement'}
										<input type="text" class="input flex-1" bind:value={outcome.template_name} placeholder="Achievement template name" />
									{:else}
										<input type="number" class="input w-24" bind:value={outcome.base_value} placeholder="Base value" min="0" />
									{/if}
									<button class="text-red-400 hover:text-red-300 text-sm" onclick={() => removeOutcome(idx)}>✕</button>
								</div>
								{#if outcome.type !== 'achievement'}
									<!-- Scaling config -->
									<details class="text-xs">
										<summary class="text-surface-400 cursor-pointer hover:text-white">Scaling curve (optional)</summary>
										<div class="grid grid-cols-2 gap-2 mt-2">
											<div>
												<label class="label text-xs" for="rule-outcome-curve-{idx}">Curve</label>
												<select class="input w-full" value={outcome.scaling?.curve ?? ""}
													id="rule-outcome-curve-{idx}"
													onchange={(e) => {
														const val = (e.target as HTMLSelectElement).value;
														if (val) {
															outcome.scaling = { curve: val, variable: 'messages_today', factor: 1 };
														} else {
															outcome.scaling = undefined;
														}
													}}
												>
													<option value="">None</option>
													{#if taxonomy}
														{#each taxonomy.scaling_curves as c}
															<option value={c.value}>{c.label}</option>
														{/each}
													{/if}
												</select>
											</div>
											{#if outcome.scaling}
												<div>
													<label class="label text-xs" for="rule-outcome-variable-{idx}">Variable</label>
													<select id="rule-outcome-variable-{idx}" class="input w-full" bind:value={outcome.scaling.variable}>
														{#if taxonomy}
															{#each taxonomy.context_variables as v}
																<option value={v.name}>{v.label}</option>
															{/each}
														{/if}
													</select>
												</div>
												<div>
													<label class="label text-xs" for="rule-outcome-factor-{idx}">Factor</label>
													<input id="rule-outcome-factor-{idx}" type="number" class="input w-full" bind:value={outcome.scaling.factor} step="0.1" min="0.1" />
												</div>
												<div class="flex items-end">
													<svg width="120" height="40" viewBox="0 0 120 40" class="border border-surface-400/20 rounded">
														<polyline
															points={sparklinePath(outcome.scaling.curve, outcome.scaling.variable, outcome.scaling.factor ?? 1, outcome.scaling.base ?? 10, outcome.scaling.thresholds ?? {})}
															fill="none" stroke="#7c3aed" stroke-width="2"
														/>
													</svg>
												</div>
											{/if}
										</div>
									</details>
								{/if}
							</div>
						{/each}
					</div>

					<!-- Actions -->
					<div class="flex justify-end gap-3 pt-2">
						<button class="btn-secondary" onclick={() => showEditor = false}>Cancel</button>
						<button class="btn-primary" onclick={saveRule} disabled={saving || !formName.trim()}>
							{saving ? 'Saving...' : (editingRule ? 'Update Rule' : 'Create Rule')}
						</button>
					</div>
				</div>
			</div>
		{/if}

	<!-- ================================================================ -->
	<!-- ZONE B — Laboratory                                              -->
	<!-- ================================================================ -->
	{:else if activeZone === 'lab'}
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<!-- Input -->
			<div class="card p-5 space-y-4">
				<h3 class="text-lg font-semibold text-white">Simulation Input</h3>

				<div>
					<label class="label" for="lab-event-type">Event Type</label>
					<select id="lab-event-type" class="input w-full" bind:value={labEventType}>
						{#if taxonomy}
							{#each taxonomy.interaction_types as t}
								<option value={t.value}>{t.label}</option>
							{/each}
						{/if}
					</select>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="label" for="lab-user-id">User ID (optional)</label>
						<input id="lab-user-id" type="text" class="input w-full" bind:value={labUserId} placeholder="Discord user ID" />
					</div>
					<div>
						<label class="label" for="lab-channel-id">Channel ID (optional)</label>
						<input id="lab-channel-id" type="text" class="input w-full" bind:value={labChannelId} placeholder="Discord channel ID" />
					</div>
				</div>

				<div>
					<h4 class="label mb-2">Context Variables</h4>
					<div class="grid grid-cols-2 gap-2">
						{#each Object.entries(labContext) as [key, val], idx}
							<div>
								<label class="text-xs text-surface-400" for="lab-context-{idx}">{key}</label>
								<input id="lab-context-{idx}" type="number" class="input w-full" bind:value={labContext[key]} min="0" />
							</div>
						{/each}
					</div>
				</div>

				<div>
					<h4 class="label mb-2">Test specific rules (optional)</h4>
					<div class="flex flex-wrap gap-1">
						{#each rules as rule (rule.id)}
							<label class="flex items-center gap-1 text-xs text-surface-300 px-2 py-1 rounded bg-surface-300/10 cursor-pointer">
								<input
									type="checkbox"
									class="accent-brand-400"
									checked={labRuleIds.includes(rule.id)}
									onchange={() => {
										if (labRuleIds.includes(rule.id)) {
											labRuleIds = labRuleIds.filter(id => id !== rule.id);
										} else {
											labRuleIds = [...labRuleIds, rule.id];
										}
									}}
								/>
								{rule.name}
							</label>
						{/each}
					</div>
				</div>

				<button class="btn-primary w-full" onclick={runSimulation} disabled={labRunning}>
					{labRunning ? 'Running...' : 'Run Simulation'}
				</button>
			</div>

			<!-- Output -->
			<div class="card p-5 space-y-4">
				<h3 class="text-lg font-semibold text-white">Results</h3>

				{#if labResult === null}
					<EmptyState title="No simulation results" description="Run a simulation to see results" />
				{:else}
					<!-- Summary -->
					<div class="grid grid-cols-2 gap-3">
						<div class="card p-3 text-center">
							<div class="text-2xl font-bold text-brand-400">{labResult.outcomes_applied.xp ?? 0}</div>
							<div class="text-xs text-surface-400">{currency.primary}</div>
						</div>
						<div class="card p-3 text-center">
							<div class="text-2xl font-bold text-yellow-400">{labResult.outcomes_applied.gold ?? 0}</div>
							<div class="text-xs text-surface-400">{currency.secondary}</div>
						</div>
					</div>

					<p class="text-sm text-surface-400">{labResult.rules_tested} rules tested, {labResult.matched_rules.length} matched</p>

					<!-- Matched rules detail -->
					{#if labResult.matched_rules.length > 0}
						<div class="space-y-2">
							<h4 class="text-sm font-semibold text-white">Matched Rules ("Why" Trace)</h4>
							{#each labResult.matched_rules as match}
								<div class="card p-3">
									<div class="flex items-center gap-2">
										<span class="font-mono text-brand-400">#{match.rule_id}</span>
										<span class="text-white text-sm">{match.rule_name}</span>
										<span class="text-xs text-surface-400">Priority {match.priority}</span>
									</div>
									<div class="mt-1 flex flex-wrap gap-1">
										{#each Object.entries(match.outcomes) as [key, val]}
											<span class="text-xs px-2 py-0.5 rounded bg-green-500/10 text-green-400">
												{key}: {val}
											</span>
										{/each}
									</div>
								</div>
							{/each}
						</div>
					{/if}

					<!-- Context snapshot -->
					<details class="text-xs">
						<summary class="text-surface-400 cursor-pointer hover:text-white">Context Snapshot</summary>
						<pre class="mt-2 p-3 rounded bg-surface-400/10 text-surface-300 overflow-x-auto">{JSON.stringify(labResult.context_snapshot, null, 2)}</pre>
					</details>
				{/if}
			</div>
		</div>

	<!-- ================================================================ -->
	<!-- ZONE C — Taxonomy Browser                                        -->
	<!-- ================================================================ -->
	{:else if activeZone === 'taxonomy'}
		<div class="space-y-6">
			{#if !taxonomy}
				<EmptyState title="Taxonomy unavailable" description="Taxonomy data not loaded" />
			{:else}
				<!-- Observed Event Types -->
				<div class="card p-5">
					<h3 class="text-lg font-semibold text-white mb-3">Observed Event Types (Last 30 Days)</h3>
					{#if taxonomy.observed_types.length === 0}
						<p class="text-sm text-surface-400">No events observed yet. Start the bot to capture events.</p>
					{:else}
						<div class="space-y-2">
							{#each taxonomy.observed_types as obs}
								{@const maxCount = Math.max(...taxonomy.observed_types.map(o => o.count), 1)}
								<div class="flex items-center gap-3">
									<span class="w-40 text-sm text-white font-mono truncate">{obs.event_type}</span>
									<div class="flex-1 h-4 bg-surface-400/10 rounded overflow-hidden">
										<div
											class="h-full bg-brand-500 rounded"
											style="width: {(obs.count / maxCount) * 100}%"
										></div>
									</div>
									<span class="text-xs text-surface-400 w-20 text-right">{obs.count.toLocaleString()}</span>
									<button
										class="text-xs text-brand-400 hover:text-brand-300 shrink-0"
										onclick={() => createRuleForEventType(obs.event_type)}
									>+ Rule</button>
								</div>
							{/each}
						</div>
					{/if}
				</div>

				<!-- Interaction Types -->
				<div class="card p-5">
					<h3 class="text-lg font-semibold text-white mb-3">Reward Pipeline Types</h3>
					<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
						{#each taxonomy.interaction_types as t}
							<div class="card p-3 text-center">
								<span class="text-sm text-white">{t.label}</span>
								<div class="text-xs text-surface-400 font-mono mt-1">{t.value}</div>
							</div>
						{/each}
					</div>
				</div>

				<!-- Event Lake Types -->
				<div class="card p-5">
					<h3 class="text-lg font-semibold text-white mb-3">Event Lake Types</h3>
					<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
						{#each taxonomy.event_lake_types as t}
							<div class="card p-3 text-center">
								<span class="text-sm text-white">{t.label}</span>
								<div class="text-xs text-surface-400 font-mono mt-1">{t.value}</div>
							</div>
						{/each}
					</div>
				</div>

				<!-- Predicate Field Reference -->
				<div class="card p-5">
					<h3 class="text-lg font-semibold text-white mb-3">Predicate Field Dictionary</h3>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-surface-400 border-b border-surface-400/20">
									<th class="pb-2 pr-4">Field</th>
									<th class="pb-2 pr-4">Label</th>
									<th class="pb-2">Type</th>
								</tr>
							</thead>
							<tbody>
								{#each taxonomy.predicate_fields as field}
									<tr class="border-b border-surface-400/10">
										<td class="py-2 pr-4 font-mono text-brand-400">{field.field}</td>
										<td class="py-2 pr-4 text-white">{field.label}</td>
										<td class="py-2 text-surface-400">{field.type}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>

				<!-- Context Variables Reference -->
				<div class="card p-5">
					<h3 class="text-lg font-semibold text-white mb-3">Context Variables</h3>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-surface-400 border-b border-surface-400/20">
									<th class="pb-2 pr-4">Variable</th>
									<th class="pb-2 pr-4">Label</th>
									<th class="pb-2">Type</th>
								</tr>
							</thead>
							<tbody>
								{#each taxonomy.context_variables as v}
									<tr class="border-b border-surface-400/10">
										<td class="py-2 pr-4 font-mono text-brand-400">{v.name}</td>
										<td class="py-2 pr-4 text-white">{v.label}</td>
										<td class="py-2 text-surface-400">{v.type}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			{/if}
		</div>

	<!-- ================================================================ -->
	<!-- ZONE D — Projection Dashboard                                    -->
	<!-- ================================================================ -->
	{:else if activeZone === 'projections'}
		<div class="space-y-6">
			<!-- Worker Status -->
			<div class="card p-5">
				<h3 class="text-lg font-semibold text-white mb-3">Projection Workers</h3>
				{#if !projectionStatus}
					<div class="flex items-center justify-center py-8">
						<div class="animate-spin h-6 w-6 border-2 border-brand-400 border-t-transparent rounded-full"></div>
					</div>
				{:else}
					<div class="grid grid-cols-2 gap-4 mb-4">
						<div class="card p-3">
							<div class="text-2xl font-bold text-brand-400">{projectionStatus.total_evaluations.toLocaleString()}</div>
							<div class="text-xs text-surface-400">Total Evaluations</div>
						</div>
						<div class="card p-3">
							<div class="text-2xl font-bold text-white">{projectionStatus.latest_evaluation_id.toLocaleString()}</div>
							<div class="text-xs text-surface-400">Latest Evaluation ID</div>
						</div>
					</div>

					{#if projectionStatus.workers.length === 0}
						<p class="text-sm text-surface-400">No projection workers registered yet.</p>
					{:else}
						<div class="space-y-2">
							{#each projectionStatus.workers as worker}
								<div class="card p-3 flex items-center gap-4">
									<span class="font-mono text-sm text-white">{worker.worker_id}</span>
									<span class="text-xs text-surface-400">
										Last processed: #{worker.last_processed_id.toLocaleString()}
									</span>
									<span class="text-xs px-2 py-0.5 rounded {worker.lag === 0 ? 'bg-green-500/20 text-green-400' : worker.lag < 100 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}">
										{worker.lag === 0 ? 'Caught up' : `${worker.lag.toLocaleString()} behind`}
									</span>
									{#if worker.updated_at}
										<span class="text-xs text-surface-400 ml-auto">
											Updated {new Date(worker.updated_at).toLocaleString()}
										</span>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
				{/if}
			</div>

			<!-- Recent Evaluations -->
			<div class="card p-5">
				<div class="flex items-center justify-between mb-3">
					<h3 class="text-lg font-semibold text-white">Recent Evaluations</h3>
					<span class="text-xs text-surface-400">{evalTotal.toLocaleString()} total</span>
				</div>

				{#if evaluations.length === 0}
					<EmptyState title="No evaluations yet" description="No rule evaluations recorded yet" />
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-surface-400 border-b border-surface-400/20">
									<th class="pb-2 pr-3">ID</th>
									<th class="pb-2 pr-3">User</th>
									<th class="pb-2 pr-3">Rules Matched</th>
									<th class="pb-2 pr-3">Outcomes</th>
									<th class="pb-2">Time</th>
								</tr>
							</thead>
							<tbody>
								{#each evaluations as evalRow}
									<tr class="border-b border-surface-400/10">
										<td class="py-2 pr-3 font-mono text-xs text-brand-400">{evalRow.id}</td>
										<td class="py-2 pr-3 font-mono text-xs text-white">{evalRow.user_id ?? '—'}</td>
										<td class="py-2 pr-3 text-xs">{evalRow.matched_rules?.length ?? 0} rules</td>
										<td class="py-2 pr-3">
											<div class="flex gap-1">
												{#if evalRow.outcomes_applied?.xp}
													<span class="text-xs px-1 rounded bg-brand-500/20 text-brand-400">+{evalRow.outcomes_applied.xp} XP</span>
												{/if}
												{#if evalRow.outcomes_applied?.gold}
													<span class="text-xs px-1 rounded bg-yellow-500/20 text-yellow-400">+{evalRow.outcomes_applied.gold} Gold</span>
												{/if}
											</div>
										</td>
										<td class="py-2 text-xs text-surface-400">{evalRow.evaluated_at ? new Date(evalRow.evaluated_at).toLocaleString() : '—'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>

					<!-- Pagination -->
					{#if evalTotal > 25}
						<div class="flex items-center justify-center gap-3 mt-4">
							<button
								class="btn-secondary text-sm"
								disabled={evalPage <= 1}
								onclick={() => { evalPage--; loadProjections(); }}
							>Previous</button>
							<span class="text-sm text-surface-400">Page {evalPage} of {Math.ceil(evalTotal / 25)}</span>
							<button
								class="btn-secondary text-sm"
								disabled={evalPage >= Math.ceil(evalTotal / 25)}
								onclick={() => { evalPage++; loadProjections(); }}
							>Next</button>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	{/if}
</div>

<!-- Delete confirmation modal -->
{#if confirmDeleteId !== null}
	<ConfirmModal
		open={true}
		title="Delete Rule"
		message="Are you sure you want to delete this rule? This action cannot be undone."
		confirmLabel="Delete"
		onconfirm={() => deleteRule(confirmDeleteId!)}
		oncancel={() => confirmDeleteId = null}
	/>
{/if}
