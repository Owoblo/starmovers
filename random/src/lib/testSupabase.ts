import { supabase } from './supabase';

// Test Supabase connection and explore database structure
async function testSupabaseConnection() {
  console.log('Testing Supabase connection...');
  
  try {
    // Test basic connection
    const { data, error } = await supabase
      .from('listings')
      .select('*')
      .limit(1);
    
    if (error) {
      console.error('Error connecting to listings table:', error);
      
      // Try sold_listings table
      const { data: soldData, error: soldError } = await supabase
        .from('sold_listings')
        .select('*')
        .limit(1);
      
      if (soldError) {
        console.error('Error connecting to sold_listings table:', soldError);
      } else {
        console.log('Successfully connected to sold_listings table');
        console.log('Sample sold listing:', soldData);
      }
    } else {
      console.log('Successfully connected to listings table');
      console.log('Sample listing:', data);
    }
    
    // Try to get table schema info
    const { data: schemaData, error: schemaError } = await supabase
      .rpc('get_table_schema', { table_name: 'listings' });
    
    if (schemaError) {
      console.log('Could not get schema info (this is normal)');
    } else {
      console.log('Schema info:', schemaData);
    }
    
  } catch (err) {
    console.error('Connection test failed:', err);
  }
}

// Export for use in React component
export { testSupabaseConnection };
