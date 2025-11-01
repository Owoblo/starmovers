# Instant Quote Builder

A clean, single-page React + Tailwind application for AI-powered moving estimates.

## Features

- **Search Panel**: Address input with autocomplete-ready placeholder and recent searches
- **Photo Gallery**: Selectable photo thumbnails with AI detection capabilities
- **Inventory Table**: Editable quantities with confidence scores and totals
- **Estimate Panel**: Comprehensive estimate calculator with multiple export options
- **Responsive Design**: 3-column layout that stacks on mobile
- **Toast Notifications**: Success/error feedback for user actions

## Getting Started

1. Install dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm start
```

3. Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

## Project Structure

```
src/
├── components/
│   ├── SearchPanel.tsx      # Address input and recent searches
│   ├── PhotoGallery.tsx     # Photo selection and detection
│   ├── InventoryTable.tsx   # Detected items with editable quantities
│   └── EstimatePanel.tsx    # Estimate calculator and export options
├── lib/
│   ├── estimate.ts          # Pure calculation functions
│   └── export.ts            # CSV and PDF export utilities
├── types/
│   └── index.ts             # TypeScript interfaces
├── App.tsx                  # Main application component
└── index.tsx               # Application entry point
```

## Key Features

### State Management
The app uses React hooks for state management with a clean, centralized state structure:

```typescript
interface AppState {
  address: string;
  photos: Photo[];
  detections: Detection[];
  mapping: MappingTable;
  estimate: Estimate;
}
```

### Pure Functions
- `calculateEstimate()`: Calculates hours, crew suggestion, and total cost
- `toCSV()`: Converts detections to CSV format
- `generatePdf()`: Creates PDF quotes (placeholder implementation)

### Responsive Design
- Desktop: 3-column grid layout
- Mobile: Stacked single-column layout
- Large tap targets for mobile usability

### Mock Data
The app includes mock data for demonstration:
- Sample photos with placeholders
- Pre-defined detections (Sofa, Dining Table, Refrigerator)
- Mapping table with cubic feet and time estimates

## Usage

1. **Enter Address**: Type an address in the search panel
2. **Fetch Photos**: Click "Fetch Photos" to load sample images
3. **Select Photos**: Choose photos for AI detection
4. **Run Detection**: Click "Run Detection" to analyze selected photos
5. **Edit Quantities**: Adjust quantities in the inventory table
6. **Configure Estimate**: Set crew size, rates, and other parameters
7. **Export Results**: Send quotes via SMS/email or download PDF/CSV

## Technologies Used

- **React 18** with TypeScript
- **Tailwind CSS** for styling
- **React Hooks** for state management
- **Pure functions** for calculations and exports

## Future Enhancements

- Real photo upload and storage
- Live AI detection API integration
- Address autocomplete with Google Maps API
- Real-time map integration
- Advanced PDF generation with charts
- User authentication and quote history

