import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { supabase } from '../lib/supabase';

interface QuoteData {
  id: string;
  customerName: string;
  customerEmail: string;
  customerPhone: string;
  moveDate: string;
  originAddress: string;
  destinationAddress: string;
  detections: any[];
  estimate: any;
  upsells: any[];
  totalAmount: number;
  photos: any[];
  status: 'pending' | 'accepted' | 'declined';
  createdAt: string;
}

export default function QuoteViewerPage() {
  const { quoteId } = useParams<{ quoteId: string }>();
  const navigate = useNavigate();
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [showQuestions, setShowQuestions] = useState(false);
  const [question, setQuestion] = useState('');
  const [, setQuestions] = useState<string[]>([]);

  useEffect(() => {
    fetchQuote();
  }, [quoteId]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchQuote = async () => {
    try {
      const { data, error } = await supabase
        .from('quotes')
        .select('*')
        .eq('id', quoteId)
        .single();

      if (error) throw error;
      setQuote(data);
    } catch (error) {
      console.error('Error fetching quote:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleQuoteAction = async (action: 'accept' | 'decline') => {
    if (!quote) return;
    
    setActionLoading(true);
    try {
      const { error } = await supabase
        .from('quotes')
        .update({ status: action === 'accept' ? 'accepted' : 'declined' })
        .eq('id', quoteId);

      if (error) throw error;
      
      setQuote(prev => prev ? { ...prev, status: action === 'accept' ? 'accepted' : 'declined' } : null);
      
      // Show success message
      alert(`Quote ${action === 'accept' ? 'accepted' : 'declined'} successfully!`);
    } catch (error) {
      console.error(`Error ${action}ing quote:`, error);
      alert(`Failed to ${action} quote. Please try again.`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitQuestion = () => {
    if (!question.trim()) return;
    
    setQuestions(prev => [...prev, question]);
    setQuestion('');
    setShowQuestions(false);
    
    // Here you would typically send the question to your backend
    // For now, we'll just show a success message
    alert('Question submitted! We\'ll get back to you soon.');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!quote) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Quote Not Found</h1>
          <p className="text-gray-600 mb-8">The quote you're looking for doesn't exist or has been removed.</p>
          <button
            onClick={() => navigate('/')}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg"
          >
            Go Home
          </button>
        </div>
      </div>
    );
  }

  const groupedItems = quote.detections.reduce((groups, item) => {
    const room = item.room || 'Other';
    if (!groups[room]) groups[room] = [];
    groups[room].push(item);
    return groups;
  }, {} as Record<string, any[]>);

  const selectedUpsells = quote.upsells.filter(u => u.selected);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Your Moving Quote</h1>
              <p className="text-gray-600">Quote #{quote.id}</p>
            </div>
            <div className="text-right">
              <p className="text-sm text-gray-500">Generated on</p>
              <p className="text-sm font-medium text-gray-900">
                {new Date(quote.createdAt).toLocaleDateString()}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Customer Info */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Customer Information</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Name</p>
                  <p className="font-medium text-gray-900">{quote.customerName}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Email</p>
                  <p className="font-medium text-gray-900">{quote.customerEmail}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Phone</p>
                  <p className="font-medium text-gray-900">{quote.customerPhone}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Move Date</p>
                  <p className="font-medium text-gray-900">{quote.moveDate}</p>
                </div>
              </div>
            </div>

            {/* Move Details */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Move Details</h2>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-gray-500">From</p>
                  <p className="font-medium text-gray-900">{quote.originAddress}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">To</p>
                  <p className="font-medium text-gray-900">{quote.destinationAddress}</p>
                </div>
              </div>
            </div>

            {/* Inventory */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Inventory Summary</h2>
              <div className="space-y-4">
                {Object.entries(groupedItems).map(([room, items]) => (
                  <div key={room}>
                    <h3 className="font-medium text-gray-900 mb-2">{room}</h3>
                    <div className="space-y-2">
                      {(items as any[]).map((item: any, index: number) => (
                        <div key={index} className="flex justify-between items-center py-2 border-b border-gray-100 last:border-b-0">
                          <div>
                            <p className="font-medium text-gray-900">{item.label}</p>
                            {item.size && (
                              <p className="text-sm text-gray-500">Size: {item.size}</p>
                            )}
                          </div>
                          <p className="text-sm text-gray-600">Qty: {item.qty}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Additional Services */}
            {selectedUpsells.length > 0 && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Additional Services</h2>
                <div className="space-y-3">
                  {selectedUpsells.map((upsell) => (
                    <div key={upsell.id} className="flex justify-between items-center py-2 border-b border-gray-100 last:border-b-0">
                      <div>
                        <p className="font-medium text-gray-900">{upsell.name}</p>
                        <p className="text-sm text-gray-500">{upsell.description}</p>
                      </div>
                      <p className="font-medium text-gray-900">${upsell.price.toFixed(2)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Pricing Summary */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Pricing Summary</h2>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">Base Moving Cost</span>
                  <span className="font-medium">${quote.estimate.total.toFixed(2)}</span>
                </div>
                {selectedUpsells.length > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Additional Services</span>
                    <span className="font-medium">
                      ${selectedUpsells.reduce((sum, u) => sum + u.price, 0).toFixed(2)}
                    </span>
                  </div>
                )}
                <div className="border-t border-gray-200 pt-3">
                  <div className="flex justify-between">
                    <span className="text-lg font-semibold text-gray-900">Total</span>
                    <span className="text-lg font-semibold text-gray-900">${quote.totalAmount.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Quote Actions</h2>
              
              {quote.status === 'pending' && (
                <div className="space-y-3">
                  <button
                    onClick={() => handleQuoteAction('accept')}
                    disabled={actionLoading}
                    className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg transition-colors"
                  >
                    {actionLoading ? 'Processing...' : 'Accept Quote'}
                  </button>
                  
                  <button
                    onClick={() => handleQuoteAction('decline')}
                    disabled={actionLoading}
                    className="w-full bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg transition-colors"
                  >
                    {actionLoading ? 'Processing...' : 'Decline Quote'}
                  </button>
                  
                  <button
                    onClick={() => setShowQuestions(true)}
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg transition-colors"
                  >
                    Ask Questions
                  </button>
                </div>
              )}

              {quote.status === 'accepted' && (
                <div className="text-center">
                  <div className="bg-green-100 text-green-800 px-4 py-3 rounded-lg mb-4">
                    <p className="font-semibold">Quote Accepted!</p>
                    <p className="text-sm">We'll contact you soon to schedule your move.</p>
                  </div>
                </div>
              )}

              {quote.status === 'declined' && (
                <div className="text-center">
                  <div className="bg-red-100 text-red-800 px-4 py-3 rounded-lg mb-4">
                    <p className="font-semibold">Quote Declined</p>
                    <p className="text-sm">Thank you for considering our services.</p>
                  </div>
                </div>
              )}

              <button
                onClick={() => window.print()}
                className="w-full bg-gray-600 hover:bg-gray-700 text-white font-semibold py-3 px-4 rounded-lg transition-colors mt-3"
              >
                Print Quote
              </button>
            </div>

            {/* Questions Modal */}
            {showQuestions && (
              <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                <div className="bg-white rounded-xl p-6 w-full max-w-md">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">Ask a Question</h3>
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="What would you like to know about this quote?"
                    rows={4}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <div className="flex space-x-3 mt-4">
                    <button
                      onClick={handleSubmitQuestion}
                      className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg"
                    >
                      Submit
                    </button>
                    <button
                      onClick={() => setShowQuestions(false)}
                      className="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-700 font-semibold py-2 px-4 rounded-lg"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
