import { Detection } from '../types';
import { estimateCubicFeet, estimateWeight } from './cubicFeetEstimator';

// OpenAI GPT-4 Vision - PRIMARY AND ONLY detection method for maximum accuracy
export const detectFurniture = async (photoUrls: string[]): Promise<Detection[]> => {
  console.log('Starting OpenAI GPT-4 Vision detection for', photoUrls.length, 'photos');
  console.log('OpenAI API Key configured:', !!process.env.REACT_APP_OPENAI_API_KEY);
  
  if (!process.env.REACT_APP_OPENAI_API_KEY) {
    throw new Error('OpenAI API key not configured');
  }

  const allDetections: Detection[] = [];
  
  for (const photoUrl of photoUrls) {
    try {
      console.log('Analyzing photo with OpenAI GPT-4 Vision:', photoUrl);
      
      const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.REACT_APP_OPENAI_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'gpt-4o', // Using latest GPT-4o model for best accuracy
          messages: [{
            role: 'user',
            content: [
                {
                  type: 'text',
                  text: `You are a professional MOVING COMPANY inventory specialist. Analyze this real estate photo and identify ONLY items that professional movers can physically move and transport.

🚚 MOVER'S INVENTORY - ONLY DETECT MOVABLE ITEMS:

✅ MOVABLE FURNITURE & ITEMS (DETECT THESE):
- SEATING: Sofas, Sectionals, Loveseats, Recliners, Chairs (Dining, Office, Accent), Ottomans, Benches, Stools
- TABLES: Dining Tables, Coffee Tables, End Tables, Console Tables, Side Tables, Kitchen Islands (if freestanding)
- BEDS: King Beds, Queen Beds, Twin Beds, Bunk Beds, Daybeds, Futons, Mattresses, Box Springs
- STORAGE: Dressers, Chests of Drawers, Nightstands, Bookshelves, Freestanding Cabinets, Wardrobes, Armoires
- APPLIANCES: Refrigerators, Stoves, Ovens, Microwaves, Dishwashers, Washers, Dryers, Toasters, Coffee Makers
- ELECTRONICS: TVs, Monitors, Computers, Laptops, Sound Systems, Gaming Consoles, Speakers
- DECOR: Floor Lamps, Table Lamps, Mirrors (wall-mounted), Artwork, Plants, Vases, Clocks, Area Rugs
- KITCHEN: Freestanding Pantries, Wine Racks, Bar Stools, Kitchen Carts
- OUTDOOR: Patio Furniture, Grills, Outdoor Chairs/Tables

❌ DO NOT DETECT (FIXED INSTALLATIONS):
- Built-in cabinets, Built-in shelving, Built-in vanities
- Chandeliers, Ceiling fans, Light fixtures
- Built-in appliances (dishwashers, built-in ovens)
- Built-in bathroom vanities, Medicine cabinets
- Built-in wardrobes, Built-in closets
- Wall-mounted items (unless easily removable)
- Built-in countertops, Built-in islands
- Fixed mirrors, Built-in mirrors
- Built-in seating, Built-in benches

CRITICAL REQUIREMENTS:
1. COUNT EXACT QUANTITIES - If you see 4 dining chairs, write qty: 4
2. BE HIGHLY SPECIFIC - "Large Oak Dining Table", "Sectional Sofa with Ottoman", "King Size Platform Bed"
3. INCLUDE ROOM CONTEXT - "Master Bedroom Dresser", "Kitchen Island Stools", "Living Room Coffee Table"
4. DISTINGUISH SIMILAR ITEMS - "Coffee Table" vs "End Table" vs "Console Table"
5. SIZE DESCRIPTORS - CRITICAL FOR MOVERS:
   - TVs: Estimate screen size in inches (e.g., "40-50 inch TV", "55-65 inch TV", "70+ inch TV"). If unsure, provide a reasonable range based on visual scale compared to furniture nearby.
   - Furniture: Provide dimensions or size range when possible (e.g., "Large (7-8 ft)", "Small (4-5 ft)", "Queen Size", "King Size"). Estimate based on visual scale or standard sizes.
   - If exact size is unclear, provide a reasonable range (e.g., "Medium-Large", "30-40 inches wide")
6. ONLY MOVABLE ITEMS - Skip anything permanently attached or built-in

Return ONLY a valid JSON array with objects containing:
- label: VERY SPECIFIC movable furniture type with descriptors (string)
- qty: EXACT quantity visible (number) 
- confidence: confidence score 0-1 (number)
- notes: room location and specific details (string)
- room: room type (string)
- size: size descriptor with specific measurements or ranges - CRITICAL for TVs: estimate inches (e.g., "55-inch", "65-75 inch range"). For furniture: dimensions or size category with ranges (e.g., "Large (7-8 ft)", "Queen Size", "30-40 inches wide")
- cubicFeet: **REQUIRED** - estimated cubic feet volume for this item (number). ALWAYS provide this field using standard moving industry estimates. Examples:
  * Sofa (3-cushion): 35 cu ft
  * Loveseat: 30 cu ft
  * Dining chair: 5 cu ft
  * Dining table (4-6 seater): 30 cu ft
  * Queen bed: 65 cu ft
  * King bed: 70 cu ft
  * Dresser (medium): 40 cu ft
  * TV 55": 45 cu ft
  * TV 60"+: 55 cu ft
  * Refrigerator: 35 cu ft
  * Washer/Dryer: 25 cu ft each
  * Piano (upright): 70 cu ft
  * Pool table: 40 cu ft
  * For items not listed, estimate based on dimensions and industry standards
- weight: **REQUIRED** - estimated weight in pounds (number). ALWAYS provide this field using Saturn Star Movers cube sheet standards:
  * 3-cushion sofa: 245 lbs
  * Loveseat: 210 lbs
  * Armchair: 105 lbs
  * Dining chair: 35 lbs
  * Dining table: 210 lbs
  * Coffee table: 84 lbs
  * End table: 35 lbs
  * Queen bed: 455 lbs
  * King bed: 490 lbs
  * Dresser (medium): 280 lbs
  * Dresser (large 8+): 350 lbs
  * TV 40-49": 280 lbs
  * TV 50-59": 315 lbs
  * TV 60"+: 385 lbs
  * Refrigerator (≤6 cu ft): 210 lbs
  * Refrigerator (7-10 cu ft): 315 lbs
  * Washer/Dryer: 175 lbs each
  * Microwave: 70 lbs
  * Upright piano: 490 lbs
  * Baby grand piano: 560 lbs
  * Pool table: 280 lbs
  * Box (medium): 21 lbs
  * Box (large): 42 lbs
  * For other items: use ~7 lbs per cubic foot as rule of thumb

EXAMPLE OUTPUT:
[
  {
    "label": "Large Oak Dining Table",
    "qty": 1,
    "confidence": 0.98,
    "notes": "Dining room centerpiece, seats 6-8 people",
    "room": "Dining Room",
    "size": "Large",
    "cubicFeet": 30,
    "weight": 210
  },
  {
    "label": "Dining Chairs",
    "qty": 6,
    "confidence": 0.95,
    "notes": "Matching upholstered dining chairs around table",
    "room": "Dining Room",
    "size": "Standard",
    "cubicFeet": 5,
    "weight": 35
  },
  {
    "label": "TV",
    "qty": 1,
    "confidence": 0.92,
    "notes": "Wall-mounted TV in living room",
    "room": "Living Room",
    "size": "55-65 inch range",
    "cubicFeet": 45,
    "weight": 315
  },
  {
    "label": "Coffee Table",
    "qty": 1,
    "confidence": 0.90,
    "notes": "Center of living room",
    "room": "Living Room",
    "size": "Large (5-6 ft long)",
    "cubicFeet": 12,
    "weight": 84
  }
]

Remember: Only detect items that professional movers can physically pick up and transport. Skip built-in, fixed, or permanently installed items.`
                },
              {
                type: 'image_url',
                image_url: { 
                  url: photoUrl,
                  detail: 'high' // Maximum detail for best accuracy
                }
              }
            ]
          }],
          max_tokens: 2000, // Increased for detailed responses
          temperature: 0.1 // Low temperature for consistent, accurate results
        })
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('OpenAI API error:', response.status, errorText);
        continue;
      }
      
      const data = await response.json();
      const content = data.choices[0].message.content;
      
      console.log('OpenAI response:', content);
      
      // Parse the JSON response
      try {
        // Clean the response by removing markdown code blocks
        let cleanContent = content.trim();
        if (cleanContent.startsWith('```json')) {
          cleanContent = cleanContent.replace(/^```json\s*/, '').replace(/\s*```$/, '');
        } else if (cleanContent.startsWith('```')) {
          cleanContent = cleanContent.replace(/^```\s*/, '').replace(/\s*```$/, '');
        }
        
        const analysis = JSON.parse(cleanContent);
        
        // Add source photo ID to each detection
        analysis.forEach((item: any) => {
          // Use detected cubicFeet/weight if provided, otherwise estimate
          let cubicFeet = item.cubicFeet;
          let weight = item.weight;
          
          if (!cubicFeet || cubicFeet === 0) {
            // Fallback to estimator
            cubicFeet = estimateCubicFeet(item.label, item.size);
            console.log(`⚠️ Missing cubicFeet for "${item.label}", estimated: ${cubicFeet} cu ft`);
          }
          
          if (!weight || weight === 0) {
            // Estimate weight from cubic feet and item label (more accurate)
            weight = estimateWeight(cubicFeet, item.label, item.size);
          }
          
          allDetections.push({
            label: item.label,
            qty: item.qty || 1,
            confidence: item.confidence || 0.9,
            sourcePhotoId: photoUrl,
            notes: item.notes || `Detected by OpenAI GPT-4o`,
            room: item.room || 'Unknown Room',
            size: item.size || '',
            cubicFeet: cubicFeet,
            weight: weight
          });
        });
        
        console.log(`Detected ${analysis.length} items in photo`);
        
      } catch (parseError) {
        console.error('Failed to parse OpenAI response:', parseError);
        console.log('Raw response:', content);
      }
      
    } catch (error) {
      console.error('OpenAI Vision error:', error);
      // Continue with other photos even if one fails
    }
  }
  
  console.log(`Total detections before deduplication: ${allDetections.length}`);
  const deduplicated = deduplicateDetections(allDetections);
  console.log(`Total detections after deduplication: ${deduplicated.length}`);
  console.log(`Duplicates removed: ${allDetections.length - deduplicated.length}`);
  return deduplicated;
};

// Enhanced deduplication for maximum accuracy
const deduplicateDetections = (detections: Detection[]): Detection[] => {
  const deduplicated: Detection[] = [];
  const seen = new Map<string, Detection>();
  let duplicatesFound = 0;
  
  detections.forEach(detection => {
    // Create a sophisticated key that includes room and size context
    const normalizedLabel = detection.label.toLowerCase()
      .replace(/\b(large|small|big|little|tall|short|wide|narrow|standard|medium)\b/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    
    const key = `${normalizedLabel}-${detection.room}-${detection.sourcePhotoId}`;
    
    if (!seen.has(key)) {
      seen.set(key, detection);
      deduplicated.push(detection);
    } else {
      // Merge quantities for similar items in the same photo and room
      const existing = seen.get(key)!;
      console.log(`🔄 Merging duplicate: "${detection.label}" (${detection.qty} + ${existing.qty} = ${detection.qty + existing.qty})`);
      existing.qty += detection.qty;
      existing.confidence = Math.max(existing.confidence, detection.confidence);
      duplicatesFound++;
      
      // Update notes to include both descriptions
      if (detection.notes && detection.notes !== existing.notes) {
        existing.notes = `${existing.notes}; ${detection.notes}`;
      }
    }
  });
  
  console.log(`✅ Deduplication complete: ${deduplicated.length} unique items, ${duplicatesFound} duplicates merged`);
  return deduplicated;
};