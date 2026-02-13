/**
 * Client-side error hook — catches chunk load failures after Docker rebuilds.
 *
 * When the backend is rebuilt while the dashboard is open, client-side
 * navigation fails because JS chunk hashes change. This hook detects
 * that specific failure and forces a full page reload to pick up the
 * new manifest.
 */

/** @type {import('@sveltejs/kit').HandleClientError} */
export function handleError({ error, status, message }) {
	// Chunk load failures from stale builds manifest as TypeError or
	// "Failed to fetch dynamically imported module" errors.
	const msg = error instanceof Error ? error.message : String(error);
	if (
		msg.includes('dynamically imported module') ||
		msg.includes('Failed to fetch') ||
		msg.includes('Loading chunk') ||
		msg.includes('error loading dynamically imported module')
	) {
		console.warn('[synapse] Stale build detected — reloading page');
		window.location.reload();
		return { message: 'Reloading…' };
	}

	console.error('[synapse] Unhandled client error:', error);
	return {
		message: message || 'An unexpected error occurred',
	};
}
