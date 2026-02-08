
import { signIn } from "@/auth"
import { FcGoogle } from "react-icons/fc"
import { FaBookOpen } from "react-icons/fa"

export default function LoginPage() {
    return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-[#f8f9fa] dark:bg-[#0a0a0a] text-foreground p-4">
            {/* Background decoration */}
            <div className="fixed inset-0 -z-10 h-full w-full bg-white dark:bg-black [background:radial-gradient(125%_125%_at_50%_10%,#fff_40%,#63e_100%)] dark:[background:radial-gradient(125%_125%_at_50%_10%,#000_40%,#63e_100%)] opacity-20"></div>

            <div className="w-full max-w-md space-y-8 bg-white/80 dark:bg-black/50 backdrop-blur-xl p-8 rounded-2xl shadow-2xl border border-gray-200/50 dark:border-white/10">
                <div className="flex flex-col items-center text-center">
                    <div className="h-12 w-12 bg-blue-600 rounded-xl flex items-center justify-center mb-6 shadow-lg shadow-blue-600/20">
                        <FaBookOpen className="text-white text-2xl" />
                    </div>
                    <h2 className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-gray-900 via-blue-800 to-gray-900 dark:from-white dark:via-blue-200 dark:to-white">
                        Welcome back
                    </h2>
                    <p className="mt-2 text-sm text-muted-foreground text-gray-500 dark:text-gray-400">
                        Sign in to access your personal research library
                    </p>
                </div>

                <form
                    action={async () => {
                        "use server"
                        await signIn("google", { redirectTo: "/" })
                    }}
                    className="mt-8 space-y-6"
                >
                    <button
                        type="submit"
                        className="group relative flex w-full justify-center items-center gap-3 rounded-xl bg-white dark:bg-zinc-900 px-4 py-3 text-sm font-semibold text-gray-700 dark:text-gray-200 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-700 hover:bg-gray-50 dark:hover:bg-zinc-800 focus:outline-offset-0 transition-all duration-200 hover:shadow-md"
                    >
                        <FcGoogle className="h-5 w-5" />
                        <span>Continue with Google</span>
                    </button>
                </form>

                <div className="relative">
                    <div className="absolute inset-0 flex items-center">
                        <span className="w-full border-t border-gray-200 dark:border-gray-800" />
                    </div>
                    <div className="relative flex justify-center text-xs uppercase">
                        <span className="bg-transparent px-2 text-gray-500">Secure Access</span>
                    </div>
                </div>
            </div>
        </div>
    )
}
