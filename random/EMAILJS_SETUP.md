# 📧 EmailJS Setup Guide

To enable email quote sending, you need to set up EmailJS (free email service).

## 📋 Setup Steps

### 1. Create EmailJS Account

1. Go to [EmailJS.com](https://www.emailjs.com/)
2. Sign up for a free account
3. Verify your email address

### 2. Create Email Service

1. In EmailJS dashboard, go to **Email Services**
2. Click **Add New Service**
3. Choose your email provider (Gmail, Outlook, etc.)
4. Follow the setup instructions
5. Copy your **Service ID**

### 3. Create Email Template

1. Go to **Email Templates**
2. Click **Create New Template**
3. Use this template:

**Subject:** `Moving Quote - {{customer_name}}`

**Body:**
```html
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="background: #2563eb; color: white; padding: 20px; text-align: center;">
    <h1 style="margin: 0; font-size: 24px;">INSTANT QUOTE BUILDER</h1>
    <p style="margin: 5px 0 0 0;">Professional Moving Services</p>
  </div>
  
  <div style="padding: 30px 20px; background: #f8fafc;">
    <h2 style="color: #1e40af; margin-bottom: 20px;">Your Moving Quote is Ready!</h2>
    
    <p>Hi {{customer_name}},</p>
    
    <p>Thank you for choosing Instant Quote Builder for your move. We've prepared a detailed quote based on your inventory and requirements.</p>
    
    <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2563eb;">
      <h3 style="margin-top: 0; color: #374151;">Move Details</h3>
      <p><strong>From:</strong> {{origin_address}}</p>
      <p><strong>To:</strong> {{destination_address}}</p>
      <p><strong>Move Date:</strong> {{move_date}}</p>
      <p><strong>Total Estimate:</strong> ${{total_amount}}</p>
    </div>
    
    <div style="text-align: center; margin: 30px 0;">
      <a href="{{quote_url}}" 
         style="background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
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
    
    <p>Best regards,<br>
    <strong>Instant Quote Builder Team</strong></p>
  </div>
  
  <div style="background: #f3f4f6; padding: 15px; text-align: center; font-size: 12px; color: #6b7280;">
    <p>This quote is valid for 30 days from the date of generation.</p>
    <p>For support, contact us at support@instantquotebuilder.com</p>
  </div>
</div>
```

4. Save the template and copy your **Template ID**

### 4. Get Public Key

1. Go to **Account** > **General**
2. Copy your **Public Key**

### 5. Add to Your Project

Add these variables to your `.env` file:

```bash
REACT_APP_EMAILJS_SERVICE_ID=your_service_id_here
REACT_APP_EMAILJS_TEMPLATE_ID=your_template_id_here
REACT_APP_EMAILJS_PUBLIC_KEY=your_public_key_here
```

### 6. Restart Development Server

```bash
npm start
```

## ✅ What Happens Next

Once set up, when users click "Send Quote via Email":

1. ✅ Quote is saved to database
2. ✅ Email is sent with professional template
3. ✅ Customer receives email with "View Quote" button
4. ✅ Button links to beautiful quote viewer page
5. ✅ Customer can accept/decline/ask questions

## 🎨 Quote Viewer Features

The quote viewer includes:
- ✅ Professional design with company branding
- ✅ Complete inventory breakdown by room
- ✅ Pricing summary with base cost + upsells
- ✅ Accept/Decline quote buttons
- ✅ Ask questions functionality
- ✅ Print quote option
- ✅ Mobile-responsive design

## 💰 Cost

- **EmailJS Free Tier**: 200 emails/month
- **After free tier**: $15/month for 1,000 emails
- Very affordable for a moving company

## 🔧 Troubleshooting

If emails aren't sending:
1. Check your `.env` variables are correct
2. Verify EmailJS service is active
3. Check browser console for errors
4. Test with a simple email first

The system will fall back to opening your email client if EmailJS fails.



