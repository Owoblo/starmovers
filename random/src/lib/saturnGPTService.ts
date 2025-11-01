/**
 * Saturn Star Movers GPT Service
 * Uses GPT to calculate accurate move time based on inventory, cubic feet, weight, and distance
 */

interface SaturnMoveTimeRequest {
  detections: Array<{
    label: string;
    qty: number;
    cubicFeet?: number;
    weight?: number;
    size?: string;
    room?: string;
  }>;
  distance: number; // miles
  travelTime: number; // minutes
  originType: 'house' | 'apartment' | 'condo' | 'business';
  destinationType: 'house' | 'apartment' | 'condo' | 'business';
  stairsOrigin: boolean;
  stairsDestination: boolean;
  elevatorOrigin: boolean;
  elevatorDestination: boolean;
  floorOrigin?: number;
  floorDestination?: number;
  parkingOrigin: 'driveway' | 'street' | 'parking_lot' | 'difficult';
  parkingDestination: 'driveway' | 'street' | 'parking_lot' | 'difficult';
}

export interface SpecialtyItem {
  item: string;
  category: 'piano' | 'safe' | 'pool_table' | 'gym' | 'tv_large' | 'appliance' | 'hoisting';
  surcharge: number;
  extraTime: number; // extra minutes
  detected: boolean;
}

export interface SaturnMoveTimeResponse {
  hoursStandard: number;
  hoursConservative: number;
  recommendedCrew: 2 | 3 | 4 | 5 | 6;
  crewRate: number; // hourly rate for the crew
  specialtyItems: SpecialtyItem[];
  baseTotal: number; // Before surcharges
  surchargesTotal: number;
  totalBeforeTax: number;
  totalAfterTax: number; // Assuming 13% HST
  reasoning: string;
  breakdown: {
    loadingHours: number;
    travelHours: number;
    unloadingHours: number;
    setupHours: number;
    bufferHours: number;
  };
  detectedUpsells: Array<{
    id: string;
    name: string;
    price: number;
    reason: string;
    required: boolean; // Auto-select if required
  }>;
}

export class SaturnGPTService {
  private static readonly API_KEY = process.env.REACT_APP_OPENAI_API_KEY;
  private static readonly GPT_MODEL = process.env.REACT_APP_GPT_MODEL || 'gpt-4-turbo-preview';

  // Saturn Star Movers crew rates
  private static readonly CREW_RATES = {
    2: 150,
    3: 230,
    4: 250,
    5: 360,
    6: 400
  };

  static async calculateMoveTime(data: SaturnMoveTimeRequest): Promise<SaturnMoveTimeResponse> {
    if (!this.API_KEY) {
      throw new Error('OpenAI API key not configured. Please add REACT_APP_OPENAI_API_KEY to your .env file');
    }

    const systemPrompt = `You are the quoting assistant for Saturn Star Movers. Calculate accurate moving quotes using detected inventory data.

CRITICAL RULES:
1. Always respect the 3-hour minimum booking rule
2. Time starts when crew leaves office and ends when they return
3. Use detected cubic feet and weight from GPT-4 Vision (don't recalculate)
4. Add travel time as separate component
5. Apply specialty item surcharges in dollars AND extra time
6. Provide both standard and conservative estimates
7. TRUCK CAPACITY: 26ft truck = ~1,700 cubic feet. If total exceeds 1,700 cu ft:
   - Multiple trucks or trips required
   - Add extra setup/breakdown time per additional truck (+15-30 min per truck)
   - Loading time increases significantly (multiple truck loading coordination)
   - Travel may require multiple trips if using one truck

CREW RATES:
- 2 movers, 1 truck: $150/hr
- 3 movers, 1 truck: $230/hr
- 4 movers, 1 truck: $250/hr
- 4 movers, 2 trucks: $330/hr
- 5 movers, 2 trucks: $360/hr
- 6 movers, 2 trucks: $400/hr

SPECIALTY ITEM DETECTION (AUTO-DETECT AND FLAG):
- Piano (upright): $150-$300 surcharge + 60-90 min extra
- Piano (baby grand/grand): $300-$500 surcharge + 90-120 min extra
- Safe <300lb: $100 surcharge + 30 min extra
- Safe 300-600lb: $200-$300 surcharge + 60 min extra
- Pool table (disassembled): $200-$400 surcharge + 90-120 min extra
- Gym equipment: $50-$200 surcharge + 30-60 min extra
- TV >60": $40 surcharge (box required)
- Appliance disconnect/reconnect: $50-$100 per unit + 30 min per unit
- Hoisting (2nd story+): $100+ surcharge + 45 min per floor

INSURANCE (ALWAYS OFFER):
- Basic: $0 (included, $0.60/lb per item)
- Premium: $100 (up to $2,000 coverage)
- Deluxe: $200 (up to $5,000 coverage)

CALCULATION METHOD:
1. Sum all detected cubic feet and weight
2. Base hours = (total_cubic_ft / 100) * efficiency_factor
   - Efficiency: 100 cu ft per hour for 3 movers (standard)
   - Adjust for crew size: 2 movers = 0.65x, 4 movers = 1.3x, 5+ movers = 1.5x
3. Apply complexity multipliers:
   - Stairs: +25% per floor, max +100%
   - Elevator: +15% if slow/wait times expected
   - Difficult parking: +20% per location
   - Multiple floors: +10% per floor difference
4. Add specialty item extra time
5. Add buffer: Standard = 10%, Conservative = 20%
6. Travel hours = (travel_mins / 60) * 2 (round trip)
7. Setup/breakdown: 15 min per truck

Return ONLY valid JSON with this exact structure:
{
  "hoursStandard": number,
  "hoursConservative": number,
  "recommendedCrew": 2|3|4|5|6,
  "crewRate": number,
  "specialtyItems": [{"item": "string", "category": "string", "surcharge": number, "extraTime": number, "detected": true}],
  "baseTotal": number,
  "surchargesTotal": number,
  "totalBeforeTax": number,
  "totalAfterTax": number,
  "reasoning": "string",
  "breakdown": {
    "loadingHours": number,
    "travelHours": number,
    "unloadingHours": number,
    "setupHours": number,
    "bufferHours": number
  },
  "detectedUpsells": [{"id": "string", "name": "string", "price": number, "reason": "string", "required": boolean}]
}`;

    // Calculate total cubic feet and weight from detections
    const totalCubicFeet = data.detections.reduce((sum, d) => {
      if (d.cubicFeet) return sum + (d.cubicFeet * d.qty);
      return sum;
    }, 0);

    const totalWeight = data.detections.reduce((sum, d) => {
      if (d.weight) return sum + (d.weight * d.qty);
      return sum;
    }, 0);

    const userPrompt = `Calculate accurate move time for Saturn Star Movers:

INVENTORY (with detected cubic feet and weight):
${data.detections.map(d => {
  const cuft = d.cubicFeet ? `${(d.cubicFeet * d.qty).toFixed(1)} cu ft` : 'estimated';
  const weight = d.weight ? `${(d.weight * d.qty).toFixed(0)} lbs` : 'estimated';
  return `- ${d.qty}x ${d.label}${d.size ? ` (${d.size})` : ''}${d.room ? ` [${d.room}]` : ''} → ${cuft}, ${weight}`;
}).join('\n')}

TOTALS:
- Total Cubic Feet: ${totalCubicFeet.toFixed(1)} ${totalCubicFeet > 1700 ? `⚠️ EXCEEDS 26FT TRUCK CAPACITY - Multiple trucks/trips required` : ''}
- Total Weight: ${totalWeight.toFixed(0)} lbs
- Distance: ${data.distance.toFixed(1)} miles
- Travel Time: ${data.travelTime} minutes
- Estimated Trucks Needed: ${totalCubicFeet > 1700 ? Math.ceil(totalCubicFeet / 1700) : 1}

LOCATIONS:
- Origin: ${data.originType}${data.stairsOrigin ? ', HAS STAIRS' : ''}${data.elevatorOrigin ? ', HAS ELEVATOR' : ''}${data.floorOrigin ? `, Floor ${data.floorOrigin}` : ''}, Parking: ${data.parkingOrigin}
- Destination: ${data.destinationType}${data.stairsDestination ? ', HAS STAIRS' : ''}${data.elevatorDestination ? ', HAS ELEVATOR' : ''}${data.floorDestination ? `, Floor ${data.floorDestination}` : ''}, Parking: ${data.parkingDestination}

REQUIREMENTS:
1. AUTO-DETECT specialty items in inventory (pianos, safes, pool tables, large TVs >60", gym equipment, appliances needing disconnect)
2. Apply appropriate surcharges and extra time
3. Recommend crew size based on volume and complexity
4. Provide both standard (10% buffer) and conservative (20% buffer) estimates
5. Generate upsell recommendations:
   - TV boxes for TVs >60" (REQUIRED, auto-select)
   - Fragile packing for art/pictures (if detected)
   - Appliance disconnect if appliances detected (REQUIRED if needed)
   - Insurance tiers (always offer all 3)
6. Minimum 3 hours applies

Provide a professional, accurate estimate.`;

    try {
      const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: this.GPT_MODEL,
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userPrompt }
          ],
          response_format: { type: 'json_object' },
          temperature: 0.2 // Low for consistency
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`OpenAI API error: ${errorData.error?.message || response.statusText}`);
      }

      const result = await response.json();
      const content = result.choices[0].message.content;
      const moveTime = JSON.parse(content) as SaturnMoveTimeResponse;

      // Validate and enforce minimum 3 hours
      moveTime.hoursStandard = Math.max(3, moveTime.hoursStandard);
      moveTime.hoursConservative = Math.max(3, moveTime.hoursConservative);

      return moveTime;
    } catch (error: any) {
      console.error('Saturn GPT Move Time Calculation Error:', error);
      throw new Error(`Failed to calculate move time: ${error.message}`);
    }
  }

  // Helper to estimate weight from cubic feet (rule of thumb: 7 lbs per cubic foot for household goods)
  static estimateWeight(cubicFeet: number): number {
    return cubicFeet * 7;
  }
}

