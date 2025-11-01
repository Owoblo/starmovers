/**
 * Cubic Feet Estimator
 * Fallback estimator for items when AI detection doesn't provide cubic feet
 * Uses standard moving industry estimates based on item type and size
 */

interface EstimationRule {
  pattern: RegExp;
  baseCf: number;
  baseWeight?: number; // Specific weight if different from 7 lbs/cf
  weightPerCf?: number; // Custom weight density per cubic foot (default: 7)
  sizeMultiplier?: {
    small?: number;
    medium?: number;
    large?: number;
    extraLarge?: number;
  };
  weightMultiplier?: {
    small?: number;
    medium?: number;
    large?: number;
    extraLarge?: number;
  };
}

const estimationRules: EstimationRule[] = [
  // Seating - Using Saturn Star Movers cube sheet weights
  { pattern: /sofa.*3.*cushion|sectional/i, baseCf: 35, baseWeight: 245 }, // 3-cushion sofa: 245 lbs
  { pattern: /sofa|couch/i, baseCf: 35, baseWeight: 245, sizeMultiplier: { small: 0.7, large: 1.5, extraLarge: 2 }, weightMultiplier: { small: 0.7, large: 1.5, extraLarge: 2 } },
  { pattern: /loveseat/i, baseCf: 30, baseWeight: 210 }, // Loveseat: 210 lbs
  { pattern: /armchair/i, baseCf: 12, baseWeight: 105 }, // Armchair: 105 lbs
  { pattern: /recliner/i, baseCf: 25, baseWeight: 175 },
  { pattern: /accent chair|office chair/i, baseCf: 12, baseWeight: 84 },
  { pattern: /dining chair|kitchen chair/i, baseCf: 5, baseWeight: 35 }, // Dining chair: 35 lbs
  { pattern: /bar stool/i, baseCf: 5, baseWeight: 35 },
  { pattern: /ottoman/i, baseCf: 8, baseWeight: 56 },
  { pattern: /rocking chair/i, baseCf: 15, baseWeight: 105 },
  
  // Tables - Using Saturn Star Movers cube sheet weights
  { pattern: /dining table.*4.*6|dining table/i, baseCf: 30, baseWeight: 210, sizeMultiplier: { small: 0.8, large: 1.5 }, weightMultiplier: { small: 0.8, large: 1.5 } }, // Dining table: 210 lbs
  { pattern: /coffee table/i, baseCf: 12, baseWeight: 84, sizeMultiplier: { small: 0.7, large: 1.5 }, weightMultiplier: { small: 0.7, large: 1.5 } }, // Coffee table: 84 lbs
  { pattern: /end table/i, baseCf: 5, baseWeight: 35 }, // End table: 35 lbs
  { pattern: /side table|console table/i, baseCf: 5, baseWeight: 35 },
  { pattern: /kitchen island/i, baseCf: 40, baseWeight: 280, sizeMultiplier: { small: 0.7, large: 1.3 }, weightMultiplier: { small: 0.7, large: 1.3 } },
  { pattern: /outdoor table/i, baseCf: 15, baseWeight: 105 },
  
  // Beds - Using Saturn Star Movers cube sheet weights
  { pattern: /bed.*single|bed.*twin|twin bed|single bed/i, baseCf: 45, baseWeight: 315 }, // Single/double: 280-420 lbs range
  { pattern: /bed.*double|double bed|full bed/i, baseCf: 50, baseWeight: 350 },
  { pattern: /queen bed/i, baseCf: 65, baseWeight: 455 }, // Queen bed: 455 lbs
  { pattern: /king bed/i, baseCf: 70, baseWeight: 490 }, // King bed: 490 lbs
  { pattern: /mattress|box spring/i, baseCf: 25, baseWeight: 175 },
  
  // Storage - Using Saturn Star Movers cube sheet weights
  { pattern: /dresser.*small|dresser.*≤4/i, baseCf: 30, baseWeight: 210 }, // Dresser small (≤4 drawers): 210 lbs
  { pattern: /dresser.*medium|dresser.*5.*8/i, baseCf: 40, baseWeight: 280, sizeMultiplier: { small: 0.7, medium: 1, large: 1.5 }, weightMultiplier: { small: 0.7, medium: 1, large: 1.5 } }, // Medium (5-8 drawers): 280 lbs
  { pattern: /dresser.*large|dresser.*8\+/i, baseCf: 50, baseWeight: 350 }, // Large (8+ drawers): 350 lbs
  { pattern: /dresser/i, baseCf: 40, baseWeight: 280, sizeMultiplier: { small: 0.7, medium: 1, large: 1.5 }, weightMultiplier: { small: 0.7, medium: 1, large: 1.5 } },
  { pattern: /chest of drawers/i, baseCf: 30, baseWeight: 210 },
  { pattern: /nightstand/i, baseCf: 5, baseWeight: 35 }, // Nightstand: 35 lbs
  { pattern: /wardrobe.*small/i, baseCf: 20, baseWeight: 140 }, // Wardrobe small: 140 lbs
  { pattern: /wardrobe.*large/i, baseCf: 40, baseWeight: 280 }, // Wardrobe large: 280 lbs
  { pattern: /wardrobe|armoire/i, baseCf: 40, baseWeight: 280, sizeMultiplier: { small: 0.7, large: 1.8 }, weightMultiplier: { small: 0.7, large: 1.8 } },
  { pattern: /bookshelf|bookcase/i, baseCf: 20, baseWeight: 140, sizeMultiplier: { small: 0.7, large: 1.5 }, weightMultiplier: { small: 0.7, large: 1.5 } }, // Bookshelf: 140-210 lbs range
  { pattern: /china cabinet/i, baseCf: 15, baseWeight: 105, sizeMultiplier: { small: 0.7, large: 1.5 }, weightMultiplier: { small: 0.7, large: 1.5 } }, // China cabinet: 70-140 lbs range
  { pattern: /cabinet/i, baseCf: 15, baseWeight: 105 },
  
  // Electronics - Using Saturn Star Movers cube sheet weights
  { pattern: /tv.*40.*49|television.*40.*49/i, baseCf: 40, baseWeight: 280 }, // TV 40-49": 280 lbs
  { pattern: /tv.*50.*59|television.*50.*59/i, baseCf: 45, baseWeight: 315 }, // TV 50-59": 315 lbs
  { pattern: /tv.*60\+|television.*60\+|tv.*70\+/i, baseCf: 55, baseWeight: 385 }, // TV 60"+: 385 lbs
  { pattern: /tv|television/i, baseCf: 40, baseWeight: 280 }, // Default for TV
  { pattern: /entertainment center|tv stand|media center/i, baseCf: 50, baseWeight: 350 },
  
  // Appliances - Using Saturn Star Movers cube sheet weights
  { pattern: /refrigerator.*≤6|fridge.*≤6/i, baseCf: 30, baseWeight: 210 }, // Refrigerator ≤6 cu ft: 210 lbs
  { pattern: /refrigerator.*7.*10|fridge.*7.*10/i, baseCf: 45, baseWeight: 315 }, // Refrigerator 7-10 cu ft: 315 lbs
  { pattern: /refrigerator|fridge/i, baseCf: 35, baseWeight: 245, sizeMultiplier: { small: 0.7, large: 1.5 }, weightMultiplier: { small: 0.7, large: 1.5 } },
  { pattern: /washer|washing machine/i, baseCf: 25, baseWeight: 175 }, // Washer: 175 lbs
  { pattern: /dryer/i, baseCf: 25, baseWeight: 175 }, // Dryer: 175 lbs
  { pattern: /microwave/i, baseCf: 10, baseWeight: 70 }, // Microwave: 70 lbs
  { pattern: /microwave.*cart/i, baseCf: 15, baseWeight: 105 }, // Microwave cart: 105 lbs
  { pattern: /dishwasher/i, baseCf: 12, baseWeight: 84 },
  { pattern: /stove|oven|range/i, baseCf: 15, baseWeight: 105 },
  
  // Specialty Items - Using Saturn Star Movers cube sheet weights
  { pattern: /piano.*upright/i, baseCf: 70, baseWeight: 490, weightPerCf: 7 }, // Upright piano: 490 lbs
  { pattern: /piano.*baby grand|piano.*grand/i, baseCf: 80, baseWeight: 560, weightPerCf: 7 }, // Baby grand: 560 lbs
  { pattern: /piano/i, baseCf: 70, baseWeight: 490 },
  { pattern: /pool table|billiard table/i, baseCf: 40, baseWeight: 280 }, // Pool table: 280 lbs
  { pattern: /safe.*<300|safe.*under.*300/i, baseCf: 10, baseWeight: 150 }, // Safe <300lb: ~150 lbs (varies)
  { pattern: /safe.*300.*600|safe.*300-600/i, baseCf: 25, baseWeight: 450 }, // Safe 300-600lb: ~450 lbs
  { pattern: /safe/i, baseCf: 10, baseWeight: 150, sizeMultiplier: { large: 3 }, weightMultiplier: { large: 4 } },
  { pattern: /treadmill|exercise equipment|gym equipment/i, baseCf: 30, baseWeight: 200 },
  { pattern: /aquarium|fish tank/i, baseCf: 20, baseWeight: 200, sizeMultiplier: { small: 0.5, large: 3 }, weightMultiplier: { small: 0.5, large: 5 } }, // Aquariums are heavy due to glass/water
  
  // Outdoor
  { pattern: /outdoor sofa|patio sofa/i, baseCf: 50, baseWeight: 350 },
  { pattern: /outdoor chair|patio chair/i, baseCf: 5, baseWeight: 35 },
  { pattern: /outdoor dining table/i, baseCf: 30, baseWeight: 210 },
  { pattern: /grill|bbq/i, baseCf: 25, baseWeight: 175 },
  
  // Garage/Workshop
  { pattern: /workbench/i, baseCf: 50, baseWeight: 350, sizeMultiplier: { small: 0.7, large: 1.5 }, weightMultiplier: { small: 0.7, large: 1.5 } },
  { pattern: /boat.*10.*12|aluminum.*boat/i, baseCf: 250, baseWeight: 800 }, // 10-12ft aluminum boat: ~800-1000 lbs
  { pattern: /boat/i, baseCf: 250, baseWeight: 1000, sizeMultiplier: { small: 0.7, large: 1.5 }, weightMultiplier: { small: 0.7, large: 1.5 } },
  { pattern: /riding.*lawn.*mower|riding.*mower/i, baseCf: 150, baseWeight: 500 }, // Riding mower: ~500 lbs
  { pattern: /lawn.*mower|mower/i, baseCf: 15, baseWeight: 50 }, // Push mower: ~50 lbs
  { pattern: /shop.*vacuum|vacuum.*shop/i, baseCf: 10, baseWeight: 50 },
  
  // Misc
  { pattern: /desk|office desk/i, baseCf: 60, baseWeight: 420, sizeMultiplier: { small: 0.7, large: 1.3 }, weightMultiplier: { small: 0.7, large: 1.3 } },
  { pattern: /file.*cabinet.*medium/i, baseCf: 10, baseWeight: 70 }, // File cabinet medium: 70 lbs
  { pattern: /file.*cabinet.*large/i, baseCf: 20, baseWeight: 140 }, // File cabinet large: 140 lbs
  { pattern: /file.*cabinet/i, baseCf: 10, baseWeight: 70 },
  { pattern: /mirror/i, baseCf: 3, baseWeight: 20, sizeMultiplier: { large: 5 }, weightMultiplier: { large: 5 } },
  { pattern: /lamp.*floor|floor lamp/i, baseCf: 3, baseWeight: 20 },
  { pattern: /lamp.*table|table lamp/i, baseCf: 2, baseWeight: 14 },
  { pattern: /rug.*large|area.*rug.*large/i, baseCf: 10, baseWeight: 70 }, // Large rug: 70 lbs
  { pattern: /rug.*small|small.*rug/i, baseCf: 3, baseWeight: 21 }, // Small rug: 21 lbs
  { pattern: /rug|area rug/i, baseCf: 10, baseWeight: 70, sizeMultiplier: { small: 0.5, large: 2 }, weightMultiplier: { small: 0.3, large: 2 } },
  { pattern: /plant|potted plant/i, baseCf: 5, baseWeight: 35, sizeMultiplier: { small: 0.5, large: 3 }, weightMultiplier: { small: 0.5, large: 5 } },
  { pattern: /box.*medium|cardboard.*box.*medium/i, baseCf: 3, baseWeight: 21 }, // Box medium: 21 lbs
  { pattern: /box.*large|cardboard.*box.*large/i, baseCf: 6, baseWeight: 42 }, // Box large: 42 lbs
  { pattern: /dish.*pack.*box/i, baseCf: 10, baseWeight: 70 }, // Dish-pack box: 70 lbs
  { pattern: /wardrobe.*box/i, baseCf: 16, baseWeight: 112 }, // Wardrobe box: 112 lbs
  { pattern: /box|cardboard box/i, baseCf: 6, baseWeight: 42, sizeMultiplier: { small: 3, large: 10 }, weightMultiplier: { small: 0.5, large: 2 } },
  { pattern: /water dispenser/i, baseCf: 10, baseWeight: 70 },
  { pattern: /christmas tree/i, baseCf: 15, baseWeight: 30 },
  { pattern: /storage.*drawer|plastic.*drawer/i, baseCf: 8, baseWeight: 30 },
  { pattern: /folding chair/i, baseCf: 5, baseWeight: 35 },
  { pattern: /sofa.*sectional.*piece/i, baseCf: 10, baseWeight: 70 }, // Sectional piece: 70 lbs
];

/**
 * Estimate cubic feet for an item based on its label and size descriptor
 */
export function estimateCubicFeet(label: string, size?: string): number {
  const normalizedLabel = label.toLowerCase();
  const normalizedSize = size?.toLowerCase() || '';
  
  // Try to find matching rule
  for (const rule of estimationRules) {
    if (rule.pattern.test(normalizedLabel)) {
      let cf = rule.baseCf;
      
      // Apply size multiplier if available
      if (rule.sizeMultiplier) {
        if (normalizedSize.includes('small') || normalizedSize.includes('compact')) {
          cf = rule.baseCf * (rule.sizeMultiplier.small || 1);
        } else if (normalizedSize.includes('large') || normalizedSize.includes('big')) {
          cf = rule.baseCf * (rule.sizeMultiplier.large || 1);
        } else if (normalizedSize.includes('extra large') || normalizedSize.includes('xl')) {
          cf = rule.baseCf * (rule.sizeMultiplier.extraLarge || 1.5);
        } else if (normalizedSize.includes('medium')) {
          cf = rule.baseCf * (rule.sizeMultiplier.medium || 1);
        }
      }
      
      // Special size-based adjustments for specific items
      if (normalizedLabel.includes('tv') || normalizedLabel.includes('television')) {
        // Extract size from size descriptor (e.g., "55-inch" or "65-75 inch range")
        const inchMatch = normalizedSize.match(/(\d+)\s*[-+]?\s*inch/i) || normalizedLabel.match(/(\d+)\s*[-+]?\s*inch/i);
        if (inchMatch) {
          const inches = parseInt(inchMatch[1]);
          if (inches >= 70) cf = 55;
          else if (inches >= 60) cf = 45;
          else if (inches >= 50) cf = 40;
          else if (inches >= 40) cf = 35;
        }
      }
      
      return Math.round(cf * 10) / 10; // Round to 1 decimal
    }
  }
  
  // Default fallback: estimate based on common furniture sizes
  if (normalizedLabel.includes('large') || normalizedLabel.includes('big')) {
    return 30;
  } else if (normalizedLabel.includes('small') || normalizedLabel.includes('compact')) {
    return 8;
  }
  
  // Generic default
  return 15;
}

/**
 * Estimate weight for an item based on its label, size descriptor, and cubic feet
 * Uses item-specific weights from Saturn Star Movers cube sheet when available
 */
export function estimateWeight(cubicFeet: number, label?: string, size?: string): number {
  // If we have a label, try to get item-specific weight
  if (label) {
    const normalizedLabel = label.toLowerCase();
    const normalizedSize = size?.toLowerCase() || '';
    
    // Try to find matching rule for weight
    for (const rule of estimationRules) {
      if (rule.pattern.test(normalizedLabel)) {
        // Use baseWeight if specified (more accurate than calculated)
        if (rule.baseWeight !== undefined) {
          let weight = rule.baseWeight;
          
          // Apply weight multiplier if available
          if (rule.weightMultiplier) {
            if (normalizedSize.includes('small') || normalizedSize.includes('compact')) {
              weight = rule.baseWeight * (rule.weightMultiplier.small || 1);
            } else if (normalizedSize.includes('large') || normalizedSize.includes('big')) {
              weight = rule.baseWeight * (rule.weightMultiplier.large || 1);
            } else if (normalizedSize.includes('extra large') || normalizedSize.includes('xl')) {
              weight = rule.baseWeight * (rule.weightMultiplier.extraLarge || 1.5);
            } else if (normalizedSize.includes('medium')) {
              weight = rule.baseWeight * (rule.weightMultiplier.medium || 1);
            }
          }
          
          // Adjust weight proportionally if cubic feet was adjusted from base
          const calculatedCf = estimateCubicFeet(label, size);
          if (calculatedCf !== rule.baseCf && calculatedCf > 0) {
            weight = (weight / rule.baseCf) * calculatedCf;
          }
          
          return Math.round(weight);
        }
        
        // Use custom weight density if specified
        if (rule.weightPerCf !== undefined) {
          return Math.round(cubicFeet * rule.weightPerCf);
        }
      }
    }
  }
  
  // Default fallback: standard rule of thumb (7 lbs per cubic foot for most furniture)
  return Math.round(cubicFeet * 7);
}

