<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type ActivityEvent, type ActivityResponse } from '$lib/api';
	import Avatar from '$lib/components/Avatar.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { timeAgo, eventTypeLabel, eventColor, fmt } from '$lib/utils';
	import { Chart, registerables } from 'chart.js';

	Chart.register(...registerables);

	let days = $state(30);
	let data = $state<ActivityResponse | null>(null);
	let loading = $state(true);
	let chartCanvas = $state<HTMLCanvasElement | null>(null);
	let chart: Chart | null = null;
	let eventFilter = $state('');

	const DAY_OPTIONS = [7, 14, 30, 90];

	async function load() {
		loading = true;
		try {
			data = await api.getActivity(days, 200, eventFilter || undefined);
		} catch (e) {
			console.error('Activity load failed:', e);
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function changeDays(d: number) {
		days = d;
		load();
	}

	function setFilter(f: string) {
		eventFilter = f;
		load();
	}

	// Build chart when data changes
	$effect(() => {
		if (!data?.daily || !chartCanvas) return;

		if (chart) chart.destroy();

		const days_sorted = Object.keys(data.daily).sort();
		const eventTypes = [...new Set(days_sorted.flatMap((d) => Object.keys(data!.daily[d])))];

		const datasets = eventTypes.map((et) => ({
			label: eventTypeLabel(et),
			data: days_sorted.map((d) => data!.daily[d][et] || 0),
			backgroundColor: eventColor(et) + '80',
			borderColor: eventColor(et),
			borderWidth: 1,
			borderRadius: 3,
		}));

		chart = new Chart(chartCanvas, {
			type: 'bar',
			data: {
				labels: days_sorted.map((d) => {
					const date = new Date(d);
					return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
				}),
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
						stacked: true,
						grid: { color: '#27272a' },
						ticks: { color: '#71717a', font: { size: 10 } },
					},
					y: {
						stacked: true,
						grid: { color: '#27272a' },
						ticks: { color: '#71717a', font: { size: 10 } },
					},
				},
			},
		});
	});

	// Collect unique event types from data
	const eventTypes = $derived(
		data ? [...new Set(data.events.map((e) => e.event_type))].sort() : []
	);
</script>

<svelte:head><title>Activity — Synapse</title></svelte:head>

<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">Activity</h1>
	<p class="text-sm text-zinc-500 mt-1">Track engagement across the community.</p>
</div>

<!-- Controls -->
<div class="flex flex-wrap gap-2 mb-6">
	{#each DAY_OPTIONS as d}
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
				{days === d
					? 'bg-brand-600 text-white'
					: 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => changeDays(d)}
		>
			{d}d
		</button>
	{/each}
	<div class="w-px bg-surface-400 mx-1"></div>
	<button
		class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
			{!eventFilter ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => setFilter('')}
	>
		All
	</button>
	{#each eventTypes as et}
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
				{eventFilter === et ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => setFilter(et)}
		>
			{eventTypeLabel(et)}
		</button>
	{/each}
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if !data || data.events.length === 0}
	<EmptyState icon="⚡" title="No activity yet" description="Events will stream in once the bot processes interactions." />
{:else}
	<!-- Chart -->
	<div class="card mb-6">
		<h2 class="text-sm font-semibold text-zinc-300 mb-4">Daily Activity Breakdown</h2>
		<div class="h-64">
			<canvas bind:this={chartCanvas}></canvas>
		</div>
	</div>

	<!-- Feed -->
	<div class="card">
		<h2 class="text-sm font-semibold text-zinc-300 mb-4">Recent Events</h2>
		<div class="space-y-2 max-h-[500px] overflow-y-auto pr-2">
			{#each data.events as event}
				<div class="flex items-center gap-3 p-2.5 rounded-lg hover:bg-surface-200/50 transition-colors">
					<Avatar src={event.avatar_url} size={32} />
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2">
							<span class="text-sm font-medium text-zinc-200 truncate">{event.user_name}</span>
							<span
								class="badge text-[10px]"
								style="background-color: {eventColor(event.event_type)}20; color: {eventColor(event.event_type)}"
							>
								{eventTypeLabel(event.event_type)}
							</span>
						</div>
						{#if event.xp_delta > 0}
							<span class="text-xs text-brand-400">+{event.xp_delta} XP</span>
						{/if}
					</div>
					<span class="text-xs text-zinc-500 whitespace-nowrap">{timeAgo(event.timestamp)}</span>
				</div>
			{/each}
		</div>
	</div>
{/if}
