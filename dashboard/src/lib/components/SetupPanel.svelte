<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type SetupStatus, type BootstrapResult } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';

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
			status = await api.admin.getSetupStatus();
			flash.success('Guild bootstrap complete!');
		} catch (e: any) {
			error = e.message || 'Bootstrap failed';
		} finally {
			bootstrapping = false;
		}
	}
</script>

{#if error}
	<div class="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-4">
		<p class="text-red-400 text-sm">{error}</p>
	</div>
{/if}

{#if loading}
	<div class="flex justify-center py-8">
		<div class="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
	</div>
{:else if status}
	<!-- Guild Snapshot Status -->
	<div class="bg-surface-200/30 border border-surface-300 rounded-lg p-5 mb-4">
		<h4 class="text-sm font-semibold text-zinc-200 mb-3">Guild Snapshot</h4>
		{#if status.has_guild_snapshot && status.guild_snapshot}
			<div class="grid grid-cols-2 gap-4 text-sm">
				<div>
					<span class="text-zinc-400 text-xs">Server</span>
					<p class="text-white font-medium">{status.guild_snapshot.guild_name}</p>
				</div>
				<div>
					<span class="text-zinc-400 text-xs">Channels Detected</span>
					<p class="text-white font-medium">{status.guild_snapshot.channel_count}</p>
				</div>
				<div>
					<span class="text-zinc-400 text-xs">Snapshot Captured</span>
					<p class="text-white font-medium">
						{new Date(status.guild_snapshot.captured_at).toLocaleString()}
					</p>
				</div>
				<div>
					<span class="text-zinc-400 text-xs">Status</span>
					<p class="{status.initialized ? 'text-emerald-400' : 'text-amber-400'} font-medium">
						{status.initialized ? '✓ Initialized' : 'Awaiting Bootstrap'}
					</p>
				</div>
			</div>
		{:else}
			<div class="text-center py-4">
				
				<p class="text-zinc-400 text-sm">
					No guild snapshot found. The bot must connect to your Discord server first.
				</p>
				<div class="flex items-center justify-center gap-2 mt-3 mb-2">
					<span class="inline-flex items-center gap-2 rounded-full border border-surface-300 px-3 py-1.5 text-xs text-zinc-400">
						<span class="h-2 w-2 rounded-full {botStatus === 'online' ? 'bg-emerald-400' : botStatus === 'offline' ? 'bg-red-400' : 'bg-zinc-500'}"></span>
						{botStatus === 'online' ? 'Bot Online' : botStatus === 'offline' ? 'Bot Offline' : 'Checking...'}
					</span>
				</div>
				{#if botStatus === 'offline'}
					<div class="text-left bg-surface-200/50 rounded-lg p-3 mt-3 text-xs text-zinc-400 space-y-1">
						<p class="font-semibold text-zinc-300 mb-2">Troubleshooting</p>
						<p>1. Verify the bot is running (check Docker logs)</p>
						<p>2. Confirm <code class="text-brand-400">DISCORD_TOKEN</code> is set</p>
						<p>3. Ensure <code class="text-brand-400">guild_id</code> matches your server</p>
						<p>4. Check bot permissions</p>
					</div>
				{/if}
				<button class="btn-secondary mt-3 text-xs" onclick={() => { loadStatus(); checkBot(); }}>
					Refresh
				</button>
			</div>
		{/if}
	</div>

	<!-- Bootstrap Action -->
	{#if status.has_guild_snapshot}
		<div class="bg-surface-200/30 border border-surface-300 rounded-lg p-5 mb-4">
			<h4 class="text-sm font-semibold text-zinc-200 mb-1">
				{status.initialized ? 'Re-run Bootstrap' : 'Run Bootstrap'}
			</h4>
			<p class="text-xs text-zinc-400 mb-3">
				{#if status.initialized}
				Safe to re-run — only adds new channels without duplicating existing ones.
			{:else}
				Sync channels from Discord, create a season, and write default settings.
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
					{status.initialized ? 'Re-run Bootstrap' : 'Run Bootstrap'}
				{/if}
			</button>
		</div>
	{/if}

	<!-- Bootstrap Result -->
	{#if result}
		<div class="bg-surface-200/30 border border-surface-300 rounded-lg p-5">
			<h4 class="text-sm font-semibold text-zinc-200 mb-3">Bootstrap Results</h4>
			<div class="grid grid-cols-2 gap-3 text-sm">
				<div class="bg-surface-100 rounded p-3 text-center">
					<span class="text-zinc-400 text-[10px] uppercase tracking-wider">Channels Synced</span>
					<p class="text-white font-bold text-lg">{result.channels_synced}</p>
				</div>
				<div class="bg-surface-100 rounded p-3 text-center">
					<span class="text-zinc-400 text-[10px] uppercase tracking-wider">Settings Written</span>
					<p class="text-white font-bold text-lg">{result.settings_written}</p>
				</div>
			</div>
			{#if result.warnings.length > 0}
				<div class="bg-yellow-500/10 border border-yellow-500/30 rounded p-3 mt-3">
					<p class="text-yellow-400 text-xs font-semibold mb-1">Warnings</p>
					{#each result.warnings as warning}
						<p class="text-yellow-300 text-xs">{warning}</p>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
{/if}
