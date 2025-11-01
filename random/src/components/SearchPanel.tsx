import React, { useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';

interface Listing {
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
  [key: string]: any;
}

interface SearchPanelProps {
  address: string;
  onAddressChange: (address: string) => void;
  onFetchPhotos: () => void;
  onClear: () => void;
  recentSearches: string[];
  onListingSelect?: (listing: Listing) => void;
}

export default function SearchPanel({
  address,
  onAddressChange,
  onFetchPhotos,
  onClear,
  recentSearches,
  onListingSelect
}: SearchPanelProps) {
  const [suggestions, setSuggestions] = useState<Listing[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading, setLoading] = useState(false);

  // Search for listings as user types
  useEffect(() => {
    const searchListings = async () => {
      if (address.length < 1) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }

      setLoading(true);
      console.log('Searching for:', address);
      
      try {
        // Search both current and sold listings
        const [currentListings, soldListings] = await Promise.all([
          supabase
            .from('just_listed')
            .select('*')
            .or(`address.ilike.%${address}%, addresscity.ilike.%${address}%, addressstate.ilike.%${address}%`)
            .limit(10),
          supabase
            .from('sold_listings')
            .select('*')
            .or(`address.ilike.%${address}%, addresscity.ilike.%${address}%, addressstate.ilike.%${address}%`)
            .limit(10)
        ]);

        console.log('Current listings:', currentListings);
        console.log('Sold listings:', soldListings);

        const allSuggestions = [
          ...(currentListings.data || []),
          ...(soldListings.data || [])
        ];

        console.log('All suggestions:', allSuggestions);
        setSuggestions(allSuggestions);
        setShowSuggestions(true);
      } catch (error) {
        console.error('Error searching listings:', error);
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    };

    const timeoutId = setTimeout(searchListings, 200); // Reduced debounce for faster response
    return () => clearTimeout(timeoutId);
  }, [address]);

  const handleSuggestionClick = (listing: Listing) => {
    const fullAddress = `${listing.address}, ${listing.addresscity}, ${listing.addressstate}`;
    onAddressChange(fullAddress);
    setShowSuggestions(false);
    
    // Store the selected listing for photo fetching
    if (onListingSelect) {
      onListingSelect(listing);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onAddressChange(e.target.value);
  };

  const handleInputFocus = () => {
    if (suggestions.length > 0) {
      setShowSuggestions(true);
    } else if (address.length > 0) {
      // Trigger search if there's text but no suggestions yet
      setShowSuggestions(true);
    }
  };

  const handleInputBlur = () => {
    // Delay hiding suggestions to allow clicks
    setTimeout(() => setShowSuggestions(false), 200);
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-8 transition-colors duration-200">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Property Search</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">Enter an address to automatically detect furniture and generate moving estimates</p>
      </div>
      
      {/* Address Input with Autocomplete */}
      <div className="mb-6 relative">
        <label htmlFor="address" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Address
        </label>
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <svg className="h-5 w-5 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <input
            id="address"
            type="text"
            value={address}
            onChange={handleInputChange}
            onFocus={handleInputFocus}
            onBlur={handleInputBlur}
            placeholder="Search for any address..."
            className="w-full pl-12 pr-4 py-3 border border-gray-200 dark:border-gray-600 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 placeholder-gray-500 dark:placeholder-gray-400"
          />
          {loading && (
            <div className="absolute right-4 top-3.5">
              <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-500 dark:border-blue-400 border-t-transparent"></div>
            </div>
          )}
        </div>
        
        {/* Autocomplete Suggestions */}
        {showSuggestions && suggestions.length > 0 && (
          <div className="absolute z-50 w-full mt-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl max-h-64 overflow-y-auto">
            {suggestions.map((listing, index) => (
              <div
                key={`${listing.id}-${index}`}
                onClick={() => handleSuggestionClick(listing)}
                className="px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer border-b border-gray-100 dark:border-gray-700 last:border-b-0 transition-colors duration-150"
              >
                <div className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                  {listing.address}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                  {listing.addresscity}, {listing.addressstate}
                  {listing.unformattedprice && (
                    <span className="ml-2 text-green-600 dark:text-green-400 font-medium">
                      ${listing.unformattedprice.toLocaleString()}
                    </span>
                  )}
                </div>
                {listing.beds && listing.baths && (
                  <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                    {listing.beds} bed • {listing.baths} bath
                    {listing.area && ` • ${listing.area} sq ft`}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        
        {/* Loading indicator */}
        {showSuggestions && loading && (
          <div className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-lg p-3">
            <div className="flex items-center justify-center">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 dark:border-blue-400 mr-2"></div>
              <span className="text-sm text-gray-500 dark:text-gray-400">Searching...</span>
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex space-x-3">
        <button
          onClick={onFetchPhotos}
          disabled={!address || loading}
          className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 text-white font-medium py-3 px-4 rounded-xl transition-colors duration-200 flex items-center justify-center space-x-2 disabled:cursor-not-allowed"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span>Load Photos & Auto-Detect</span>
        </button>
        <button
          onClick={onClear}
          className="px-4 py-3 border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300 font-medium rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
