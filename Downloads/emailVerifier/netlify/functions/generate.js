const {
    parseNameDomainInput,
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
        const { input, level = 'dns' } = JSON.parse(event.body);

        if (!input || !input.trim()) {
            return {
                statusCode: 200,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ results: [] })
            };
        }

        // Parse the name-domain input
        const people = parseNameDomainInput(input);

        if (people.length === 0) {
            return {
                statusCode: 200,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    results: [],
                    error: 'Invalid format. Use: FirstName, LastName, Domain (one per line)'
                })
            };
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

        return {
            statusCode: 200,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ results: allResults })
        };
    } catch (error) {
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
