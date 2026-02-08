
import { auth } from "@/auth"

export default auth((req) => {
    const isLoggedIn = !!req.auth
    const isOnDashboard = req.nextUrl.pathname === '/' || req.nextUrl.pathname.startsWith('/library')

    if (isOnDashboard) {
        if (isLoggedIn) return
        return Response.redirect(new URL('/login', req.nextUrl))
    }
})

export const config = {
    // https://nextjs.org/docs/app/building-your-application/routing/middleware#matcher
    matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
