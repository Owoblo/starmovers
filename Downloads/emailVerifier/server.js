const express = require('express');
const dns = require('dns');
const net = require('net');
const { promisify } = require('util');
const validator = require('email-validator');
const path = require('path');
const OpenAI = require('openai');
const axios = require('axios');

const app = express();
const PORT = 3000;

// Promisify DNS functions
const resolveMx = promisify(dns.resolveMx);

// Cache for domain lookups and AI responses
const domainCache = new Map();
const aiResponseCache = new Map();

// OpenAI client (will be initialized per request with user's key)
function getOpenAIClient(apiKey) {
    return new OpenAI({ apiKey });
}

// Middleware
app.use(express.json());
app.use(express.static('public'));

// ============================================
// AI-POWERED INTELLIGENCE LAYER
// ============================================

// AI-powered smart parser - understands ANY input
async function aiSmartParse(input, apiKey) {
    const cacheKey = `parse_${input.substring(0, 100)}`;
    if (aiResponseCache.has(cacheKey)) {
        return aiResponseCache.get(cacheKey);
    }

    const openai = getOpenAIClient(apiKey);

    try {
        const response = await openai.chat.completions.create({
            model: 'gpt-4o-mini',
            messages: [{
                role: 'system',
                content: `You are an intelligent data extractor for email generation. Extract people's information from any format of text.

RULES:
1. Extract: firstName, lastName, company (if available), role (if mentioned)
2. Return ONLY valid JSON array, no explanations
3. Skip headers, empty lines, invalid data
4. If only first name given, use it as lastName too
5. Company names should be extracted even from descriptions like "works at", "from", "CEO of"
6. Handle any format: tables, CSV, sentences, messy text

OUTPUT FORMAT (wrap in object):
{"people": [{"firstName": "John", "lastName": "Doe", "company": "Tesla", "role": "CEO"}]}`
            }, {
                role: 'user',
                content: input
            }],
            temperature: 0,
            response_format: { type: "json_object" }
        });

        const result = JSON.parse(response.choices[0].message.content);
        const people = result.people || result.data || result.contacts || result.results || [];

        aiResponseCache.set(cacheKey, people);
        return people;
    } catch (error) {
        console.error('AI Parse Error:', error.message);
        return [];
    }
}

// AI-powered domain lookup
async function aiLookupDomain(companyName, apiKey) {
    const cacheKey = `domain_${companyName.toLowerCase()}`;
    if (domainCache.has(cacheKey)) {
        return domainCache.get(cacheKey);
    }

    const openai = getOpenAIClient(apiKey);

    try {
        const response = await openai.chat.completions.create({
            model: 'gpt-4o-mini',
            messages: [{
                role: 'system',
                content: 'Return ONLY the primary domain name for companies. No explanations, no protocols, just domain. Examples: Tesla → tesla.com, Microsoft → microsoft.com'
            }, {
                role: 'user',
                content: `Company: ${companyName}`
            }],
            temperature: 0,
            max_tokens: 20
        });

        const domain = response.choices[0].message.content.trim().toLowerCase()
            .replace(/^https?:\/\//i, '')
            .replace(/^www\./i, '')
            .replace(/\/.*$/, '');

        domainCache.set(cacheKey, domain);
        return domain;
    } catch (error) {
        console.error('Domain Lookup Error:', error.message);
        return null;
    }
}

// Search API fallback for domain verification
async function searchDomain(companyName) {
    const cacheKey = `search_${companyName.toLowerCase()}`;
    if (domainCache.has(cacheKey)) {
        return domainCache.get(cacheKey);
    }

    try {
        // Using DuckDuckGo Instant Answer API (free, no key needed)
        const response = await axios.get(`https://api.duckduckgo.com/?q=${encodeURIComponent(companyName + ' official website')}&format=json`);

        if (response.data.AbstractURL) {
            const url = new URL(response.data.AbstractURL);
            const domain = url.hostname.replace(/^www\./i, '');
            domainCache.set(cacheKey, domain);
            return domain;
        }

        // Fallback: try to extract from RelatedTopics
        if (response.data.RelatedTopics && response.data.RelatedTopics.length > 0) {
            const firstResult = response.data.RelatedTopics[0];
            if (firstResult.FirstURL) {
                const url = new URL(firstResult.FirstURL);
                const domain = url.hostname.replace(/^www\./i, '');
                domainCache.set(cacheKey, domain);
                return domain;
            }
        }
    } catch (error) {
        console.error('Search Error:', error.message);
    }

    return null;
}

// Hybrid domain lookup: AI first, then search fallback
async function intelligentDomainLookup(companyName, apiKey) {
    // Try AI first (fast)
    let domain = await aiLookupDomain(companyName, apiKey);

    // Verify domain has valid TLD
    if (domain && domain.includes('.') && domain.split('.').length >= 2) {
        return domain;
    }

    // Fallback to search if AI failed or seems incorrect
    domain = await searchDomain(companyName);
    return domain || `${companyName.toLowerCase().replace(/\s+/g, '')}.com`; // Last resort guess
}

// Role-based person lookup (e.g., "CEO of Tesla")
async function aiRoleLookup(role, company, apiKey) {
    const openai = getOpenAIClient(apiKey);

    try {
        const response = await openai.chat.completions.create({
            model: 'gpt-4o-mini',
            messages: [{
                role: 'system',
                content: 'You help find people by their role at companies. Return ONLY JSON with firstName and lastName. If unknown, return null values.'
            }, {
                role: 'user',
                content: `Who is the ${role} of ${company}? Return: {"firstName": "...", "lastName": "..."}`
            }],
            temperature: 0,
            response_format: { type: "json_object" }
        });

        return JSON.parse(response.choices[0].message.content);
    } catch (error) {
        console.error('Role Lookup Error:', error.message);
        return { firstName: null, lastName: null };
    }
}

// Email pattern generation functions
function generateEmailVariations(firstName, lastName, domain) {
    // Clean inputs
    const first = firstName.toLowerCase().trim();
    const last = lastName.toLowerCase().trim();
    const dom = domain.toLowerCase().trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0];

    // Generate common email patterns
    const variations = [
        `${first}@${dom}`,                    // john@company.com
        `${last}@${dom}`,                     // doe@company.com
        `${first}.${last}@${dom}`,            // john.doe@company.com
        `${first}${last}@${dom}`,             // johndoe@company.com
        `${first[0]}.${last}@${dom}`,         // j.doe@company.com
        `${first}_${last}@${dom}`,            // john_doe@company.com
        `${first[0]}${last}@${dom}`,          // jdoe@company.com
        `${last}.${first}@${dom}`,            // doe.john@company.com
    ];

    // Remove duplicates and return
    return [...new Set(variations)];
}

function parseNameDomainInput(input) {
    // Smart parser - handles ANY format: CSV, tables, documents, messy data
    const lines = input.trim().split('\n').filter(line => line.trim());
    const parsed = [];

    // Domain regex to extract domains/URLs from text
    const domainRegex = /(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)/g;

    // Common name patterns (handles "First Last", "Last, First", etc.)
    const cleanText = (text) => {
        return text
            .replace(/[|]/g, ' ')        // Replace table separators
            .replace(/\t/g, ' ')         // Replace tabs
            .replace(/\s+/g, ' ')        // Normalize spaces
            .replace(/[""'']/g, '')      // Remove quotes
            .trim();
    };

    for (const line of lines) {
        const cleaned = cleanText(line);

        // Skip empty lines or lines that look like headers
        if (!cleaned ||
            /^(name|first|last|email|domain|company|website)/i.test(cleaned)) {
            continue;
        }

        let firstName = '';
        let lastName = '';
        let domain = '';

        // Extract domain/URL from anywhere in the line
        const domainMatches = [...cleaned.matchAll(domainRegex)];
        if (domainMatches.length > 0) {
            domain = domainMatches[0][1]; // Get the domain without protocol
        }

        // Remove domain from line to extract names
        let nameText = cleaned;
        if (domain) {
            nameText = nameText.replace(domainRegex, '').trim();
        }

        // Remove common noise words
        nameText = nameText
            .replace(/\b(company|corp|inc|ltd|llc|at|from|contact)\b/gi, '')
            .trim();

        // Try different parsing strategies
        if (nameText.includes(',')) {
            // CSV format: "First, Last" or "Last, First"
            const parts = nameText.split(',').map(p => p.trim()).filter(p => p);
            if (parts.length >= 2) {
                // Check if first part looks like a last name (all caps or common pattern)
                if (parts[0] === parts[0].toUpperCase() && parts[0].length > 1) {
                    // "LAST, First" format
                    lastName = parts[0];
                    firstName = parts[1].split(/\s+/)[0];
                } else {
                    // "First, Last" format
                    firstName = parts[0].split(/\s+/)[0];
                    lastName = parts[1].split(/\s+/)[0];
                }
            }
        } else {
            // Space-separated or tab-separated
            const words = nameText.split(/\s+/).filter(w => w && w.length > 1);

            if (words.length >= 2) {
                // Take first word as first name, last word as last name
                firstName = words[0];
                lastName = words[words.length - 1];
            } else if (words.length === 1) {
                // Single name, use as first name
                firstName = words[0];
                lastName = words[0]; // Fallback
            }
        }

        // Only add if we have at least a name and domain
        if ((firstName || lastName) && domain) {
            parsed.push({
                firstName: firstName || lastName,
                lastName: lastName || firstName,
                domain: domain
            });
        }
    }

    return parsed;
}

// Email verification functions
function verifyEmailSyntax(email) {
    // Basic checks first
    if (!email || typeof email !== 'string') {
        return {
            valid: false,
            message: 'Email is empty or invalid type'
        };
    }
    
    // Must have exactly one @ symbol
    const atCount = (email.match(/@/g) || []).length;
    if (atCount !== 1) {
        return {
            valid: false,
            message: atCount === 0 ? 'Missing @ symbol' : 'Too many @ symbols'
        };
    }
    
    // Split by @ and check parts
    const parts = email.split('@');
    const localPart = parts[0];
    const domain = parts[1];
    
    // Local part cannot be empty
    if (!localPart || localPart.length === 0) {
        return {
            valid: false,
            message: 'Local part (before @) is empty'
        };
    }
    
    // Domain cannot be empty
    if (!domain || domain.length === 0) {
        return {
            valid: false,
            message: 'Domain part (after @) is empty'
        };
    }
    
    // Domain must have at least one dot
    if (!domain.includes('.')) {
        return {
            valid: false,
            message: 'Domain must contain at least one dot'
        };
    }
    
    // Use email-validator for stricter validation
    try {
        const isValid = validator.validate(email);
        return {
            valid: isValid,
            message: isValid ? 'Valid email format' : 'Invalid email format'
        };
    } catch (error) {
        return {
            valid: false,
            message: `Validation error: ${error.message}`
        };
    }
}

async function verifyEmailDNS(email) {
    try {
        // First check if email has @ symbol
        if (!email.includes('@')) {
            return {
                valid: false,
                message: 'Email missing @ symbol'
            };
        }
        
        const domain = email.split('@')[1];
        
        // Check if domain exists
        if (!domain || domain.length === 0) {
            return {
                valid: false,
                message: 'Invalid domain'
            };
        }
        
        // Try to resolve MX records
        const mxRecords = await resolveMx(domain);
        
        if (mxRecords && mxRecords.length > 0) {
            return {
                valid: true,
                message: `Domain has ${mxRecords.length} MX record(s)`
            };
        }
        return {
            valid: false,
            message: 'No MX records found'
        };
    } catch (error) {
        // DNS errors mean domain doesn't exist or has no mail servers
        return {
            valid: false,
            message: `DNS error: ${error.code === 'ENOTFOUND' ? 'Domain not found' : error.message}`
        };
    }
}

async function verifyEmailSMTP(email) {
    try {
        const domain = email.split('@')[1];
        const mxRecords = await resolveMx(domain);
        
        if (!mxRecords || mxRecords.length === 0) {
            return {
                valid: false,
                message: 'No MX records found'
            };
        }
        
        // Sort by priority (lowest number is highest priority)
        mxRecords.sort((a, b) => a.priority - b.priority);
        const mxHost = mxRecords[0].exchange;
        
        // Perform actual SMTP handshake
        return await checkSMTPHandshake(email, mxHost);
    } catch (error) {
        return {
            valid: null,
            message: `SMTP check unavailable: ${error.message}`
        };
    }
}

function checkSMTPHandshake(email, mxHost) {
    return new Promise((resolve) => {
        const socket = new net.Socket();
        let step = 0;
        let hasResolved = false;
        
        // Timeout after 5 seconds
        const timeout = setTimeout(() => {
            if (!hasResolved) {
                hasResolved = true;
                socket.destroy();
                resolve({ valid: null, message: 'Connection timed out (Port 25 likely blocked)' });
            }
        }, 5000);

        socket.connect(25, mxHost);
        socket.setEncoding('utf8');

        socket.on('connect', () => {
            // Waiting for 220 banner
        });

        socket.on('data', (data) => {
            if (hasResolved) return;
            
            const response = data.toString();
            const code = parseInt(response.substring(0, 3));
            
            // Basic SMTP State Machine
            try {
                if (step === 0 && code === 220) {
                    // Banner received, say HELO
                    socket.write(`HELO ${mxHost}\r\n`);
                    step = 1;
                } else if (step === 1 && code === 250) {
                    // HELO accepted, set sender
                    socket.write('MAIL FROM:<test@example.com>\r\n');
                    step = 2;
                } else if (step === 2 && code === 250) {
                    // Sender accepted, check recipient (THE REAL TEST)
                    socket.write(`RCPT TO:<${email}>\r\n`);
                    step = 3;
                } else if (step === 3) {
                    // RCPT TO response
                    hasResolved = true;
                    clearTimeout(timeout);
                    socket.write('QUIT\r\n');
                    socket.end();
                    
                    if (code === 250) {
                        resolve({ valid: true, message: 'Exists (Server accepted)' });
                    } else if (code === 550) {
                        resolve({ valid: false, message: 'Does not exist (Server rejected)' });
                    } else {
                        // Greylisting or other non-committal error
                        resolve({ valid: null, message: `Uncertain response: ${code}` });
                    }
                }
            } catch (e) {
                hasResolved = true;
                clearTimeout(timeout);
                socket.destroy();
                resolve({ valid: null, message: 'Protocol error' });
            }
        });

        socket.on('error', (err) => {
            if (!hasResolved) {
                hasResolved = true;
                clearTimeout(timeout);
                resolve({ valid: null, message: `Connection failed: ${err.message}` });
            }
        });
    });
}

// API endpoint for AI-powered smart lookup
app.post('/api/smart-lookup', async (req, res) => {
    try {
        const { input, level = 'dns', apiKey } = req.body;

        if (!input || !input.trim()) {
            return res.json({ results: [], error: 'No input provided' });
        }

        if (!apiKey) {
            return res.json({ results: [], error: 'OpenAI API key required for Smart Lookup' });
        }

        // Step 1: AI parses the input
        const people = await aiSmartParse(input, apiKey);

        if (people.length === 0) {
            return res.json({
                results: [],
                error: 'Could not extract any contact information. Try: "John Doe at Tesla" or "Find CEO of SpaceX"'
            });
        }

        const allResults = [];
        const aiInsights = [];

        // Step 2: For each person, lookup domain if needed and generate emails
        for (const person of people) {
            let domain = person.domain;

            // If no domain but has company, use AI to find it
            if (!domain && person.company) {
                aiInsights.push(`🔍 Looking up domain for ${person.company}...`);
                domain = await intelligentDomainLookup(person.company, apiKey);
                aiInsights.push(`✓ Found: ${person.company} → ${domain}`);
            }

            // If role mentioned but no name (e.g., "CEO of Tesla")
            if (person.role && (!person.firstName || !person.lastName) && person.company) {
                aiInsights.push(`🔍 Looking up ${person.role} of ${person.company}...`);
                const roleInfo = await aiRoleLookup(person.role, person.company, apiKey);
                if (roleInfo.firstName) {
                    person.firstName = roleInfo.firstName;
                    person.lastName = roleInfo.lastName;
                    aiInsights.push(`✓ Found: ${roleInfo.firstName} ${roleInfo.lastName}`);
                }
            }

            if (!domain || !person.firstName) {
                continue; // Skip if we still don't have enough info
            }

            // Generate email variations
            const variations = generateEmailVariations(
                person.firstName,
                person.lastName || person.firstName,
                domain
            );

            // Verify each variation
            for (const email of variations) {
                const result = {
                    email: email,
                    person: `${person.firstName} ${person.lastName || ''}`.trim(),
                    company: person.company || domain,
                    role: person.role,
                    domain: domain,
                    syntax: verifyEmailSyntax(email)
                };

                // DNS check if syntax is valid
                if (result.syntax.valid && (level === 'dns' || level === 'smtp')) {
                    result.dns = await verifyEmailDNS(email);
                }

                // SMTP check if DNS is valid
                if (result.syntax.valid && level === 'smtp') {
                    result.smtp = await verifyEmailSMTP(email);
                }

                // Overall validation
                if (level === 'syntax') {
                    result.overallValid = result.syntax.valid;
                } else if (level === 'dns') {
                    result.overallValid = result.syntax.valid && result.dns?.valid === true;
                } else if (level === 'smtp') {
                    result.overallValid = result.syntax.valid && result.dns?.valid === true;
                } else {
                    result.overallValid = result.syntax.valid;
                }

                allResults.push(result);
            }
        }

        res.json({
            results: allResults,
            aiInsights: aiInsights,
            peopleFound: people.length
        });
    } catch (error) {
        console.error('Smart Lookup Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// API endpoint for generating email variations from names + domains
app.post('/api/generate', async (req, res) => {
    try {
        const { input, level = 'dns' } = req.body;

        if (!input || !input.trim()) {
            return res.json({ results: [] });
        }

        // Parse the name-domain input
        const people = parseNameDomainInput(input);

        if (people.length === 0) {
            return res.json({
                results: [],
                error: 'Invalid format. Use: FirstName, LastName, Domain (one per line)'
            });
        }

        const allResults = [];

        // For each person, generate variations and verify them
        for (const person of people) {
            const variations = generateEmailVariations(
                person.firstName,
                person.lastName,
                person.domain
            );

            // Verify each variation
            for (const email of variations) {
                const result = {
                    email: email,
                    person: `${person.firstName} ${person.lastName}`,
                    domain: person.domain,
                    syntax: verifyEmailSyntax(email)
                };

                // DNS check if syntax is valid
                if (result.syntax.valid && (level === 'dns' || level === 'smtp')) {
                    result.dns = await verifyEmailDNS(email);
                }

                // SMTP check if DNS is valid
                if (result.syntax.valid && level === 'smtp') {
                    result.smtp = await verifyEmailSMTP(email);
                }

                // Overall validation
                if (level === 'syntax') {
                    result.overallValid = result.syntax.valid;
                } else if (level === 'dns') {
                    result.overallValid = result.syntax.valid && result.dns?.valid === true;
                } else if (level === 'smtp') {
                    result.overallValid = result.syntax.valid && result.dns?.valid === true;
                } else {
                    result.overallValid = result.syntax.valid;
                }

                allResults.push(result);
            }
        }

        res.json({ results: allResults });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API endpoint for direct email verification
app.post('/api/verify', async (req, res) => {
    try {
        const { emails, level = 'syntax' } = req.body;

        if (!emails || !emails.trim()) {
            return res.json({ results: [] });
        }

        // Parse emails from text (one per line or comma-separated)
        const emailList = emails
            .split(/\n|,/)
            .map(email => email.trim())
            .filter(email => {
                // Basic filter: must have some content and contain @ symbol
                return email.length > 0 && email.includes('@');
            });

        const results = [];

        for (const email of emailList) {
            const result = {
                email: email,
                syntax: verifyEmailSyntax(email)
            };

            // DNS check if syntax is valid
            if (result.syntax.valid && (level === 'dns' || level === 'smtp')) {
                result.dns = await verifyEmailDNS(email);
            }

            // SMTP check if DNS is valid
            if (result.syntax.valid && level === 'smtp') {
                result.smtp = await verifyEmailSMTP(email);
            }

            // Overall validation - must pass syntax AND (if DNS/SMTP level) must pass DNS check
            if (level === 'syntax') {
                result.overallValid = result.syntax.valid;
            } else if (level === 'dns') {
                result.overallValid = result.syntax.valid && result.dns?.valid === true;
            } else if (level === 'smtp') {
                // For SMTP, we need syntax, DNS, and optionally SMTP (SMTP failures are often due to server restrictions)
                result.overallValid = result.syntax.valid && result.dns?.valid === true;
            } else {
                result.overallValid = result.syntax.valid;
            }

            results.push(result);
        }

        res.json({ results });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Email Verifier running at http://localhost:${PORT}`);
    console.log(`📧 Ready to verify emails!`);
});
