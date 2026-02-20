<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		api,
		type CutoverStatus,
		type CutoverFlag,
		type PreflightCheck,
	} from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import { timeAgo } from '$lib/utils';

	// ---------------------------------------------------------------------------
	//  State
	// ---------------------------------------------------------------------------
	let data = $state<CutoverStatus | null>(null);
	let loading = $state(true);
	let pollTimer = $state<ReturnType<typeof setInterval> | null>(null);
	let toggling = $state<string | null>(null);

	// Confirm modal state
	let confirmOpen = $state(false);
	let confirmFlag = $state<CutoverFlag | null>(null);
	let confirmAction = $state<'enable' | 'disable'>('enable');

	// ---------------------------------------------------------------------------
	//  Data loading
	// ---------------------------------------------------------------------------
	async function load() {
		try {
			data = await api.admin.getCutoverStatus();
		} catch (e: any) {
			flash.error(e.message || 'Failed to load cutover status');
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		load();
		pollTimer = setInterval(load, 30_000);
	});

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});

	// ---------------------------------------------------------------------------
	//  Actions
	// ---------------------------------------------------------------------------
	function requestToggle(flag: CutoverFlag, action: 'enable' | 'disable') {
		confirmFlag = flag;
		confirmAction = action;
		confirmOpen = true;
	}

	async function executeToggle() {
		if (!confirmFlag) return;
		const key = confirmFlag.key;
		const enable = confirmAction === 'enable';
		toggling = key;
		try {
			const res = await api.admin.toggleCutoverFlag(key, enable);
			flash.success(res.message);
			await load();
		} catch (e: any) {
			flash.error(e.message || 'Toggle failed');
		} finally {
			toggling = null;
		}
	}

	// ---------------------------------------------------------------------------
	//  Helpers
	// ---------------------------------------------------------------------------
	const statusColors: Record<string, string> = {
		healthy: 'text-green-400',
		warning: 'text-amber-400',
		critical: 'text-red-400',
		unknown: 'text-zinc-500',
	};

	const statusBgs: Record<string, string> = {
		healthy: 'bg-green-500/10 border-green-500/30',
		warning: 'bg-amber-500/10 border-amber-500/30',
		critical: 'bg-red-500/10 border-red-500/30',
		unknown: 'bg-zinc-500/10 border-zinc-500/30',
	};

	const statusIcons: Record<string, string> = {
		healthy: '✓',
		warning: '⚠',
		critical: '✕',
		unknown: '?',
	};

	const overallLabels: Record<string, { text: string; color: string }> = {
		not_started: { text: 'Not Started', color: 'text-zinc-500 bg-zinc-500/10 border-zinc-500/20' },
		in_progress: { text: 'In Progress', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
		complete: { text: 'All Flags Live', color: 'text-green-400 bg-green-500/10 border-green-500/20' },
	};

	const enabledCount = $derived(data?.flags.filter(f => f.enabled).length ?? 0);
	const totalCount = $derived(data?.flags.length ?? 0);
	const progressPct = $derived(totalCount > 0 ? (enabledCount / totalCount) * 100 : 0);
</script>

<svelte:head><title>Admin: Feature Cutover — Synapse</title></svelte:head>

<div class="mb-6">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold text-white">Feature Flag Cutover</h1>
			<p class="text-sm text-zinc-500 mt-1">
				Enable features one at a time. Each flag must be stable before the next can be activated.
			</p>
		</div>
		{#if data}
			{@const overall = overallLabels[data.overall_status] ?? overallLabels.not_started}
			<span class="px-4 py-1.5 rounded-full text-sm font-semibold border {overall.color}">
				{overall.text}
			</span>
		{/if}
	</div>

	<!-- Progress bar -->
	{#if data}
		<div class="mt-4">
			<div class="flex items-center justify-between text-xs text-zinc-500 mb-1.5">
				<span>{enabledCount} of {totalCount} flags enabled</span>
				<span>{Math.round(progressPct)}%</span>
			</div>
			<div class="w-full h-2 bg-surface-300 rounded-full overflow-hidden">
				<div
					class="h-full rounded-full transition-all duration-500 ease-out
						{progressPct === 100 ? 'bg-green-500' : 'bg-brand-500'}"
					style="width: {progressPct}%"
				></div>
			</div>
		</div>
	{/if}
</div>

{#if loading}
	<SynapseLoader />
{:else if data}
	<div class="space-y-6">
		{#each data.flags as flag, i (flag.key)}
			{@const isActive = flag.enabled}
			{@const isNext = !isActive && flag.can_enable && !data.flags.slice(0, i).some(f => !f.enabled && f.can_enable)}
			{@const isLocked = !isActive && !flag.can_enable}
			<div
				class="card overflow-hidden transition-all duration-300
					{isActive ? 'ring-1 ring-green-500/30' : isNext ? 'ring-1 ring-brand-500/30' : 'opacity-75'}"
			>
				<!-- Header -->
				<div class="flex items-center justify-between p-5 border-b border-surface-300/30">
					<div class="flex items-center gap-4">
						<!-- Step indicator -->
						<div
							class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold
								{isActive ? 'bg-green-500/20 text-green-400 ring-2 ring-green-500/40' :
								 isNext ? 'bg-brand-500/20 text-brand-400 ring-2 ring-brand-500/40' :
								 'bg-surface-300 text-zinc-500'}"
						>
							{#if isActive}
								✓
							{:else}
								{flag.order}
							{/if}
						</div>

						<div>
							<div class="flex items-center gap-2">
								<h3 class="text-base font-semibold text-white">{flag.label}</h3>
								{#if isActive}
									<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">
										Live
									</span>
								{:else if isNext}
									<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-brand-500/10 text-brand-400 border border-brand-500/20">
										Ready
									</span>
								{:else if isLocked}
									<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-500/10 text-zinc-500 border border-zinc-500/20">
										Locked
									</span>
								{/if}
							</div>
							<p class="text-sm text-zinc-400 mt-0.5">{flag.description}</p>
							{#if flag.enabled_at}
								<p class="text-xs text-zinc-600 mt-1">Enabled {timeAgo(flag.enabled_at)}</p>
							{/if}
						</div>
					</div>

					<!-- Toggle button -->
					<div class="flex items-center gap-2 flex-shrink-0">
						{#if isActive}
							<button
								class="btn-danger text-xs px-4 py-2"
								disabled={toggling === flag.key}
								onclick={() => requestToggle(flag, 'disable')}
							>
								{#if toggling === flag.key}
									<span class="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
								{:else}
									Rollback
								{/if}
							</button>
						{:else if flag.can_enable}
							<button
								class="btn-primary text-xs px-4 py-2"
								disabled={toggling === flag.key}
								onclick={() => requestToggle(flag, 'enable')}
							>
								{#if toggling === flag.key}
									<span class="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
								{:else}
									Enable
								{/if}
							</button>
						{:else}
							<button class="btn-secondary text-xs px-4 py-2 opacity-50 cursor-not-allowed" disabled>
								Locked
							</button>
						{/if}
					</div>
				</div>

				<!-- Body: Preflight + Monitoring -->
				<div class="grid grid-cols-1 lg:grid-cols-2 gap-0 divide-y lg:divide-y-0 lg:divide-x divide-surface-300/30">
					<!-- Preflight checks -->
					<div class="p-5">
						<h4 class="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">Preflight Checks</h4>
						{#if flag.preflight_checks.length === 0}
							<p class="text-sm text-zinc-600 italic">No prerequisites for this flag</p>
						{:else}
							<div class="space-y-2">
								{#each flag.preflight_checks as check (check.label)}
									<div class="flex items-start gap-2">
										<span class="mt-0.5 text-sm {check.passed ? 'text-green-400' : 'text-red-400'}">
											{check.passed ? '✓' : '✕'}
										</span>
										<div>
											<p class="text-sm {check.passed ? 'text-zinc-300' : 'text-red-300'}">{check.label}</p>
											{#if check.detail}
												<p class="text-xs text-zinc-500">{check.detail}</p>
											{/if}
										</div>
									</div>
								{/each}
							</div>
						{/if}

						<!-- Blockers -->
						{#if flag.blockers.length > 0}
							<div class="mt-3 p-3 rounded-lg bg-red-500/5 border border-red-500/20">
								<p class="text-xs font-semibold text-red-400 mb-1">Blockers</p>
								{#each flag.blockers as blocker}
									<p class="text-xs text-red-300">• {blocker}</p>
								{/each}
							</div>
						{/if}
					</div>

					<!-- Monitoring -->
					<div class="p-5">
						<div class="flex items-center justify-between mb-3">
							<h4 class="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Monitoring</h4>
							<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border {statusBgs[flag.monitoring.status]}">
								<span class={statusColors[flag.monitoring.status]}>{statusIcons[flag.monitoring.status]}</span>
								<span class={statusColors[flag.monitoring.status]}>{flag.monitoring.status}</span>
							</span>
						</div>

						<p class="text-sm text-zinc-400 mb-3">{flag.monitoring.summary}</p>

						<!-- Metrics -->
						{#if Object.keys(flag.monitoring.metrics).length > 0}
							<div class="space-y-1.5">
								{#each Object.entries(flag.monitoring.metrics) as [key, value] (key)}
									{#if typeof value !== 'object'}
										<div class="flex items-center justify-between text-xs">
											<span class="text-zinc-500">{key.replace(/_/g, ' ')}</span>
											<span class="text-zinc-300 font-mono">{value}</span>
										</div>
									{/if}
								{/each}
							</div>
						{/if}

						<!-- Worker detail (for projection workers) -->
						{#if flag.key === 'flags.projection_workers_enabled' && Array.isArray(flag.monitoring.metrics.workers)}
							<div class="mt-3 border-t border-surface-300/30 pt-3">
								<p class="text-xs text-zinc-500 mb-2">Worker Checkpoints</p>
								{#each flag.monitoring.metrics.workers as worker}
									<div class="flex items-center justify-between text-xs py-1">
										<span class="text-zinc-400 font-mono">{worker.worker_id}</span>
										<span class="text-zinc-300">lag: {worker.lag}</span>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				</div>
			</div>
		{/each}
	</div>

	<!-- Final verification gate -->
	{#if data.overall_status === 'complete'}
		<div class="mt-8 card ring-1 ring-green-500/30 p-6">
			<div class="flex items-start gap-4">
				<div class="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center text-2xl flex-shrink-0">
					✓
				</div>
				<div>
					<h3 class="text-lg font-semibold text-green-400">All Flags Live</h3>
					<p class="text-sm text-zinc-400 mt-1">
						All four feature flags are enabled. Monitor the
						<a href="/admin/observability" class="text-brand-400 hover:text-brand-300 underline">observability dashboard</a>
						for at least 72 hours to verify stability before marking the cutover complete.
					</p>
					<div class="mt-4 space-y-2 text-sm text-zinc-400">
						<p>Final verification checklist:</p>
						<ul class="list-disc list-inside space-y-1 ml-2">
							<li>All four flags enabled and stable for ≥72 hours</li>
							<li>No anomaly flags in the observability feed</li>
							<li>Test suite passes against production schema</li>
							<li>Admin confirms: legacy pipeline can be deprecated</li>
						</ul>
					</div>
				</div>
			</div>
		</div>
	{/if}
{/if}

<!-- Confirm Modal -->
<ConfirmModal
	bind:open={confirmOpen}
	title={confirmAction === 'enable'
		? `Enable ${confirmFlag?.label ?? ''}?`
		: `Disable ${confirmFlag?.label ?? ''}?`}
	message={confirmAction === 'enable'
		? `This will activate ${confirmFlag?.label} in production. Changes propagate within 60 seconds via PG NOTIFY.`
		: `This will immediately disable ${confirmFlag?.label}. The rollback takes effect within 60 seconds. Any dependent flags should be disabled first.`}
	confirmLabel={confirmAction === 'enable' ? 'Enable Flag' : 'Rollback'}
	danger={confirmAction === 'disable'}
	onconfirm={executeToggle}
	oncancel={() => { confirmOpen = false; }}
/>
