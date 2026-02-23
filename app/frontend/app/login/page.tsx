
'use client'

import { signIn } from 'next-auth/react'
import Image from 'next/image'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

function LoginContent() {
    const searchParams = useSearchParams()
    const callbackUrl = searchParams.get('callbackUrl') || '/'

    return (
        <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-blue-50/30 font-sans">
            <div className="w-full max-w-sm mx-auto">
                <div className="bg-white rounded-3xl shadow-xl border border-gray-100 p-8 space-y-8">
                    {/* Logo & Title */}
                    <div className="flex flex-col items-center space-y-4">
                        <div className="relative w-14 h-14">
                            <Image src="/logo.svg" alt="ReadPaper Logo" fill className="object-contain" priority />
                        </div>
                        <div className="text-center">
                            <h1 className="text-3xl font-light tracking-tight text-[#202124]">ReadPaper</h1>
                            <p className="text-sm text-[#5f6368] mt-1.5">
                                Bilingual arXiv reading powered by Gemini
                            </p>
                        </div>
                    </div>

                    {/* Divider */}
                    <div className="flex items-center gap-3">
                        <div className="flex-1 h-px bg-gray-200" />
                        <span className="text-xs text-gray-400 uppercase tracking-wider">Sign in to continue</span>
                        <div className="flex-1 h-px bg-gray-200" />
                    </div>

                    {/* Google Sign-In Button */}
                    <button
                        onClick={() => signIn('google', { callbackUrl })}
                        className="w-full flex items-center justify-center gap-3 py-3 px-4 bg-white border border-gray-300 rounded-full hover:bg-gray-50 hover:shadow-md transition-all text-sm font-medium text-[#202124] active:scale-[0.98]"
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24">
                            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                        </svg>
                        Sign in with Google
                    </button>

                    <p className="text-[10px] text-gray-400 text-center leading-relaxed">
                        By signing in, you agree to use this service responsibly.
                        <br />Your Google email is used for access control only.
                    </p>
                </div>
            </div>
        </div>
    )
}

export default function LoginPage() {
    return (
        <Suspense fallback={
            <div className="flex min-h-screen items-center justify-center">
                <div className="animate-pulse text-gray-400">Loading...</div>
            </div>
        }>
            <LoginContent />
        </Suspense>
    )
}
