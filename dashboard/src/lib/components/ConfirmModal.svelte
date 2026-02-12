<script lang="ts">
	interface Props {
		open: boolean;
		title?: string;
		message?: string;
		confirmLabel?: string;
		cancelLabel?: string;
		danger?: boolean;
		onconfirm: () => void;
		oncancel: () => void;
	}

	let {
		open = $bindable(false),
		title = 'Confirm Action',
		message = 'Are you sure you want to proceed?',
		confirmLabel = 'Confirm',
		cancelLabel = 'Cancel',
		danger = false,
		onconfirm,
		oncancel,
	}: Props = $props();

	function handleConfirm() {
		open = false;
		onconfirm();
	}

	function handleCancel() {
		open = false;
		oncancel();
	}
</script>

{#if open}
	<!-- Backdrop -->
	<div class="fixed inset-0 z-50 flex items-center justify-center">
		<button
			class="absolute inset-0 bg-black/60 backdrop-blur-sm"
			onclick={handleCancel}
			aria-label="Close dialog"
		></button>

		<!-- Dialog -->
		<div class="relative z-10 bg-surface-100 border border-surface-300 rounded-2xl shadow-2xl p-6 max-w-md w-full mx-4 animate-slide-up">
			<h3 class="text-lg font-semibold text-white">{title}</h3>
			<p class="text-sm text-zinc-400 mt-2">{message}</p>

			<div class="flex justify-end gap-3 mt-6">
				<button class="btn-secondary" onclick={handleCancel}>
					{cancelLabel}
				</button>
				<button
					class={danger ? 'btn-danger' : 'btn-primary'}
					onclick={handleConfirm}
				>
					{confirmLabel}
				</button>
			</div>
		</div>
	</div>
{/if}
