<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, type SetupStatus, type BootstrapResult } from '$lib/api';
	import { flash } from '$lib/stores/flash';

	let status = $state<SetupStatus | null>(null);
	let result = $state<BootstrapResult | null>(null);
	let loading = $state(true);
	let bootstrapping = $state(false);
	let error = $state<string | null>(null);
	let botStatus = $state<'checking' | 'online' | 'offline'>('checking');

	async function loadStatus() {
		loading = true;
		error = null;
		try {
			status = await api.admin.getSetupStatus();
		} catch (e: any) {
			error = e.message || 'Failed to load setup status';
		} finally {
			loading = false;
		}
	}

	async function checkBot() {
		try {
			const res = await fetch('/api/health/bot', { cache: 'no-store' });
			if (res.ok) {
				const data = await res.json();
				botStatus = data.status === 'online' ? 'online' : 'offline';
			} else {
				botStatus = 'offline';
			}
		} catch {
			botStatus = 'offline';
		}
	}

	onMount(() => {
		loadStatus();
		checkBot();
	});

	async function runBootstrap() {
		bootstrapping = true;
		error = null;
		try {
			result = await api.admin.runBootstrap();
			// Refresh status
			status = await api.admin.getSetupStatus();
			flash.success('Guild bootstrap complete!');
		} catch (e: any) {
			error = e.message || 'Bootstrap failed';
		} finally {
			bootstrapping = false;
		}
	}

	function continueToAdmin() {
		goto('/admin/zones');
	}
</script>

<svelte:head>
	<title>Setup · Synapse</title>
</svelte:head>

<div class="py-12 px-4">
	<div class="text-center mb-8">
		<span class="text-5xl mb-4 block">⚡</span>
		<h1 class="text-2xl font-bold text-white mb-2">Synapse Setup</h1>
		<p class="text-sm text-zinc-400">
			Auto-discover your Discord server structure and initialize zones, channels, and settings.
		</p>
	</div>

	{#if loading}
		<div class="flex justify-center py-12">
			<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
		</div>
	{:else if error}
		<div class="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6">
			<p class="text-red-400 text-sm">{error}</p>
		</div>
	{/if}

	{#if status && !loading}
		<!-- Guild Snapshot Status -->
		<div class="bg-surface-50 border border-surface-300 rounded-lg p-6 mb-6">
			<h2 class="text-lg font-semibold text-white mb-4">Guild Snapshot</h2>
			{#if status.has_guild_snapshot && status.guild_snapshot}
				<div class="grid grid-cols-2 gap-4 text-sm">
					<div>
						<span class="text-zinc-400">Server</span>
						<p class="text-white font-medium">{status.guild_snapshot.guild_name}</p>
					</div>
					<div>
						<span class="text-zinc-400">Channels Detected</span>
						<p class="text-white font-medium">{status.guild_snapshot.channel_count}</p>
					</div>
					<div>
						<span class="text-zinc-400">Snapshot Captured</span>
						<p class="text-white font-medium">
							{new Date(status.guild_snapshot.captured_at).toLocaleString()}
						</p>
					</div>
					<div>
						<span class="text-zinc-400">Status</span>
						<p class="text-emerald-400 font-medium">Ready</p>
					</div>
				</div>
			{:else}
				<div class="text-center py-4">
					<span class="text-3xl mb-2 block">🔌</span>
					<p class="text-zinc-400 text-sm">
						No guild snapshot found. The Synapse bot must connect to your Discord server
						at least once before setup can run.
					</p>

					<!-- Bot status indicator -->
					<div class="flex items-center justify-center gap-2 mt-4 mb-3">
						<span class="inline-flex items-center gap-1.5 rounded-full border border-surface-300 px-3 py-1.5 text-xs text-zinc-400">
							<span class="h-2 w-2 rounded-full {botStatus === 'online' ? 'bg-emerald-400' : botStatus === 'offline' ? 'bg-red-400' : 'bg-zinc-500'}"></span>
							{botStatus === 'online' ? 'Bot Online' : botStatus === 'offline' ? 'Bot Offline' : 'Checking Bot...'}
						</span>
					</div>

					{#if botStatus === 'offline'}
						<div class="text-left bg-surface-200/50 rounded-lg p-4 mt-3 text-xs text-zinc-400 space-y-1">
							<p class="font-semibold text-zinc-300 mb-2">Troubleshooting</p>
							<p>1. Verify the bot is running (check Docker logs or terminal output)</p>
							<p>2. Confirm the <code class="text-brand-400">DISCORD_TOKEN</code> env variable is set correctly</p>
							<p>3. Ensure <code class="text-brand-400">guild_id</code> in config.yaml matches your Discord server</p>
							<p>4. Check that the bot has been invited with proper permissions</p>
						</div>
					{/if}

					<button
						class="btn-secondary mt-4 text-sm"
						onclick={() => { loadStatus(); checkBot(); }}
					>
						🔄 Refresh Status
					</button>
				</div>
			{/if}
		</div>

		<!-- Bootstrap Action -->
		{#if status.has_guild_snapshot}
			<div class="bg-surface-50 border border-surface-300 rounded-lg p-6 mb-6">
				<h2 class="text-lg font-semibold text-white mb-2">
					{status.initialized ? 'Re-run Bootstrap' : 'Run Bootstrap'}
				</h2>
				<p class="text-sm text-zinc-400 mb-4">
					{#if status.initialized}
						Bootstrap has already run. Re-running is safe — it will only add new zones
						and channels without duplicating existing ones.
					{:else}
						This will create zones from your Discord categories, map channels to zones,
						create a default season, and set up baseline settings.
					{/if}
				</p>
				<button
					onclick={runBootstrap}
					disabled={bootstrapping}
					class="btn-primary w-full disabled:opacity-50"
				>
					{#if bootstrapping}
						<span class="inline-flex items-center gap-2">
							<span class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
							Running Bootstrap…
						</span>
					{:else}
						{status.initialized ? '🔄 Re-run Bootstrap' : '🚀 Run Bootstrap'}
					{/if}
				</button>
			</div>
		{/if}

		<!-- Bootstrap Result -->
		{#if result}
			<div class="bg-surface-50 border border-surface-300 rounded-lg p-6 mb-6">
				<h2 class="text-lg font-semibold text-white mb-4">Bootstrap Results</h2>
				<div class="grid grid-cols-2 gap-3 text-sm mb-4">
					<div class="bg-surface-100 rounded p-3">
						<span class="text-zinc-400 text-xs">Zones Created</span>
						<p class="text-white font-bold text-lg">{result.zones_created}</p>
					</div>
					<div class="bg-surface-100 rounded p-3">
						<span class="text-zinc-400 text-xs">Zones Existing</span>
						<p class="text-zinc-300 font-bold text-lg">{result.zones_existing}</p>
					</div>
					<div class="bg-surface-100 rounded p-3">
						<span class="text-zinc-400 text-xs">Channels Mapped</span>
						<p class="text-white font-bold text-lg">{result.channels_mapped}</p>
					</div>
					<div class="bg-surface-100 rounded p-3">
						<span class="text-zinc-400 text-xs">Channels Existing</span>
						<p class="text-zinc-300 font-bold text-lg">{result.channels_existing}</p>
					</div>
					<div class="bg-surface-100 rounded p-3">
						<span class="text-zinc-400 text-xs">Season Created</span>
						<p class="text-white font-bold text-lg">{result.season_created ? 'Yes' : 'No'}</p>
					</div>
					<div class="bg-surface-100 rounded p-3">
						<span class="text-zinc-400 text-xs">Settings Written</span>
						<p class="text-white font-bold text-lg">{result.settings_written}</p>
					</div>
				</div>

				{#if result.warnings.length > 0}
					<div class="bg-yellow-500/10 border border-yellow-500/30 rounded p-3">
						<p class="text-yellow-400 text-xs font-semibold mb-1">Warnings</p>
						{#each result.warnings as warning}
							<p class="text-yellow-300 text-xs">{warning}</p>
						{/each}
					</div>
				{/if}
			</div>

			<button onclick={continueToAdmin} class="btn-primary w-full">
				Continue to Admin Dashboard →
			</button>
		{/if}

		<!-- Already initialized — skip link -->
		{#if status.initialized && !result}
			<div class="text-center mt-4">
				<button onclick={continueToAdmin} class="text-sm text-brand-400 hover:text-brand-300 underline">
					Skip — go to Admin Dashboard
				</button>
			</div>
		{/if}
	{/if}
</div>
