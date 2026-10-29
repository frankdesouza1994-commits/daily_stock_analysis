export type DashboardWidgetType = 'markdown' | 'metric' | 'stock_list';
export type DashboardWidgetWidth = 'sm' | 'md' | 'lg' | 'full';
export type DashboardMetricTone = 'default' | 'primary' | 'success' | 'warning' | 'danger';

export type MarkdownWidgetData = { content?: string };
export type MetricWidgetData = { value?: string | number; hint?: string; tone?: DashboardMetricTone };
export type StockListItem = { code: string; name?: string; note?: string };
export type StockListWidgetData = { items?: StockListItem[] };

export type DashboardWidget = {
  id: string;
  type: DashboardWidgetType;
  title: string;
  width: DashboardWidgetWidth;
  data: Record<string, unknown>;
};

export type DashboardWidgetInput = Omit<DashboardWidget, 'id'> & { id?: string };

export type CustomDashboard = {
  slug: string;
  title: string;
  description: string;
  widgets: DashboardWidget[];
  version: number;
  updatedBy?: string | null;
  updatedAt?: string | null;
};
