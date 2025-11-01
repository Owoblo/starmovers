// Utility functions for handling Zillow-style photo data

export interface ZillowPhotoData {
  baseUrl: string;
  photoData: Array<{ photoKey: string }>;
  communityPhotoData?: any;
  isStaticUrls: boolean;
}

export function parseZillowPhotos(carouselData: string | ZillowPhotoData): string[] {
  try {
    const data = typeof carouselData === 'string' 
      ? JSON.parse(carouselData) 
      : carouselData;
    
    const baseUrl = data.baseUrl;
    const photoData = data.photoData || [];
    
    if (!baseUrl || !Array.isArray(photoData)) {
      return [];
    }
    
    return photoData.map((photo: any) => {
      const photoKey = photo.photoKey;
      return baseUrl.replace('{photoKey}', photoKey);
    });
  } catch (error) {
    console.error('Error parsing Zillow photos:', error);
    return [];
  }
}

export function generateThumbnailUrl(fullUrl: string): string {
  // For Zillow URLs, we can generate different sizes by modifying the URL
  // This is a placeholder - you might want to implement actual thumbnail generation
  return fullUrl;
}


