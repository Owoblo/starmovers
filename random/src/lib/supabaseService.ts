import { supabase } from './supabase';

export interface Listing {
  id: string;
  address: string;
  city: string;
  state: string;
  zip_code?: string;
  price?: number;
  bedrooms?: number;
  bathrooms?: number;
  square_feet?: number;
  listing_date?: string;
  status?: string;
  // Add other fields as needed based on your schema
  [key: string]: any;
}

export interface CarouselImage {
  id: string;
  listing_id: string;
  image_url: string;
  image_order?: number;
  alt_text?: string;
  // Add other fields as needed
  [key: string]: any;
}

export class SupabaseService {
  // Search listings with autocomplete
  static async searchListings(query: string, limit: number = 10): Promise<Listing[]> {
    try {
      const { data, error } = await supabase
        .from('just_listed')
        .select('*')
        .or(`address.ilike.%${query}%, city.ilike.%${query}%, state.ilike.%${query}%`)
        .limit(limit);

      if (error) {
        console.error('Error searching listings:', error);
        return [];
      }

      return data || [];
    } catch (error) {
      console.error('Error in searchListings:', error);
      return [];
    }
  }

  // Get sold listings
  static async getSoldListings(query: string, limit: number = 10): Promise<Listing[]> {
    try {
      const { data, error } = await supabase
        .from('sold_listings')
        .select('*')
        .or(`address.ilike.%${query}%, city.ilike.%${query}%, state.ilike.%${query}%`)
        .limit(limit);

      if (error) {
        console.error('Error searching sold listings:', error);
        return [];
      }

      return data || [];
    } catch (error) {
      console.error('Error in getSoldListings:', error);
      return [];
    }
  }

  // Get carousel images for a specific listing
  static async getCarouselImages(listingId: string): Promise<CarouselImage[]> {
    try {
      const { data, error } = await supabase
        .from('carousel_images') // Assuming this is your carousel table name
        .select('*')
        .eq('listing_id', listingId)
        .order('image_order', { ascending: true });

      if (error) {
        console.error('Error fetching carousel images:', error);
        return [];
      }

      return data || [];
    } catch (error) {
      console.error('Error in getCarouselImages:', error);
      return [];
    }
  }

  // Get a specific listing by ID
  static async getListingById(id: string): Promise<Listing | null> {
    try {
      const { data, error } = await supabase
        .from('just_listed')
        .select('*')
        .eq('id', id)
        .single();

      if (error) {
        console.error('Error fetching listing:', error);
        return null;
      }

      return data;
    } catch (error) {
      console.error('Error in getListingById:', error);
      return null;
    }
  }

  // Get recent searches (you might want to store these in a separate table)
  static async getRecentSearches(): Promise<string[]> {
    // For now, return empty array - you can implement this based on your needs
    return [];
  }

  // Save recent search
  static async saveRecentSearch(address: string): Promise<void> {
    // Implement this if you want to persist recent searches
    console.log('Saving recent search:', address);
  }
}
