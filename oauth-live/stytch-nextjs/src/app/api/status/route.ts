import { isValidLivePublicToken } from '@/lib/liveToken';

export const dynamic = 'force-dynamic';

/** Public, non-sensitive readiness check. Never return secrets or tokens. */
export async function GET() {
  const configured = isValidLivePublicToken(process.env.NEXT_PUBLIC_STYTCH_PUBLIC_TOKEN || '');
  return Response.json(
    { service: 'panadan-live-authorization-ui',
      status: configured ? 'configured' : 'setup_required' },
    { status: 200, headers: { 'Cache-Control': 'no-store' } },
  );
}
