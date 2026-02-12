<script lang="ts">
	interface Props {
		src: string;
		alt?: string;
		size?: number; /** px */
		ring?: boolean;
	}

	let { src, alt = 'avatar', size = 40, ring = true }: Props = $props();

	function handleError(event: Event) {
		const img = event.currentTarget as HTMLImageElement | null;
		if (!img) return;
		img.src = 'https://cdn.discordapp.com/embed/avatars/0.png';
	}
</script>

<img
	{src}
	{alt}
	width={size}
	height={size}
	class="rounded-full object-cover flex-shrink-0
		{ring ? 'ring-2 ring-brand-500/30' : ''}"
	style="width: {size}px; height: {size}px;"
	loading="lazy"
	onerror={handleError}
/>
