import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import CustomDashboardPage from '../CustomDashboardPage';

const { get, patch, post, del } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
}));

vi.mock('../../api/index', () => ({
  default: { get, patch, post, delete: del },
}));

const dashboardResponse = {
  slug: 'default',
  title: 'Morning board',
  description: '',
  version: 3,
  updated_by: 'openclaw',
  updated_at: '2026-10-29T09:30:00',
  widgets: [
    { id: 'pnl', type: 'metric', title: 'Watchlist P&L', width: 'sm', data: { value: '+3.2%', hint: 'vs yesterday', tone: 'success' } },
    { id: 'picks', type: 'stock_list', title: 'Picks', width: 'md', data: { items: [{ code: '600519', name: 'Moutai', note: 'hold' }] } },
    { id: 'notes', type: 'markdown', title: 'Notes', width: 'full', data: { content: '**Buy the dip**' } },
  ],
};

const renderPage = () => render(
  <UiLanguageProvider>
    <CustomDashboardPage />
  </UiLanguageProvider>,
);

describe('CustomDashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockResolvedValue({ data: dashboardResponse });
  });

  it('renders every widget type written through the API', async () => {
    renderPage();

    expect(await screen.findByText('+3.2%')).toBeInTheDocument();
    expect(screen.getByText('Morning board')).toBeInTheDocument();
    expect(screen.getByText('vs yesterday')).toBeInTheDocument();
    expect(screen.getByText('600519')).toBeInTheDocument();
    expect(screen.getByText('Moutai')).toBeInTheDocument();
    expect(screen.getByText('Buy the dip')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/api/v1/dashboard');
  });

  it('moves a widget with the current version and web actor', async () => {
    patch.mockResolvedValue({
      data: { ...dashboardResponse, version: 4, widgets: [dashboardResponse.widgets[1], dashboardResponse.widgets[0], dashboardResponse.widgets[2]] },
    });
    renderPage();
    await screen.findByText('+3.2%');

    fireEvent.click(screen.getAllByRole('button', { name: 'Move down' })[0]);

    await waitFor(() => expect(patch).toHaveBeenCalledWith(
      '/api/v1/dashboard/widgets/pnl',
      { position: 1, expected_version: 3, actor: 'web' },
    ));
  });
});
