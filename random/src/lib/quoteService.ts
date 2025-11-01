/**
 * Quote Service for managing quotes in Supabase
 */

import { supabase } from './supabase';

export interface QuoteData {
  id?: string;
  customerName: string;
  customerEmail: string;
  customerPhone: string;
  moveDate: string;
  originAddress: string;
  destinationAddress: string;
  detections: any[];
  estimate: any;
  upsells: any[];
  totalAmount: number;
  photos?: any[];
  status?: 'pending' | 'accepted' | 'declined';
  questions?: string[];
}

export class QuoteService {
  static async createQuote(quoteData: QuoteData): Promise<QuoteData> {
    const { data, error } = await supabase
      .from('quotes')
      .insert({
        customer_name: quoteData.customerName,
        customer_email: quoteData.customerEmail,
        customer_phone: quoteData.customerPhone,
        move_date: quoteData.moveDate,
        origin_address: quoteData.originAddress,
        destination_address: quoteData.destinationAddress,
        detections: quoteData.detections,
        estimate: quoteData.estimate,
        upsells: quoteData.upsells,
        total_amount: quoteData.totalAmount,
        photos: quoteData.photos || [],
        status: quoteData.status || 'pending',
        questions: quoteData.questions || []
      })
      .select()
      .single();

    if (error) throw error;

    return {
      id: data.id,
      customerName: data.customer_name,
      customerEmail: data.customer_email,
      customerPhone: data.customer_phone,
      moveDate: data.move_date,
      originAddress: data.origin_address,
      destinationAddress: data.destination_address,
      detections: data.detections,
      estimate: data.estimate,
      upsells: data.upsells,
      totalAmount: data.total_amount,
      photos: data.photos,
      status: data.status,
      questions: data.questions
    };
  }

  static async getQuote(quoteId: string): Promise<QuoteData | null> {
    const { data, error } = await supabase
      .from('quotes')
      .select('*')
      .eq('id', quoteId)
      .single();

    if (error) {
      if (error.code === 'PGRST116') return null; // Not found
      throw error;
    }

    return {
      id: data.id,
      customerName: data.customer_name,
      customerEmail: data.customer_email,
      customerPhone: data.customer_phone,
      moveDate: data.move_date,
      originAddress: data.origin_address,
      destinationAddress: data.destination_address,
      detections: data.detections,
      estimate: data.estimate,
      upsells: data.upsells,
      totalAmount: data.total_amount,
      photos: data.photos,
      status: data.status,
      questions: data.questions
    };
  }

  static async updateQuoteStatus(quoteId: string, status: 'pending' | 'accepted' | 'declined'): Promise<void> {
    const { error } = await supabase
      .from('quotes')
      .update({ status })
      .eq('id', quoteId);

    if (error) throw error;
  }

  static async getUserQuotes(): Promise<QuoteData[]> {
    const { data, error } = await supabase
      .from('quotes')
      .select('*')
      .order('created_at', { ascending: false });

    if (error) throw error;

    return data.map(quote => ({
      id: quote.id,
      customerName: quote.customer_name,
      customerEmail: quote.customer_email,
      customerPhone: quote.customer_phone,
      moveDate: quote.move_date,
      originAddress: quote.origin_address,
      destinationAddress: quote.destination_address,
      detections: quote.detections,
      estimate: quote.estimate,
      upsells: quote.upsells,
      totalAmount: quote.total_amount,
      photos: quote.photos,
      status: quote.status,
      questions: quote.questions
    }));
  }
}



