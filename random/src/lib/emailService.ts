/**
 * Email Service for sending quotes
 * Uses EmailJS for client-side email sending
 * 
 * Setup:
 * 1. Sign up at https://www.emailjs.com/
 * 2. Create email template
 * 3. Add service ID, template ID, and public key to .env
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

export class EmailService {
  private static readonly SERVICE_ID = process.env.REACT_APP_EMAILJS_SERVICE_ID;
  private static readonly TEMPLATE_ID = process.env.REACT_APP_EMAILJS_TEMPLATE_ID;
  private static readonly PUBLIC_KEY = process.env.REACT_APP_EMAILJS_PUBLIC_KEY;

  static async sendQuote(data: QuoteEmailData): Promise<boolean> {
    if (!this.SERVICE_ID || !this.TEMPLATE_ID || !this.PUBLIC_KEY) {
      throw new Error('EmailJS configuration missing. Please add EMAILJS_* variables to .env');
    }

    try {
      // Load EmailJS dynamically
      const emailjs = await import('@emailjs/browser');
      
      const templateParams = {
        to_email: data.customerEmail,
        customer_name: data.customerName,
        customer_phone: data.customerPhone,
        move_date: data.moveDate,
        origin_address: data.originAddress,
        destination_address: data.destinationAddress,
        total_amount: data.totalAmount.toFixed(2),
        quote_id: data.quoteId,
        quote_url: data.quoteUrl,
        company_name: 'Quote2Move',
        // Add some common alternative variable names
        from_name: 'Quote2Move',
        reply_to: 'noreply@instantquotebuilder.com',
        subject: `Moving Quote - ${data.customerName}`
      };

      console.log('Sending email with params:', {
        serviceId: this.SERVICE_ID,
        templateId: this.TEMPLATE_ID,
        publicKey: this.PUBLIC_KEY ? 'Present' : 'Missing',
        templateParams
      });

      const result = await emailjs.send(
        this.SERVICE_ID,
        this.TEMPLATE_ID,
        templateParams,
        this.PUBLIC_KEY
      );

      console.log('Email sent successfully:', result);
      return true;
    } catch (error: any) {
      console.error('Email sending failed:', error);
      console.error('Error details:', {
        message: error.message,
        status: error.status,
        text: error.text
      });
      throw new Error(`EmailJS Error: ${error.message || error.text || 'Unknown error'}`);
    }
  }

  // Fallback: Generate mailto link
  static generateMailtoLink(data: QuoteEmailData): string {
    const subject = `Moving Quote - ${data.customerName}`;
    const body = `Hi ${data.customerName},

Thank you for choosing Quote2Move for your move!

Move Details:
- From: ${data.originAddress}
- To: ${data.destinationAddress}
- Move Date: ${data.moveDate}
- Total Estimate: $${data.totalAmount.toFixed(2)}

View your detailed quote: ${data.quoteUrl}

Best regards,
Quote2Move Team`;

    return `mailto:${data.customerEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
}
