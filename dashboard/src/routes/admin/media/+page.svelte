<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type MediaFileItem } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';

	let files = $state<MediaFileItem[]>([]);
	let loading = $state(true);
	let uploading = $state(false);
	let dragOver = $state(false);

	async function load() {
		try {
			const res = await api.admin.getMedia();
			files = res.files;
		} catch (e) {
			flash.error('Failed to load media');
		} finally {
			loading = false;
		}
	}

	onMount(load);

	async function uploadFiles(fileList: FileList | File[]) {
		uploading = true;
		let count = 0;
		for (const file of fileList) {
			try {
				await api.admin.uploadMedia(file);
				count++;
			} catch (e: any) {
				flash.error(`${file.name}: ${e.message || 'Upload failed'}`);
			}
		}
		if (count > 0) {
			flash.success(`Uploaded ${count} file${count > 1 ? 's' : ''}`);
			await load();
		}
		uploading = false;
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		if (input.files?.length) uploadFiles(input.files);
		input.value = '';
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
	}

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		dragOver = true;
	}

	async function deleteFile(f: MediaFileItem) {
		if (!confirm(`Delete "${f.original_name}"? Any references to this image will break.`)) return;
		try {
			await api.admin.deleteMedia(f.id);
			flash.success('Deleted');
			await load();
		} catch (e: any) { flash.error(e.message); }
	}

	function copyUrl(url: string) {
		navigator.clipboard.writeText(url);
		flash.success('URL copied to clipboard');
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}
</script>

<svelte:head><title>Admin: Media — Synapse</title></svelte:head>

<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">Media</h1>
		<p class="text-sm text-zinc-500 mt-1">Upload and manage images for badges, cards, and more.</p>
	</div>
	<label class="btn-primary cursor-pointer">
		{uploading ? 'Uploading...' : 'Upload Image'}
		<input type="file" accept="image/*" multiple class="hidden" onchange={handleFileInput} disabled={uploading} />
	</label>
</div>

<!-- Drop zone -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="border-2 border-dashed rounded-xl p-8 mb-6 text-center transition-colors duration-200
		{dragOver ? 'border-brand-400 bg-brand-400/5' : 'border-surface-300 hover:border-surface-200'}"
	ondrop={handleDrop}
	ondragover={handleDragOver}
	ondragleave={() => dragOver = false}
>
	<p class="text-zinc-400 text-sm">
		{uploading ? 'Uploading...' : 'Drag & drop images here, or click Upload above'}
	</p>
	<p class="text-zinc-600 text-xs mt-1">PNG, JPG, GIF, WebP, SVG · Max 2 MB each</p>
</div>

{#if loading}
	<div class="flex items-center justify-center h-48">
		<SynapseLoader text="Loading media..." />
	</div>
{:else if files.length === 0}
	<EmptyState title="No media" description="Upload your first image to get started." />
{:else}
	<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
		{#each files as f (f.id)}
			<div class="group card !p-0 overflow-hidden relative">
				<div class="aspect-square bg-surface-200 flex items-center justify-center overflow-hidden">
					<img
						src={f.url}
						alt={f.alt_text || f.original_name}
						class="w-full h-full object-contain"
						loading="lazy"
					/>
				</div>
				<div class="p-2">
					<p class="text-xs text-zinc-300 truncate" title={f.original_name}>{f.original_name}</p>
					<p class="text-[10px] text-zinc-600">{formatSize(f.size_bytes)}</p>
				</div>
				<!-- Hover actions -->
				<div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity
					flex flex-col items-center justify-center gap-2">
					<button class="btn-secondary !text-xs !px-3 !py-1" onclick={() => copyUrl(f.url)}>Copy URL</button>
					<button class="btn-danger !text-xs !px-3 !py-1" onclick={() => deleteFile(f)}>Delete</button>
				</div>
			</div>
		{/each}
	</div>
{/if}
