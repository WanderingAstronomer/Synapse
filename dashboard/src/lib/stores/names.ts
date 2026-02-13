import { writable, get } from 'svelte/store';
import { api } from '$lib/api';

/**
 * Client-side cache for resolved Discord names.
 *
 * Batches unknown IDs into a single API call to avoid N+1 fetches.
 * Once resolved, names are cached for the lifetime of the page.
 */
const userNames = writable<Record<string, string>>({});
const channelNames = writable<Record<string, string>>({});

/** Pending IDs waiting to be resolved (batched) */
let pendingUserIds = new Set<string>();
let pendingChannelIds = new Set<string>();
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleFlush() {
	if (flushTimer) return;
	flushTimer = setTimeout(flush, 50);
}

async function flush() {
	flushTimer = null;
	const uids = [...pendingUserIds];
	const cids = [...pendingChannelIds];
	pendingUserIds.clear();
	pendingChannelIds.clear();

	if (uids.length === 0 && cids.length === 0) return;

	try {
		const res = await api.admin.resolveNames(uids, cids);
		if (res.users && Object.keys(res.users).length > 0) {
			userNames.update((m) => ({ ...m, ...res.users }));
		}
		if (res.channels && Object.keys(res.channels).length > 0) {
			channelNames.update((m) => ({ ...m, ...res.channels }));
		}
	} catch {
		// Resolution is best-effort; don't block the UI
	}
}

/**
 * Request resolution for a set of user/channel IDs.
 * Returns immediately; subscribe to `userNames` / `channelNames` for results.
 */
export function requestResolve(userIds: string[] = [], channelIds: string[] = []) {
	const currentUsers = get(userNames);
	const currentChannels = get(channelNames);

	for (const id of userIds) {
		if (!currentUsers[id]) pendingUserIds.add(id);
	}
	for (const id of channelIds) {
		if (!currentChannels[id]) pendingChannelIds.add(id);
	}

	if (pendingUserIds.size > 0 || pendingChannelIds.size > 0) {
		scheduleFlush();
	}
}

/** Get a resolved user name or fall back to abbreviated ID. */
export function resolveUser(id: string, cache: Record<string, string>): string {
	return cache[id] || (id.length > 6 ? `User …${id.slice(-4)}` : id);
}

/** Get a resolved channel name or fall back to abbreviated ID. */
export function resolveChannel(id: string, cache: Record<string, string>): string {
	return cache[id] || (id.length > 6 ? `#…${id.slice(-4)}` : `#${id}`);
}

export { userNames, channelNames };
