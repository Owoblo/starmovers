/**
 * Setup script to create the projects table in Supabase
 * 
 * Usage:
 * 1. Make sure you have REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY in your .env
 * 2. Get your Supabase service role key from your Supabase dashboard (Settings > API > service_role key)
 * 3. Run: SUPABASE_SERVICE_KEY=your_service_key node setup-projects-table.js
 */

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL || process.env.SUPABASE_URL;
const serviceKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl) {
  console.error('❌ Error: SUPABASE_URL or REACT_APP_SUPABASE_URL not found in environment');
  console.log('Please set it in your .env file or as an environment variable');
  process.exit(1);
}

if (!serviceKey) {
  console.error('❌ Error: SUPABASE_SERVICE_KEY not found');
  console.log('\nTo get your service key:');
  console.log('1. Go to https://supabase.com/dashboard');
  console.log('2. Select your project');
  console.log('3. Go to Settings > API');
  console.log('4. Copy the "service_role" key (NOT the anon key)');
  console.log('\nThen run:');
  console.log('SUPABASE_SERVICE_KEY=your_service_key node setup-projects-table.js');
  process.exit(1);
}

const sql = `
-- Create the projects table
CREATE TABLE IF NOT EXISTS projects (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  address TEXT NOT NULL,
  project_name TEXT,
  detections JSONB NOT NULL,
  estimate JSONB NOT NULL,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (for re-running)
DROP POLICY IF EXISTS "Users can view their own projects" ON projects;
DROP POLICY IF EXISTS "Users can insert their own projects" ON projects;
DROP POLICY IF EXISTS "Users can update their own projects" ON projects;
DROP POLICY IF EXISTS "Users can delete their own projects" ON projects;

-- Create RLS policies
CREATE POLICY "Users can view their own projects"
  ON projects
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own projects"
  ON projects
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own projects"
  ON projects
  FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own projects"
  ON projects
  FOR DELETE
  USING (auth.uid() = user_id);
`;

async function setupTable() {
  try {
    console.log('🚀 Setting up projects table...\n');
    
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/exec_sql`, {
      method: 'POST',
      headers: {
        'apikey': serviceKey,
        'Authorization': `Bearer ${serviceKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ sql }),
    });

    if (!response.ok) {
      // Try alternative method using Management API
      console.log('Trying alternative method...\n');
      
      // Alternative: Use SQL Editor API if available
      const altResponse = await fetch(`${supabaseUrl}/rest/v1/`, {
        method: 'POST',
        headers: {
          'apikey': serviceKey,
          'Authorization': `Bearer ${serviceKey}`,
          'Content-Type': 'application/json',
        },
      });
      
      throw new Error(`Failed to create table. Status: ${response.status}`);
    }

    const result = await response.json();
    console.log('✅ Projects table created successfully!');
    console.log('\nYou can now save and load projects in the dashboard.');
    
  } catch (error) {
    console.error('❌ Error setting up table:', error.message);
    console.log('\n💡 Alternative: Run the SQL manually in Supabase Dashboard:');
    console.log('1. Go to https://supabase.com/dashboard');
    console.log('2. Select your project');
    console.log('3. Go to SQL Editor');
    console.log('4. Copy the SQL from PROJECT_HISTORY_SETUP.md');
    console.log('5. Run it');
  }
}

setupTable();




