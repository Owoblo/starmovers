import { supabase } from './supabase';
import { QuotePayload, Detection } from '../types';

export interface Project {
  id: string;
  user_id: string;
  address: string;
  detections: Detection[];
  estimate: QuotePayload['estimate'];
  created_at: string;
  updated_at: string;
  notes?: string;
  project_name?: string;
}

export class ProjectService {
  // Save a project/quote
  static async saveProject(
    address: string,
    detections: Detection[],
    estimate: QuotePayload['estimate'],
    projectName?: string,
    notes?: string
  ): Promise<Project> {
    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
      throw new Error('User must be logged in to save projects');
    }

    const projectData = {
      user_id: user.id,
      address,
      detections,
      estimate,
      project_name: projectName || address || 'Untitled Project',
      notes: notes || null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    const { data, error } = await supabase
      .from('projects')
      .insert([projectData])
      .select()
      .single();

    if (error) {
      console.error('Error saving project:', error);
      throw new Error(`Failed to save project: ${error.message}`);
    }

    return data;
  }

  // Get all projects for the current user
  static async getUserProjects(): Promise<Project[]> {
    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
      throw new Error('User must be logged in to view projects');
    }

    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .eq('user_id', user.id)
      .order('updated_at', { ascending: false });

    if (error) {
      console.error('Error loading projects:', error);
      throw new Error(`Failed to load projects: ${error.message}`);
    }

    return data || [];
  }

  // Get a single project by ID
  static async getProject(projectId: string): Promise<Project> {
    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
      throw new Error('User must be logged in to view projects');
    }

    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .eq('id', projectId)
      .eq('user_id', user.id)
      .single();

    if (error) {
      console.error('Error loading project:', error);
      throw new Error(`Failed to load project: ${error.message}`);
    }

    if (!data) {
      throw new Error('Project not found');
    }

    return data;
  }

  // Update an existing project
  static async updateProject(
    projectId: string,
    address: string,
    detections: Detection[],
    estimate: QuotePayload['estimate'],
    projectName?: string,
    notes?: string
  ): Promise<Project> {
    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
      throw new Error('User must be logged in to update projects');
    }

    const { data, error } = await supabase
      .from('projects')
      .update({
        address,
        detections,
        estimate,
        project_name: projectName || address || 'Untitled Project',
        notes: notes || null,
        updated_at: new Date().toISOString(),
      })
      .eq('id', projectId)
      .eq('user_id', user.id)
      .select()
      .single();

    if (error) {
      console.error('Error updating project:', error);
      throw new Error(`Failed to update project: ${error.message}`);
    }

    return data;
  }

  // Delete a project
  static async deleteProject(projectId: string): Promise<void> {
    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
      throw new Error('User must be logged in to delete projects');
    }

    const { error } = await supabase
      .from('projects')
      .delete()
      .eq('id', projectId)
      .eq('user_id', user.id);

    if (error) {
      console.error('Error deleting project:', error);
      throw new Error(`Failed to delete project: ${error.message}`);
    }
  }
}




