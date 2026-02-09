
import { signIn } from "@/auth"
import Image from "next/image"
import { FcGoogle } from "react-icons/fc"

export default function LoginPage() {
    return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-[#f0f2f5] text-[#202124] p-4 font-sans">
            <div className="w-full max-w-[448px] bg-white p-10 rounded-[28px] shadow-none sm:border sm:border-[#dadce0] flex flex-col items-center">
                <div className="mb-8 flex flex-col items-center">
                    <div className="relative h-12 w-12 mb-4">
                        <Image
                            src="/logo.svg"
                            alt="ReadPaper Logo"
                            fill
                            className="object-contain"
                            priority
                        />
                    </div>
                    <h1 className="text-2xl font-normal text-[#202124] mb-2">
                        Sign in
                    </h1>
                    <p className="text-base text-[#202124]">
                        to continue to ReadPaper
                    </p>
                </div>

                <form
                    action={async () => {
                        "use server"
                        await signIn("google", { redirectTo: "/" })
                    }}
                    className="w-full space-y-8"
                >
                    <div className="w-full flex justify-center">
                         <button
                            type="submit"
                            className="flex items-center justify-center gap-3 w-full max-w-[300px] bg-white text-[#1f1f1f] border border-[#747775] hover:bg-[#f0f4f9] hover:border-[#1f1f1f] px-6 py-2.5 rounded-full text-sm font-medium transition-colors duration-200"
                        >
                            <FcGoogle className="h-5 w-5" />
                            <span>Continue with Google</span>
                        </button>
                    </div>
                </form>

                <div className="mt-14 text-xs text-[#5f6368] text-center max-w-xs">
                    <p>
                        By continuing, you agree to the Terms of Service and Privacy Policy.
                    </p>
                </div>
            </div>
             <div className="mt-6 flex justify-between w-full max-w-[448px] text-xs text-[#5f6368]">
                <div className="flex gap-4">
                    <span>English (United States)</span>
                </div>
                <div className="flex gap-4">
                    <span>Help</span>
                    <span>Privacy</span>
                    <span>Terms</span>
                </div>
            </div>
        </div>
    )
}
