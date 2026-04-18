export interface LineItem {
  description: string;
  itemCode: string;
  upc: string;
  cases: number;
  quantity: number;
  unitPrice: number;
  netAmount: number;
}

export interface Invoice {
  vendor: string;
  vendorCode: string;
  invoiceNumber: string;
  /** YYYY-MM-DD or null when unknown. */
  date: string | null;
  items: LineItem[];
  taxes: number;
  total: number;
}

export interface ConvertResponse {
  invoice: Invoice;
  ediText: string;
  ediFilename: string;
  warnings: string[];
}
