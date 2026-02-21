
// Login page — auth disabled, redirect to home
import { redirect } from 'next/navigation'

export default function LoginPage() {
    redirect('/')
}
