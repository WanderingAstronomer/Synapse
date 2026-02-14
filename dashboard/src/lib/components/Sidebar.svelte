<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { auth } from '$lib/stores/auth.svelte';
	import { siteSettings } from '$lib/stores/siteSettings.svelte';
	import { NAV_LINKS } from '$lib/constants';
	import { fly } from 'svelte/transition';

	// ---------------------------------------------------------------------------
	//  Mobile sidebar state
	// ---------------------------------------------------------------------------

	/** Whether the mobile sidebar overlay is open. */
	let mobileOpen = $state(false);

	export function open() { mobileOpen = true; }
	export function close() { mobileOpen = false; }

	// Close the sidebar overlay whenever the route changes
	$effect(() => {
		// Reading $page.url.pathname subscribes to route changes
		void $page.url.pathname;
		mobileOpen = false;
	});

	// ---------------------------------------------------------------------------
	//  Navigation links
	// ---------------------------------------------------------------------------

	// Slug → default label & icon for public pages
	const PUBLIC_DEFAULTS = NAV_LINKS.public;

	// Build public links using settings-based page titles
	let publicLinks = $derived(
		PUBLIC_DEFAULTS.map((def) => {
			const titleKey = `display.${def.slug}_title`;
			const settingsTitle = siteSettings.settings[titleKey] as string | undefined;
			return {
				href: def.href,
				label: (settingsTitle && settingsTitle.trim()) || def.label,
				icon: def.icon,
			};
		})
	);

	const adminLinks = NAV_LINKS.admin;

	// ---------------------------------------------------------------------------
	//  Health checks
	// ---------------------------------------------------------------------------

	type HealthStatus = 'checking' | 'online' | 'offline';
	let apiHealth = $state<HealthStatus>('checking');
	let botHealth = $state<HealthStatus>('checking');

	async function checkApiHealth() {
		try {
			const response = await fetch('/api/health', { cache: 'no-store' });
			apiHealth = response.ok ? 'online' : 'offline';
		} catch {
			apiHealth = 'offline';
		}
	}

	async function checkBotHealth() {
		try {
			const response = await fetch('/api/health/bot', { cache: 'no-store' });
			if (response.ok) {
				const data = await response.json();
				botHealth = data.status === 'online' ? 'online' : 'offline';
			} else {
				botHealth = 'offline';
			}
		} catch {
			botHealth = 'offline';
		}
	}

	onMount(() => {
		checkApiHealth();
		checkBotHealth();
		const intervalId = window.setInterval(() => {
			checkApiHealth();
			checkBotHealth();
		}, 30000);
		return () => window.clearInterval(intervalId);
	});

	function isActive(href: string, pathname: string): boolean {
		if (href === '/') return pathname === '/';
		return pathname.startsWith(href);
	}

	function handleBackdropClick() {
		mobileOpen = false;
	}

	function handleBackdropKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') mobileOpen = false;
	}
</script>

{#snippet sidebarContent()}
	<div class="flex flex-col h-full">
		<!-- Brand -->
		<div class="px-5 py-5 border-b border-surface-300">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2 flex-1 justify-center">
					<span class="text-xl font-bold text-white tracking-tight">Synapse</span>
				</div>
				<!-- Mobile close button -->
				<button
					class="lg:hidden -mr-1 p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-surface-200 transition-colors"
					onclick={() => (mobileOpen = false)}
					aria-label="Close sidebar"
				>
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<p class="text-xs text-zinc-500 mt-1 text-center">Dashboard</p>
		</div>

		<!-- Navigation -->
		<nav class="flex-1 overflow-y-auto px-3 py-4 space-y-1">
			<p class="px-3 text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">Public</p>
			{#each publicLinks as link}
				<a
					href={link.href}
					class="nav-link {isActive(link.href, $page.url.pathname) ? 'nav-link-active' : ''}"
				>
					{#if link.icon}<span class="text-base">{link.icon}</span>{/if}
					<span>{link.label}</span>
				</a>
			{/each}

			{#if auth.isAdmin}
				<hr class="border-surface-300 my-4" />
				<p class="px-3 text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">Admin</p>
				{#each adminLinks as link}
					<a
						href={link.href}
						class="nav-link {isActive(link.href, $page.url.pathname) ? 'nav-link-active' : ''}"
					>
						{#if link.icon}<span class="text-base">{link.icon}</span>{/if}
						<span>{link.label}</span>
					</a>
				{/each}
			{/if}
		</nav>

		<!-- Footer -->
		<div class="px-4 py-4 border-t border-surface-300">
			<div class="flex flex-wrap gap-2 mb-4 justify-center">
				<span class="inline-flex items-center gap-2 rounded-full border border-surface-300 px-3 py-1.5 text-xs text-zinc-300"
					role="status" aria-label={apiHealth === 'online' ? 'API Online' : apiHealth === 'offline' ? 'API Offline' : 'Checking API status'}>
					<span class="h-2 w-2 rounded-full {apiHealth === 'online' ? 'bg-emerald-400' : apiHealth === 'offline' ? 'bg-red-400' : 'bg-zinc-500'}"></span>
					{apiHealth === 'online' ? 'API Online' : apiHealth === 'offline' ? 'API Offline' : 'API Checking'}
				</span>
				<span class="inline-flex items-center gap-2 rounded-full border border-surface-300 px-3 py-1.5 text-xs text-zinc-300"
					role="status" aria-label={botHealth === 'online' ? 'Bot Online' : botHealth === 'offline' ? 'Bot Offline' : 'Checking Bot status'}>
					<span class="h-2 w-2 rounded-full {botHealth === 'online' ? 'bg-emerald-400' : botHealth === 'offline' ? 'bg-red-400' : 'bg-zinc-500'}"></span>
					{botHealth === 'online' ? 'Bot Online' : botHealth === 'offline' ? 'Bot Offline' : 'Bot Checking'}
				</span>
			</div>
		{#if auth.user}
			<div class="flex flex-col items-center text-center mb-4">
				<img
					src={auth.user.avatar
						? `https://cdn.discordapp.com/avatars/${auth.user.id}/${auth.user.avatar}.png?size=128`
						: `https://cdn.discordapp.com/embed/avatars/0.png`}
					alt="avatar"
					class="w-12 h-12 rounded-full ring-2 ring-brand-500/40 mb-2"
				/>
				<p class="text-base font-semibold text-zinc-100 truncate max-w-full">{auth.user.username}</p>
					<p class="text-xs text-brand-400 font-medium">Admin</p>
				</div>
				<button class="btn-secondary w-full text-sm justify-center" onclick={() => { auth.logout(); goto('/'); }}>
					Sign Out
				</button>
			{:else}
				<a href="/api/auth/login" class="btn-primary w-full text-xs justify-center">
					Admin Login
				</a>
			{/if}
		</div>
	</div>
{/snippet}

<!-- Desktop sidebar: always visible above lg breakpoint -->
<aside
	class="hidden lg:block sticky top-0 h-screen w-72 shrink-0 bg-surface-50 border-r border-surface-300"
>
	{@render sidebarContent()}
</aside>

<!-- Mobile sidebar: overlay + backdrop below lg breakpoint -->
{#if mobileOpen}
	<!-- Backdrop -->
	<div
		class="sidebar-backdrop"
		onclick={handleBackdropClick}
		onkeydown={handleBackdropKeydown}
		role="button"
		tabindex="-1"
		aria-label="Close sidebar"
		transition:fly={{ duration: 200, opacity: 0 }}
	></div>
	<!-- Sidebar panel -->
	<aside
		class="sidebar-mobile"
		transition:fly={{ x: -288, duration: 250 }}
	>
		{@render sidebarContent()}
	</aside>
{/if}
