
// Auth middleware — DISABLED. All requests pass through freely.
// Google OAuth has been removed from this application.
export default function middleware() {
    // No-op: allow all requests without authentication check
}

export const config = {
    matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
