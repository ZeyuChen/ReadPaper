
import NextAuth from "next-auth"
import Google from "next-auth/providers/google"

export const { handlers, signIn, signOut, auth } = NextAuth({
    providers: [
        Google({
            authorization: {
                params: {
                    prompt: "consent",
                    access_type: "offline",
                    response_type: "code",
                },
            },
        }),
    ],
    callbacks: {
        async jwt({ token, account }) {
            if (account) {
                token.accessToken = account.access_token
                token.idToken = account.id_token
            }
            return token
        },
        async session({ session, token }) {
            // Expose the user ID (sub) and potentially the access token
            if (session.user) {
                if (token.sub) {
                    // @ts-ignore
                    session.user.id = token.sub
                }
                // @ts-ignore
                session.idToken = token.idToken
            }
            return session
        },
    },
    pages: {
        signIn: "/login",
    },
    session: {
        strategy: "jwt",
    }
})
