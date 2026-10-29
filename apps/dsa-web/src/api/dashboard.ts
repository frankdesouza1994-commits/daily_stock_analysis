import apiClient from './index';
import type { CustomDashboard, DashboardWidget, DashboardWidgetInput } from '../types/dashboard';

const WEB_ACTOR = 'web';

type DashboardResponse = {
  slug: string;
  title: string;
  description: string;
  widgets: DashboardWidget[];
  version: number;
  updated_by?: string | null;
  updated_at?: string | null;
};

// Widget data keys are passed through untouched so they match what openclaw writes.
function toDashboard(data: DashboardResponse): CustomDashboard {
  return {
    slug: data.slug,
    title: data.title,
    description: data.description,
    widgets: data.widgets,
    version: data.version,
    updatedBy: data.updated_by,
    updatedAt: data.updated_at,
  };
}

export const dashboardApi = {
  async get(): Promise<CustomDashboard> {
    const response = await apiClient.get<DashboardResponse>('/api/v1/dashboard');
    return toDashboard(response.data);
  },

  async updateMeta(
    payload: { title?: string; description?: string },
    expectedVersion: number,
  ): Promise<CustomDashboard> {
    const response = await apiClient.patch<DashboardResponse>('/api/v1/dashboard', {
      ...payload,
      expected_version: expectedVersion,
      actor: WEB_ACTOR,
    });
    return toDashboard(response.data);
  },

  async addWidget(widget: DashboardWidgetInput, expectedVersion: number): Promise<CustomDashboard> {
    const response = await apiClient.post<DashboardResponse>('/api/v1/dashboard/widgets', {
      ...widget,
      expected_version: expectedVersion,
      actor: WEB_ACTOR,
    });
    return toDashboard(response.data);
  },

  async updateWidget(
    widgetId: string,
    patch: { title?: string; width?: DashboardWidget['width']; data?: Record<string, unknown>; position?: number },
    expectedVersion: number,
  ): Promise<CustomDashboard> {
    const response = await apiClient.patch<DashboardResponse>(
      `/api/v1/dashboard/widgets/${encodeURIComponent(widgetId)}`,
      { ...patch, expected_version: expectedVersion, actor: WEB_ACTOR },
    );
    return toDashboard(response.data);
  },

  async deleteWidget(widgetId: string, expectedVersion: number): Promise<CustomDashboard> {
    const response = await apiClient.delete<DashboardResponse>(
      `/api/v1/dashboard/widgets/${encodeURIComponent(widgetId)}`,
      { params: { expected_version: expectedVersion, actor: WEB_ACTOR } },
    );
    return toDashboard(response.data);
  },
};
