import React, { useState } from 'react';
import { Photo } from '../types';

interface PhotoGalleryProps {
  photos: Photo[];
  selectedPhotos: string[];
  onPhotoSelect: (photoId: string) => void;
  onRunDetection: () => void;
  isDetecting?: boolean;
  onSelectAll?: () => void;
  onDeselectAll?: () => void;
}

export default function PhotoGallery({
  photos,
  selectedPhotos,
  onPhotoSelect,
  onRunDetection,
  isDetecting = false,
  onSelectAll,
  onDeselectAll
}: PhotoGalleryProps) {
  const [selectedPhotoForView, setSelectedPhotoForView] = useState<Photo | null>(null);
  const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);

  if (photos.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-8 transition-colors duration-200">
        <div className="text-center py-12">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full mb-4">
            <svg className="w-8 h-8 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">No photos loaded</h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">Search for an address to load property photos</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-8 transition-colors duration-200">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Property Photos</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">AI will analyze these photos to detect furniture</p>
        </div>
        {photos.length > 0 && (
          <div className="flex items-center space-x-3">
            <button
              onClick={selectedPhotos.length === photos.length ? onDeselectAll : onSelectAll}
              className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors duration-200"
            >
              {selectedPhotos.length === photos.length ? 'Deselect All' : 'Select All'}
            </button>
            <div className="text-sm text-gray-500 dark:text-gray-400">
              {selectedPhotos.length}/{photos.length} selected
            </div>
          </div>
        )}
      </div>

        {photos.length > 0 && (
          <div className="space-y-4">
            {/* Detection Progress Indicator */}
            {isDetecting && (
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4">
                <div className="flex items-center space-x-3">
                  <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-500 dark:border-blue-400 border-t-transparent"></div>
                  <div>
                    <p className="text-sm font-medium text-blue-900 dark:text-blue-200">AI Analyzing Photos</p>
                    <p className="text-xs text-blue-700 dark:text-blue-300">Detecting furniture in real-time...</p>
                  </div>
                </div>
              </div>
            )}
            
            {/* Photo Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {photos.map((photo, index) => (
                <div
                  key={photo.id}
                  className={`relative aspect-square rounded-xl overflow-hidden transition-all duration-200 ${
                    selectedPhotos.includes(photo.id)
                      ? 'ring-2 ring-blue-500 dark:ring-blue-400 ring-offset-2 dark:ring-offset-gray-800'
                      : 'hover:ring-2 hover:ring-gray-200 dark:hover:ring-gray-700'
                  }`}
                >
                  <div
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedPhotoForView(photo);
                      setCurrentPhotoIndex(index);
                    }}
                    className="absolute inset-0 cursor-zoom-in z-10"
                    title="Click to view full size"
                  />
                  <img
                    src={photo.thumbnailUrl}
                    alt={photo.filename}
                    className="w-full h-full object-cover"
                  />
                  {selectedPhotos.includes(photo.id) && (
                    <div 
                      className="absolute inset-0 bg-blue-500 bg-opacity-20 flex items-center justify-center z-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        onPhotoSelect(photo.id);
                      }}
                    >
                      <div className="w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center">
                        <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            
            {/* Full Size Image Modal */}
            {selectedPhotoForView && (
              <div 
                className="fixed inset-0 z-50 bg-black bg-opacity-90 flex items-center justify-center p-4"
                onClick={() => setSelectedPhotoForView(null)}
              >
                <div className="relative max-w-7xl max-h-[90vh] w-full h-full flex items-center justify-center">
                  <button
                    onClick={() => setSelectedPhotoForView(null)}
                    className="absolute top-4 right-4 text-white hover:text-gray-300 z-10 bg-black bg-opacity-50 rounded-full p-2 transition-colors"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                  
                  {photos.length > 1 && (
                    <>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          const newIndex = currentPhotoIndex > 0 ? currentPhotoIndex - 1 : photos.length - 1;
                          setCurrentPhotoIndex(newIndex);
                          setSelectedPhotoForView(photos[newIndex]);
                        }}
                        className="absolute left-4 top-1/2 transform -translate-y-1/2 text-white hover:text-gray-300 z-10 bg-black bg-opacity-50 rounded-full p-3 transition-colors"
                      >
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          const newIndex = currentPhotoIndex < photos.length - 1 ? currentPhotoIndex + 1 : 0;
                          setCurrentPhotoIndex(newIndex);
                          setSelectedPhotoForView(photos[newIndex]);
                        }}
                        className="absolute right-4 top-1/2 transform -translate-y-1/2 text-white hover:text-gray-300 z-10 bg-black bg-opacity-50 rounded-full p-3 transition-colors"
                      >
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </button>
                    </>
                  )}
                  
                  <img
                    src={selectedPhotoForView.url}
                    alt={selectedPhotoForView.filename}
                    className="max-w-full max-h-full object-contain"
                    onClick={(e) => e.stopPropagation()}
                  />
                  
                  <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 text-white bg-black bg-opacity-50 px-4 py-2 rounded-lg text-sm">
                    {currentPhotoIndex + 1} / {photos.length}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
    </div>
  );
}
