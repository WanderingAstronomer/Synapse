/**
 * Flash message store — rune-based singleton.
 *
 * Provides success/error/info/warning flash notifications
 * that auto-dismiss after a configurable duration.
 */

export type FlashType = 'success' | 'error' | 'info' | 'warning';

export interface FlashMessage {
	id: number;
	type: FlashType;
	message: string;
}

let nextId = 0;
let messages = $state<FlashMessage[]>([]);

function add(type: FlashType, message: string, duration = 4000) {
	const id = nextId++;
	messages = [...messages, { id, type, message }];
	if (duration > 0) {
		setTimeout(() => dismiss(id), duration);
	}
}

function dismiss(id: number) {
	messages = messages.filter((m) => m.id !== id);
}

export const flash = {
	get messages() {
		return messages;
	},
	success: (msg: string) => add('success', msg),
	error: (msg: string) => add('error', msg, 6000),
	info: (msg: string) => add('info', msg),
	warning: (msg: string) => add('warning', msg, 5000),
	dismiss,
};
