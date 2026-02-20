<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type MediaFileItem, type MediaFolder } from '$lib/api';
	import { flash } from '$lib/stores/flash.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SynapseLoader from '$lib/components/SynapseLoader.svelte';

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------
	let folders = $state<MediaFolder[]>([]);
	let files = $state<MediaFileItem[]>([]);
	let loading = $state(true);
	let uploading = $state(false);
	let dragOver = $state(false);

	/** null = "All Files" root view */
	let selectedFolderId = $state<number | null>(null);

	// Folder management UI
	let creatingFolder = $state(false);
	let newFolderName = $state('');
	let newFolderParentId = $state<number | null>(null);
	let renamingFolderId = $state<number | null>(null);
	let renamingFolderName = $state('');

	// ---------------------------------------------------------------------------
	// Data loading
	// ---------------------------------------------------------------------------
	async function loadFolders() {
		try {
			const res = await api.admin.listFolders();
			folders = res.folders;
		} catch {
			flash.error('Failed to load folders');
		}
	}

	async function loadFiles() {
		try {
			const res = await api.admin.getMedia(selectedFolderId);
			files = res.files;
		} catch {
			flash.error('Failed to load media');
		}
	}

	async function load() {
		loading = true;
		await Promise.all([loadFolders(), loadFiles()]);
		loading = false;
	}

	onMount(load);

	// ---------------------------------------------------------------------------
	// Folder tree helpers
	// ---------------------------------------------------------------------------
	function rootFolders(): MediaFolder[] {
		return folders.filter((f) => f.parent_id === null).sort((a, b) => a.name.localeCompare(b.name));
	}

	function childFolders(parentId: number): MediaFolder[] {
		return folders.filter((f) => f.parent_id === parentId).sort((a, b) => a.name.localeCompare(b.name));
	}

	function selectedFolderName(): string {
		if (selectedFolderId === null) return 'All Files';
		return folders.find((f) => f.id === selectedFolderId)?.name ?? 'Folder';
	}

	// ---------------------------------------------------------------------------
	// Folder actions
	// ---------------------------------------------------------------------------
	async function submitCreateFolder() {
		if (!newFolderName.trim()) return;
		try {
			await api.admin.createFolder({ name: newFolderName.trim(), parent_id: newFolderParentId });
			flash.success(`Folder "${newFolderName.trim()}" created`);
			newFolderName = '';
			creatingFolder = false;
			await loadFolders();
		} catch (e: any) {
			flash.error(e.message || 'Failed to create folder');
		}
	}

	async function submitRenameFolder(folderId: number) {
		if (!renamingFolderName.trim()) return;
		try {
			await api.admin.renameFolder(folderId, renamingFolderName.trim());
			flash.success('Folder renamed');
			renamingFolderId = null;
			await loadFolders();
		} catch (e: any) {
			flash.error(e.message || 'Failed to rename folder');
		}
	}

	async function deleteFolder(folder: MediaFolder) {
		if (!confirm(`Delete folder "${folder.name}"? It must be empty.`)) return;
		try {
			await api.admin.deleteFolder(folder.id);
			flash.success(`Folder "${folder.name}" deleted`);
			if (selectedFolderId === folder.id) selectedFolderId = null;
			await Promise.all([loadFolders(), loadFiles()]);
		} catch (e: any) {
			flash.error(e.message || 'Failed to delete folder');
		}
	}

	function startRename(folder: MediaFolder) {
		renamingFolderId = folder.id;
		renamingFolderName = folder.name;
	}

	// ---------------------------------------------------------------------------
	// File upload
	// ---------------------------------------------------------------------------
	async function uploadFiles(fileList: FileList | File[]) {
		uploading = true;
		let count = 0;
		for (const file of fileList) {
			try {
				await api.admin.uploadMedia(file, selectedFolderId);
				count++;
			} catch (e: any) {
				flash.error(`${file.name}: ${e.message || 'Upload failed'}`);
			}
		}
		if (count > 0) {
			flash.success(`Uploaded ${count} file${count > 1 ? 's' : ''}`);
			await loadFiles();
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

	// ---------------------------------------------------------------------------
	// File actions
	// ---------------------------------------------------------------------------
	async function deleteFile(f: MediaFileItem) {
		if (!confirm(`Delete "${f.original_name}"? Any references to this image will break.`)) return;
		try {
			await api.admin.deleteMedia(f.id);
			flash.success('Deleted');
			await loadFiles();
		} catch (e: any) {
			flash.error(e.message);
		}
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

	// ---------------------------------------------------------------------------
	// Sidebar Resizing
	// ---------------------------------------------------------------------------
	let sidebarWidth = $state(224); // Default 56 * 4 = 224px
	let isResizing = $state(false);

	onMount(() => {
		const saved = localStorage.getItem('synapse_media_sidebar_w');
		if (saved) {
			const w = parseInt(saved, 10);
			if (!isNaN(w) && w >= 160 && w <= 400) {
				sidebarWidth = w;
			}
		}
	});

	function startResize(e: MouseEvent) {
		e.preventDefault();
		isResizing = true;
		document.body.style.cursor = 'col-resize';
		document.body.style.userSelect = 'none';
		
		const onMouseMove = (moveEvent: MouseEvent) => {
			if (!isResizing) return;
			// Calculate new width based on mouse position relative to the left edge of the container
			// We'll just use movementX for simplicity, assuming the sidebar is on the left
			let newWidth = sidebarWidth + moveEvent.movementX;
			if (newWidth < 160) newWidth = 160;
			if (newWidth > 400) newWidth = 400;
			sidebarWidth = newWidth;
		};
		
		const onMouseUp = () => {
			isResizing = false;
			document.body.style.cursor = '';
			document.body.style.userSelect = '';
			localStorage.setItem('synapse_media_sidebar_w', sidebarWidth.toString());
			document.removeEventListener('mousemove', onMouseMove);
			document.removeEventListener('mouseup', onMouseUp);
		};
		
		document.addEventListener('mousemove', onMouseMove);
		document.addEventListener('mouseup', onMouseUp);
	}

	// Re-load files when the selected folder changes (but not on initial load)
	let _initialized = false;
	$effect(() => {
		void selectedFolderId; // track dependency
		if (_initialized) loadFiles();
		else _initialized = true;
	});
</script>

<svelte:head><title>Admin: Media — Synapse</title></svelte:head>

<!-- Page header -->
<div class="flex items-center justify-between mb-6">
	<div>
		<h1 class="text-2xl font-bold text-white">Media</h1>
		<p class="text-sm text-zinc-500 mt-1">Manage images, SVGs, and other assets.</p>
	</div>
	<label class="btn-primary cursor-pointer">
		{uploading ? 'Uploading...' : 'Upload'}
		<input type="file" accept="image/*" multiple class="hidden" onchange={handleFileInput} disabled={uploading} />
	</label>
</div>

{#if loading}
	<div class="flex items-center justify-center h-64">
		<SynapseLoader text="Loading media library..." />
	</div>
{:else}
	<div class="flex gap-4 h-[calc(100vh-14rem)]" style="--sidebar-w: {sidebarWidth}px;">
		<!-- ----------------------------------------------------------------- -->
		<!-- Left panel — folder tree -->
		<!-- ----------------------------------------------------------------- -->
		<aside class="shrink-0 flex flex-col gap-1 overflow-y-auto pr-1" style="width: var(--sidebar-w);">
			<!-- All files root node -->
			<button
				class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors w-full text-left
					{selectedFolderId === null
						? 'bg-brand-500/20 text-brand-300 font-medium'
						: 'text-zinc-400 hover:text-zinc-200 hover:bg-surface-200'}"
				onclick={() => (selectedFolderId = null)}
			>
				<svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
						d="M4 6h16M4 10h16M4 14h16M4 18h16" />
				</svg>
				All Files
			</button>

			<!-- Root-level folders -->
			{#each rootFolders() as folder (folder.id)}
				{@const isSelected = selectedFolderId === folder.id}
				{@const renaming = renamingFolderId === folder.id}

				<div class="group">
					{#if renaming}
						<form
							class="flex gap-1 px-2"
							onsubmit={(e) => { e.preventDefault(); submitRenameFolder(folder.id); }}
						>
							<input
								class="input flex-1 text-xs !py-1"
								bind:value={renamingFolderName}
								onblur={() => (renamingFolderId = null)}
							/>
						</form>
					{:else}
						<div class="flex items-center gap-1">
							<button
								class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors flex-1 text-left truncate
									{isSelected
										? 'bg-brand-500/20 text-brand-300 font-medium'
										: 'text-zinc-400 hover:text-zinc-200 hover:bg-surface-200'}"
								onclick={() => (selectedFolderId = folder.id)}
							>
								<svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
										d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
								</svg>
								<span class="truncate">{folder.name}</span>
							</button>
							<div class="opacity-0 group-hover:opacity-100 flex gap-0.5 pr-1 shrink-0">
								<button class="p-1 text-zinc-500 hover:text-zinc-200 rounded" title="Rename"
									onclick={() => startRename(folder)}>
									<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
											d="M15.232 5.232l3.536 3.536M9 13l6.293-6.293a1 1 0 011.414 0l1.586 1.586a1 1 0 010 1.414L12 16H9v-3z" />
									</svg>
								</button>
								<button class="p-1 text-zinc-500 hover:text-red-400 rounded" title="Delete (must be empty)"
									onclick={() => deleteFolder(folder)}>
									<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
											d="M6 18L18 6M6 6l12 12" />
									</svg>
								</button>
							</div>
						</div>

						<!-- Sub-folders (one level deep) -->
						{#each childFolders(folder.id) as child (child.id)}
							{@const childSelected = selectedFolderId === child.id}
							{@const childRenaming = renamingFolderId === child.id}
							<div class="group/child ml-4">
								{#if childRenaming}
									<form
										class="flex gap-1 px-2"
										onsubmit={(e) => { e.preventDefault(); submitRenameFolder(child.id); }}
									>
										<input
											class="input flex-1 text-xs !py-1"
											bind:value={renamingFolderName}
											onblur={() => (renamingFolderId = null)}
										/>
									</form>
								{:else}
									<div class="flex items-center gap-1">
										<button
											class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors flex-1 text-left truncate
												{childSelected
													? 'bg-brand-500/20 text-brand-300 font-medium'
													: 'text-zinc-500 hover:text-zinc-300 hover:bg-surface-200'}"
											onclick={() => (selectedFolderId = child.id)}
										>
											<svg class="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
													d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
											</svg>
											<span class="truncate">{child.name}</span>
										</button>
										<div class="opacity-0 group-hover/child:opacity-100 flex gap-0.5 pr-1 shrink-0">
											<button class="p-1 text-zinc-500 hover:text-zinc-200 rounded" title="Rename"
												onclick={() => startRename(child)}>
												<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
														d="M15.232 5.232l3.536 3.536M9 13l6.293-6.293a1 1 0 011.414 0l1.586 1.586a1 1 0 010 1.414L12 16H9v-3z" />
												</svg>
											</button>
											<button class="p-1 text-zinc-500 hover:text-red-400 rounded" title="Delete"
												onclick={() => deleteFolder(child)}>
												<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
														d="M6 18L18 6M6 6l12 12" />
												</svg>
											</button>
										</div>
									</div>
								{/if}
							</div>
						{/each}
					{/if}
				</div>
			{/each}

			<!-- New folder button / inline form -->
			{#if creatingFolder}
				<form
					class="flex gap-1 px-2 mt-1"
					onsubmit={(e) => { e.preventDefault(); submitCreateFolder(); }}
				>
					<input
						class="input flex-1 text-xs !py-1"
						placeholder="Folder name"
						bind:value={newFolderName}
						onblur={() => { if (!newFolderName.trim()) creatingFolder = false; }}
					/>
				</form>
			{:else}
				<button
					class="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-zinc-600 hover:text-zinc-400
						hover:bg-surface-200 transition-colors w-full text-left mt-1"
					onclick={() => { creatingFolder = true; newFolderParentId = selectedFolderId; }}
				>
					<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
					</svg>
					New folder
				</button>
			{/if}
		</aside>

		<!-- Resizer -->
		<div 
			class="w-1 cursor-col-resize hover:bg-purple-500 transition-colors shrink-0"
			onmousedown={startResize}
			role="separator"
			aria-orientation="vertical"
			tabindex="0"
		></div>

		<!-- ----------------------------------------------------------------- -->
		<!-- Right panel — file grid -->
		<!-- ----------------------------------------------------------------- -->
		<div class="flex-1 flex flex-col min-w-0 overflow-y-auto pl-4">
			<div class="mb-4">
				<p class="text-sm text-zinc-400 mb-3">
					<span class="font-medium text-zinc-200">{selectedFolderName()}</span>
					{#if files.length > 0}
						<span class="ml-2 text-zinc-600">· {files.length} file{files.length !== 1 ? 's' : ''}</span>
					{/if}
				</p>

				<!-- Drop zone -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					class="border-2 border-dashed rounded-xl p-6 text-center transition-colors duration-200
						{dragOver ? 'border-brand-400 bg-brand-400/5' : 'border-surface-300 hover:border-surface-200'}"
					ondrop={handleDrop}
					ondragover={handleDragOver}
					ondragleave={() => (dragOver = false)}
				>
					<p class="text-zinc-400 text-sm">
						{uploading ? 'Uploading…' : 'Drag & drop images here, or click Upload above'}
					</p>
					<p class="text-zinc-600 text-xs mt-1">PNG, JPG, GIF, WebP, SVG · Max 25 MB each</p>
				</div>
			</div>

			{#if files.length === 0}
				<EmptyState title="No files here" description="Upload your first file to get started." />
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
								<button class="btn-secondary !text-xs !px-3 !py-1" onclick={() => copyUrl(f.url)}>
									Copy URL
								</button>
								<button class="btn-danger !text-xs !px-3 !py-1" onclick={() => deleteFile(f)}>
									Delete
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/if}
