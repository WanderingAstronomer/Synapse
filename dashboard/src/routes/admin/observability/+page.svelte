<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		api,
		type ObservabilityResponse,
		type EconomicBucket,
		type AnomalyEntry,
		type RulePerformanceBucket,
		type TopEarner,
		type SystemHealth,
	} from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { fmt, timeAgo, eventTypeLabel, eventColor } from '$lib/utils';

	import type { Chart as ChartType } from 'chart.js';

	// ---------------------------------------------------------------------------
	//  State
	// ---------------------------------------------------------------------------
	let data = $state<ObservabilityResponse | null>(null);
	let loading = $state(true);
	let pollTimer = $state<ReturnType<typeof setInterval> | null>(null);
	let lastRefreshed = $state<string | null>(null);
	let chartCanvas = $state<HTMLCanvasElement | null>(null);

	/** Lazy-loaded Chart constructor — resolved on first render. */
	let ChartCtor: typeof ChartType | null = null;

	async function ensureChart(): Promise<typeof ChartType> {
		if (ChartCtor) return ChartCtor;
		const {
			Chart,
			LineController,
			LineElement,
			PointElement,
			Filler,
			CategoryScale,
			LinearScale,
			Tooltip,
			Legend,
		} = await import('chart.js');
		Chart.register(LineController, LineElement, PointElement, Filler, CategoryScale, LinearScale, Tooltip, Legend);
		ChartCtor = Chart;
		return Chart;
	}

	// ---------------------------------------------------------------------------
	//  Data loading
	// ---------------------------------------------------------------------------
	async function load() {
		try {
			data = await api.admin.getObservability();
			lastRefreshed = new Date().toISOString();
		} catch (e: any) {
			flash.error(e.message || 'Failed to load observability data');
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		load();
		// Poll every 60 seconds
		pollTimer = setInterval(load, 60_000);
	});

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});

	// ---------------------------------------------------------------------------
	//  Chart Rendering
	// ---------------------------------------------------------------------------
	$effect(() => {
		if (!data?.rule_performance || !chartCanvas) return;

		const performance = data.rule_performance;
		const canvas = chartCanvas;

		let cancelled = false;
		let instance: ChartType | null = null;

		(async () => {
			const Chart = await ensureChart();
			if (cancelled) return;

			// Extract unique hours and rules
			const hours = Array.from(new Set(performance.map(b => b.hour))).sort();
			const ruleNames = Array.from(new Set(performance.map(b => b.rule_name))).sort();

			// Generate a color for each rule
			const colors = [
				'#3b82f6', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316',
				'#eab308', '#84cc16', '#22c55e', '#10b981', '#14b8a6',
				'#06b6d4', '#0ea5e9', '#6366f1'
			];
			const ruleColors = new Map<string, string>();
			ruleNames.forEach((name, i) => {
				ruleColors.set(name, colors[i % colors.length]);
			});

			const datasets = ruleNames.map((ruleName) => {
				const color = ruleColors.get(ruleName)!;
				return {
					label: ruleName,
					data: hours.map(h => {
						const found = performance.find(b => b.hour === h && b.rule_name === ruleName);
						return found ? found.match_count : 0;
					}),
					backgroundColor: color + '80',
					borderColor: color,
					borderWidth: 2,
					tension: 0.3,
					pointRadius: 3,
					pointHoverRadius: 5,
				};
			});

			instance = new Chart(canvas, {
				type: 'line',
				data: {
					labels: hours.map((h) => hourLabel(h)),
					datasets,
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					interaction: { mode: 'index', intersect: false },
					plugins: {
						legend: {
							position: 'bottom',
							labels: { color: '#a1a1aa', padding: 16, usePointStyle: true, font: { size: 11 } },
						},
						tooltip: {
							backgroundColor: '#18181b',
							borderColor: '#3f3f46',
							borderWidth: 1,
							titleColor: '#e4e4e7',
							bodyColor: '#a1a1aa',
							padding: 12,
						},
					},
					scales: {
						x: {
							grid: { color: '#27272a' },
							ticks: { color: '#71717a', font: { size: 10 } },
						},
						y: {
							grid: { color: '#27272a' },
							ticks: { color: '#71717a', font: { size: 10 } },
						},
					},
				},
			});
		})();

		return () => {
			cancelled = true;
			if (instance) { instance.destroy(); instance = null; }
		};
	});

	// ---------------------------------------------------------------------------
	//  Helpers
	// ---------------------------------------------------------------------------
	function fmtUptime(seconds: number): string {
		const d = Math.floor(seconds / 86400);
		const h = Math.floor((seconds % 86400) / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		if (d > 0) return `${d}d ${h}h ${m}m`;
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	function fmtBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function poolUtilPct(health: SystemHealth): number {
		const total = health.db_pool.pool_size + health.db_pool.overflow;
		if (total === 0) return 0;
		return Math.round((health.db_pool.checked_out / total) * 100);
	}

	/** Get max value in a histogram for bar scaling */
	function histMax(buckets: EconomicBucket[], key: 'xp_issued' | 'gold_issued'): number {
		if (buckets.length === 0) return 1;
		return Math.max(1, ...buckets.map((b) => b[key]));
	}

	/** Extract a short hour label from an ISO string */
	function hourLabel(iso: string): string {
		try {
			const d = new Date(iso);
			return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
		} catch {
			return iso.slice(11, 16);
		}
	}

	/** Group top earners by event type */
	function groupByEventType(earners: TopEarner[]): Map<string, TopEarner[]> {
		const map = new Map<string, TopEarner[]>();
		for (const e of earners) {
			const existing = map.get(e.event_type);
			if (existing) existing.push(e);
			else map.set(e.event_type, [e]);
		}
		return map;
	}

	function severityColor(severity: string): string {
		if (severity === 'critical') return 'text-red-400';
		if (severity === 'warning') return 'text-amber-400';
		return 'text-zinc-400';
	}

	function severityBg(severity: string): string {
		if (severity === 'critical') return 'bg-red-500/10 border-red-500/20';
		if (severity === 'warning') return 'bg-amber-500/10 border-amber-500/20';
		return 'bg-surface-200 border-surface-300';
	}
</script>

<svelte:head><title>Observability — Synapse</title></svelte:head>

{#if loading}
	<div class="flex items-center justify-center h-64">
		<SynapseLoader text="Loading observability data..." />
	</div>
{:else if !data}
	<EmptyState
		title="No data available"
		description="Could not load observability data. Please try again."
		variant="hero"
	/>
{:else}
	<!-- Header -->
	<div class="flex items-center justify-between mb-6">
		<div>
			<h1 class="text-2xl font-bold text-white">Observability</h1>
			<p class="text-sm text-zinc-500 mt-1">
				System health, economy, anomalies, and rule performance.
				{#if lastRefreshed}
					<span class="ml-2 text-zinc-600">Updated {timeAgo(lastRefreshed)}</span>
				{/if}
			</p>
		</div>
		<button
			class="text-xs px-3 py-1.5 rounded-lg bg-surface-200 text-zinc-400 hover:text-zinc-200 hover:bg-surface-300 transition-all"
			onclick={() => { loading = true; load(); }}
		>
			Refresh
		</button>
	</div>

	<!-- ===================================================================== -->
	<!-- System Health Cards                                                    -->
	<!-- ===================================================================== -->
	<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
		<!-- Bot Status -->
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">Bot</p>
			<div class="flex items-center justify-center gap-2">
				<span
					class="w-2.5 h-2.5 rounded-full {data.health.bot.status === 'online' ? 'bg-emerald-400 shadow-lg shadow-emerald-400/30' : 'bg-red-400 shadow-lg shadow-red-400/30'}"
				></span>
				<span class="text-lg font-bold {data.health.bot.status === 'online' ? 'text-emerald-400' : 'text-red-400'}">
					{data.health.bot.status === 'online' ? 'Online' : 'Offline'}
				</span>
			</div>
			{#if data.health.bot.last_heartbeat}
				<p class="text-xs text-zinc-600 mt-1">{timeAgo(data.health.bot.last_heartbeat)}</p>
			{/if}
		</div>

		<!-- API Uptime -->
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">API Uptime</p>
			<p class="text-lg font-bold text-brand-400">{fmtUptime(data.health.api_uptime_seconds)}</p>
		</div>

		<!-- DB Pool -->
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">DB Pool</p>
			<p class="text-lg font-bold text-zinc-200">{poolUtilPct(data.health)}%</p>
			<p class="text-xs text-zinc-600 mt-1">
				{data.health.db_pool.checked_out}/{data.health.db_pool.pool_size + data.health.db_pool.overflow} connections
			</p>
		</div>

		<!-- Last Event -->
		<div class="card text-center py-4">
			<p class="text-xs text-zinc-500 uppercase tracking-wider mb-1">Last Event</p>
			<p class="text-sm font-bold text-zinc-300">
				{data.health.last_event_at ? timeAgo(data.health.last_event_at) : '—'}
			</p>
			{#if data.health.last_activity_at}
				<p class="text-xs text-zinc-600 mt-1">
					Activity: {timeAgo(data.health.last_activity_at)}
				</p>
			{/if}
		</div>
	</div>

	<!-- ===================================================================== -->
	<!-- Anomaly Feed                                                           -->
	<!-- ===================================================================== -->
	<div class="card mb-6">
		<h2 class="text-lg font-semibold text-white mb-4">Anomaly Feed</h2>
		{#if data.anomalies.length === 0}
			<div class="flex items-center gap-2 text-sm text-emerald-400">
				<span class="w-2 h-2 rounded-full bg-emerald-400"></span>
				No anomalies detected. All signals normal.
			</div>
		{:else}
			<div class="space-y-2">
				{#each data.anomalies as anomaly}
					<div class="flex items-start gap-3 p-3 rounded-lg border {severityBg(anomaly.severity)}">
						<span class="text-sm mt-0.5 {severityColor(anomaly.severity)}">
							{anomaly.severity === 'critical' ? '🚨' : '⚠️'}
						</span>
						<div class="flex-1 min-w-0">
							<p class="text-sm text-zinc-200">{anomaly.message}</p>
							<div class="flex items-center gap-3 mt-1 text-xs text-zinc-500">
								<span class="uppercase tracking-wider">{anomaly.kind.replace('_', ' ')}</span>
								{#if anomaly.details.user_id}
									<span>User: {anomaly.details.user_id}</span>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- ===================================================================== -->
	<!-- Economic Health — XP/Gold per Hour (last 24h)                          -->
	<!-- ===================================================================== -->
	<div class="card mb-6">
		<h2 class="text-lg font-semibold text-white mb-4">Economic Health — Last 24h</h2>
		{#if data.economic_histogram.length === 0}
			<p class="text-sm text-zinc-500">No activity data in the selected window.</p>
		{:else}
			{@const maxXp = histMax(data.economic_histogram, 'xp_issued')}
			{@const maxGold = histMax(data.economic_histogram, 'gold_issued')}

			<!-- XP Histogram -->
			<div class="mb-6">
				<h3 class="text-sm font-medium text-brand-400 mb-3">{currency.primary} Issued per Hour</h3>
				<div class="flex items-end gap-[2px] h-28">
					{#each data.economic_histogram as bucket}
						{@const pct = (bucket.xp_issued / maxXp) * 100}
						<div
							class="flex-1 bg-brand-500/60 hover:bg-brand-400/80 transition-colors rounded-t cursor-default group relative"
							style="height: {Math.max(pct, 2)}%"
						>
							<div class="hidden group-hover:block absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 rounded bg-surface-100 text-xs text-zinc-200 whitespace-nowrap z-10 shadow-lg border border-surface-300">
								{hourLabel(bucket.hour)}<br/>{fmt(bucket.xp_issued)} {currency.primary}
							</div>
						</div>
					{/each}
				</div>
				<div class="flex justify-between text-[10px] text-zinc-600 mt-1">
					<span>{hourLabel(data.economic_histogram[0].hour)}</span>
					<span>{hourLabel(data.economic_histogram[data.economic_histogram.length - 1].hour)}</span>
				</div>
			</div>

			<!-- Gold Histogram -->
			<div>
				<h3 class="text-sm font-medium text-gold-400 mb-3">{currency.secondary} Issued per Hour</h3>
				<div class="flex items-end gap-[2px] h-28">
					{#each data.economic_histogram as bucket}
						{@const pct = (bucket.gold_issued / maxGold) * 100}
						<div
							class="flex-1 bg-gold-500/60 hover:bg-gold-400/80 transition-colors rounded-t cursor-default group relative"
							style="height: {Math.max(pct, 2)}%"
						>
							<div class="hidden group-hover:block absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 rounded bg-surface-100 text-xs text-zinc-200 whitespace-nowrap z-10 shadow-lg border border-surface-300">
								{hourLabel(bucket.hour)}<br/>{fmt(bucket.gold_issued)} {currency.secondary}
							</div>
						</div>
					{/each}
				</div>
				<div class="flex justify-between text-[10px] text-zinc-600 mt-1">
					<span>{hourLabel(data.economic_histogram[0].hour)}</span>
					<span>{hourLabel(data.economic_histogram[data.economic_histogram.length - 1].hour)}</span>
				</div>
			</div>
		{/if}
	</div>

	<!-- ===================================================================== -->
	<!-- Rule Performance — Match Rate per Hour                                 -->
	<!-- ===================================================================== -->
	<div class="card mb-6">
		<h2 class="text-lg font-semibold text-white mb-4">Rule Performance — Last 24h</h2>
		{#if data.rule_performance.length === 0}
			<p class="text-sm text-zinc-500">No rule evaluations in the selected window.</p>
		{:else}
			<div class="h-64">
				<canvas bind:this={chartCanvas}></canvas>
			</div>
		{/if}
	</div>

	<!-- ===================================================================== -->
	<!-- Top Earners — Per Event Type (last 24h)                                -->
	<!-- ===================================================================== -->
	<div class="card">
		<h2 class="text-lg font-semibold text-white mb-4">Top Earners — Last 24h</h2>
		{#if data.top_earners.length === 0}
			<p class="text-sm text-zinc-500">No earnings data in the selected window.</p>
		{:else}
			{@const grouped = groupByEventType(data.top_earners)}
			<div class="space-y-6">
				{#each [...grouped.entries()] as [eventType, earners]}
					<div>
						<div class="flex items-center gap-2 mb-3">
							<span
								class="w-2.5 h-2.5 rounded-full flex-shrink-0"
								style="background-color: {eventColor(eventType)}"
							></span>
							<h3 class="text-sm font-medium text-zinc-300">{eventTypeLabel(eventType)}</h3>
						</div>
						<div class="overflow-x-auto">
							<table class="w-full text-sm">
								<thead>
									<tr class="text-xs text-zinc-500 uppercase tracking-wider border-b border-surface-300/50">
										<th class="text-left py-2 pr-4">#</th>
										<th class="text-left py-2 pr-4">User</th>
										<th class="text-right py-2 pr-4">{currency.primary}</th>
										<th class="text-right py-2 pr-4">{currency.secondary}</th>
										<th class="text-right py-2">Events</th>
									</tr>
								</thead>
								<tbody>
									{#each earners as earner, i}
										<tr class="border-b border-surface-300/30 hover:bg-surface-200/30">
											<td class="py-2 pr-4 text-zinc-500">{i + 1}</td>
											<td class="py-2 pr-4 text-zinc-200 font-medium truncate max-w-[200px]">
												{earner.user_name ?? earner.user_id}
											</td>
											<td class="py-2 pr-4 text-right text-brand-400 font-mono">{fmt(earner.total_xp)}</td>
											<td class="py-2 pr-4 text-right text-gold-400 font-mono">{fmt(earner.total_gold)}</td>
											<td class="py-2 text-right text-zinc-400 font-mono">{fmt(earner.event_count)}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/if}
