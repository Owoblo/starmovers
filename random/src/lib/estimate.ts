import { Detection, MappingTable, Estimate } from '../types';

export interface EstimateResult {
  hours: number;
  crewSuggestion: number;
  total: number;
}

export function calculateEstimate(
  detections: Detection[],
  mapping: MappingTable,
  params: Omit<Estimate, 'hours' | 'total'>
): EstimateResult {
  let totalMinutes = 0;
  let totalCubicFeet = 0;

  // Calculate total time and cubic feet based on detections
  detections.forEach(detection => {
    const mappingItem = mapping[detection.label];
    if (mappingItem) {
      totalMinutes += mappingItem.minutes * detection.qty;
      totalCubicFeet += mappingItem.cf * detection.qty;
    }
  });

  // Add travel time
  totalMinutes += params.travelMins;

  // Apply stairs/elevator multipliers
  if (params.stairs) {
    totalMinutes *= 1.3; // 30% increase for stairs
  }
  if (params.elevator) {
    totalMinutes *= 1.1; // 10% increase for elevator
  }

  // Apply safety factor
  const safetyMultiplier = 1 + (params.safetyPct / 100);
  totalMinutes *= safetyMultiplier;

  // Convert to hours
  const hours = totalMinutes / 60;

  // Suggest crew size based on cubic feet and complexity
  let crewSuggestion = 2;
  if (totalCubicFeet > 1000) crewSuggestion = 4;
  else if (totalCubicFeet > 500) crewSuggestion = 3;
  
  // Adjust for stairs/elevator
  if (params.stairs) crewSuggestion = Math.min(crewSuggestion + 1, 6);
  if (params.elevator) crewSuggestion = Math.min(crewSuggestion + 1, 6);

  // Calculate total cost
  const total = hours * params.rate * params.crew;

  return {
    hours: Math.round(hours * 10) / 10, // Round to 1 decimal
    crewSuggestion,
    total: Math.round(total)
  };
}

