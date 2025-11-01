import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Detection, MappingTable, Estimate } from '../types';
import { calculateEstimate } from '../lib/estimate';
import { GoogleMapsService } from '../lib/googleMapsService';
import { SimplePDFService } from '../lib/simplePDFService';
import { SaturnGPTService, SaturnMoveTimeResponse } from '../lib/saturnGPTService';
import ThemeToggle from '../components/ThemeToggle';

interface LocationState {
  address: string;
  detections: Detection[];
  estimate: Estimate;
  mapping: MappingTable;
}

interface Upsell {
  id: string;
  name: string;
  description: string;
  price: number;
  recommended: boolean;
  selected: boolean;
}

export default function EstimatePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as LocationState;

  const [customerInfo, setCustomerInfo] = useState({
    name: '',
    email: '',
    phone: '',
    moveDate: ''
  });

  const [originAddress, setOriginAddress] = useState(state?.address || '');
  const [destinationAddress, setDestinationAddress] = useState('');
  const [detections] = useState<Detection[]>(state?.detections || []);
  const [mapping] = useState<MappingTable>(state?.mapping || {});
  const [baseEstimate] = useState<Estimate>(state?.estimate || {
    crew: 3,
    rate: 75,
    travelMins: 30,
    stairs: false,
    elevator: false,
    wrapping: false,
    safetyPct: 10,
    hours: 0,
    total: 0
  });

  // Generate upsells based on detected items - auto-select items that need special care
  const [upsells, setUpsells] = useState<Upsell[]>(() => {
    const initialUpsells: Upsell[] = [
      {
        id: 'insurance',
        name: 'Moving Insurance',
        description: 'Protect your belongings during the move',
        price: (state?.estimate?.total || 0) * 0.05, // 5% of total
        recommended: true,
        selected: false
      },
      {
        id: 'packing',
        name: 'Packing Service',
        description: 'Professional packing of your items',
        price: detections.reduce((sum, d) => sum + (d.qty * 25), 0), // $25 per item
        recommended: detections.length > 10,
        selected: false
      },
      {
        id: 'unpacking',
        name: 'Unpacking Service',
        description: 'We unpack and organize at your new location',
        price: detections.reduce((sum, d) => sum + (d.qty * 15), 0), // $15 per item
        recommended: false,
        selected: false
      }
    ];

    // Detect TVs - AUTO-SELECT TV boxes (they NEED special boxes)
    const tvDetections = detections.filter(d => 
      d.label.toLowerCase().includes('tv') || 
      d.label.toLowerCase().includes('television') ||
      d.label.toLowerCase().includes('flat screen')
    );
    const tvCount = tvDetections.reduce((sum, d) => sum + d.qty, 0);

    if (tvCount > 0) {
      initialUpsells.push({
        id: 'tv-boxes',
        name: `TV Boxes (${tvCount} TV${tvCount > 1 ? 's' : ''})`,
        description: 'Specialty boxes and protective wrapping - Required for safe transport',
        price: tvCount * 35,
        recommended: true,
        selected: true // AUTO-SELECTED - TVs need boxes!
      });
    }

    // Detect fragile items (art, pictures, mirrors) - recommend fragile packing
    const fragileDetections = detections.filter(d => 
      d.label.toLowerCase().includes('art') ||
      d.label.toLowerCase().includes('picture') ||
      d.label.toLowerCase().includes('painting') ||
      d.label.toLowerCase().includes('mirror') ||
      d.label.toLowerCase().includes('glass')
    );
    const fragileCount = fragileDetections.reduce((sum, d) => sum + d.qty, 0);

    if (fragileCount > 0) {
      initialUpsells.push({
        id: 'fragile-packing',
        name: `Fragile Item Packing (${fragileCount} item${fragileCount > 1 ? 's' : ''})`,
        description: 'Special wrapping and cushioning for fragile items',
        price: fragileCount * 20,
        recommended: true,
        selected: false
      });
    }

    // Detect specialty items - recommend specialty handling
    const specialtyDetections = detections.filter(d => 
      d.label.toLowerCase().includes('piano') ||
      d.label.toLowerCase().includes('treadmill') ||
      d.label.toLowerCase().includes('pool table') ||
      d.label.toLowerCase().includes('safe') ||
      d.label.toLowerCase().includes('grandfather clock')
    );
    const specialtyCount = specialtyDetections.reduce((sum, d) => sum + d.qty, 0);

    if (specialtyCount > 0) {
      initialUpsells.push({
        id: 'specialty-handling',
        name: `Specialty Item Handling (${specialtyCount} item${specialtyCount > 1 ? 's' : ''})`,
        description: 'Expert handling for heavy or delicate specialty items',
        price: specialtyCount * 100,
        recommended: true,
        selected: false
      });
    }

    return initialUpsells;
  });

  const [travelDistance, setTravelDistance] = useState(0);
  const [travelTime, setTravelTime] = useState(0);
  const [isCalculatingDistance, setIsCalculatingDistance] = useState(false);
  const [isCalculatingGPT, setIsCalculatingGPT] = useState(false);
  const [distanceError, setDistanceError] = useState<string | null>(null);
  const [gptError, setGptError] = useState<string | null>(null);
  const [finalEstimate, setFinalEstimate] = useState<Estimate>({ ...baseEstimate });
  const [gptReasoning, setGptReasoning] = useState<string | null>(null);
  const [gptBreakdown, setGptBreakdown] = useState<SaturnMoveTimeResponse['breakdown'] | null>(null);

  // Building/Parking details for GPT calculation
  const [originType, setOriginType] = useState<'house' | 'apartment' | 'condo' | 'business'>('house');
  const [destinationType, setDestinationType] = useState<'house' | 'apartment' | 'condo' | 'business'>('house');
  const [stairsDestination, setStairsDestination] = useState(false);
  const [elevatorDestination, setElevatorDestination] = useState(false);
  const [floorOrigin, setFloorOrigin] = useState<number | undefined>();
  const [floorDestination, setFloorDestination] = useState<number | undefined>();
  const [parkingOrigin, setParkingOrigin] = useState<'driveway' | 'street' | 'parking_lot' | 'difficult'>('driveway');
  const [parkingDestination, setParkingDestination] = useState<'driveway' | 'street' | 'parking_lot' | 'difficult'>('driveway');

  // Auto-calculate distance and GPT estimate when both addresses are provided
  useEffect(() => {
    const calculateGPTEstimate = async () => {
      if (!originAddress || !destinationAddress || destinationAddress.length < 10) {
        return; // Wait for complete addresses
      }

      if (detections.length === 0) {
        return; // Need inventory first
      }

      setIsCalculatingDistance(true);
      setIsCalculatingGPT(true);
      setDistanceError(null);
      setGptError(null);

      try {
        // Step 1: Get distance first
        const distanceResult = await GoogleMapsService.getDistance(
          originAddress,
          destinationAddress
        );

        setTravelDistance(Math.round(distanceResult.distance));
        setTravelTime(distanceResult.duration);

        // Step 2: Calculate total cubic feet and weight from detections
        const totalCubicFeet = detections.reduce((sum, d) => {
          // Priority: detected value > mapping > 0 (shouldn't happen with estimator)
          const cf = d.cubicFeet || mapping[d.label]?.cf || 0;
          return sum + (cf * d.qty);
        }, 0);

        const totalWeight = detections.reduce((sum, d) => {
          // Priority: detected weight > calculated from cubicFeet > mapping table > 0
          let weight = 0;
          if (d.weight && d.weight > 0) {
            weight = d.weight;
          } else if (d.cubicFeet && d.cubicFeet > 0) {
            weight = d.cubicFeet * 7;
          } else if (mapping[d.label]?.cf) {
            weight = mapping[d.label].cf * 7;
          }
          return sum + (weight * d.qty);
        }, 0);

        console.log(`📊 Volume Calculation: ${totalCubicFeet.toFixed(1)} cu ft, ${totalWeight.toFixed(0)} lbs total from ${detections.length} items`);

        // Step 3: Call GPT for accurate move time calculation
        const gptResult = await SaturnGPTService.calculateMoveTime({
          detections: detections.map(d => ({
            label: d.label,
            qty: d.qty,
            cubicFeet: d.cubicFeet || mapping[d.label]?.cf,
            weight: d.weight || (mapping[d.label]?.cf ? mapping[d.label].cf * 7 : undefined),
            size: d.size,
            room: d.room
          })),
          distance: distanceResult.distance,
          travelTime: distanceResult.duration,
          originType,
          destinationType,
          stairsOrigin: baseEstimate.stairs,
          stairsDestination,
          elevatorOrigin: baseEstimate.elevator,
          elevatorDestination,
          floorOrigin,
          floorDestination,
          parkingOrigin,
          parkingDestination
        });

        // Step 4: Update estimate with GPT results
        setFinalEstimate({
          ...baseEstimate,
          hours: gptResult.hoursStandard,
          crew: gptResult.recommendedCrew,
          rate: gptResult.crewRate / gptResult.recommendedCrew,
          total: gptResult.totalBeforeTax - gptResult.surchargesTotal,
          travelMins: distanceResult.duration
        });

        // Step 5: Auto-apply detected upsells from GPT
        const newUpsells = [...upsells];

        // Update existing upsells with GPT recommendations
        gptResult.detectedUpsells.forEach(gptUpsell => {
          const existingIndex = newUpsells.findIndex(u => u.id === gptUpsell.id);
          if (existingIndex >= 0) {
            newUpsells[existingIndex] = {
              ...newUpsells[existingIndex],
              price: gptUpsell.price,
              description: gptUpsell.reason,
              recommended: true,
              selected: gptUpsell.required || newUpsells[existingIndex].selected
            };
          } else {
            // Add new upsell from GPT
            newUpsells.push({
              id: gptUpsell.id,
              name: gptUpsell.name,
              description: gptUpsell.reason,
              price: gptUpsell.price,
              recommended: true,
              selected: gptUpsell.required
            });
          }
        });

        // Add specialty item surcharges as separate upsells
        if (gptResult.specialtyItems.length > 0) {
          gptResult.specialtyItems.forEach(item => {
            const existingSpecialtyIndex = newUpsells.findIndex(u => u.id === `specialty-${item.category}`);
            if (existingSpecialtyIndex < 0) {
              newUpsells.push({
                id: `specialty-${item.category}`,
                name: `${item.item} Specialty Handling`,
                description: `Specialty handling for ${item.item} (+${item.extraTime} min)`,
                price: item.surcharge,
                recommended: true,
                selected: true
              });
            }
          });
        }

        setUpsells(newUpsells);
        setGptReasoning(gptResult.reasoning);
        setGptBreakdown(gptResult.breakdown);

      } catch (error: any) {
        console.error('GPT Estimate Error:', error);
        setGptError(error.message || 'Could not calculate estimate with GPT');

        // Fallback to simple calculation if GPT fails
        try {
          const distanceResult = await GoogleMapsService.getDistance(
            originAddress,
            destinationAddress
          );
          const updatedEstimate = {
            ...baseEstimate,
            travelMins: distanceResult.duration
          };
          const result = calculateEstimate(detections, mapping, updatedEstimate);
          setFinalEstimate({ ...updatedEstimate, ...result });
        } catch (fallbackError: any) {
          setDistanceError(fallbackError.message || 'Could not calculate distance');
        }
      } finally {
        setIsCalculatingDistance(false);
        setIsCalculatingGPT(false);
      }
    };

    // Debounce to avoid too many API calls
    const timer = setTimeout(() => {
      calculateGPTEstimate();
    }, 1500);

    return () => clearTimeout(timer);
  }, [originAddress, destinationAddress, detections, mapping, baseEstimate, originType, destinationType, stairsDestination, elevatorDestination, floorOrigin, floorDestination, parkingOrigin, parkingDestination]);

  const handleUpsellToggle = (id: string) => {
    setUpsells(prev => prev.map(u => 
      u.id === id ? { ...u, selected: !u.selected } : u
    ));
  };

  const handleSendQuote = () => {
    const totalUpsells = upsells.filter(u => u.selected).reduce((sum, u) => sum + u.price, 0);
    const finalTotal = finalEstimate.total + totalUpsells;

    navigate('/quote-preview', {
      state: {
        customerName: customerInfo.name,
        customerEmail: customerInfo.email,
        customerPhone: customerInfo.phone,
        moveDate: customerInfo.moveDate,
        originAddress,
        destinationAddress,
        detections,
        estimate: finalEstimate,
        upsells: upsells.filter(u => u.selected),
        totalAmount: finalTotal,
        photos: [] // Add photos if available
      }
    });
  };

  const handleDownloadPDF = async () => {
    const totalUpsells = upsells.filter(u => u.selected).reduce((sum, u) => sum + u.price, 0);
    const finalTotal = finalEstimate.total + totalUpsells;

    try {
      await SimplePDFService.downloadQuote({
        customerName: customerInfo.name,
        customerEmail: customerInfo.email,
        customerPhone: customerInfo.phone,
        moveDate: customerInfo.moveDate,
        originAddress,
        destinationAddress,
        detections,
        estimate: finalEstimate,
        upsells: upsells.filter(u => u.selected),
        totalAmount: finalTotal,
        photos: [],
        id: 'preview'
      });
    } catch (error) {
      console.error('PDF download error:', error);
      alert('Failed to download PDF. Please try again.');
    }
  };

  const handleContinue = () => {
    navigate('/dashboard');
  };

  const totalUpsells = upsells.filter(u => u.selected).reduce((sum, u) => sum + u.price, 0);
  const finalTotal = finalEstimate.total + totalUpsells;

  const totalItems = detections.reduce((sum, d) => sum + d.qty, 0);
  const totalCubicFeet = detections.reduce((sum, detection) => {
    const cf = detection.cubicFeet || mapping[detection.label]?.cf || 0;
    const totalCf = cf * detection.qty;
    
    if (!detection.cubicFeet && !mapping[detection.label]?.cf) {
      console.warn(`⚠️ Missing cubicFeet for "${detection.label}" - using 0 as fallback`);
    }
    
    return sum + totalCf;
  }, 0);

  const totalWeight = detections.reduce((sum, detection) => {
    let weight = 0;
    if (detection.weight && detection.weight > 0) {
      weight = detection.weight;
    } else if (detection.cubicFeet && detection.cubicFeet > 0) {
      weight = detection.cubicFeet * 7;
    } else if (mapping[detection.label]?.cf) {
      weight = mapping[detection.label].cf * 7;
    }
    
    const totalWeight = weight * detection.qty;
    
    if (!detection.weight && !detection.cubicFeet && !mapping[detection.label]?.cf) {
      console.warn(`⚠️ Missing weight for "${detection.label}" - using 0 as fallback`);
    }
    
    return sum + totalWeight;
  }, 0);

  // Truck capacity check: 26ft truck = ~1,700 cubic feet
  const TRUCK_CAPACITY = 1700;
  const needsMultipleTrucks = totalCubicFeet > TRUCK_CAPACITY;
  const estimatedTrucks = needsMultipleTrucks ? Math.ceil(totalCubicFeet / TRUCK_CAPACITY) : 1;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50/30 to-purple-50/30 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 transition-colors duration-200">
      {/* Header */}
      <header className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-md border-b border-gray-200/50 dark:border-gray-700/50 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-4">
              <button
                onClick={() => navigate('/dashboard')}
                className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div>
                <h1 className="text-xl font-bold bg-gradient-to-r from-gray-900 to-gray-700 dark:from-gray-100 dark:to-gray-300 bg-clip-text text-transparent">
                  Complete Your Quote
                </h1>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Review and finalize your moving estimate</p>
              </div>
            </div>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
          {/* Left Column: Form */}
          <div className="lg:col-span-2 space-y-6">
            {/* Customer Information */}
            <div className="bg-white/70 dark:bg-gray-800/70 backdrop-blur-sm rounded-2xl shadow-lg border border-gray-200/50 dark:border-gray-700/50 p-6 lg:p-8 hover:shadow-xl transition-all duration-300">
              <div className="flex items-center space-x-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Customer Information</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Enter customer details for the quote</p>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-5">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Full Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={customerInfo.name}
                    onChange={(e) => setCustomerInfo(prev => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    placeholder="John Doe"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Email Address <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="email"
                    value={customerInfo.email}
                    onChange={(e) => setCustomerInfo(prev => ({ ...prev, email: e.target.value }))}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    placeholder="john@example.com"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Phone Number <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="tel"
                    value={customerInfo.phone}
                    onChange={(e) => setCustomerInfo(prev => ({ ...prev, phone: e.target.value }))}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    placeholder="(555) 123-4567"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Move Date <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="date"
                    value={customerInfo.moveDate}
                    onChange={(e) => setCustomerInfo(prev => ({ ...prev, moveDate: e.target.value }))}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                    min={new Date().toISOString().split('T')[0]}
                    required
                  />
                </div>
              </div>
            </div>

            {/* Origin & Destination */}
            <div className="bg-white/70 dark:bg-gray-800/70 backdrop-blur-sm rounded-2xl shadow-lg border border-gray-200/50 dark:border-gray-700/50 p-6 lg:p-8 hover:shadow-xl transition-all duration-300">
              <div className="flex items-center space-x-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center shadow-lg">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Origin & Destination</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Moving from and to locations</p>
                </div>
              </div>
              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Origin Address
                  </label>
                  <input
                    type="text"
                    value={originAddress}
                    onChange={(e) => setOriginAddress(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    placeholder="123 Main St, City, State"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      Origin Type
                    </label>
                    <select
                      value={originType}
                      onChange={(e) => setOriginType(e.target.value as any)}
                      className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                    >
                      <option value="house">House</option>
                      <option value="apartment">Apartment</option>
                      <option value="condo">Condo</option>
                      <option value="business">Business</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      Origin Floor (if applicable)
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={floorOrigin || ''}
                      onChange={(e) => setFloorOrigin(e.target.value ? parseInt(e.target.value) : undefined)}
                      className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                      placeholder="e.g. 3"
                    />
                  </div>
                </div>
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={baseEstimate.stairs}
                      disabled
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">Origin has stairs</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={baseEstimate.elevator}
                      disabled
                      className="w-4 h-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 dark:bg-gray-700"
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">Origin has elevator</span>
                  </label>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Origin Parking
                  </label>
                  <select
                    value={parkingOrigin}
                    onChange={(e) => setParkingOrigin(e.target.value as any)}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                  >
                    <option value="driveway">Driveway</option>
                    <option value="street">Street Parking</option>
                    <option value="parking_lot">Parking Lot</option>
                    <option value="difficult">Difficult/Limited</option>
                  </select>
                </div>

                <div className="border-t border-gray-200 dark:border-gray-700 pt-5 mt-5">
                  <div className="mb-5">
                    <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      Destination Address <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={destinationAddress}
                      onChange={(e) => setDestinationAddress(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                      placeholder="456 Oak Ave, City, State"
                      required
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        Destination Type
                      </label>
                      <select
                        value={destinationType}
                        onChange={(e) => setDestinationType(e.target.value as any)}
                        className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                      >
                        <option value="house">House</option>
                        <option value="apartment">Apartment</option>
                        <option value="condo">Condo</option>
                        <option value="business">Business</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        Destination Floor (if applicable)
                      </label>
                      <input
                        type="number"
                        min="1"
                        value={floorDestination || ''}
                        onChange={(e) => setFloorDestination(e.target.value ? parseInt(e.target.value) : undefined)}
                        className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                        placeholder="e.g. 5"
                      />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-4 mt-4">
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={stairsDestination}
                        onChange={(e) => setStairsDestination(e.target.checked)}
                        className="w-4 h-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 dark:bg-gray-700"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Destination has stairs</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={elevatorDestination}
                        onChange={(e) => setElevatorDestination(e.target.checked)}
                        className="w-4 h-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 dark:bg-gray-700"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Destination has elevator</span>
                    </label>
                  </div>
                  <div className="mt-4">
                    <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      Destination Parking
                    </label>
                    <select
                      value={parkingDestination}
                      onChange={(e) => setParkingDestination(e.target.value as any)}
                      className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white/50 dark:bg-gray-700/50 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                    >
                      <option value="driveway">Driveway</option>
                      <option value="street">Street Parking</option>
                      <option value="parking_lot">Parking Lot</option>
                      <option value="difficult">Difficult/Limited</option>
                    </select>
                  </div>
                </div>
                
                {/* Distance & Travel Time */}
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4 mt-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-gray-700 dark:text-gray-300">Travel Distance</div>
                      {isCalculatingDistance ? (
                        <div className="flex items-center space-x-2 mt-1">
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 dark:border-blue-400"></div>
                          <span className="text-xs text-gray-600 dark:text-gray-400">Calculating...</span>
                        </div>
                      ) : travelDistance > 0 ? (
                        <div className="text-lg font-bold text-gray-900 dark:text-gray-100 mt-1">{travelDistance} miles</div>
                      ) : (
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Enter addresses to calculate</div>
                      )}
                    </div>
                    {travelTime > 0 && (
                      <div className="text-right">
                        <div className="text-sm font-semibold text-gray-700 dark:text-gray-300">Travel Time</div>
                        <div className="text-lg font-bold text-gray-900 dark:text-gray-100 mt-1">{travelTime} min</div>
                      </div>
                    )}
                  </div>
                  {distanceError && (
                    <p className="text-xs text-red-600 dark:text-red-400 mt-2">{distanceError}</p>
                  )}
                </div>
              </div>
            </div>

            {/* Inventory Summary */}
            <div className="bg-white/70 dark:bg-gray-800/70 backdrop-blur-sm rounded-2xl shadow-lg border border-gray-200/50 dark:border-gray-700/50 p-6 lg:p-8 hover:shadow-xl transition-all duration-300">
              <div className="flex items-center space-x-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-green-600 flex items-center justify-center shadow-lg">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Detected Inventory</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{totalItems} items • {totalCubicFeet.toFixed(0)} cu ft • {totalWeight.toFixed(0)} lbs</p>
                </div>
              </div>
              
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/30 dark:to-blue-800/30 rounded-xl p-4 border border-blue-200 dark:border-blue-800">
                    <div className="text-xs font-semibold text-blue-700 dark:text-blue-300 uppercase mb-1">Total Items</div>
                    <div className="text-2xl font-bold text-blue-900 dark:text-blue-100">{totalItems}</div>
                  </div>
                  <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/30 dark:to-purple-800/30 rounded-xl p-4 border border-purple-200 dark:border-purple-800">
                    <div className="text-xs font-semibold text-purple-700 dark:text-purple-300 uppercase mb-1">Total Volume</div>
                    <div className="text-2xl font-bold text-purple-900 dark:text-purple-100">{totalCubicFeet.toFixed(0)} <span className="text-sm">cu ft</span></div>
                  </div>
                  <div className="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/30 dark:to-orange-800/30 rounded-xl p-4 border border-orange-200 dark:border-orange-800">
                    <div className="text-xs font-semibold text-orange-700 dark:text-orange-300 uppercase mb-1">Total Weight</div>
                    <div className="text-2xl font-bold text-orange-900 dark:text-orange-100">{totalWeight.toFixed(0)} <span className="text-sm">lbs</span></div>
                  </div>
                </div>
                
                {/* Truck Capacity Warning */}
                {needsMultipleTrucks && (
                  <div className="bg-orange-50 dark:bg-orange-900/20 border-2 border-orange-300 dark:border-orange-700 rounded-xl p-4">
                    <div className="flex items-start space-x-3">
                      <svg className="w-5 h-5 text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <div>
                        <div className="font-semibold text-orange-900 dark:text-orange-200 text-sm mb-1">
                          ⚠️ Truck Capacity Exceeded
                        </div>
                        <p className="text-xs text-orange-800 dark:text-orange-300 leading-relaxed">
                          Total volume ({totalCubicFeet.toFixed(0)} cu ft) exceeds 26ft truck capacity ({TRUCK_CAPACITY} cu ft).
                          <br />
                          <strong>Required: {estimatedTrucks} truck{estimatedTrucks > 1 ? 's' : ''} or multiple trips.</strong>
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {!needsMultipleTrucks && totalCubicFeet > 0 && (
                  <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-3">
                    <div className="flex items-center space-x-2 text-sm">
                      <svg className="w-4 h-4 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="text-green-800 dark:text-green-200 font-medium">
                        ✓ Fits in single 26ft truck ({totalCubicFeet.toFixed(0)} / {TRUCK_CAPACITY} cu ft)
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Additional Services / Upsells */}
            <div className="bg-white/70 dark:bg-gray-800/70 backdrop-blur-sm rounded-2xl shadow-lg border border-gray-200/50 dark:border-gray-700/50 p-6 lg:p-8 hover:shadow-xl transition-all duration-300">
              <div className="flex items-center space-x-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-yellow-500 to-orange-500 flex items-center justify-center shadow-lg">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Additional Services</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Enhance your move with these services</p>
                </div>
              </div>
              <div className="space-y-3">
                {upsells.map((upsell) => (
                  <label
                    key={upsell.id}
                    className={`flex items-start p-4 border-2 rounded-xl cursor-pointer transition-all duration-200 ${
                      upsell.selected
                        ? 'border-green-500 dark:border-green-600 bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/30 dark:to-emerald-900/30 shadow-md'
                        : upsell.recommended
                        ? 'border-yellow-300 dark:border-yellow-600 bg-gradient-to-r from-yellow-50 to-amber-50 dark:from-yellow-900/30 dark:to-amber-900/30 hover:border-yellow-400 dark:hover:border-yellow-500'
                        : 'border-gray-200 dark:border-gray-700 bg-white/50 dark:bg-gray-800/50 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-white dark:hover:bg-gray-800'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={upsell.selected}
                      onChange={() => handleUpsellToggle(upsell.id)}
                      className="mt-1 w-5 h-5 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-blue-500 dark:bg-gray-700"
                    />
                    <div className="ml-3 flex-1">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-2 flex-wrap">
                            <span className="font-semibold text-gray-900 dark:text-gray-100">{upsell.name}</span>
                            {upsell.selected && (
                              <span className="text-xs bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200 px-2 py-0.5 rounded-full font-medium">
                                ✓ Selected
                              </span>
                            )}
                            {upsell.recommended && !upsell.selected && (
                              <span className="text-xs bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200 px-2 py-0.5 rounded-full font-medium">
                                ⭐ Recommended
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{upsell.description}</p>
                        </div>
                        <span className="font-bold text-gray-900 dark:text-gray-100 ml-4 text-lg">
                          ${upsell.price.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Quote Summary */}
          <div className="lg:col-span-1">
            <div className="bg-white/70 dark:bg-gray-800/70 backdrop-blur-sm rounded-2xl shadow-xl border border-gray-200/50 dark:border-gray-700/50 p-6 sticky top-24">
              <div className="flex items-center space-x-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Quote Summary</h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Final pricing breakdown</p>
                </div>
              </div>
              
              <div className="space-y-4">
                {/* Truck Capacity Alert in Summary */}
                {needsMultipleTrucks && (
                  <div className="bg-orange-50 dark:bg-orange-900/20 border-2 border-orange-400 dark:border-orange-700 rounded-xl p-3">
                    <div className="flex items-start space-x-2">
                      <svg className="w-5 h-5 text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <div>
                        <div className="text-sm font-bold text-orange-900 dark:text-orange-200 mb-1">
                          Multiple Trucks Required
                        </div>
                        <p className="text-xs text-orange-800 dark:text-orange-300">
                          Volume: <strong>{totalCubicFeet.toFixed(0)} cu ft</strong> exceeds single truck capacity.
                          <br />
                          <strong>{estimatedTrucks} truck{estimatedTrucks > 1 ? 's' : ''} needed</strong>
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {gptBreakdown && (
                  <div className="bg-gradient-to-br from-purple-50 to-blue-50 dark:from-purple-900/30 dark:to-blue-900/30 border border-purple-200 dark:border-purple-800 rounded-xl p-4">
                    <div className="flex items-center space-x-2 mb-3">
                      <svg className="w-5 h-5 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      <span className="text-sm font-semibold text-purple-900 dark:text-purple-200">AI-Powered Estimate</span>
                    </div>
                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-gray-400">Loading:</span>
                        <span className="font-semibold text-gray-900 dark:text-gray-100">{gptBreakdown.loadingHours.toFixed(1)}h</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-gray-400">Travel:</span>
                        <span className="font-semibold text-gray-900 dark:text-gray-100">{gptBreakdown.travelHours.toFixed(1)}h</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-gray-400">Unloading:</span>
                        <span className="font-semibold text-gray-900 dark:text-gray-100">{gptBreakdown.unloadingHours.toFixed(1)}h</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 dark:text-gray-400">Setup:</span>
                        <span className="font-semibold text-gray-900 dark:text-gray-100">{gptBreakdown.setupHours.toFixed(1)}h</span>
                      </div>
                      <div className="flex justify-between border-t border-gray-300 dark:border-gray-600 pt-1 mt-1">
                        <span className="text-gray-600 dark:text-gray-400">Buffer:</span>
                        <span className="font-semibold text-gray-900 dark:text-gray-100">{gptBreakdown.bufferHours.toFixed(1)}h</span>
                      </div>
                    </div>
                  </div>
                )}

                {gptReasoning && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4">
                    <h3 className="text-xs font-semibold text-blue-900 dark:text-blue-200 mb-2">🤖 AI Analysis</h3>
                    <p className="text-xs text-blue-800 dark:text-blue-300 leading-relaxed">{gptReasoning}</p>
                  </div>
                )}

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Base Moving Cost:</span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">${finalEstimate.total.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Estimated Time:</span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{finalEstimate.hours.toFixed(1)} hours</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Crew Size:</span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{finalEstimate.crew} people</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Travel Time:</span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{finalEstimate.travelMins} min</span>
                  </div>
                </div>

                {totalUpsells > 0 && (
                  <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600 dark:text-gray-400">Additional Services:</span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">${totalUpsells.toFixed(2)}</span>
                    </div>
                  </div>
                )}

                <div className="pt-4 border-t-2 border-gray-300 dark:border-gray-600">
                  <div className="flex justify-between items-center">
                    <span className="text-lg font-bold text-gray-900 dark:text-gray-100">Total:</span>
                    <span className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 dark:from-blue-400 dark:to-purple-400 bg-clip-text text-transparent">
                      ${finalTotal.toFixed(2)}
                    </span>
                  </div>
                </div>

                <div className="mt-6 space-y-3">
                  <button
                    onClick={handleSendQuote}
                    disabled={!destinationAddress || !customerInfo.name || !customerInfo.email || !customerInfo.phone || !customerInfo.moveDate || isCalculatingGPT}
                    className="w-full bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 disabled:from-gray-400 disabled:to-gray-500 text-white font-bold py-3.5 px-4 rounded-xl transition-all duration-200 disabled:cursor-not-allowed flex items-center justify-center space-x-2 shadow-lg hover:shadow-xl disabled:shadow-none"
                  >
                    {isCalculatingGPT ? (
                      <>
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                        <span>Calculating...</span>
                      </>
                    ) : (
                      <>
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        <span>Send Quote via Email</span>
                      </>
                    )}
                  </button>
                  
                  <button
                    onClick={handleDownloadPDF}
                    disabled={!destinationAddress || !customerInfo.name || !customerInfo.email || !customerInfo.phone || !customerInfo.moveDate}
                    className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:from-gray-400 disabled:to-gray-500 text-white font-bold py-3.5 px-4 rounded-xl transition-all duration-200 disabled:cursor-not-allowed flex items-center justify-center space-x-2 shadow-lg hover:shadow-xl disabled:shadow-none"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span>Download PDF Quote</span>
                  </button>
                  
                  <button
                    onClick={handleContinue}
                    disabled={!destinationAddress || !customerInfo.name || !customerInfo.email || !customerInfo.phone || !customerInfo.moveDate}
                    className="w-full bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:bg-gray-100 dark:disabled:bg-gray-700 text-gray-700 dark:text-gray-300 font-semibold py-3 px-4 rounded-xl transition-colors duration-200 disabled:cursor-not-allowed border border-gray-300 dark:border-gray-600"
                  >
                    Save & Continue Later
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
