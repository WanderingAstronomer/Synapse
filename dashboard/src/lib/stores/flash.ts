import { writable } from 'svelte/store';

export type FlashType = 'success' | 'error' | 'info' | 'warning';

interface FlashMessage {
	id: number;
	type: FlashType;
	message: string;
}

let nextId = 0;

function createFlashStore() {
	const { subscribe, update } = writable<FlashMessage[]>([]);

	function add(type: FlashType, message: string, duration = 4000) {
		const id = nextId++;
		update((msgs) => [...msgs, { id, type, message }]);
		if (duration > 0) {
			setTimeout(() => dismiss(id), duration);
		}
	}

	function dismiss(id: number) {
		update((msgs) => msgs.filter((m) => m.id !== id));
	}

	return {
		subscribe,
		success: (msg: string) => add('success', msg),
		error: (msg: string) => add('error', msg, 6000),
		info: (msg: string) => add('info', msg),
		warning: (msg: string) => add('warning', msg, 5000),
		dismiss,
	};
}

export const flash = createFlashStore();
