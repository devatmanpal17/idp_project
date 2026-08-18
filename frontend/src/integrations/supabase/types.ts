export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.15";
  };
  public: {
    Tables: {
      activity_log: {
        Row: {
          course_id: string | null;
          created_at: string;
          event_type: string;
          id: string;
          metadata: Json;
        };
        Insert: {
          course_id?: string | null;
          created_at?: string;
          event_type: string;
          id?: string;
          metadata?: Json;
        };
        Update: {
          course_id?: string | null;
          created_at?: string;
          event_type?: string;
          id?: string;
          metadata?: Json;
        };
        Relationships: [
          {
            foreignKeyName: "activity_log_course_id_fkey";
            columns: ["course_id"];
            isOneToOne: false;
            referencedRelation: "courses";
            referencedColumns: ["id"];
          },
        ];
      };
      courses: {
        Row: {
          completion_pct: number;
          created_at: string;
          id: string;
          overall_mastery: number;
          platform: string;
          thumbnail_url: string | null;
          title: string;
        };
        Insert: {
          completion_pct?: number;
          created_at?: string;
          id?: string;
          overall_mastery?: number;
          platform: string;
          thumbnail_url?: string | null;
          title: string;
        };
        Update: {
          completion_pct?: number;
          created_at?: string;
          id?: string;
          overall_mastery?: number;
          platform?: string;
          thumbnail_url?: string | null;
          title?: string;
        };
        Relationships: [];
      };
      quizzes: {
        Row: {
          completed_at: string;
          course_id: string | null;
          id: string;
          question_type: string;
          questions: Json;
          score: number;
          topic_id: string | null;
        };
        Insert: {
          completed_at?: string;
          course_id?: string | null;
          id?: string;
          question_type: string;
          questions?: Json;
          score?: number;
          topic_id?: string | null;
        };
        Update: {
          completed_at?: string;
          course_id?: string | null;
          id?: string;
          question_type?: string;
          questions?: Json;
          score?: number;
          topic_id?: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "quizzes_course_id_fkey";
            columns: ["course_id"];
            isOneToOne: false;
            referencedRelation: "courses";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "quizzes_topic_id_fkey";
            columns: ["topic_id"];
            isOneToOne: false;
            referencedRelation: "topics";
            referencedColumns: ["id"];
          },
        ];
      };
      recommendations: {
        Row: {
          created_at: string;
          estimated_minutes: number;
          id: string;
          impact_score: number;
          reasoning: string;
          topic_id: string | null;
          type: string;
        };
        Insert: {
          created_at?: string;
          estimated_minutes?: number;
          id?: string;
          impact_score?: number;
          reasoning?: string;
          topic_id?: string | null;
          type: string;
        };
        Update: {
          created_at?: string;
          estimated_minutes?: number;
          id?: string;
          impact_score?: number;
          reasoning?: string;
          topic_id?: string | null;
          type?: string;
        };
        Relationships: [
          {
            foreignKeyName: "recommendations_topic_id_fkey";
            columns: ["topic_id"];
            isOneToOne: false;
            referencedRelation: "topics";
            referencedColumns: ["id"];
          },
        ];
      };
      study_events: {
        Row: {
          created_at: string;
          event_type: string;
          id: string;
          scheduled_at: string;
          status: string;
          topic_id: string | null;
        };
        Insert: {
          created_at?: string;
          event_type: string;
          id?: string;
          scheduled_at: string;
          status?: string;
          topic_id?: string | null;
        };
        Update: {
          created_at?: string;
          event_type?: string;
          id?: string;
          scheduled_at?: string;
          status?: string;
          topic_id?: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "study_events_topic_id_fkey";
            columns: ["topic_id"];
            isOneToOne: false;
            referencedRelation: "topics";
            referencedColumns: ["id"];
          },
        ];
      };
      topics: {
        Row: {
          course_id: string;
          id: string;
          last_updated: string;
          mastery_score: number;
          minutes_on_section: number;
          quiz_perf_pct: number;
          revisit_frequency_pct: number;
          revisits: number;
          time_on_section_pct: number;
          title: string;
          trend_delta: number;
        };
        Insert: {
          course_id: string;
          id?: string;
          last_updated?: string;
          mastery_score?: number;
          minutes_on_section?: number;
          quiz_perf_pct?: number;
          revisit_frequency_pct?: number;
          revisits?: number;
          time_on_section_pct?: number;
          title: string;
          trend_delta?: number;
        };
        Update: {
          course_id?: string;
          id?: string;
          last_updated?: string;
          mastery_score?: number;
          minutes_on_section?: number;
          quiz_perf_pct?: number;
          revisit_frequency_pct?: number;
          revisits?: number;
          time_on_section_pct?: number;
          title?: string;
          trend_delta?: number;
        };
        Relationships: [
          {
            foreignKeyName: "topics_course_id_fkey";
            columns: ["course_id"];
            isOneToOne: false;
            referencedRelation: "courses";
            referencedColumns: ["id"];
          },
        ];
      };
    };
    Views: {
      [_ in never]: never;
    };
    Functions: {
      [_ in never]: never;
    };
    Enums: {
      [_ in never]: never;
    };
    CompositeTypes: {
      [_ in never]: never;
    };
  };
};

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">;

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">];

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R;
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R;
      }
      ? R
      : never
    : never;

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I;
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I;
      }
      ? I
      : never
    : never;

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U;
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U;
      }
      ? U
      : never
    : never;

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    keyof DefaultSchema["Enums"] | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never;

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    keyof DefaultSchema["CompositeTypes"] | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never;

export const Constants = {
  public: {
    Enums: {},
  },
} as const;
