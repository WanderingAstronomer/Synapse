<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { api, type AdminSetting } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import { currency } from '$lib/stores/currency.svelte';
	import { capitalize } from '$lib/utils';
	import SetupPanel from '$lib/components/SetupPanel.svelte';

	let settings = $state<AdminSetting[]>([]);
	let loading = $state(true);
	let editedValues = $state<Record<string, string>>({});
	let saving = $state(false);
	let filterCategory = $state('');

	// Detect ?tab= from URL for direct-link support
	$effect(() => {
		const tab = $page.url.searchParams.get('tab');
		if (tab === 'setup') filterCategory = '__setup__';
	});

	// ---------------------------------------------------------------------------
	// Setting metadata — type, constraints, and improved descriptions
	// ---------------------------------------------------------------------------
	interface SettingMeta {
		type: 'number' | 'float' | 'boolean' | 'string';
		min?: number;
		max?: number;
		step?: number;
		description?: string;
	}

	/** Type metadata + constraints for every known setting key.
	 *  Unknown keys fall back to a plain text input. */
	const SETTING_META: Record<string, SettingMeta> = {
		'economy.xp_per_message':         { type: 'number', min: 0, max: 1000, step: 1, description: 'XP awarded for each qualifying message. Set to 0 to disable message XP. Default: 5' },
		'economy.xp_per_reaction':        { type: 'number', min: 0, max: 1000, step: 1, description: 'XP awarded when a message receives a reaction. Set to 0 to disable reaction XP. Default: 2' },
		'economy.xp_per_voice_minute':    { type: 'number', min: 0, max: 100, step: 1, description: 'XP earned per minute spent in a voice channel. Set to 0 to disable voice XP. Default: 1' },
		'economy.gold_per_message':       { type: 'number', min: 0, max: 1000, step: 1, description: 'Gold earned per qualifying message. Set to 0 to disable gold from messages. Default: 1' },
		'economy.message_cooldown_seconds': { type: 'number', min: 0, max: 3600, step: 5, description: 'Minimum seconds between XP-earning messages per user. Prevents rapid-fire spam. 0 = no cooldown. Default: 60' },
		'economy.daily_xp_cap':           { type: 'number', min: 0, max: 100000, step: 50, description: 'Maximum XP a single user can earn per day. 0 = unlimited. Default: 500' },
		'economy.daily_gold_cap':         { type: 'number', min: 0, max: 100000, step: 10, description: 'Maximum gold a single user can earn per day. 0 = unlimited. Default: 100' },
		'economy.primary_currency_name':  { type: 'string', description: 'Display name for the primary currency shown throughout the dashboard. Default: "XP"' },
		'economy.secondary_currency_name': { type: 'string', description: 'Display name for the secondary currency shown throughout the dashboard. Default: "Gold"' },
		'anti_gaming.min_message_length':  { type: 'number', min: 0, max: 500, step: 1, description: 'Messages shorter than this (in characters) earn no XP. Prevents one-word spam. 0 = no minimum. Default: 5' },
		'anti_gaming.unique_reactor_threshold': { type: 'number', min: 1, max: 100, step: 1, description: 'Number of unique users who must react before the reaction gives full XP value. Prevents self-reaction farming. Default: 3' },
		'anti_gaming.diminishing_returns_after': { type: 'number', min: 1, max: 1000, step: 5, description: 'After this many messages in a day, XP per message starts decreasing. Discourages marathon grinding. Default: 50' },
		'quality.code_block_bonus':       { type: 'float', min: 0.0, max: 10.0, step: 0.1, description: 'Multiplier applied when a message contains a code block. 1.0 = no bonus. Default: 1.5' },
		'quality.link_bonus':             { type: 'float', min: 0.0, max: 10.0, step: 0.1, description: 'Multiplier applied when a message contains a link. 1.0 = no bonus. Default: 1.2' },
		'quality.long_message_threshold': { type: 'number', min: 10, max: 5000, step: 10, description: 'Character count that qualifies a message as "long" for the bonus multiplier. Default: 200' },
		'quality.long_message_bonus':     { type: 'float', min: 0.0, max: 10.0, step: 0.1, description: 'Multiplier applied to messages exceeding the long-message threshold. 1.0 = no bonus. Default: 1.3' },
		'announcements.achievement_channel_enabled': { type: 'boolean', description: 'When enabled, the bot posts announcement messages for level-ups and achievements. Default: On' },
		'announcements.leaderboard_public': { type: 'boolean', description: 'When enabled, the public leaderboard page is visible to all visitors. When off, only admins can see it. Default: On' },
		'display.favicon_url': { type: 'string', description: 'URL for the dashboard favicon image. Leave blank for the default ⚡ emoji.' },
		'display.primary_color': { type: 'string', description: 'Primary brand color hex code (e.g. #7c3aed). Used for accent elements.' },
		'display.dashboard_title': { type: 'string', description: 'Display name for the home page. Shown in the sidebar and page header. Default: "Community Dashboard"' },
		'display.leaderboard_title': { type: 'string', description: 'Display name for the leaderboard page. Shown in the sidebar and page header. Default: "Leaderboard"' },
		'display.activity_title': { type: 'string', description: 'Display name for the activity page. Shown in the sidebar and page header. Default: "Activity"' },
		'display.achievements_title': { type: 'string', description: 'Display name for the achievements page. Shown in the sidebar and page header. Default: "Achievements"' },
	};

	/** Infer type from a setting value if not in the metadata map */
	function inferMeta(s: AdminSetting): SettingMeta {
		if (SETTING_META[s.key]) return SETTING_META[s.key];
		if (typeof s.value === 'boolean') return { type: 'boolean' };
		if (typeof s.value === 'number') {
			return Number.isInteger(s.value)
				? { type: 'number', min: 0, max: 100000, step: 1 }
				: { type: 'float', min: 0, max: 100, step: 0.1 };
		}
		return { type: 'string' };
	}

	/** Human-friendly labels keyed to actual setting keys from the backend.
	 *  Uses reactive currency names so labels cascade when renamed. */
	const friendlyLabel = $derived.by(() => {
		const p = currency.primary;
		const s = currency.secondary;
		const map: Record<string, string> = {
			// Economy
			'economy.xp_per_message':         `Base ${p} per Message`,
			'economy.xp_per_reaction':        `Base ${p} per Reaction`,
			'economy.xp_per_voice_minute':    `Base ${p} per Voice Minute`,
			'economy.gold_per_message':       `Base ${s} per Message`,
			'economy.message_cooldown_seconds': 'Message Cooldown (sec)',
			'economy.daily_xp_cap':           `Daily ${p} Cap`,
			'economy.daily_gold_cap':         `Daily ${s} Cap`,
			'economy.primary_currency_name':  'Primary Currency Name',
			'economy.secondary_currency_name': 'Secondary Currency Name',
			// Anti-gaming
			'anti_gaming.min_message_length':        `Min Message Length for ${p}`,
			'anti_gaming.unique_reactor_threshold':   'Unique Reactors for Full Value',
			'anti_gaming.diminishing_returns_after':  'Diminishing Returns After (msgs)',
			// Quality
			'quality.code_block_bonus':        'Code Block Multiplier',
			'quality.link_bonus':              'Link Multiplier',
			'quality.long_message_threshold':  'Long Message Length (chars)',
			'quality.long_message_bonus':      'Long Message Multiplier',
			// Announcements
			'announcements.achievement_channel_enabled': 'Post Achievements & Level-Ups',
			'announcements.leaderboard_public':          'Public Leaderboard Visible',
		};
		return (key: string) => map[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
	});

	/** Category display config */
	const CATEGORY_META: Record<string, { icon: string; label: string; description: string; danger?: boolean }> = {
		economy:        { icon: '', label: 'Economy',         description: 'Currency rates, leveling curve, and daily caps' },
		anti_gaming:    { icon: '', label: 'Anti-Gaming',     description: 'Spam protection and reward throttling' },
		quality:        { icon: '', label: 'Quality',          description: 'Bonus multipliers for high-quality content' },
		announcements:  { icon: '', label: 'Announcements',   description: 'Achievement and level-up notification settings' },
		display:        { icon: '', label: 'Display',          description: 'Branding, titles, and UI settings' },
		setup:          { icon: '', label: 'Setup',            description: 'Bootstrap and initialization state (read-only)' },
		dangerous:      { icon: '', label: 'Danger Zone',     description: 'Settings that can significantly affect the game', danger: true },
	};

	async function load() {
		try {
			const res = await api.admin.getSettings();
			settings = res.settings;
			editedValues = {};
			for (const s of settings) {
				editedValues[s.key] = typeof s.value === 'string' ? s.value : JSON.stringify(s.value);
			}
		} catch (e) { flash.error('Failed to load settings'); }
		finally { loading = false; }
	}

	onMount(load);

	const categories = $derived([...new Set(settings.map((s) => s.category))].filter(c => c !== 'setup').sort());

	const filtered = $derived(
		filterCategory ? settings.filter((s) => s.category === filterCategory) : settings
	);

	/** Group settings by category */
	const grouped = $derived(() => {
		const groups: Record<string, AdminSetting[]> = {};
		for (const s of filtered) {
			const cat = s.category || 'other';
			if (!groups[cat]) groups[cat] = [];
			groups[cat].push(s);
		}
		return groups;
	});

	function hasChanged(key: string): boolean {
		const orig = settings.find((s) => s.key === key);
		if (!orig) return false;
		const origStr = typeof orig.value === 'string' ? orig.value : JSON.stringify(orig.value);
		return editedValues[key] !== origStr;
	}

	const changedCount = $derived(settings.filter((s) => hasChanged(s.key)).length);

	// ---------------------------------------------------------------------------
	// Toggle helpers for boolean settings
	// ---------------------------------------------------------------------------
	function toggleBoolean(key: string) {
		const current = editedValues[key];
		editedValues[key] = current === 'true' ? 'false' : 'true';
	}

	function getBooleanValue(key: string): boolean {
		return editedValues[key] === 'true';
	}

	// ---------------------------------------------------------------------------
	// Validation helpers
	// ---------------------------------------------------------------------------
	function getValidationError(key: string): string | null {
		const meta = SETTING_META[key];
		if (!meta || meta.type === 'string' || meta.type === 'boolean') return null;
		const val = Number(editedValues[key]);
		if (isNaN(val)) return 'Must be a number';
		if (meta.min !== undefined && val < meta.min) return `Minimum: ${meta.min}`;
		if (meta.max !== undefined && val > meta.max) return `Maximum: ${meta.max}`;
		return null;
	}

	const hasValidationErrors = $derived(
		settings.some((s) => getValidationError(s.key) !== null)
	);

	async function saveAll() {
		if (hasValidationErrors) {
			flash.error('Fix validation errors before saving');
			return;
		}

		const changed = settings
			.filter((s) => hasChanged(s.key))
			.map((s) => {
				let val: unknown;
				try { val = JSON.parse(editedValues[s.key]); } catch { val = editedValues[s.key]; }
				return { key: s.key, value: val, category: s.category };
			});

		if (changed.length === 0) { flash.info('No changes to save'); return; }
		saving = true;
		try {
			await api.admin.updateSettings(changed);
			flash.success(`${changed.length} setting(s) updated`);
			// Refresh the global currency labels so all UI updates instantly
			await currency.refresh();
			await load();
		} catch (e: any) { flash.error(e.message); }
		finally { saving = false; }
	}
</script>

<svelte:head><title>Admin: Settings — Synapse</title></svelte:head>

<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">Settings</h1>
		<p class="text-sm text-zinc-500 mt-1">Tune gameplay parameters and dashboard branding.</p>
	</div>
	<button class="btn-primary" onclick={saveAll} disabled={saving || changedCount === 0}>
		{#if saving}
			<span class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
			Saving…
		{:else}
			Save {changedCount} change{changedCount !== 1 ? 's' : ''}
		{/if}
	</button>
</div>

<!-- Category filter pills -->
<div class="flex flex-wrap gap-2 mb-6">
	<button
		class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
			{!filterCategory ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => { filterCategory = ''; history.replaceState(null, '', '/admin/settings'); }}
	>
		All ({settings.length})
	</button>
	{#each categories as cat}
		{@const meta = CATEGORY_META[cat]}
		{@const count = settings.filter((s) => s.category === cat).length}
		<button
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
				{filterCategory === cat ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
			onclick={() => { filterCategory = cat; history.replaceState(null, '', '/admin/settings'); }}
		>
			{meta?.label || capitalize(cat)} ({count})
		</button>
	{/each}
	<!-- Setup tab (embedded from former standalone page) -->
	<button
		class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all
			{filterCategory === '__setup__' ? 'bg-brand-600 text-white shadow-lg shadow-brand-500/20' : 'bg-surface-200 text-zinc-400 hover:text-zinc-200'}"
		onclick={() => { filterCategory = '__setup__'; history.replaceState(null, '', '/admin/settings?tab=setup'); }}
	>
		Setup
	</button>
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if filterCategory === '__setup__'}
	<!-- Embedded Setup Panel -->
	<div class="settings-group mb-6">
		<div class="settings-group-header flex items-center gap-3">
			
			<div>
				<h3 class="text-sm font-semibold text-zinc-200">Setup & Bootstrap</h3>
				<p class="text-xs text-zinc-500">Guild discovery, channel mapping, and initialization state</p>
			</div>
		</div>
		<div class="p-5">
			<SetupPanel />
		</div>
	</div>
{:else}
	{@const groups = grouped()}
	{#each Object.entries(groups) as [cat, catSettings] (cat)}
		{@const meta = CATEGORY_META[cat]}
		<div class="settings-group mb-6 {meta?.danger ? 'danger-zone' : ''}">
			<div class="settings-group-header flex items-center gap-3">
				
				<div>
					<h3 class="text-sm font-semibold text-zinc-200">{meta?.label || capitalize(cat)}</h3>
					{#if meta?.description}
						<p class="text-xs text-zinc-500">{meta.description}</p>
					{/if}
				</div>
				{#if meta?.danger}
					<span class="ml-auto badge bg-red-500/10 text-red-400 border border-red-500/20">⚠ Caution</span>
				{/if}
			</div>
			<div class="divide-y divide-surface-300/30">
				{#each catSettings as s (s.key)}
					{@const meta = inferMeta(s)}
					{@const validErr = getValidationError(s.key)}
					{@const desc = meta.description || SETTING_META[s.key]?.description || s.description}
					<div class="flex flex-col sm:flex-row sm:items-center gap-3 px-5 py-4 hover:bg-surface-200/30 transition-colors
						{hasChanged(s.key) ? 'bg-brand-500/5 border-l-2 border-l-brand-500' : ''}">
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-2">
								<span class="text-base font-medium text-zinc-200">{friendlyLabel(s.key)}</span>
								{#if hasChanged(s.key)}
									<span class="w-2 h-2 rounded-full bg-brand-400 animate-pulse"></span>
								{/if}
							</div>
							<div class="flex flex-col gap-0.5 mt-0.5">
								<code class="text-[10px] font-mono text-zinc-600">{s.key}</code>
								{#if desc}
									<span class="text-sm text-zinc-400">{desc}</span>
								{/if}
								{#if validErr}
									<span class="text-xs text-red-400">{validErr}</span>
								{/if}
							</div>
						</div>
						<div class="w-full sm:w-80 flex-shrink-0">
							{#if meta.type === 'boolean'}
								<!-- Toggle switch -->
								<button
									type="button"
									class="relative inline-flex h-7 w-12 items-center rounded-full transition-colors duration-200
										{getBooleanValue(s.key) ? 'bg-brand-600' : 'bg-surface-400'}"
									onclick={() => toggleBoolean(s.key)}
									role="switch"
									aria-checked={getBooleanValue(s.key)}								aria-label="Toggle {s.key}"								>
									<span
										class="inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition-transform duration-200
											{getBooleanValue(s.key) ? 'translate-x-6' : 'translate-x-1'}"
									></span>
								</button>
								<span class="ml-3 text-sm {getBooleanValue(s.key) ? 'text-brand-400' : 'text-zinc-500'}">
									{getBooleanValue(s.key) ? 'On' : 'Off'}
								</span>
							{:else if meta.type === 'number' || meta.type === 'float'}
								<!-- Constrained number input -->
								<input
									type="number"
									class="input text-sm font-mono {validErr ? 'border-red-500/50 focus:ring-red-500/40' : ''}"
									bind:value={editedValues[s.key]}
									min={meta.min}
									max={meta.max}
									step={meta.step}
								/>
							{:else}
								<!-- String text input -->
								<input
									class="input text-sm"
									bind:value={editedValues[s.key]}
								/>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/each}
{/if}
