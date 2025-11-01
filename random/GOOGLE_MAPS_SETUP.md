# 🗺️ Google Maps API Setup Guide

To automatically calculate distances between addresses, you need to set up Google Maps Distance Matrix API.

## 📋 Setup Steps

### 1. Get Google Cloud API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to **APIs & Services** > **Library**
4. Search for **"Distance Matrix API"**
5. Click **Enable**

### 2. Get Your API Key

1. Go to **APIs & Services** > **Credentials**
2. Click **+ CREATE CREDENTIALS** > **API Key**
3. Copy your API key
4. (Recommended) Click **Restrict Key** and:
   - Under **Application restrictions**, select **HTTP referrers (web sites)**
   - Add your domain (e.g., `localhost` for development, your production domain)
   - Under **API restrictions**, select **Restrict key** and choose **Distance Matrix API**

### 3. Add to Your Project

Add the API key to your `.env` file:

```bash
REACT_APP_GOOGLE_MAPS_API_KEY=your_api_key_here
```

### 4. Restart Development Server

After adding the API key, restart your development server:

```bash
npm start
```

## ✅ How It Works

Once set up, the estimate page will:
- ✅ Automatically calculate distance when both addresses are entered
- ✅ Show real-time travel time in minutes
- ✅ Update the quote estimate based on actual distance
- ✅ Fall back to manual entry if API is unavailable

## 💰 Pricing

Google Maps Distance Matrix API:
- **Free tier**: $200/month credit (covers ~40,000 requests)
- **After free tier**: $5 per 1,000 requests

For a moving company app, this should be very affordable.

## 🔒 Security

**Important**: The API key is exposed in the frontend. To secure it:
1. Use API key restrictions (domain/IP restrictions)
2. Set up API quotas in Google Cloud Console
3. Monitor usage regularly
4. For production, consider a backend proxy (optional)

## 🚫 Alternative: OpenRouteService (Free)

If you prefer a free alternative, I can set up OpenRouteService instead:
- ✅ Completely free (no API key needed for basic usage)
- ✅ Open source
- ✅ Good accuracy
- ❌ Slightly slower than Google Maps
- ❌ Less polished UX

Let me know if you'd prefer OpenRouteService!




