<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type ActivityEvent, type ActivityResponse, type PageLayout } from '$lib/api';
	import Avatar from '$lib/components/Avatar.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import { timeAgo, eventTypeLabel, eventColor, fmt } from '$lib/utils';
	import type { Chart as ChartType } from 'chart.js';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';
	import EditableCard from '$lib/components/EditableCard.svelte';
	import CardPropertyPanel from '$lib/components/CardPropertyPanel.svelte';
	import { editMode } from '$lib/stores/editMode.svelte';
	import { siteSettings } from '$lib/stores/siteSettings.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import { ACTIVITY_DAY_OPTIONS } from '$lib/constants';

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

	let days = $state(30);
	let data = $state<ActivityResponse | null>(null);
	let layout = $state<PageLayout | null>(null);
	let loading = $state(true);
	let chartCanvas = $state<HTMLCanvasElement | null>(null);
	let eventFilters = $state<string[]>([]);
	let allEventTypes = $state<string[]>([]);

	let isEditing = $derived(editMode.canEdit);

	let heading = $derived(siteSettings.pageTitle('activity', 'Activity'));

	

	async function load() {
		loading = true;
		try {
			data = await api.getActivity(days, 200, eventFilters.length > 0 ? eventFilters : undefined);
			// Populate all known event types on the first unfiltered load
			if (eventFilters.length === 0 && data) {
				allEventTypes = [...new Set(data.events.map((e) => e.event_type))].sort();
			}
		} catch (e) {
			console.error('Activity load failed:', e);
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		api.getLayout('activity').then((l) => (layout = l)).catch(() => null);
		load();
	});

	function changeDays(d: number) {
		days = d;
		load();
	}

	function toggleFilter(f: string) {
		if (f === '') {
			eventFilters = [];
		} else {
			if (eventFilters.includes(f)) {
				eventFilters = eventFilters.filter(x => x !== f);
			} else {
				eventFilters = [...eventFilters, f];
			}
		}
		load();
	}

	// Build chart when data changes — lazy-load Chart.js, destroy + recreate
	$effect(() => {
		if (!data?.daily || !chartCanvas) return;

		// Snapshot reactive values to sever tracking
		const daily = data.daily;
		const canvas = chartCanvas;

		let cancelled = false;
		let instance: ChartType | null = null;

		(async () => {
			const Chart = await ensureChart();
			if (cancelled) return;

			const days_sorted = Object.keys(daily).sort();
			const eventTypes = [...new Set(days_sorted.flatMap((d) => Object.keys(daily[d])))];

			const datasets = eventTypes.map((et) => ({
				label: eventTypeLabel(et),
				data: days_sorted.map((d) => daily[d][et] || 0),
				backgroundColor: eventColor(et) + '80',
				borderColor: eventColor(et),
				borderWidth: 1,
				tension: 0.3,
				pointRadius: 5,
				pointHoverRadius: 7,
			}));

			instance = new Chart(canvas, {
				type: 'line',
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
							grid: { color: '#27272a' },
							ticks: { color: '#71717a', font: { size: 12 } },
						},
						y: {
							grid: { color: '#27272a' },
							ticks: { color: '#71717a', font: { size: 12 } },
						},
					},
				},
			});
		})();

		// Cleanup: cancel pending async work and destroy chart
		return () => {
			cancelled = true;
			if (instance) { instance.destroy(); instance = null; }
		};
	});

	let sortedCards = $derived(
		layout?.cards
			?.filter((c) => isEditing || c.visible)
			.sort((a, b) => a.position - b.position) ?? []
	);
	let wrapCard = $derived(sortedCards.find((c) => c.card_type === 'activity_feed'));
</script>

<svelte:head><title>{heading} — Synapse</title></svelte:head>

{#snippet pageContent()}
<div class="mb-6">
	<h1 class="text-2xl font-bold text-white">{heading}</h1>
	<p class="text-sm text-zinc-500 mt-1">Track engagement across the community.</p>
</div>

<!-- Controls -->
<div class="flex flex-wrap gap-2 mb-6" role="group" aria-label="Activity filters">
	{#each ACTIVITY_DAY_OPTIONS as d}
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
				{days === d
					? 'bg-brand-600 text-white'
					: 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => changeDays(d)}
			aria-pressed={days === d}
		>
			{d}d
		</button>
	{/each}
	<div class="w-px bg-surface-400 mx-1" role="separator"></div>
	<button
		class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
			{eventFilters.length === 0 ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => toggleFilter('')}
		aria-pressed={eventFilters.length === 0}
	>
		All
	</button>
	{#each allEventTypes as et}
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
				{eventFilters.includes(et) ? 'bg-brand-600 text-white' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => toggleFilter(et)}
			aria-pressed={eventFilters.includes(et)}
		>
			{eventTypeLabel(et)}
		</button>
	{/each}
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<SynapseLoader text="Loading activity..." />
	</div>
{:else if !data || data.events.length === 0}
	<EmptyState title="No activity yet" description="Events will stream in once the bot processes interactions." />
{:else}
	<!-- Chart -->
	<div class="card mb-6">
		<h2 class="text-sm font-semibold text-zinc-300 mb-4 text-center">Daily Activity Breakdown</h2>
		<div class="h-64">
			<canvas bind:this={chartCanvas}></canvas>
		</div>
	</div>

	<!-- Feed -->
	<div class="card">
		<div class="bg-purple-900/40 -mx-4 px-4 py-2 rounded-t-lg mb-4">
			<h2 class="text-sm font-semibold text-zinc-300 text-center">Recent Events</h2>
		</div>
		<div class="space-y-2 max-h-[500px] overflow-y-auto pr-2">
			{#each data.events as event}
				<div class="flex items-center gap-3 p-2.5 rounded-lg hover:bg-surface-200/50 hover:scale-[1.005] active:scale-[0.995] transition-all duration-150">
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
						<span class="text-xs text-brand-400">+{event.xp_delta} {currency.primary}</span>
						{/if}
					</div>
					<span class="text-xs text-zinc-500 whitespace-nowrap">{timeAgo(event.timestamp)}</span>
				</div>
			{/each}
		</div>
	</div>
{/if}
{/snippet}

{#if wrapCard}
<EditableCard card={wrapCard} showTitles={false}>
	{@render pageContent()}
</EditableCard>
<CardPropertyPanel cards={sortedCards} />
{:else}
{@render pageContent()}
{/if}
