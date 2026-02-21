
import { NextResponse } from 'next/server'

// Auth routes disabled — authentication has been removed from this application.
export async function GET() {
    return NextResponse.json({ message: 'Authentication disabled' }, { status: 404 })
}

export async function POST() {
    return NextResponse.json({ message: 'Authentication disabled' }, { status: 404 })
}
