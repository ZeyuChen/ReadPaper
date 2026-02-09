
import ClientHome from "@/components/ClientHome";

// Force dynamic rendering to ensure runtime env vars are read if needed (though we use rewrites now)
export const dynamic = 'force-dynamic';

// Server Component (Default in App Router)
export default async function Home() {
  // Use relative path for API calls, creating a proxy via Next.js Rewrites
  // This avoids baking in the backend URL at build time
  const apiUrl = '/backend';
  const disableAuth = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true';

  const config = {
    apiUrl,
    disableAuth
  };

  return <ClientHome config={config} />;
}
