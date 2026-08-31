export interface PipelineCounts {
  enquiry: number;
  quoted: number;
  booked: number;
  templated: number;
  fabricated: number;
  installed: number;
  complete: number;
}

export interface QuoteFunnel {
  draft: number;
  approved: number;
  handed_off: number;
}

export interface QuotedValue {
  quoted_value: number;
  approved_quoted_value: number;
}

export interface SiteVisitCounts {
  scheduled: number;
  completed: number;
  cancelled: number;
}

export interface FollowUpAttention {
  unread_follow_ups: number;
}

export interface CommandCentreStats {
  customers: number;
  pipeline: PipelineCounts;
  quotes: QuoteFunnel;
  value: QuotedValue;
  site_visits: SiteVisitCounts;
  follow_up: FollowUpAttention;
}
