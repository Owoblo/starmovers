# 📋 Project History Setup Guide

This guide will help you set up the database table needed for storing user projects/quotes.

## 🗄️ Database Setup

You need to create a `projects` table in your Supabase database. Here's how:

### Option 1: Using Supabase Dashboard (Recommended)

1. Go to your Supabase Dashboard: https://supabase.com/dashboard
2. Select your project
3. Go to **SQL Editor**
4. Run this SQL query:

```sql
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

-- Create an index for faster queries
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- Create RLS policies
-- Policy: Users can only see their own projects
CREATE POLICY "Users can view their own projects"
  ON projects
  FOR SELECT
  USING (auth.uid() = user_id);

-- Policy: Users can insert their own projects
CREATE POLICY "Users can insert their own projects"
  ON projects
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Policy: Users can update their own projects
CREATE POLICY "Users can update their own projects"
  ON projects
  FOR UPDATE
  USING (auth.uid() = user_id);

-- Policy: Users can delete their own projects
CREATE POLICY "Users can delete their own projects"
  ON projects
  FOR DELETE
  USING (auth.uid() = user_id);
```

### Option 2: Using Supabase CLI

If you have Supabase CLI installed:

```bash
supabase migration new create_projects_table
```

Then add the SQL from Option 1 to the migration file and run:

```bash
supabase db push
```

## ✅ Verification

After creating the table, verify it works:

1. The table should appear in your Supabase **Table Editor**
2. Try saving a project from the dashboard
3. Check that projects appear in the project history

## 🎯 Features Enabled

Once set up, users will be able to:
- ✅ Save their quotes/projects
- ✅ View all past projects in a list
- ✅ Load and reopen previous projects
- ✅ Update existing projects
- ✅ Delete projects they no longer need
- ✅ All data is securely stored per user account

## 🔒 Security

- Row Level Security (RLS) ensures users can only access their own projects
- Projects are automatically associated with the logged-in user
- All operations require authentication




