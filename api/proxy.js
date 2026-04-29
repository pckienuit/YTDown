export const config = {
  runtime: 'edge',
};

export default async function handler(req) {
  const { searchParams } = new URL(req.url);
  const url = searchParams.get('url');
  const title = searchParams.get('title') || 'download';
  
  if (!url) {
    return new Response(JSON.stringify({ error: 'Missing url parameter' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    // Forward the request to YouTube
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': '*/*'
      }
    });

    if (!response.ok) {
      return new Response(`Error from source: ${response.status} ${response.statusText}`, { status: response.status });
    }

    // Set headers to force download and allow CORS
    const headers = new Headers(response.headers);
    headers.set('Content-Disposition', `attachment; filename="${encodeURIComponent(title)}"`);
    headers.set('Access-Control-Allow-Origin', '*');

    // Return the readable stream directly to the client
    return new Response(response.body, {
      status: response.status,
      headers
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
