-- Saturn Star Movers Outreach Engine — Database Schema

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT DEFAULT '',
    company_name TEXT DEFAULT '',
    street_address TEXT DEFAULT '',
    province TEXT DEFAULT 'ON',
    postal_code TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    domain TEXT DEFAULT '',
    contact_name TEXT DEFAULT '',
    title_role TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    tier TEXT DEFAULT 'D',
    industry_code TEXT DEFAULT '',
    csv_source TEXT DEFAULT '',
    priority_score INTEGER DEFAULT 50,
    discovered_email TEXT DEFAULT '',
    email_status TEXT DEFAULT 'pending',
    outreach_status TEXT DEFAULT 'pending',
    bounce_count INTEGER DEFAULT 0,
    bounced_emails TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- CRM account fields
    company_size TEXT DEFAULT '',
    company_type TEXT DEFAULT '',
    confidence_score INTEGER DEFAULT 0,
    account_status TEXT DEFAULT 'cold',
    last_touch_date TEXT DEFAULT '',
    next_action_date TEXT DEFAULT '',
    next_action TEXT DEFAULT '',
    decision_maker_found INTEGER DEFAULT 0,
    procurement_required INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_contacts_tier ON contacts(tier);
CREATE INDEX IF NOT EXISTS idx_contacts_account_status ON contacts(account_status);
CREATE INDEX IF NOT EXISTS idx_contacts_industry ON contacts(industry_code);
CREATE INDEX IF NOT EXISTS idx_contacts_email_status ON contacts(email_status);
CREATE INDEX IF NOT EXISTS idx_contacts_outreach_status ON contacts(outreach_status);
CREATE INDEX IF NOT EXISTS idx_contacts_domain ON contacts(domain);
CREATE INDEX IF NOT EXISTS idx_contacts_priority ON contacts(priority_score DESC);

CREATE TABLE IF NOT EXISTS email_discovery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    step TEXT NOT NULL,
    result TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE TABLE IF NOT EXISTS outreach_bundles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    batch_date TEXT NOT NULL,
    email_subject TEXT DEFAULT '',
    email_body TEXT DEFAULT '',
    status TEXT DEFAULT 'queued',
    approved_at TEXT,
    sent_at TEXT,
    email_sent INTEGER DEFAULT 0,
    open_count INTEGER DEFAULT 0,
    first_opened_at TEXT,
    notes TEXT DEFAULT '',
    reply_type TEXT DEFAULT '',
    reply_snippet TEXT DEFAULT '',
    redirect_email TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE INDEX IF NOT EXISTS idx_bundles_status ON outreach_bundles(status);
CREATE INDEX IF NOT EXISTS idx_bundles_batch_date ON outreach_bundles(batch_date);
CREATE INDEX IF NOT EXISTS idx_bundles_contact ON outreach_bundles(contact_id);

CREATE TABLE IF NOT EXISTS email_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bundle_id INTEGER NOT NULL,
    tracking_id TEXT NOT NULL UNIQUE,
    sent_at TEXT,
    FOREIGN KEY (bundle_id) REFERENCES outreach_bundles(id)
);

CREATE INDEX IF NOT EXISTS idx_tracking_id ON email_tracking(tracking_id);

CREATE TABLE IF NOT EXISTS email_opens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_id TEXT NOT NULL,
    bundle_id INTEGER NOT NULL,
    ip_address TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bundle_id) REFERENCES outreach_bundles(id)
);

CREATE TABLE IF NOT EXISTS send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bundle_id INTEGER NOT NULL,
    recipient_email TEXT NOT NULL,
    smtp_response_code INTEGER,
    smtp_response_text TEXT DEFAULT '',
    error TEXT DEFAULT '',
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bundle_id) REFERENCES outreach_bundles(id)
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL,
    industry_code TEXT DEFAULT '',
    name TEXT NOT NULL,
    subject_template TEXT DEFAULT '',
    body_template TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT NOT NULL UNIQUE,
    contacts_discovered INTEGER DEFAULT 0,
    emails_found INTEGER DEFAULT 0,
    bundles_generated INTEGER DEFAULT 0,
    bundles_sent INTEGER DEFAULT 0,
    bounces INTEGER DEFAULT 0,
    opens INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    bundle_id INTEGER,
    sequence_number INTEGER DEFAULT 1,
    scheduled_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    sent_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (bundle_id) REFERENCES outreach_bundles(id)
);

CREATE INDEX IF NOT EXISTS idx_followups_date ON follow_ups(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_followups_status ON follow_ups(status);

CREATE TABLE IF NOT EXISTS news_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    headline TEXT DEFAULT '',
    content_snippet TEXT DEFAULT '',
    signal_type TEXT NOT NULL,
    company_name TEXT DEFAULT '',
    opportunity TEXT DEFAULT '',
    city TEXT DEFAULT '',
    urgency TEXT DEFAULT 'medium',
    recommended_action TEXT DEFAULT '',
    contact_id INTEGER DEFAULT NULL,
    status TEXT DEFAULT 'new',
    published_date TEXT DEFAULT '',
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_url ON news_signals(source_url);
CREATE INDEX IF NOT EXISTS idx_signals_status ON news_signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_type ON news_signals(signal_type);

-- Touch log — multi-channel interaction tracking
CREATE TABLE IF NOT EXISTS touch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    direction TEXT DEFAULT 'outbound',
    subject TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    logged_by TEXT DEFAULT 'system',
    touch_date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);
CREATE INDEX IF NOT EXISTS idx_touch_log_contact ON touch_log(contact_id);
CREATE INDEX IF NOT EXISTS idx_touch_log_channel ON touch_log(channel);

-- Ecosystem contacts — post-move participant capture
CREATE TABLE IF NOT EXISTS ecosystem_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    role TEXT NOT NULL,
    company TEXT DEFAULT '',
    source_contact_id INTEGER DEFAULT NULL,
    notes TEXT DEFAULT '',
    promoted_contact_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_contact_id) REFERENCES contacts(id)
);
CREATE INDEX IF NOT EXISTS idx_ecosystem_role ON ecosystem_contacts(role);

-- Partner codes — partner program with revenue tracking
CREATE TABLE IF NOT EXISTS partner_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    discount_percent REAL DEFAULT 0,
    bonus_per_referral REAL DEFAULT 0,
    total_referrals INTEGER DEFAULT 0,
    total_revenue REAL DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_partner_code ON partner_codes(code);

-- Jobs — quote-to-complete revenue pipeline
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER DEFAULT NULL,
    partner_code TEXT DEFAULT '',
    job_type TEXT DEFAULT 'commercial',
    status TEXT DEFAULT 'quoted',
    quote_amount REAL DEFAULT 0,
    final_amount REAL DEFAULT 0,
    move_date TEXT DEFAULT '',
    origin_address TEXT DEFAULT '',
    destination_address TEXT DEFAULT '',
    crew_size INTEGER DEFAULT 0,
    truck_count INTEGER DEFAULT 0,
    labor_hours REAL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_contact ON jobs(contact_id);
CREATE INDEX IF NOT EXISTS idx_jobs_partner ON jobs(partner_code);

-- Field Intel — research pipeline for companies spotted in the field
CREATE TABLE IF NOT EXISTS account_research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    user_notes TEXT DEFAULT '',
    research_status TEXT DEFAULT 'new',
    company_brief TEXT DEFAULT '',
    company_type TEXT DEFAULT '',
    approach_strategy TEXT DEFAULT '',
    angles TEXT DEFAULT '[]',
    procurement_notes TEXT DEFAULT '',
    target_contacts TEXT DEFAULT '[]',
    recommended_first_message TEXT DEFAULT '',
    stages_json TEXT DEFAULT '[]',
    current_stage INTEGER DEFAULT 0,
    contact_id INTEGER DEFAULT NULL,
    city TEXT DEFAULT '',
    industry TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    next_action_date TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_status ON account_research(research_status);
CREATE INDEX IF NOT EXISTS idx_research_priority ON account_research(priority);
