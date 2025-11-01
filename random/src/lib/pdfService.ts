/**
 * PDF Quote Generator
 * Creates beautiful, professional PDF quotes with maps and photos
 * 
 * Dependencies:
 * - jsPDF for PDF generation
 * - html2canvas for capturing elements
 * - Map integration for route visualization
 */

import { jsPDF } from 'jspdf';
// import html2canvas from 'html2canvas'; // Will be used for future photo integration

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
}

export class PDFService {
  static async generateQuotePDF(quoteData: QuoteData): Promise<Blob> {
    const pdf = new jsPDF('p', 'mm', 'a4');
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    
    // Colors
    const primaryColor = '#2563eb';
    const textColor = '#374151';
    const lightGray = '#f3f4f6';

    // Header
    pdf.setFillColor(primaryColor);
    pdf.rect(0, 0, pageWidth, 30, 'F');
    
    pdf.setTextColor(255, 255, 255);
    pdf.setFontSize(24);
    pdf.setFont('helvetica', 'bold');
    pdf.text('QUOTE2MOVE', 20, 20);
    
    pdf.setFontSize(12);
    pdf.setFont('helvetica', 'normal');
    pdf.text('Professional Moving Services', 20, 25);

    // Quote ID and Date
    pdf.setTextColor(255, 255, 255);
    pdf.setFontSize(10);
    pdf.text(`Quote #${quoteData.id}`, pageWidth - 60, 15);
    pdf.text(`Generated: ${new Date().toLocaleDateString()}`, pageWidth - 60, 20);

    // Customer Information Section
    pdf.setTextColor(textColor);
    pdf.setFontSize(16);
    pdf.setFont('helvetica', 'bold');
    pdf.text('Customer Information', 20, 45);
    
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`Name: ${quoteData.customerName}`, 20, 55);
    pdf.text(`Email: ${quoteData.customerEmail}`, 20, 60);
    pdf.text(`Phone: ${quoteData.customerPhone}`, 20, 65);
    pdf.text(`Move Date: ${quoteData.moveDate}`, 20, 70);

    // Move Details Section
    pdf.setFontSize(16);
    pdf.setFont('helvetica', 'bold');
    pdf.text('Move Details', 20, 85);
    
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`From: ${quoteData.originAddress}`, 20, 95);
    pdf.text(`To: ${quoteData.destinationAddress}`, 20, 100);

    // Map placeholder (you can integrate with Google Maps Static API)
    pdf.setFillColor(lightGray);
    pdf.rect(20, 110, pageWidth - 40, 40, 'F');
    pdf.setTextColor(textColor);
    pdf.setFontSize(12);
    pdf.text('Route Map', pageWidth/2 - 20, 135, { align: 'center' });

    // Inventory Section
    pdf.setFontSize(16);
    pdf.setFont('helvetica', 'bold');
    pdf.text('Inventory Summary', 20, 170);
    
    let yPosition = 180;
    pdf.setFontSize(10);
    pdf.setFont('helvetica', 'normal');
    
    // Group by room
    const groupedItems = quoteData.detections.reduce((groups, item) => {
      const room = item.room || 'Other';
      if (!groups[room]) groups[room] = [];
      groups[room].push(item);
      return groups;
    }, {});

    Object.entries(groupedItems).forEach(([room, items]) => {
      pdf.setFont('helvetica', 'bold');
      pdf.text(`${room}:`, 20, yPosition);
      yPosition += 5;
      
      (items as any[]).forEach((item: any) => {
        pdf.setFont('helvetica', 'normal');
        pdf.text(`• ${item.label} (${item.qty}x)`, 25, yPosition);
        if (item.size) {
          pdf.text(`  Size: ${item.size}`, 30, yPosition + 3);
          yPosition += 3;
        }
        yPosition += 5;
      });
      yPosition += 3;
    });

    // Photos section
    if (quoteData.photos && quoteData.photos.length > 0) {
      pdf.setFontSize(16);
      pdf.setFont('helvetica', 'bold');
      pdf.text('Property Photos', 20, yPosition + 10);
      yPosition += 20;
      
      // Add photo placeholders (you can integrate actual photo rendering)
      const photosPerRow = 3;
      const photoWidth = (pageWidth - 60) / photosPerRow;
      const photoHeight = 30;
      
      quoteData.photos.slice(0, 6).forEach((photo, index) => {
        const x = 20 + (index % photosPerRow) * (photoWidth + 10);
        const y = yPosition + Math.floor(index / photosPerRow) * (photoHeight + 10);
        
        pdf.setFillColor(lightGray);
        pdf.rect(x, y, photoWidth, photoHeight, 'F');
        pdf.setTextColor(textColor);
        pdf.setFontSize(8);
        pdf.text('Photo', x + photoWidth/2 - 10, y + photoHeight/2);
      });
    }

    // Pricing Section
    const pricingY = pageHeight - 80;
    pdf.setFillColor(lightGray);
    pdf.rect(20, pricingY, pageWidth - 40, 60, 'F');
    
    pdf.setTextColor(textColor);
    pdf.setFontSize(16);
    pdf.setFont('helvetica', 'bold');
    pdf.text('Pricing Breakdown', 30, pricingY + 15);
    
    pdf.setFontSize(12);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`Base Moving Cost: $${quoteData.estimate.total.toFixed(2)}`, 30, pricingY + 25);
    
    const upsellTotal = quoteData.upsells
      .filter(u => u.selected)
      .reduce((sum, u) => sum + u.price, 0);
    
    if (upsellTotal > 0) {
      pdf.text(`Additional Services: $${upsellTotal.toFixed(2)}`, 30, pricingY + 35);
    }
    
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(18);
    pdf.text(`Total: $${quoteData.totalAmount.toFixed(2)}`, 30, pricingY + 50);

    // Footer
    pdf.setTextColor(100, 100, 100);
    pdf.setFontSize(8);
    pdf.text('This quote is valid for 30 days from the date of generation.', 20, pageHeight - 10);
    pdf.text('For questions, contact us at support@instantquotebuilder.com', 20, pageHeight - 5);

    return pdf.output('blob');
  }

  static async downloadQuote(quoteData: QuoteData): Promise<void> {
    const blob = await this.generateQuotePDF(quoteData);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `quote-${quoteData.id}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}
