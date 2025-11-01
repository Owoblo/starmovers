import React from 'react';
import { Link } from 'react-router-dom';

export default function PricingPage() {
  const plans = [
    {
      name: 'Starter',
      price: 49,
      period: 'month',
      description: 'Perfect for small moving companies',
      features: [
        '50 property scans per month',
        'AI-powered inventory detection',
        'Room-by-room organization',
        'CSV & PDF exports',
        'Email support',
        'Basic analytics',
      ],
      cta: 'Start Free Trial',
      popular: false,
      color: 'blue',
    },
    {
      name: 'Professional',
      price: 149,
      period: 'month',
      description: 'Ideal for growing moving businesses',
      features: [
        '200 property scans per month',
        'Advanced AI detection',
        'Photo thumbnails & verification',
        'Priority support',
        'API access',
        'Custom integrations',
        'Advanced analytics',
        'Team collaboration',
      ],
      cta: 'Start Free Trial',
      popular: true,
      color: 'purple',
    },
    {
      name: 'Enterprise',
      price: 399,
      period: 'month',
      description: 'For large moving companies',
      features: [
        'Unlimited property scans',
        'Custom AI training',
        'White-label options',
        'Dedicated support',
        'Custom integrations',
        'SLA guarantee',
        'On-premise deployment',
        'Custom reporting',
      ],
      cta: 'Contact Sales',
      popular: false,
      color: 'green',
    },
  ];

  const getColorClasses = (color: string) => {
    switch (color) {
      case 'blue':
        return {
          bg: 'bg-blue-600',
          hover: 'hover:bg-blue-700',
          border: 'border-blue-200',
          text: 'text-blue-600',
          badge: 'bg-blue-100 text-blue-800',
        };
      case 'purple':
        return {
          bg: 'bg-purple-600',
          hover: 'hover:bg-purple-700',
          border: 'border-purple-200',
          text: 'text-purple-600',
          badge: 'bg-purple-100 text-purple-800',
        };
      case 'green':
        return {
          bg: 'bg-green-600',
          hover: 'hover:bg-green-700',
          border: 'border-green-200',
          text: 'text-green-600',
          badge: 'bg-green-100 text-green-800',
        };
      default:
        return {
          bg: 'bg-gray-600',
          hover: 'hover:bg-gray-700',
          border: 'border-gray-200',
          text: 'text-gray-600',
          badge: 'bg-gray-100 text-gray-800',
        };
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      {/* Navigation */}
      <nav className="bg-white/80 backdrop-blur-md border-b border-gray-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h1 className="text-xl font-semibold text-gray-900 tracking-tight">Quote2Move</h1>
            </Link>
            <div className="flex items-center space-x-6">
              <Link to="/" className="text-gray-600 hover:text-gray-900 font-medium transition-colors">
                Home
              </Link>
              <Link to="/login" className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors">
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-6">
            Simple, Transparent Pricing
          </h1>
          <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto">
            Choose the plan that fits your moving business. All plans include our core AI detection features.
          </p>
          
          {/* Toggle */}
          <div className="flex items-center justify-center mb-12">
            <span className="text-gray-600 font-medium">Monthly</span>
            <div className="mx-4 relative">
              <div className="w-12 h-6 bg-blue-600 rounded-full p-1">
                <div className="w-4 h-4 bg-white rounded-full shadow transform transition-transform"></div>
              </div>
            </div>
            <span className="text-gray-600 font-medium">Annual <span className="text-green-600 font-semibold">(Save 20%)</span></span>
          </div>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {plans.map((plan) => {
              const colors = getColorClasses(plan.color);
              return (
                <div
                  key={plan.name}
                  className={`relative bg-white rounded-2xl shadow-xl border-2 ${
                    plan.popular ? colors.border : 'border-gray-200'
                  } overflow-hidden`}
                >
                  {plan.popular && (
                    <div className="absolute top-0 left-0 right-0 bg-gradient-to-r from-purple-600 to-blue-600 text-white text-center py-2 text-sm font-semibold">
                      Most Popular
                    </div>
                  )}
                  
                  <div className="p-8">
                    <div className="text-center mb-8">
                      <h3 className="text-2xl font-bold text-gray-900 mb-2">{plan.name}</h3>
                      <p className="text-gray-600 mb-6">{plan.description}</p>
                      <div className="mb-6">
                        <span className="text-5xl font-bold text-gray-900">${plan.price}</span>
                        <span className="text-gray-600 ml-2">/{plan.period}</span>
                      </div>
                    </div>

                    <ul className="space-y-4 mb-8">
                      {plan.features.map((feature, index) => (
                        <li key={index} className="flex items-start">
                          <svg className="w-5 h-5 text-green-500 mt-0.5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          <span className="text-gray-700">{feature}</span>
                        </li>
                      ))}
                    </ul>

                    <Link
                      to="/login"
                      className={`w-full ${colors.bg} ${colors.hover} text-white font-semibold py-3 px-4 rounded-xl transition-all duration-200 shadow-lg hover:shadow-xl text-center block`}
                    >
                      {plan.cta}
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Pay Per Use Option */}
      <section className="py-20 bg-white">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <div className="bg-gradient-to-r from-gray-50 to-blue-50 rounded-2xl p-8 border border-gray-200">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">Pay Per Use</h2>
            <p className="text-xl text-gray-600 mb-6">
              Perfect for occasional users or testing the service
            </p>
            <div className="mb-8">
              <span className="text-4xl font-bold text-gray-900">$2.99</span>
              <span className="text-gray-600 ml-2">per property scan</span>
            </div>
            <ul className="text-left max-w-md mx-auto space-y-2 mb-8">
              <li className="flex items-center">
                <svg className="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-gray-700">No monthly commitment</span>
              </li>
              <li className="flex items-center">
                <svg className="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-gray-700">Full AI detection features</span>
              </li>
              <li className="flex items-center">
                <svg className="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-gray-700">CSV & PDF exports</span>
              </li>
            </ul>
            <Link
              to="/login"
              className="bg-gray-900 hover:bg-gray-800 text-white font-semibold py-3 px-8 rounded-xl transition-all duration-200 shadow-lg hover:shadow-xl"
            >
              Try Pay Per Use
            </Link>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="py-20 bg-gray-50">
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-3xl font-bold text-gray-900 text-center mb-12">
            Frequently Asked Questions
          </h2>
          <div className="space-y-8">
            <div className="bg-white rounded-xl p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 mb-3">
                How accurate is the AI detection?
              </h3>
              <p className="text-gray-600">
                Our AI achieves 95%+ accuracy in detecting movable furniture and appliances. It's specifically trained to identify items that professional movers can transport, excluding built-in fixtures.
              </p>
            </div>
            <div className="bg-white rounded-xl p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 mb-3">
                Can I change plans anytime?
              </h3>
              <p className="text-gray-600">
                Yes! You can upgrade or downgrade your plan at any time. Changes take effect immediately, and we'll prorate any billing differences.
              </p>
            </div>
            <div className="bg-white rounded-xl p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 mb-3">
                What happens if I exceed my monthly limit?
              </h3>
              <p className="text-gray-600">
                We'll notify you when you're approaching your limit. You can either upgrade your plan or purchase additional scans at $2.99 each.
              </p>
            </div>
            <div className="bg-white rounded-xl p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 mb-3">
                Do you offer custom pricing for large companies?
              </h3>
              <p className="text-gray-600">
                Yes! Contact our sales team for custom pricing, volume discounts, and enterprise features tailored to your specific needs.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-gradient-to-r from-blue-600 to-purple-600">
        <div className="max-w-4xl mx-auto text-center px-6">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
            Ready to Get Started?
          </h2>
          <p className="text-xl text-blue-100 mb-8">
            Join hundreds of moving companies already using AI to generate accurate quotes faster.
          </p>
          <Link 
            to="/login" 
            className="bg-white hover:bg-gray-100 text-blue-600 px-8 py-4 rounded-xl font-semibold text-lg transition-all duration-200 shadow-lg hover:shadow-xl"
          >
            Start Your Free Trial
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-white py-12">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            <div>
              <div className="flex items-center space-x-3 mb-4">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h3 className="text-xl font-semibold">Quote2Move</h3>
              </div>
              <p className="text-gray-400">
                AI-powered moving estimates that save time and increase accuracy.
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Product</h4>
              <ul className="space-y-2 text-gray-400">
                <li><Link to="/pricing" className="hover:text-white transition-colors">Pricing</Link></li>
                <li><Link to="/login" className="hover:text-white transition-colors">Get Started</Link></li>
                <li><a href="#" className="hover:text-white transition-colors">API Documentation</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Support</h4>
              <ul className="space-y-2 text-gray-400">
                <li><a href="#" className="hover:text-white transition-colors">Help Center</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Contact Us</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Status</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Company</h4>
              <ul className="space-y-2 text-gray-400">
                <li><a href="#" className="hover:text-white transition-colors">About</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Privacy Policy</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Terms of Service</a></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-800 mt-8 pt-8 text-center text-gray-400">
            <p>&copy; 2024 Quote2Move. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}



