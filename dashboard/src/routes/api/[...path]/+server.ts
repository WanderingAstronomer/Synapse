import { env } from '$env/dynamic/private';
import { error } from '@sveltejs/kit';
import type { RequestHandler } from '@sveltejs/kit';

const baseUrl = (env.API_BASE_URL || 'http://localhost:8000/api').replace(/\/$/, '');

const proxy: RequestHandler = async ({ params, request, url, fetch }) => {
	const path = params.path || '';
	const targetUrl = new URL(`${baseUrl}/${path}`);
	targetUrl.search = url.search;
	const hasBody = request.method !== 'GET' && request.method !== 'HEAD';

	const requestHeaders = new Headers(request.headers);
	requestHeaders.delete('host');

	let upstream: Response;
	try {
		upstream = await fetch(targetUrl, {
			method: request.method,
			headers: requestHeaders,
			body: hasBody ? await request.arrayBuffer() : undefined,
			redirect: 'manual',
		});
	} catch (err) {
		console.error(`[proxy] Failed to reach API: ${request.method} ${targetUrl}`, err);
		error(502, `API unreachable: ${(err as Error).message}`);
	}

	const responseHeaders = new Headers(upstream.headers);
	responseHeaders.delete('connection');
	responseHeaders.delete('content-encoding');
	responseHeaders.delete('content-length');

	return new Response(upstream.body, {
		status: upstream.status,
		statusText: upstream.statusText,
		headers: responseHeaders,
	});
};

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
