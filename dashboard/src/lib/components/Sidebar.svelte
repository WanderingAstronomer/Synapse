<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { auth, isAdmin } from '$lib/stores/auth';

	const publicLinks = [
		{ href: '/', label: 'Overview', icon: '📊' },
		{ href: '/leaderboard', label: 'Leaderboard', icon: '🏆' },
		{ href: '/activity', label: 'Activity', icon: '⚡' },
		{ href: '/achievements', label: 'Achievements', icon: '🏅' },
	];

	const adminLinks = [
		{ href: '/admin/zones', label: 'Zones', icon: '🗺️' },
		{ href: '/admin/achievements', label: 'Achievements', icon: '🎖️' },
		{ href: '/admin/awards', label: 'Awards', icon: '🎁' },
		{ href: '/admin/settings', label: 'Settings', icon: '⚙️' },
		{ href: '/admin/audit', label: 'Audit Log', icon: '📋' },
	];

	interface Props {
		open?: boolean;
	}

	let { open = $bindable(true) }: Props = $props();

	type ApiHealth = 'checking' | 'online' | 'offline';
	let apiHealth = $state<ApiHealth>('checking');

	async function checkApiHealth() {
		try {
			const response = await fetch('/api/health', { cache: 'no-store' });
			apiHealth = response.ok ? 'online' : 'offline';
		} catch {
			apiHealth = 'offline';
		}
	}

	onMount(() => {
		checkApiHealth();
		const intervalId = window.setInterval(checkApiHealth, 30000);
		return () => window.clearInterval(intervalId);
	});

	function isActive(href: string, pathname: string): boolean {
		if (href === '/') return pathname === '/';
		return pathname.startsWith(href);
	}
</script>

<!-- Mobile overlay -->
{#if open}
	<button
		class="fixed inset-0 bg-black/50 z-30 lg:hidden"
		onclick={() => (open = false)}
		aria-label="Close sidebar"
	></button>
{/if}

<aside
	class="fixed top-0 left-0 z-40 h-screen w-64 bg-surface-50 border-r border-surface-300
		transform transition-transform duration-200 ease-in-out
		{open ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 lg:static lg:z-auto"
>
	<div class="flex flex-col h-full">
		<!-- Brand -->
		<div class="px-5 py-5 border-b border-surface-300">
			<div class="flex items-center gap-2">
				<span class="text-xl">⚡</span>
				<span class="text-lg font-bold text-white tracking-tight">Synapse</span>
			</div>
			<p class="text-xs text-zinc-500 mt-1">Dashboard</p>
		</div>

		<!-- Navigation -->
		<nav class="flex-1 overflow-y-auto px-3 py-4 space-y-1">
			<p class="px-3 text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">Public</p>
			{#each publicLinks as link}
				<a
					href={link.href}
					class="nav-link {isActive(link.href, $page.url.pathname) ? 'nav-link-active' : ''}"
					onclick={() => { if (window.innerWidth < 1024) open = false; }}
				>
					<span class="text-base">{link.icon}</span>
					<span>{link.label}</span>
				</a>
			{/each}

			{#if $isAdmin}
				<hr class="border-surface-300 my-4" />
				<p class="px-3 text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">Admin</p>
				{#each adminLinks as link}
					<a
						href={link.href}
						class="nav-link {isActive(link.href, $page.url.pathname) ? 'nav-link-active' : ''}"
						onclick={() => { if (window.innerWidth < 1024) open = false; }}
					>
						<span class="text-base">{link.icon}</span>
						<span>{link.label}</span>
					</a>
				{/each}
			{/if}
		</nav>

		<!-- Footer -->
		<div class="px-4 py-4 border-t border-surface-300">
			<div class="mb-3">
				<span class="inline-flex items-center gap-1.5 rounded-full border border-surface-300 px-2 py-1 text-[10px] text-zinc-400">
					<span class="h-1.5 w-1.5 rounded-full {apiHealth === 'online' ? 'bg-emerald-400' : apiHealth === 'offline' ? 'bg-red-400' : 'bg-zinc-500'}"></span>
					{apiHealth === 'online' ? 'API Online' : apiHealth === 'offline' ? 'API Offline' : 'API Checking'}
				</span>
			</div>
			{#if $auth}
				<div class="flex items-center gap-3 mb-3">
					<img
						src={$auth.avatar
							? `https://cdn.discordapp.com/avatars/${$auth.id}/${$auth.avatar}.png?size=64`
							: `https://cdn.discordapp.com/embed/avatars/0.png`}
						alt="avatar"
						class="w-8 h-8 rounded-full ring-2 ring-brand-500/40"
					/>
					<div class="min-w-0">
						<p class="text-sm font-medium text-zinc-200 truncate">{$auth.username}</p>
						<p class="text-[10px] text-brand-400">Admin</p>
					</div>
				</div>
				<button class="btn-secondary w-full text-xs justify-center" onclick={() => auth.logout()}>
					Sign Out
				</button>
			{:else}
				<a href="/api/auth/login" class="btn-primary w-full text-xs justify-center">
					🔒 Admin Login
				</a>
			{/if}
		</div>
	</div>
</aside>
