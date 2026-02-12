/**
 * Shared utility functions for the Synapse dashboard.
 */

/** Format a number with locale separators (e.g., 12,345) */
export function fmt(n: number): string {
	return n.toLocaleString();
}

/** Short number format (e.g., 1.2k, 3.4M) */
export function fmtShort(n: number): string {
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
	if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
	return n.toString();
}

/** Human-readable time ago (e.g., "3h ago", "2d ago") */
export function timeAgo(iso: string | null): string {
	if (!iso) return '—';
	const diff = Date.now() - new Date(iso).getTime();
	const seconds = Math.floor(diff / 1000);
	if (seconds < 60) return 'just now';
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	if (days < 30) return `${days}d ago`;
	const months = Math.floor(days / 30);
	return `${months}mo ago`;
}

/** Format ISO date string to short locale date */
export function fmtDate(iso: string | null): string {
	if (!iso) return '—';
	return new Date(iso).toLocaleDateString(undefined, {
		month: 'short',
		day: 'numeric',
		year: 'numeric',
	});
}

/** Format ISO date string to locale date+time */
export function fmtDateTime(iso: string | null): string {
	if (!iso) return '—';
	return new Date(iso).toLocaleString(undefined, {
		month: 'short',
		day: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
	});
}

/** Capitalize first letter */
export function capitalize(s: string): string {
	return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

/** Convert event_type like "REACTION_GIVEN" to "Reaction Given" */
export function eventTypeLabel(type: string): string {
	return type
		.split('_')
		.map((w) => capitalize(w))
		.join(' ');
}

/** Clamp a value between min and max */
export function clamp(value: number, min: number, max: number): number {
	return Math.min(Math.max(value, min), max);
}

/** Rarity sort order */
const RARITY_ORDER: Record<string, number> = {
	common: 0,
	uncommon: 1,
	rare: 2,
	epic: 3,
	legendary: 4,
};

export function raritySort(a: string, b: string): number {
	return (RARITY_ORDER[a] ?? 0) - (RARITY_ORDER[b] ?? 0);
}

/** Event type colors for charts */
export const EVENT_COLORS: Record<string, string> = {
	MESSAGE: '#7c3aed',
	REACTION_GIVEN: '#2196f3',
	REACTION_RECEIVED: '#4caf50',
	THREAD_CREATE: '#ff9800',
	VOICE_TICK: '#e91e63',
	MANUAL_AWARD: '#fbbf24',
	ACHIEVEMENT_EARNED: '#9c27b0',
	LEVEL_UP: '#00bcd4',
	// Event Lake types (P4)
	message_create: '#7c3aed',
	reaction_add: '#2196f3',
	reaction_remove: '#ef4444',
	thread_create: '#ff9800',
	voice_join: '#10b981',
	voice_leave: '#f59e0b',
	voice_move: '#06b6d4',
	member_join: '#8b5cf6',
	member_leave: '#ec4899',
};

export function eventColor(type: string): string {
	return EVENT_COLORS[type] || '#71717a';
}
