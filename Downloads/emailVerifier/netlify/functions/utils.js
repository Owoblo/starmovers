const dns = require('dns');
const net = require('net');
const { promisify } = require('util');
const validator = require('email-validator');
const OpenAI = require('openai');
const axios = require('axios');

// Promisify DNS functions
const resolveMx = promisify(dns.resolveMx);

// Cache for domain lookups and AI responses
const domainCache = new Map();
const aiResponseCache = new Map();

// OpenAI client
function getOpenAIClient(apiKey) {
    return new OpenAI({ apiKey });
}

// AI-powered smart parser
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

// Search API fallback
async function searchDomain(companyName) {
    const cacheKey = `search_${companyName.toLowerCase()}`;
    if (domainCache.has(cacheKey)) {
        return domainCache.get(cacheKey);
    }

    try {
        const response = await axios.get(`https://api.duckduckgo.com/?q=${encodeURIComponent(companyName + ' official website')}&format=json`);

        if (response.data.AbstractURL) {
            const url = new URL(response.data.AbstractURL);
            const domain = url.hostname.replace(/^www\./i, '');
            domainCache.set(cacheKey, domain);
            return domain;
        }

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

// Hybrid domain lookup
async function intelligentDomainLookup(companyName, apiKey) {
    let domain = await aiLookupDomain(companyName, apiKey);

    if (domain && domain.includes('.') && domain.split('.').length >= 2) {
        return domain;
    }

    domain = await searchDomain(companyName);
    return domain || `${companyName.toLowerCase().replace(/\s+/g, '')}.com`;
}

// Role-based person lookup
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

// Email pattern generation
function generateEmailVariations(firstName, lastName, domain) {
    const first = firstName.toLowerCase().trim();
    const last = lastName.toLowerCase().trim();
    const dom = domain.toLowerCase().trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0];

    const variations = [
        `${first}@${dom}`,
        `${last}@${dom}`,
        `${first}.${last}@${dom}`,
        `${first}${last}@${dom}`,
        `${first[0]}.${last}@${dom}`,
        `${first}_${last}@${dom}`,
        `${first[0]}${last}@${dom}`,
        `${last}.${first}@${dom}`,
    ];

    return [...new Set(variations)];
}

// Parse name-domain input
function parseNameDomainInput(input) {
    const lines = input.trim().split('\n').filter(line => line.trim());
    const parsed = [];

    const domainRegex = /(?:https?:\/\/)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)/g;

    const cleanText = (text) => {
        return text
            .replace(/[|]/g, ' ')
            .replace(/\t/g, ' ')
            .replace(/\s+/g, ' ')
            .replace(/[""'']/g, '')
            .trim();
    };

    for (const line of lines) {
        const cleaned = cleanText(line);

        if (!cleaned || /^(name|first|last|email|domain|company|website)/i.test(cleaned)) {
            continue;
        }

        let firstName = '';
        let lastName = '';
        let domain = '';

        const domainMatches = [...cleaned.matchAll(domainRegex)];
        if (domainMatches.length > 0) {
            domain = domainMatches[0][1];
        }

        let nameText = cleaned;
        if (domain) {
            nameText = nameText.replace(domainRegex, '').trim();
        }

        nameText = nameText
            .replace(/\b(company|corp|inc|ltd|llc|at|from|contact)\b/gi, '')
            .trim();

        if (nameText.includes(',')) {
            const parts = nameText.split(',').map(p => p.trim()).filter(p => p);
            if (parts.length >= 2) {
                if (parts[0] === parts[0].toUpperCase() && parts[0].length > 1) {
                    lastName = parts[0];
                    firstName = parts[1].split(/\s+/)[0];
                } else {
                    firstName = parts[0].split(/\s+/)[0];
                    lastName = parts[1].split(/\s+/)[0];
                }
            }
        } else {
            const words = nameText.split(/\s+/).filter(w => w && w.length > 1);

            if (words.length >= 2) {
                firstName = words[0];
                lastName = words[words.length - 1];
            } else if (words.length === 1) {
                firstName = words[0];
                lastName = words[0];
            }
        }

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
    if (!email || typeof email !== 'string') {
        return {
            valid: false,
            message: 'Email is empty or invalid type'
        };
    }

    const atCount = (email.match(/@/g) || []).length;
    if (atCount !== 1) {
        return {
            valid: false,
            message: atCount === 0 ? 'Missing @ symbol' : 'Too many @ symbols'
        };
    }

    const parts = email.split('@');
    const localPart = parts[0];
    const domain = parts[1];

    if (!localPart || localPart.length === 0) {
        return {
            valid: false,
            message: 'Local part (before @) is empty'
        };
    }

    if (!domain || domain.length === 0) {
        return {
            valid: false,
            message: 'Domain part (after @) is empty'
        };
    }

    if (!domain.includes('.')) {
        return {
            valid: false,
            message: 'Domain must contain at least one dot'
        };
    }

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
        if (!email.includes('@')) {
            return {
                valid: false,
                message: 'Email missing @ symbol'
            };
        }

        const domain = email.split('@')[1];

        if (!domain || domain.length === 0) {
            return {
                valid: false,
                message: 'Invalid domain'
            };
        }

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

        mxRecords.sort((a, b) => a.priority - b.priority);
        const mxHost = mxRecords[0].exchange;

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

        const timeout = setTimeout(() => {
            if (!hasResolved) {
                hasResolved = true;
                socket.destroy();
                resolve({ valid: null, message: 'Connection timed out (Port 25 likely blocked)' });
            }
        }, 5000);

        socket.connect(25, mxHost);
        socket.setEncoding('utf8');

        socket.on('connect', () => {});

        socket.on('data', (data) => {
            if (hasResolved) return;

            const response = data.toString();
            const code = parseInt(response.substring(0, 3));

            try {
                if (step === 0 && code === 220) {
                    socket.write(`HELO ${mxHost}\r\n`);
                    step = 1;
                } else if (step === 1 && code === 250) {
                    socket.write('MAIL FROM:<test@example.com>\r\n');
                    step = 2;
                } else if (step === 2 && code === 250) {
                    socket.write(`RCPT TO:<${email}>\r\n`);
                    step = 3;
                } else if (step === 3) {
                    hasResolved = true;
                    clearTimeout(timeout);
                    socket.write('QUIT\r\n');
                    socket.end();

                    if (code === 250) {
                        resolve({ valid: true, message: 'Exists (Server accepted)' });
                    } else if (code === 550) {
                        resolve({ valid: false, message: 'Does not exist (Server rejected)' });
                    } else {
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

module.exports = {
    aiSmartParse,
    intelligentDomainLookup,
    aiRoleLookup,
    generateEmailVariations,
    parseNameDomainInput,
    verifyEmailSyntax,
    verifyEmailDNS,
    verifyEmailSMTP
};
