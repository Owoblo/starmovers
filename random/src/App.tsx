import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './contexts/ThemeContext';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import PricingPage from './pages/PricingPage';
import DashboardPage from './pages/DashboardPage';
import EstimatePage from './pages/EstimatePage';
import QuoteViewerPage from './pages/QuoteViewerPage';
import QuotePreviewPage from './pages/QuotePreviewPage';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <ThemeProvider>
      <Router>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route 
            path="/dashboard" 
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            } 
          />
          <Route
            path="/estimate"
            element={
              <ProtectedRoute>
                <EstimatePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/quote-preview"
            element={<QuotePreviewPage />}
          />
          <Route
            path="/quote/:quoteId"
            element={<QuoteViewerPage />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </ThemeProvider>
  );
}

export default App;
