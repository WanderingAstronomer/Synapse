<script lang="ts">
	interface Props {
		icon?: string;
		title?: string;
		description?: string;
		action?: { label: string; onclick: () => void } | null;
		variant?: 'default' | 'hero';
	}

	let {
		icon = '🔍',
		title = 'Nothing here yet',
		description = 'Data will appear once there is activity.',
		action = null,
		variant = 'default',
	}: Props = $props();
</script>

{#if variant === 'hero'}
	<div class="relative overflow-hidden rounded-2xl border border-surface-300 bg-gradient-to-br from-brand-950/50 via-surface-100 to-surface-100 p-12 text-center animate-fade-in">
		<!-- Decorative background -->
		<div class="absolute inset-0 opacity-5">
			<div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full bg-brand-500 blur-3xl"></div>
		</div>
		<div class="relative z-10">
			<span class="text-6xl mb-6 block animate-float">{icon}</span>
			<h3 class="text-xl font-bold text-white mb-2">{title}</h3>
			<p class="text-sm text-zinc-400 max-w-lg mx-auto mb-6">{description}</p>
			{#if action}
				<button class="btn-primary text-sm" onclick={action.onclick}>
					{action.label}
				</button>
			{/if}
		</div>
	</div>
{:else}
	<div class="flex flex-col items-center justify-center py-16 text-center animate-fade-in">
		<div class="w-20 h-20 rounded-2xl bg-surface-200 border border-surface-300 flex items-center justify-center mb-4">
			<span class="text-4xl">{icon}</span>
		</div>
		<h3 class="text-lg font-semibold text-zinc-300">{title}</h3>
		<p class="text-sm text-zinc-500 mt-1 max-w-md">{description}</p>
		{#if action}
			<button class="btn-primary mt-4 text-sm" onclick={action.onclick}>
				{action.label}
			</button>
		{/if}
	</div>
{/if}
