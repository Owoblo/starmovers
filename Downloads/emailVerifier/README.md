# VerifyMind - Email Generation & Validation Platform

A powerful local email verification and generation tool built with Node.js. Transform names and domains into verified email addresses, or verify existing email lists instantly.

## Features

### 🎯 Generate & Verify Mode
- 📧 **Smart Email Generation**: Input names + domains, get 8 email pattern variations automatically
- 🔍 **Instant Verification**: All generated variations are verified in one go
- 📊 **Split Results View**: Clean separation of verified vs undeliverable emails
- 📋 **One-Click Copy**: Copy individual emails or all verified emails at once
- 💾 **CSV Export**: Download verified emails as CSV for your outreach tools

### ⚡ Quick Verify Mode
- ✅ Syntax validation (email format)
- ✅ DNS/MX record verification
- ✅ SMTP handshake validation
- 🎨 Clean, modern web interface
- 🚀 Built with Node.js and Express

## Email Pattern Generation

Generates 8 common email patterns for each name + domain:
1. `first@domain.com`
2. `last@domain.com`
3. `first.last@domain.com`
4. `firstlast@domain.com`
5. `f.last@domain.com`
6. `first_last@domain.com`
7. `flast@domain.com`
8. `last.first@domain.com`

## Installation

1. Make sure you have Node.js installed (v14 or higher)

2. Install dependencies:
```bash
npm install
```

## Usage

1. Start the server:
```bash
npm start
```

Or directly:
```bash
node server.js
```

2. Open your browser and go to:
```
http://localhost:3000
```

3. Paste your email list (one per line or comma-separated) and click "Verify Emails"

## Verification Levels

- **Syntax Check**: Fast, validates email format only
- **DNS + MX Records** (Recommended): Validates format and checks if domain has mail servers
- **Full SMTP Check**: Attempts to verify email exists on server (may be limited)

## Project Structure

```
emailVerifier/
├── server.js          # Express backend server
├── public/
│   └── index.html     # Frontend interface
├── package.json       # Dependencies
└── README.md         # This file
```

## Notes

- The server runs on port 3000 by default
- DNS verification checks for MX records which indicate mail servers
- SMTP verification may be limited due to server restrictions

## Example Usage

### Generate & Verify Mode (Primary Use Case)

1. Start the server
2. Open the web interface at http://localhost:3000
3. Click "Generate & Verify" tab (default)
4. Paste names and domains (one per line):
   ```
   John, Doe, company.com
   Jane, Smith, example.com
   Mike, Johnson, startup.io
   ```

   Or space-separated:
   ```
   John Doe company.com
   Jane Smith example.com
   Mike Johnson startup.io
   ```

5. Select verification level (DNS Check recommended)
6. Click the arrow button or press Cmd/Ctrl+Enter
7. **Results appear in two columns:**
   - ✅ **Deliverable**: All verified emails with copy buttons
   - ❌ **Undeliverable**: Invalid emails with reason
8. **Copy All Verified** - One click to copy all verified emails to clipboard
9. **Export CSV** - Download verified emails as CSV file

### Quick Verify Mode

1. Switch to "Quick Verify" tab
2. Paste emails directly:
   ```
   user1@example.com
   user2@gmail.com
   invalid-email
   test@nonexistentdomain12345.com
   ```
3. Verify and see results split by deliverability

## Use Cases

- **B2B Lead Generation**: Upload prospect names + company domains, get verified decision-maker emails
- **Email List Cleaning**: Verify existing email lists before sending campaigns
- **Outreach Preparation**: Generate and validate multiple email patterns for cold outreach
- **Data Enrichment**: Convert partial contact data (name + company) into verified email addresses

