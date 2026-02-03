export interface Book {
  asin?: string;
  title: string;
  subtitle?: string;
  authors: string[];
  cover_image?: string;
  runtime_length_hrs?: number;
  downloaded?: boolean;
  already_requested?: boolean;
}

export interface BookCardProps {
  book: Book;
  baseUrl: string;
  autoStartDownload?: boolean;
  userCanDownload?: boolean;
}
