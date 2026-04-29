# Vercel Deployment Guide

## Problem

When deploying YTDown to Vercel, video fetching fails with the error:

```
Cannot download video B3NEtEDzlQk.
Last error: age-restricted or login required
The video may be private, DRM-protected, or region-locked.
```

## Root Cause

YTDown uses YouTube's InnerTube API to fetch video information and streaming URLs. YouTube's API has strict bot detection that requires:

1. **Visitor Data** (`VISITOR_DATA`) - A short-lived token (few hours) obtained from YouTube's homepage
2. **Authenticated Cookies** (optional but more reliable) - Full cookie string from a logged-in browser session

On Vercel's serverless platform:
- Outbound requests to youtube.com may be blocked or filtered
- Vercel's IP ranges are commonly flagged as datacenter/bot IPs
- The automatic visitor data fetch often fails
- Without valid credentials, YouTube returns `LOGIN_REQUIRED` errors

## Solution

Provide authentication credentials via environment variables on Vercel.

### Option 1: Use YOUTUBE_COOKIES (Recommended)

This is the most reliable method as authenticated cookies last for months.

#### Step 1: Get Your Cookies

1. Open Chrome/Firefox and log into your YouTube account
2. Open Developer Tools:
   - Press `F12` or right-click → **Inspect**
3. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
4. In the left sidebar, expand **Cookies** and select `https://www.youtube.com`
5. Select all cookies:
   - Click the first cookie row
   - Shift+click the last cookie row
6. Right-click on the selected rows → **Copy** → **Copy value** (Chrome) or **Copy string** (Firefox)
7. You should get a long string like:
   ```
   SID=...; HSID=...; SSID=...; APISID=...; SAPISID=...; __Secure-1PSID=...; ...
   ```

#### Step 2: Set Environment Variable on Vercel

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Select your YTDown project
3. Go to **Settings** → **Environment Variables**
4. Click **Add Variable**
   - Key: `YOUTUBE_COOKIES`
   - Value: `<paste your cookie string here>`
   - Environment: Select **Production**, **Preview**, and **Development** (or as needed)
5. Click **Save**
6. **Redeploy** your project

### Option 2: Use VISITOR_DATA (Fallback)

VISITOR_DATA expires after a few hours, so this is less reliable for production but can be used as a temporary solution.

#### Step 1: Get VISITOR_DATA

Run the helper script locally:

```bash
python get_credentials.py
```

It will fetch and display your current VISITOR_DATA.

Alternatively, manually:
1. Open https://www.youtube.com/ in your browser
2. View page source (Ctrl+U)
3. Search for `"VISITOR_DATA":"` and copy the value

#### Step 2: Set Environment Variable on Vercel

1. Vercel Dashboard → Your Project → Settings → Environment Variables
2. Add:
   - Key: `VISITOR_DATA`
   - Value: `<your visitor data string>`
   - Select all environments
3. Redeploy

### Option 3: Use Both

For maximum reliability, set **both** `YOUTUBE_COOKIES` and `VISITOR_DATA`. The code will use whichever is available.

## Testing Locally Before Deploying

To verify your credentials work:

```bash
# Set as environment variables temporarily
export YOUTUBE_COOKIES="your-cookie-string-here"
# OR
export VISITOR_DATA="your-visitor-data-here"

# Test with a video
python ytdown.py "https://www.youtube.com/watch?v=B3NEtEDzlQk"

# Or use the web server
python server.py
# Then open http://localhost:8080 and test
```

## Debugging on Vercel

If issues persist, check Vercel function logs:

1. Vercel Dashboard → Your Project → **Deployments**
2. Click on the latest deployment
3. Go to **Functions** tab
4. Click on `api/index.py` (or the function that executed)
5. View logs

Look for debug messages like:
- `[DEBUG] Successfully extracted visitorData...`
- `[DEBUG] Using VISITOR_DATA from environment`
- `[WARN] Vercel: Unable to fetch visitorData automatically`

These logs will help identify which step is failing.

## Notes

- **Security**: Keep your credentials secure. Never commit them to git. `.gitignore` already excludes `.env` files.
- **Cookie Updates**: Cookies may expire after several months. If you start getting login errors again, refresh your cookies.
- **VISITOR_DATA Lifetime**: Visitor data tokens typically last 1-4 hours. For production, use cookies.
- **Serverless Limitations**: Vercel's serverless functions have cold starts and limited execution time (10-60s). Large downloads may time out. Use the web UI for streaming downloads directly to the client.

## How It Works

The updated `core/extractor.py`:

1. Checks for `VISITOR_DATA` environment variable first (fast fallback)
2. Attempts to fetch visitor data from youtube.com with multiple retries and user agents
3. Shortens timeout to 5s on Vercel to avoid function timeout
4. Injects visitor data into InnerTube API requests
5. If cookies are provided via `YOUTUBE_COOKIES`, generates SAPISIDHASH authorization header
6. Tries multiple InnerTube clients (IOS, ANDROID, ANDROID_VR, TVHTML5, WEB) until one succeeds

## Still Having Issues?

Check the following:

1. Ensure environment variables are set for **all environments** (Production, Preview, Development) or at least the one you're deploying to
2. Verify your cookies are valid (log into YouTube with the same browser)
3. Make sure you copied the **entire** cookie string (should be long, containing many `key=value;` pairs)
4. Redeploy after setting environment variables
5. Check Vercel logs for specific error messages

For persistent issues, open an issue on GitHub with:
- Vercel function logs
- The video ID that fails
- Whether you're using cookies, visitor data, or both
