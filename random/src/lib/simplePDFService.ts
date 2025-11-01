/**
 * Simple PDF Service
 * Generate PDF quotes using a simpler approach
 */

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
  photos?: any[];
}

export class SimplePDFService {
  static async downloadQuote(quoteData: QuoteData): Promise<void> {
    try {
      // For now, create a simple text-based PDF
      const content = this.generateQuoteContent(quoteData);
      
      // Create a simple HTML content
      const htmlContent = `
        <!DOCTYPE html>
        <html>
        <head>
          <title>Quote ${quoteData.id}</title>
          <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .header { background: #2563eb; color: white; padding: 20px; text-align: center; margin-bottom: 30px; }
            .section { margin-bottom: 25px; padding: 15px; background: #f8fafc; border-radius: 8px; }
            .section h3 { color: #1e40af; margin-top: 0; }
            .item { margin: 8px 0; padding: 5px 0; border-bottom: 1px solid #e5e7eb; }
            .total { font-size: 18px; font-weight: bold; color: #1e40af; text-align: right; margin-top: 20px; }
            .footer { text-align: center; margin-top: 40px; color: #6b7280; font-size: 12px; }
          </style>
        </head>
        <body>
          <div class="header">
            <h1>QUOTE2MOVE</h1>
            <p>Professional Moving Services</p>
          </div>
          
          <div class="section">
            <h3>Customer Information</h3>
            <p><strong>Name:</strong> ${quoteData.customerName}</p>
            <p><strong>Email:</strong> ${quoteData.customerEmail}</p>
            <p><strong>Phone:</strong> ${quoteData.customerPhone}</p>
            <p><strong>Move Date:</strong> ${quoteData.moveDate}</p>
          </div>
          
          <div class="section">
            <h3>Move Details</h3>
            <p><strong>From:</strong> ${quoteData.originAddress}</p>
            <p><strong>To:</strong> ${quoteData.destinationAddress}</p>
          </div>
          
          <div class="section">
            <h3>Inventory</h3>
            ${this.generateInventoryHTML(quoteData.detections)}
          </div>
          
          ${quoteData.upsells.filter(u => u.selected).length > 0 ? `
          <div class="section">
            <h3>Additional Services</h3>
            ${quoteData.upsells.filter(u => u.selected).map(upsell => 
              `<div class="item">${upsell.name}: $${upsell.price.toFixed(2)}</div>`
            ).join('')}
          </div>
          ` : ''}
          
          <div class="total">
            Total: $${quoteData.totalAmount.toFixed(2)}
          </div>
          
          <div class="footer">
            <p>This quote is valid for 30 days from the date of generation.</p>
            <p>For support, contact us at support@instantquotebuilder.com</p>
          </div>
        </body>
        </html>
      `;
      
      // Create and download the HTML file (can be printed to PDF)
      const blob = new Blob([htmlContent], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `quote-${quoteData.id}.html`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error('Error generating PDF:', error);
      throw new Error('Failed to generate PDF');
    }
  }

  private static generateQuoteContent(quoteData: QuoteData): string {
    // This method is kept for future use but not currently used
    // It generates a text-based quote content
    return `QUOTE ${quoteData.id} - ${quoteData.customerName}`;
  }

  private static generateInventoryHTML(detections: any[]): string {
    const grouped = detections.reduce((groups, item) => {
      const room = item.room || 'Other';
      if (!groups[room]) groups[room] = [];
      groups[room].push(item);
      return groups;
    }, {} as Record<string, any[]>);

    let html = '';
    Object.entries(grouped).forEach(([room, items]) => {
      html += `<h4>${room}</h4>`;
      (items as any[]).forEach((item: any) => {
        html += `<div class="item">${item.label} (${item.qty}x)`;
        if (item.size) html += ` - ${item.size}`;
        html += '</div>';
      });
    });

    return html;
  }
}
