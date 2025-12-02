const {
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
        const { emails, level = 'syntax' } = JSON.parse(event.body);

        if (!emails || !emails.trim()) {
            return {
                statusCode: 200,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ results: [] })
            };
        }

        // Parse emails from text
        const emailList = emails
            .split(/\n|,/)
            .map(email => email.trim())
            .filter(email => email.length > 0 && email.includes('@'));

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

            results.push(result);
        }

        return {
            statusCode: 200,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ results })
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
