const {
    aiSmartParse,
    intelligentDomainLookup,
    aiRoleLookup,
    generateEmailVariations,
    verifyEmailSyntax,
    verifyEmailDNS,
    verifyEmailSMTP
} = require('./utils');

exports.handler = async (event) => {
    // Handle CORS preflight
    if (event.httpMethod === 'OPTIONS') {
        return {
            statusCode: 200,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            body: ''
        };
    }

    // Only allow POST
    if (event.httpMethod !== 'POST') {
        return {
            statusCode: 405,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ error: 'Method not allowed' })
        };
    }

    try {
        const { input, level = 'dns', apiKey } = JSON.parse(event.body);

        if (!input || !input.trim()) {
            return {
                statusCode: 200,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ results: [], error: 'No input provided' })
            };
        }

        if (!apiKey) {
            return {
                statusCode: 200,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ results: [], error: 'OpenAI API key required for Smart Lookup' })
            };
        }

        // Step 1: AI parses the input
        const people = await aiSmartParse(input, apiKey);

        if (people.length === 0) {
            return {
                statusCode: 200,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    results: [],
                    error: 'Could not extract any contact information. Try: "John Doe at Tesla" or "Find CEO of SpaceX"'
                })
            };
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

            // If role mentioned but no name
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
                continue;
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

        return {
            statusCode: 200,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                results: allResults,
                aiInsights: aiInsights,
                peopleFound: people.length
            })
        };
    } catch (error) {
        console.error('Smart Lookup Error:', error);
        return {
            statusCode: 500,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ error: error.message })
        };
    }
};
