/**
 * Google Maps Distance Matrix API Service
 * Calculates real distance and travel time between two addresses
 * 
 * Setup:
 * 1. Get API key from: https://console.cloud.google.com/google/maps-apis
 * 2. Enable "Distance Matrix API" in Google Cloud Console
 * 3. Add to .env: REACT_APP_GOOGLE_MAPS_API_KEY=your_key_here
 */

interface DistanceResult {
  distance: number; // in miles
  duration: number; // in minutes
  distanceText: string; // formatted (e.g., "125 mi")
  durationText: string; // formatted (e.g., "2h 15min")
}

export class GoogleMapsService {
  private static readonly API_KEY = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
  private static readonly API_URL = 'https://maps.googleapis.com/maps/api/distancematrix/json';

  static async getDistance(
    origin: string,
    destination: string
  ): Promise<DistanceResult> {
    if (!this.API_KEY) {
      throw new Error('Google Maps API key not configured. Please add REACT_APP_GOOGLE_MAPS_API_KEY to your .env file');
    }

    if (!origin || !destination) {
      throw new Error('Origin and destination addresses are required');
    }

    try {
      const params = new URLSearchParams({
        origins: origin,
        destinations: destination,
        units: 'imperial', // Get results in miles/feet
        key: this.API_KEY
      });

      const response = await fetch(`${this.API_URL}?${params.toString()}`);
      
      if (!response.ok) {
        throw new Error(`Google Maps API error: ${response.status}`);
      }

      const data = await response.json();

      if (data.status === 'REQUEST_DENIED') {
        throw new Error(`Google Maps API error: ${data.error_message || 'API key invalid or missing'}`);
      }

      if (data.status !== 'OK') {
        throw new Error(`Google Maps API error: ${data.status}`);
      }

      const element = data.rows[0]?.elements[0];

      if (!element || element.status !== 'OK') {
        throw new Error(`Could not calculate distance: ${element?.status || 'Unknown error'}`);
      }

      // Convert meters to miles
      const distanceMiles = element.distance.value / 1609.34;
      // Convert seconds to minutes
      const durationMinutes = Math.ceil(element.duration.value / 60);

      return {
        distance: distanceMiles,
        duration: durationMinutes,
        distanceText: element.distance.text,
        durationText: element.duration.text
      };
    } catch (error: any) {
      console.error('Google Maps API error:', error);
      throw error;
    }
  }

  // Fallback: Simple estimation when API is not available
  static estimateDistance(origin: string, destination: string): number {
    // Very rough estimation - this is not accurate
    // Returns a placeholder that the user can manually adjust
    return 0;
  }
}




