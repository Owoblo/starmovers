export interface Photo {
  id: string;
  url: string;
  thumbnailUrl: string;
  filename: string;
  uploadedAt: Date;
}

export interface Detection {
  label: string;
  qty: number;
  confidence: number;
  sourcePhotoId: string;
  notes?: string;
  room?: string; // Optional room context
  size?: string; // Optional size descriptor (e.g., "55-inch", "Large", "Queen Size")
  boxes?: number; // Number of boxes needed for this item
  cubicFeet?: number; // Detected cubic feet from AI analysis
  weight?: number; // Detected weight in pounds from AI analysis
}

export interface MappingItem {
  cf: number; // cubic feet
  minutes: number; // estimated minutes to move
  wrap: boolean; // requires wrapping
}

export interface MappingTable {
  [label: string]: MappingItem;
}

export interface Estimate {
  crew: number;
  rate: number;
  travelMins: number;
  stairs: boolean;
  elevator: boolean;
  wrapping: boolean;
  safetyPct: number;
  hours: number;
  total: number;
}

export interface AppState {
  address: string;
  photos: Photo[];
  detections: Detection[];
  mapping: MappingTable;
  estimate: Estimate;
}

export interface QuotePayload {
  address: string;
  detections: Detection[];
  estimate: Estimate;
  timestamp: Date;
}
