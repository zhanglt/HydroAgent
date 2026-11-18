import { NextRequest, NextResponse } from 'next/server'
import { getDashboardData } from '@/lib/server-data'

export async function GET(request: NextRequest) {
  const data = await getDashboardData(request.nextUrl.searchParams.get('include_weather') !== 'false')
  return NextResponse.json(data, { status: data.backendReachable ? 200 : 503 })
}
