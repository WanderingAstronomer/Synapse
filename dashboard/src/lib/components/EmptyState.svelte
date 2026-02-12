<script lang="ts">
	interface Props {
		icon?: string;
		title?: string;
		description?: string;
	}

	let { icon = '🔍', title = 'Nothing here yet', description = 'Data will appear once there is activity.' }: Props = $props();
</script>

<div class="flex flex-col items-center justify-center py-16 text-center animate-fade-in">
	<span class="text-5xl mb-4 opacity-60">{icon}</span>
	<h3 class="text-lg font-semibold text-zinc-300">{title}</h3>
	<p class="text-sm text-zinc-500 mt-1 max-w-md">{description}</p>
</div>
