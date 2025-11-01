import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ResendService } from '../lib/resendService';

interface QuotePreviewData {
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
}

export default function QuotePreviewPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const quoteData = location.state as QuotePreviewData;
  
  const [isSending, setIsSending] = useState(false);
  const [showEmailPreview, setShowEmailPreview] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  if (!quoteData) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">No Quote Data</h1>
          <p className="text-gray-600 mb-8">Please go back and create a quote first.</p>
          <button
            onClick={() => navigate('/dashboard')}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg"
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }

  const groupedItems = quoteData.detections.reduce((groups, item) => {
    const room = item.room || 'Other';
    if (!groups[room]) groups[room] = [];
    groups[room].push(item);
    return groups;
  }, {} as Record<string, any[]>);

  const selectedUpsells = quoteData.upsells.filter(u => u.selected);

  const handleSendEmail = async () => {
    setIsSending(true);
    try {
      const tempQuoteId = 'quote-' + Date.now();
      const quoteUrl = `${window.location.origin}/quote/${tempQuoteId}`;

      await ResendService.sendQuote({
        customerName: quoteData.customerName,
        customerEmail: quoteData.customerEmail,
        customerPhone: quoteData.customerPhone,
        moveDate: quoteData.moveDate,
        originAddress: quoteData.originAddress,
        destinationAddress: quoteData.destinationAddress,
        totalAmount: quoteData.totalAmount,
        quoteId: tempQuoteId,
        quoteUrl
      });

      setEmailSent(true);
    } catch (error: any) {
      console.error('Error sending email:', error);
      console.error('Full error object:', error);
      alert(`Failed to send email: ${error.message || 'Unknown error. Check console for details.'}`);
    } finally {
      setIsSending(false);
    }
  };

  if (emailSent) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md text-center">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Quote Sent Successfully!</h1>
          <p className="text-gray-600 mb-6">
            Your quote has been sent to <strong>{quoteData.customerEmail}</strong>
          </p>
          <div className="space-y-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg"
            >
              Back to Dashboard
            </button>
            <button
              onClick={() => setEmailSent(false)}
              className="w-full bg-gray-300 hover:bg-gray-400 text-gray-700 font-semibold py-3 px-4 rounded-lg"
            >
              Send Another Quote
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <button
                onClick={() => navigate(-1)}
                className="text-gray-600 hover:text-gray-900"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <h1 className="text-2xl font-bold text-gray-900">Quote Preview</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => setShowEmailPreview(true)}
                className="bg-gray-600 hover:bg-gray-700 text-white font-semibold py-2 px-4 rounded-lg"
              >
                Preview Email
              </button>
              <button
                onClick={handleSendEmail}
                disabled={isSending}
                className="bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold py-2 px-6 rounded-lg flex items-center space-x-2"
              >
                {isSending ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    <span>Sending...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                    <span>Send Now</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Quote Preview */}
          <div className="lg:col-span-2 space-y-6">
            {/* Customer Info */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Customer Information</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Name</p>
                  <p className="font-medium text-gray-900">{quoteData.customerName}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Email</p>
                  <p className="font-medium text-gray-900">{quoteData.customerEmail}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Phone</p>
                  <p className="font-medium text-gray-900">{quoteData.customerPhone}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Move Date</p>
                  <p className="font-medium text-gray-900">{quoteData.moveDate}</p>
                </div>
              </div>
            </div>

            {/* Move Details */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Move Details</h2>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-gray-500">From</p>
                  <p className="font-medium text-gray-900">{quoteData.originAddress}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">To</p>
                  <p className="font-medium text-gray-900">{quoteData.destinationAddress}</p>
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

          {/* Pricing Summary */}
          <div className="space-y-6">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Pricing Summary</h2>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">Base Moving Cost</span>
                  <span className="font-medium">${quoteData.estimate.total.toFixed(2)}</span>
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
                    <span className="text-lg font-semibold text-gray-900">${quoteData.totalAmount.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Email Preview Button */}
            <div className="bg-blue-50 rounded-xl p-6">
              <h3 className="font-semibold text-blue-900 mb-2">Email Preview</h3>
              <p className="text-sm text-blue-700 mb-4">
                See exactly what your customer will receive in their email.
              </p>
              <button
                onClick={() => setShowEmailPreview(true)}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg"
              >
                Preview Email Content
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Email Preview Modal */}
      {showEmailPreview && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] overflow-hidden">
            <div className="flex items-center justify-between p-6 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">Email Preview</h3>
              <button
                onClick={() => setShowEmailPreview(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
              <div className="bg-gray-50 rounded-lg p-6">
                <div className="bg-white rounded-lg shadow-sm p-6">
                  <div className="bg-blue-600 text-white p-4 rounded-t-lg">
                    <h1 className="text-xl font-bold">QUOTE2MOVE</h1>
                    <p className="text-blue-100">Professional Moving Services</p>
                  </div>
                  
                  <div className="p-6">
                    <h2 className="text-lg font-semibold text-gray-900 mb-4">Your Moving Quote is Ready!</h2>
                    
                    <p>Hi {quoteData.customerName},</p>
                    
                    <p className="mt-4">Thank you for choosing Quote2Move for your move. We've prepared a detailed quote based on your inventory and requirements.</p>
                    
                    <div className="bg-gray-50 p-4 rounded-lg my-6 border-l-4 border-blue-600">
                      <h3 className="font-semibold text-gray-900 mb-2">Move Details</h3>
                      <p><strong>From:</strong> {quoteData.originAddress}</p>
                      <p><strong>To:</strong> {quoteData.destinationAddress}</p>
                      <p><strong>Move Date:</strong> {quoteData.moveDate}</p>
                      <p><strong>Total Estimate:</strong> ${quoteData.totalAmount.toFixed(2)}</p>
                    </div>
                    
                    <div className="text-center my-6">
                      <div className="bg-green-600 text-white px-6 py-3 rounded-lg inline-block font-semibold">
                        View Your Detailed Quote
                      </div>
                    </div>
                    
                    <p className="text-sm text-gray-600">
                      This quote includes detailed inventory analysis, professional moving services, and additional services (if selected).
                    </p>
                    
                    <p className="mt-4 text-sm text-gray-600">
                      Best regards,<br />
                      <strong>Quote2Move Team</strong>
                    </p>
                  </div>
                  
                  <div className="bg-gray-100 p-4 text-center text-xs text-gray-500">
                    <p>This quote is valid for 30 days from the date of generation.</p>
                    <p>For support, contact us at support@instantquotebuilder.com</p>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex items-center justify-end space-x-3 p-6 border-t border-gray-200">
              <button
                onClick={() => setShowEmailPreview(false)}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Close
              </button>
              <button
                onClick={handleSendEmail}
                disabled={isSending}
                className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400"
              >
                {isSending ? 'Sending...' : 'Send Email Now'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
