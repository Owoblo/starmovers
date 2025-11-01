import { Detection } from '../types';
import { detectFurniture } from './aiDetectionServices';

// AI Furniture Detection Service
export class FurnitureDetectionService {
  // Real AI detection using external services
  static async detectFurniture(photoUrls: string[]): Promise<Detection[]> {
    console.log('Starting AI furniture detection for', photoUrls.length, 'photos');
    
    try {
      // Use real AI detection
      const detections = await detectFurniture(photoUrls);
      
      console.log('AI detection completed. Found', detections.length, 'items');
      return detections;
    } catch (error) {
      console.error('AI detection failed:', error);
      throw new Error('AI detection failed. Please check your API keys and try again.');
    }
  }
  
  // Analyze photos for furniture detection
  static async analyzePhotos(photos: any[]): Promise<Detection[]> {
    if (photos.length === 0) {
      return [];
    }
    
    const photoUrls = photos.map(photo => photo.url);
    return await this.detectFurniture(photoUrls);
  }
}
