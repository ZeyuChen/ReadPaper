
import { auth } from "@/auth"
import { NextResponse } from "next/server"

export default auth((req) => {
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
