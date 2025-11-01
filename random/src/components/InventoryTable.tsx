import React from 'react';
import { Detection, MappingTable } from '../types';

interface InventoryTableProps {
  detections: Detection[];
  mapping: MappingTable;
  onQuantityChange: (detectionIndex: number, quantity: number) => void;
  onNotesChange: (detectionIndex: number, notes: string) => void;
  onRemove: (detectionIndex: number) => void;
  isDetecting?: boolean;
}

export default function InventoryTable({
  detections,
  mapping,
  onQuantityChange,
  onNotesChange,
  onRemove,
  isDetecting = false
}: InventoryTableProps) {
  // Group detections by room and collect photo URLs, preserving original index
  const groupedDetections = detections.reduce((groups, detection, index) => {
    const room = detection.room || 'Unknown Room';
    if (!groups[room]) {
      groups[room] = [];
    }
    // Store detection with its original index
    groups[room].push({ ...detection, _originalIndex: index } as Detection & { _originalIndex: number });
    return groups;
  }, {} as Record<string, (Detection & { _originalIndex: number })[]>);

  const roomNames = Object.keys(groupedDetections).sort();

  // Collect unique photo URLs for each room
  const roomPhotos = roomNames.reduce((photos, room) => {
    const photoUrls = groupedDetections[room]
      .map(detection => detection.sourcePhotoId)
      .filter(Boolean) as string[];
    
    const uniquePhotos = Array.from(new Set(photoUrls));
    photos[room] = uniquePhotos;
    return photos;
  }, {} as Record<string, string[]>);

  // Calculate totals
  const totalItems = detections.reduce((sum, detection) => sum + detection.qty, 0);
  const totalCubicFeet = detections.reduce((sum, detection) => {
    // Priority: detected cubicFeet > mapping table > estimator fallback
    const cf = detection.cubicFeet || mapping[detection.label]?.cf || 0;
    return sum + (cf * detection.qty);
  }, 0);

  if (detections.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-8 transition-colors duration-200">
        <div className="text-center py-8">
          {isDetecting ? (
            <>
              <div className="mx-auto w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mb-3">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 dark:border-blue-400"></div>
              </div>
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">AI Analyzing Photos...</h3>
              <p className="text-sm text-blue-600 dark:text-blue-400 mb-4">Detecting furniture in real-time</p>
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  🎯 <strong>Real-time Detection:</strong> Watch as furniture appears in the inventory as each photo is analyzed!
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="mx-auto w-12 h-12 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-3">
                <svg className="w-6 h-6 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              </div>
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">No detections yet</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">AI will detect furniture automatically</p>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 transition-colors duration-200">
      <div className="p-8 border-b border-gray-100 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Detected Inventory</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {isDetecting ? 'AI is analyzing photos and detecting furniture...' : 'Furniture and items found by AI analysis'}
            </p>
          </div>
          {isDetecting && (
            <div className="flex items-center text-sm text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 px-3 py-2 rounded-lg">
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-600 dark:border-blue-400 border-t-transparent mr-2"></div>
              <span>Live Detection</span>
            </div>
          )}
        </div>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-700/50">
            <tr>
              <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Item
              </th>
              <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Qty
              </th>
              <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Notes
              </th>
              <th className="px-6 py-4 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider w-16">
                {/* Actions column - subtle */}
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-100 dark:divide-gray-700">
            {roomNames.map((roomName) => (
              <React.Fragment key={roomName}>
                {/* Room Header */}
                <tr className="bg-blue-50 dark:bg-blue-900/20">
                  <td colSpan={4} className="px-6 py-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <span className="text-sm font-semibold text-blue-800 dark:text-blue-200">
                          🏠 {roomName}
                        </span>
                        {roomPhotos[roomName] && roomPhotos[roomName].length > 0 && (
                          <div className="flex items-center space-x-1">
                            <span className="text-xs text-blue-600 dark:text-blue-400">from:</span>
                            <div className="flex space-x-1">
                              {roomPhotos[roomName].slice(0, 3).map((photoUrl, idx) => (
                                <div
                                  key={idx}
                                  className="w-6 h-6 rounded border border-blue-200 dark:border-blue-700 overflow-hidden bg-gray-100 dark:bg-gray-700"
                                >
                                  <img
                                    src={photoUrl}
                                    alt={`Room detection source ${idx + 1}`}
                                    className="w-full h-full object-cover"
                                    onError={(e) => {
                                      e.currentTarget.style.display = 'none';
                                    }}
                                  />
                                </div>
                              ))}
                              {roomPhotos[roomName].length > 3 && (
                                <div className="w-6 h-6 rounded border border-blue-200 dark:border-blue-700 bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center">
                                  <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                                    +{roomPhotos[roomName].length - 3}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                      <div className="text-xs text-blue-600 dark:text-blue-400">
                        {groupedDetections[roomName].length} item{groupedDetections[roomName].length !== 1 ? 's' : ''}
                      </div>
                    </div>
                  </td>
                </tr>
                {/* Room Items */}
                {groupedDetections[roomName].map((detection, roomItemIndex) => {
                  // Use the preserved original index
                  const detectionIndex = detection._originalIndex;
                  const mappingItem = mapping[detection.label];
                  
                  return (
                    <tr key={`${roomName}-${roomItemIndex}`} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 group">
                      <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                        <div className="font-medium">{detection.label}</div>
                        {detection.size && (
                          <div className="text-xs text-blue-600 dark:text-blue-400 font-medium mt-1">
                            📏 Size: {detection.size}
                          </div>
                        )}
                          {(detection.cubicFeet || mappingItem || detection.weight) && (
                            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                              {(detection.cubicFeet || mappingItem?.cf || 0).toFixed(1)} cf
                              {detection.weight && ` • ${(detection.weight * detection.qty).toFixed(0)} lbs`}
                              {!detection.weight && detection.cubicFeet && ` • ~${Math.round(detection.cubicFeet * 7 * detection.qty)} lbs`}
                              {mappingItem && ` • ${mappingItem.minutes} min`}
                              {mappingItem?.wrap && ' • Wrap needed'}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                        <div className="flex items-center space-x-2">
                          <span className="font-medium text-gray-900 dark:text-gray-100">{detection.qty}</span>
                          <button
                            onClick={() => {
                              const newQty = prompt(`Edit quantity for ${detection.label}:`, detection.qty.toString());
                              if (newQty !== null) {
                                const parsed = parseInt(newQty, 10);
                                if (!isNaN(parsed) && parsed >= 0) {
                                  onQuantityChange(detectionIndex, parsed);
                                }
                              }
                            }}
                            className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Edit quantity"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                          </button>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                          <textarea
                            value={detection.notes || ''}
                          onChange={(e) => onNotesChange(detectionIndex, e.target.value)}
                            placeholder="Add notes about this item..."
                            rows={2}
                          className="w-full border-0 bg-transparent px-0 py-2 text-sm focus:outline-none resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                        />
                      </td>
                      <td className="px-6 py-4 text-sm text-center">
                        <button
                          onClick={() => onRemove(detectionIndex)}
                          className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg p-2 transition-colors opacity-0 group-hover:opacity-100"
                          title="Remove this item"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
      
      {/* Totals */}
      <div className="p-8 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-100 dark:border-gray-700 flex justify-between items-center">
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Total Items: <span className="font-semibold text-gray-900 dark:text-gray-100">{totalItems}</span>
        </div>
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Total Cubic Feet: <span className="font-semibold text-gray-900 dark:text-gray-100">{totalCubicFeet.toFixed(2)} cf</span>
        </div>
      </div>
    </div>
  );
}
