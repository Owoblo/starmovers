import { Detection, QuotePayload } from '../types';

export function toCSV(detections: Detection[]): string {
  const headers = ['Item', 'Quantity', 'Confidence', 'Notes'];
  const rows = detections.map(detection => [
    detection.label,
    detection.qty.toString(),
    `${Math.round(detection.confidence * 100)}%`,
    detection.notes || ''
  ]);

  return [headers, ...rows]
    .map(row => row.map(cell => `"${cell}"`).join(','))
    .join('\n');
}

export function generatePdf(quotePayload: QuotePayload): Promise<Blob> {
  // Placeholder implementation - would integrate with a PDF library like jsPDF
  return new Promise((resolve) => {
    const content = `
      QUOTE2MOVE
      
      Address: ${quotePayload.address}
      Date: ${quotePayload.timestamp.toLocaleDateString()}
      
      INVENTORY:
      ${quotePayload.detections.map(d => 
        `• ${d.label} (${d.qty}) - ${Math.round(d.confidence * 100)}% confidence`
      ).join('\n')}
      
      ESTIMATE:
      Crew Size: ${quotePayload.estimate.crew}
      Hourly Rate: $${quotePayload.estimate.rate}
      Estimated Hours: ${quotePayload.estimate.hours}
      Total: $${quotePayload.estimate.total}
    `;
    
    const blob = new Blob([content], { type: 'text/plain' });
    resolve(blob);
  });
}

export function downloadFile(content: string | Blob, filename: string, mimeType: string = 'text/plain') {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

