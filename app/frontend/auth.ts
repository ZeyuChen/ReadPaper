
import NextAuth from "next-auth"
import Google from "next-auth/providers/google"

export const { handlers, signIn, signOut, auth } = NextAuth({
    providers: [
        Google({
            clientId: process.env.AUTH_GOOGLE_ID,
            clientSecret: process.env.AUTH_GOOGLE_SECRET,
        }),
    ],
    pages: {
        signIn: "/login",
    },
    callbacks: {
        async jwt({ token, account, profile }) {
            // On initial sign-in, persist the user's email into the JWT
            if (account && profile?.email) {
                token.email = profile.email
                token.name = profile.name
                token.picture = profile.picture || (profile as any).avatar_url
            }
            return token
        },
        async session({ session, token }) {
            // Expose the email to the client session
            if (session.user && token.email) {
                session.user.email = token.email as string
            }
            return session
        },
        async authorized({ auth }) {
            // For middleware: return true if the user has a valid session
            return !!auth
        },
    },
    session: {
        strategy: "jwt",
    },
    secret: process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET,
})
