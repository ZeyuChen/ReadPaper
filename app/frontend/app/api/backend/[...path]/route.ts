/**
 * Runtime proxy for all /backend/* requests.
 *
 * WHY THIS EXISTS:
 * next.config.ts rewrites() are evaluated at BUILD TIME, not runtime.
 * So `process.env.API_URL` in rewrites() always reads as undefined during
 * `next build`, falling back to localhost:8000 — which breaks Cloud Run.
 *
 * This API route runs at REQUEST TIME and can read the runtime env var.
 * It also injects the authenticated user's email as x-user-email header
 * so the backend can identify the user without decoding NextAuth JWTs.
 */
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/auth';

// Allow long-running requests (PDF downloads, translation polling)
export const maxDuration = 300;

// This is the runtime backend URL — read from env at request time, not build time.
const BACKEND_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://localhost:8000';

const DISABLE_AUTH = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true';

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    return proxyRequest(request, await params);
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    return proxyRequest(request, await params);
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    return proxyRequest(request, await params);
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    return proxyRequest(request, await params);
}

export async function OPTIONS(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    return proxyRequest(request, await params);
}

async function proxyRequest(request: NextRequest, params: { path: string[] }) {
    const path = params.path?.join('/') ?? '';
    const search = request.nextUrl.search || '';
    const targetUrl = `${BACKEND_URL}/${path}${search}`;

    // Forward relevant headers (skip host which must be rewritten)
    const headers = new Headers();
    for (const [key, value] of request.headers.entries()) {
        if (key.toLowerCase() === 'host') continue;
        headers.set(key, value);
    }

    // ── Inject authenticated user email for backend identification ──────
    // The backend reads x-user-email to identify the user without needing
    // to decode NextAuth session tokens itself.
    if (!DISABLE_AUTH) {
        try {
            const session = await auth();
            if (session?.user?.email) {
                headers.set('x-user-email', session.user.email);
            }
        } catch (e) {
            // If auth() fails, let the request through without the header.
            // The backend will reject it with 401 if auth is required.
            console.warn('[Backend Proxy] Failed to get session:', e);
        }
    }

    let body: BodyInit | null = null;
    const method = request.method;
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
        body = await request.arrayBuffer();
    }

    try {
        const response = await fetch(targetUrl, {
            method,
            headers,
            body,
            // @ts-ignore
            duplex: 'half',
        });

        const responseHeaders = new Headers();
        for (const [key, value] of response.headers.entries()) {
            // Skip transfer-encoding which causes issues with Next.js response streaming
            if (key.toLowerCase() === 'transfer-encoding') continue;
            responseHeaders.set(key, value);
        }

        // Stream binary responses (PDFs, images) instead of buffering the entire body.
        // For large files (e.g. 6MB translated PDFs), buffering with arrayBuffer()
        // can exceed the serverless function timeout and cause "Failed to fetch" errors.
        const contentType = response.headers.get('content-type') || '';
        const isBinary = contentType.startsWith('application/pdf') ||
            contentType.startsWith('image/') ||
            contentType.startsWith('application/octet-stream');

        if (isBinary && response.body) {
            return new NextResponse(response.body as any, {
                status: response.status,
                headers: responseHeaders,
            });
        }

        // For JSON/text responses, buffer as before
        const responseBody = await response.arrayBuffer();
        return new NextResponse(responseBody, {
            status: response.status,
            headers: responseHeaders,
        });
    } catch (error: any) {
        console.error(`[Backend Proxy] Error proxying to ${targetUrl}:`, error);
        return NextResponse.json(
            { detail: `Backend proxy error: ${error.message}` },
            { status: 502 }
        );
    }
}

