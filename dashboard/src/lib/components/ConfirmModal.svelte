<script lang="ts">
	import { onMount, tick } from 'svelte';

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

	let dialogEl: HTMLDivElement | undefined = $state();
	/** The element that had focus before the modal opened — restored on close. */
	let previousFocus: HTMLElement | null = null;

	function handleConfirm() {
		open = false;
		restoreFocus();
		onconfirm();
	}

	function handleCancel() {
		open = false;
		restoreFocus();
		oncancel();
	}

	function restoreFocus() {
		previousFocus?.focus();
		previousFocus = null;
	}

	/** Trap focus within the dialog: Tab cycles through focusable children. */
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			handleCancel();
			return;
		}
		if (e.key !== 'Tab' || !dialogEl) return;
		const focusable = dialogEl.querySelectorAll<HTMLElement>(
			'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
		);
		if (focusable.length === 0) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		if (e.shiftKey && document.activeElement === first) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && document.activeElement === last) {
			e.preventDefault();
			first.focus();
		}
	}

	/** When `open` becomes true, capture previous focus and auto-focus the dialog. */
	$effect(() => {
		if (open) {
			previousFocus = document.activeElement as HTMLElement;
			tick().then(() => {
				// Focus the cancel button (safest default — non-destructive action)
				const cancel = dialogEl?.querySelector<HTMLElement>('.btn-secondary');
				cancel?.focus();
			});
		}
	});
</script>

{#if open}
	<!-- Backdrop -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center"
		onkeydown={handleKeydown}
	>
		<button
			class="absolute inset-0 bg-black/60 backdrop-blur-sm"
			onclick={handleCancel}
			aria-label="Close dialog"
			tabindex="-1"
		></button>

		<!-- Dialog -->
		<div
			bind:this={dialogEl}
			class="relative z-10 bg-surface-100 border border-surface-300 rounded-2xl shadow-2xl p-6 max-w-md w-full mx-4 animate-slide-up"
			role="alertdialog"
			aria-modal="true"
			aria-labelledby="confirm-modal-title"
			aria-describedby="confirm-modal-desc"
		>
			<h3 id="confirm-modal-title" class="text-lg font-semibold text-white">{title}</h3>
			<p id="confirm-modal-desc" class="text-sm text-zinc-400 mt-2">{message}</p>

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
