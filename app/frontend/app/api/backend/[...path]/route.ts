/**
 * Runtime proxy for all /backend/* requests.
 *
 * WHY THIS EXISTS:
 * next.config.ts rewrites() are evaluated at BUILD TIME, not runtime.
 * So `process.env.API_URL` in rewrites() always reads as undefined during
 * `next build`, falling back to localhost:8000 — which breaks Cloud Run.
 *
 * This API route runs at REQUEST TIME and can read the runtime env var.
 */
import { NextRequest, NextResponse } from 'next/server';

// This is the runtime backend URL — read from env at request time, not build time.
const BACKEND_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://localhost:8000';

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
