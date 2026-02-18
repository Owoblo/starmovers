# SATURN STAR MOVERS — DIRECT MAIL CAMPAIGN
## Master Implementation Guide

---

## OVERVIEW

You have **21 CSV files** with **1,500+ contacts** organized by industry. This guide shows you how to execute personalized direct mail campaigns that convert.

---

## YOUR CAMPAIGN STRUCTURE

| Tier | Letter Template | Target Industries | CSV Files to Use |
|------|-----------------|-------------------|------------------|
| **A** | Referral Partners | Lawyers, Mortgage Brokers | `Divorce_Law_Firms_*.csv`, `estate_lawyers_*.csv`, `mortgage_brokers_*.csv` |
| **B** | B2B Services | Builders, Insurance, Property Mgmt | `home_builders_*.csv`, `insurance_adjusters_*.csv`, `condo_corporations_*.csv` |
| **C** | Corporate HR | Employers, Schools, Hospitals | `large_employers_*.csv`, `universities_colleges_*.csv`, `hospitals_healthcare_*.csv`, `hotels_hospitality_*.csv`, `government_offices_*.csv` |
| **D** | Community | Churches, Nonprofits, Clubs | `churches_places_of_worship_*.csv`, `nonprofits_*.csv`, `sports_clubs_*.csv`, `cultural_ethnic_clubs_*.csv` |
| **E** | Care Facilities | Retirement, Funeral Homes | `retirement_care_homes_*.csv`, `funeral_homes_*.csv` |

---

## STEP-BY-STEP EXECUTION

### STEP 1: PREPARE YOUR CSV FILES

**For Each CSV, Ensure These Columns Exist:**

| Column Name | Required | Example |
|-------------|----------|---------|
| Company Name / Organization Name | YES | "Johnson Miller Family Lawyers" |
| Decision Maker Name | YES | "Jason Paul Howie" |
| Title/Role | YES | "Founding Partner" |
| Street Address | YES | "420 Devonshire Road" |
| City | YES | "Windsor" |
| Province | YES | "ON" |
| Postal Code | YES | "N8Y 4T6" |
| Phone Number | Optional | "519-973-1500" |
| Website | Optional | "jasonpaulhowie.com" |

**Standardize Column Names Across Files:**
If your columns are named differently, rename them to match the mail merge fields.

---

### STEP 2: ADD TRACKING CODES

Before mail merge, add a column for tracking:

| Industry | Tracking Code |
|----------|---------------|
| Divorce Lawyers | DL25 |
| Estate Lawyers | EL25 |
| Mortgage Brokers | MB25 |
| Home Builders | HB25 |
| Insurance/Restoration | IR25 |
| Condo Corps | CC25 |
| Large Employers | LE25 |
| Universities | UN25 |
| Hospitals | HO25 |
| Hotels | HT25 |
| Government | GV25 |
| Churches | CH25 |
| Nonprofits | NP25 |
| Sports Clubs | SC25 |
| Cultural Clubs | CU25 |
| Retirement Homes | RH25 |
| Funeral Homes | FH25 |

---

### STEP 3: SET UP MAIL MERGE

#### Option A: Microsoft Word + Excel

1. **Open Word** → Click "Mailings" tab
2. **Start Mail Merge** → Select "Letters"
3. **Select Recipients** → "Use an Existing List" → Choose your CSV
4. **Copy letter template** into Word document
5. **Replace placeholders** with merge fields:
   - Highlight `{{Company Name}}` → Click "Insert Merge Field" → Select "Company Name"
   - Repeat for all fields
6. **Preview Results** → Check several letters look correct
7. **Finish & Merge** → Print or save as individual documents

#### Option B: Google Docs + Sheets (Free)

1. **Upload CSV** to Google Sheets
2. **Install Add-on:** "Yet Another Mail Merge" or "Autocrat"
3. **Create Template** in Google Docs with `{{Field Name}}` placeholders
4. **Connect Sheet** to the add-on
5. **Map Fields** and generate personalized documents
6. **Export as PDFs** for printing

#### Option C: Professional Print Services

**Canada Post Smartmail Marketing:**
- Upload your CSV + letter template
- They print, fold, stuff, stamp, and mail
- Volume discounts available
- Track delivery

**Local Print Shops:**
- Most can do mail merge printing
- Provide CSV + Word document
- They handle the rest

---

### STEP 4: PRINT & MAIL

**Recommended Paper:**
- 24lb bond or 28lb for premium feel
- White or off-white (ivory)
- Letter size (8.5" x 11")

**Envelopes:**
- #10 business envelopes (standard)
- Consider window envelopes (address shows through)
- Or hand-address for personal touch (high-value targets)

**Postage:**
- Lettermail: ~$1.15 per letter (1-30g)
- Oversized: ~$1.39 per letter (31-50g)
- Bulk rates available for 500+ pieces

**Inserts to Include:**
- Business card
- Flyer/brochure (optional)
- Rate sheet (for B2B)
- Testimonial sheet (optional)

---

### STEP 5: FOLLOW-UP SCHEDULE

**Critical:** The letter is just the first touch. Follow-up is where deals close.

| Day | Action | Tool |
|-----|--------|------|
| 0 | Mail letter | Physical mail |
| 5 | Email to decision maker | Email + digital brochure |
| 10 | Phone call | Direct call |
| 15 | LinkedIn connection | LinkedIn |
| 21 | Second letter (shorter) | Physical mail |
| 30 | Final phone call | Direct call |

**Track Everything:**
Create a simple spreadsheet:

| Company | Contact | Letter Sent | Email Sent | Called | Response | Status |
|---------|---------|-------------|------------|--------|----------|--------|
| ABC Law | Jane Doe | Jan 15 | Jan 20 | Jan 25 | Voicemail | Follow-up |

---

## PRIORITY EXECUTION ORDER

Don't try to do everything at once. Focus and execute:

### Week 1-2: HOT LEADS (High Intent)
- `HOT_LEADS_SIGNALS_*.csv` — Time-sensitive opportunities
- Call first, then send personalized letters

### Week 3-4: TIER A (Referral Partners)
- Divorce Lawyers → Estate Lawyers → Mortgage Brokers
- These generate ongoing referrals = high ROI

### Week 5-6: TIER E (Care Facilities)
- Retirement Homes → Funeral Homes
- Emotional moves = premium pricing, less competition

### Week 7-8: TIER B (B2B Services)
- Home Builders → Insurance → Condo Corps
- Commercial accounts = repeat business

### Week 9-10: TIER C (Corporate)
- Large Employers (focus on growing companies)
- Universities → Hospitals

### Week 11-12: TIER D (Community)
- Churches → Cultural Clubs → Sports Clubs
- Build word-of-mouth and community presence

---

## BUDGET PLANNING

| Item | Cost per Letter | 100 Letters | 500 Letters | 1,000 Letters |
|------|-----------------|-------------|-------------|---------------|
| Printing | $0.25-$0.50 | $25-$50 | $125-$250 | $250-$500 |
| Envelopes | $0.05-$0.15 | $5-$15 | $25-$75 | $50-$150 |
| Postage | $1.15 | $115 | $575 | $1,150 |
| Business Cards | $0.05 | $5 | $25 | $50 |
| **TOTAL** | ~$1.50-$2.00 | $150-$200 | $750-$1,000 | $1,500-$2,000 |

**ROI Calculation:**
- If 1% response rate = 5-10 bookings per 1,000 letters
- Average move value = $800-$1,500
- Revenue = $4,000-$15,000
- **ROI = 300%-1,000%**

---

## TRACKING YOUR RESULTS

### Method 1: Unique Phone Numbers
- Get a separate tracking number for direct mail
- Count calls to that number

### Method 2: Promo Codes
- Each letter has a unique code (DL25, HB25, etc.)
- Track which codes are used at booking

### Method 3: Ask Every Caller
- "How did you hear about us?"
- Log responses in your CRM

### Key Metrics to Track:

| Metric | Formula | Target |
|--------|---------|--------|
| Response Rate | Responses ÷ Letters Sent | 1-3% |
| Conversion Rate | Bookings ÷ Responses | 25-50% |
| Cost per Lead | Total Cost ÷ Responses | <$50 |
| Cost per Booking | Total Cost ÷ Bookings | <$150 |
| Revenue per Campaign | Total Bookings × Avg Move Value | 5-10x cost |

---

## FILES IN THIS FOLDER

```
/direct_mail_templates/
├── 00_MASTER_IMPLEMENTATION_GUIDE.md (this file)
├── TIER_A_Referral_Partners_Letter.md
├── TIER_B_B2B_Services_Letter.md
├── TIER_C_Corporate_HR_Letter.md
├── TIER_D_Community_Partners_Letter.md
├── TIER_E_Care_Facilities_Letter.md
├── TRACKING_CODES_REFERENCE.md
└── WORD_TEMPLATES/ (coming next)
```

---

## NEED HELP?

For each letter template, you'll find:
- Full letter copy ready to use
- Mail merge field locations marked
- Envelope teaser options
- Follow-up sequence recommendations
- Industry-specific customizations

**You're ready to dominate Windsor-Essex-Chatham. Go get 'em.**
