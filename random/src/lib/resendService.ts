/**
 * Resend Email Service
 * Modern, reliable email service with beautiful templates
 * 
 * Setup:
 * 1. Sign up at https://resend.com/
 * 2. Get API key from dashboard
 * 3. Add to .env: REACT_APP_RESEND_API_KEY=your_key_here
 */

interface QuoteEmailData {
  customerName: string;
  customerEmail: string;
  customerPhone: string;
  moveDate: string;
  originAddress: string;
  destinationAddress: string;
  totalAmount: number;
  quoteId: string;
  quoteUrl: string;
}

export class ResendService {
  private static readonly API_KEY = process.env.REACT_APP_RESEND_API_KEY;
  private static readonly API_URL = 'https://api.resend.com/emails';

  static async sendQuote(data: QuoteEmailData): Promise<boolean> {
    if (!this.API_KEY) {
      throw new Error('Resend API key not configured. Please add REACT_APP_RESEND_API_KEY to your .env file');
    }

    try {
      const emailData = {
        from: 'Quote2Move <onboarding@resend.dev>',
        to: [data.customerEmail],
        subject: `Your Moving Quote - ${data.customerName}`,
        html: this.generateEmailHTML(data)
      };

      console.log('Sending email with Resend:', emailData);

      const response = await fetch(this.API_URL, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(emailData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`Resend API error: ${errorData.message || response.statusText}`);
      }

      const result = await response.json();
      console.log('Email sent successfully:', result);
      return true;
    } catch (error: any) {
      console.error('Resend email sending failed:', error);
      throw new Error(`Email sending failed: ${error.message}`);
    }
  }

  private static generateEmailHTML(data: QuoteEmailData): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Your Moving Quote</title>
        <style>
          body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }
          .container { max-width: 600px; margin: 0 auto; background: #fff; }
          .header { background: linear-gradient(135deg, #2563eb, #1e40af); color: white; padding: 30px; text-align: center; }
          .header h1 { margin: 0; font-size: 28px; font-weight: bold; }
          .header p { margin: 5px 0 0 0; font-size: 16px; opacity: 0.9; }
          .content { padding: 30px; background: #f8fafc; }
          .quote-box { background: white; padding: 25px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2563eb; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
          .cta-button { display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 20px 0; }
          .footer { background: #f3f4f6; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; }
          .details { margin: 15px 0; }
          .details strong { color: #1e40af; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>QUOTE2MOVE</h1>
            <p>Professional Moving Services</p>
          </div>
          
          <div class="content">
            <h2 style="color: #1e40af; margin-bottom: 20px;">Your Moving Quote is Ready!</h2>
            
            <p>Hi ${data.customerName},</p>
            
            <p>Thank you for choosing Quote2Move for your move. We've prepared a detailed quote based on your inventory and requirements.</p>
            
            <div class="quote-box">
              <h3 style="margin-top: 0; color: #374151;">Move Details</h3>
              <div class="details">
                <p><strong>From:</strong> ${data.originAddress}</p>
                <p><strong>To:</strong> ${data.destinationAddress}</p>
                <p><strong>Move Date:</strong> ${data.moveDate}</p>
                <p><strong>Total Estimate:</strong> $${data.totalAmount.toFixed(2)}</p>
              </div>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
              <a href="${data.quoteUrl}" class="cta-button">
                View Your Detailed Quote
              </a>
            </div>
            
            <p>This quote includes:</p>
            <ul>
              <li>Detailed inventory analysis</li>
              <li>Professional moving services</li>
              <li>Additional services (if selected)</li>
              <li>Interactive quote viewer with accept/decline options</li>
            </ul>
            
            <p>If you have any questions, you can ask them directly in the quote viewer.</p>
            
            <p style="margin-top: 30px;">
              Best regards,<br>
              <strong>Quote2Move Team</strong>
            </p>
          </div>
          
          <div class="footer">
            <p>This quote is valid for 30 days from the date of generation.</p>
            <p>For support, contact us at support@instantquotebuilder.com</p>
          </div>
        </div>
      </body>
      </html>
    `;
  }
}
