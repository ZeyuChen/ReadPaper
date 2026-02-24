
import { auth } from "@/auth"
import { NextRequest, NextResponse } from "next/server"

// ---- IP Blocklist ----
// Add IPs here to block abusive/unwanted traffic before any processing.
const BLOCKED_IPS = new Set([
    "129.213.150.237",
])

function getClientIp(req: NextRequest): string {
    // Cloud Run always sets X-Forwarded-For with the real client IP
    return req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || ""
}

export default auth((req) => {
    // IP blocking — runs before any auth logic to minimize resource usage
    const clientIp = getClientIp(req)
    if (BLOCKED_IPS.has(clientIp)) {
        return new NextResponse("Forbidden", { status: 403 })
    }

    const isLoggedIn = !!req.auth
    const isAuthPage = req.nextUrl.pathname.startsWith("/login")
    const isApiRoute = req.nextUrl.pathname.startsWith("/api")
    const isStaticAsset = req.nextUrl.pathname.startsWith("/_next") ||
        req.nextUrl.pathname.startsWith("/favicon") ||
        req.nextUrl.pathname.startsWith("/logo")

    // Skip auth check for API routes, static assets, and auth pages
    if (isApiRoute || isStaticAsset) {
        return NextResponse.next()
    }

    // If DISABLE_AUTH is set, allow all requests
    if (process.env.NEXT_PUBLIC_DISABLE_AUTH === "true") {
        return NextResponse.next()
    }

    // Redirect logged-in users away from login page
    if (isAuthPage && isLoggedIn) {
        return NextResponse.redirect(new URL("/", req.nextUrl))
    }

    // Redirect unauthenticated users to login
    if (!isLoggedIn && !isAuthPage) {
        return NextResponse.redirect(new URL("/login", req.nextUrl))
    }

    return NextResponse.next()
})

export const config = {
    matcher: ['/((?!api|_next/static|_next/image|favicon.ico|logo.svg).*)'],
}

