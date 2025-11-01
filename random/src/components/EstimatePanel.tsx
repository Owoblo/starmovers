import React from 'react';
import { Estimate } from '../types';

interface EstimatePanelProps {
  estimate: Estimate;
  onEstimateChange: (field: keyof Estimate, value: any) => void;
  onSendSMS: () => void;
  onSendEmail: () => void;
  onDownloadPDF: () => void;
  onCopyCSV: () => void;
}

export default function EstimatePanel({
  estimate,
  onEstimateChange,
  onSendSMS,
  onSendEmail,
  onDownloadPDF,
  onCopyCSV
}: EstimatePanelProps) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Moving Estimate</h2>
        <p className="text-sm text-gray-600">Configure crew settings and view pricing breakdown</p>
      </div>
      
      {/* Input Fields */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Crew Size */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Crew Size
          </label>
          <select
            value={estimate.crew}
            onChange={(e) => onEstimateChange('crew', parseInt(e.target.value))}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
          >
            {[2, 3, 4, 5, 6].map(size => (
              <option key={size} value={size}>{size} people</option>
            ))}
          </select>
        </div>

        {/* Hourly Rate */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Hourly Rate ($)
          </label>
          <input
            type="number"
            value={estimate.rate}
            onChange={(e) => onEstimateChange('rate', parseFloat(e.target.value) || 0)}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
            min="0"
            step="0.01"
          />
        </div>

        {/* Travel Time */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Travel Time (minutes)
          </label>
          <input
            type="number"
            value={estimate.travelMins}
            onChange={(e) => onEstimateChange('travelMins', parseInt(e.target.value) || 0)}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
            min="0"
          />
        </div>

        {/* Toggle Options */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Stairs</label>
            <button
              onClick={() => onEstimateChange('stairs', !estimate.stairs)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                estimate.stairs ? 'bg-blue-600' : 'bg-gray-200'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  estimate.stairs ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Elevator</label>
            <button
              onClick={() => onEstimateChange('elevator', !estimate.elevator)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                estimate.elevator ? 'bg-blue-600' : 'bg-gray-200'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  estimate.elevator ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Wrapping</label>
            <button
              onClick={() => onEstimateChange('wrapping', !estimate.wrapping)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                estimate.wrapping ? 'bg-blue-600' : 'bg-gray-200'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  estimate.wrapping ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Safety Factor */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Safety Factor ({estimate.safetyPct}%)
          </label>
          <input
            type="range"
            min="0"
            max="20"
            value={estimate.safetyPct}
            onChange={(e) => onEstimateChange('safetyPct', parseInt(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>0%</span>
            <span>20%</span>
          </div>
        </div>
      </div>

      {/* Read-only Results */}
      <div className="bg-gray-50 rounded-xl p-6 mb-8">
        <h3 className="text-sm font-medium text-gray-700 mb-4">Estimate Results</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-2xl font-semibold text-gray-900">{estimate.hours}</div>
            <div className="text-sm text-gray-600">Est. Hours</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-semibold text-gray-900">${estimate.total.toLocaleString()}</div>
            <div className="text-sm text-gray-600">Est. Total</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-semibold text-gray-900">{estimate.crew}</div>
            <div className="text-sm text-gray-600">Recommended Crew</div>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <button
          onClick={onSendSMS}
          className="bg-green-600 hover:bg-green-700 text-white font-medium py-3 px-4 rounded-xl transition-colors duration-200 flex items-center justify-center space-x-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <span>Send SMS Quote</span>
        </button>
        <button
          onClick={onSendEmail}
          className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-xl transition-colors duration-200 flex items-center justify-center space-x-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <span>Send Email</span>
        </button>
        <button
          onClick={onDownloadPDF}
          className="bg-gray-600 hover:bg-gray-700 text-white font-medium py-3 px-4 rounded-xl transition-colors duration-200 flex items-center justify-center space-x-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span>Download PDF</span>
        </button>
        <button
          onClick={onCopyCSV}
          className="bg-purple-600 hover:bg-purple-700 text-white font-medium py-3 px-4 rounded-xl transition-colors duration-200 flex items-center justify-center space-x-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span>Copy CSV</span>
        </button>
      </div>
    </div>
  );
}
