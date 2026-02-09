
import ClientHome from "@/components/ClientHome";

// Server Component (Default in App Router)
export default async function Home() {
  // Read environment variables at runtime (Server-Side)
  // This works even in Cloud Run where vars are injected at container start
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const disableAuth = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true';

  const config = {
    apiUrl,
    disableAuth
  };

  return <ClientHome config={config} />;
}
