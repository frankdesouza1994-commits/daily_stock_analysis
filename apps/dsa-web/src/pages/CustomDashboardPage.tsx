import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Bot, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { dashboardApi } from '../api/dashboard';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Button,
  Card,
  ConfirmDialog,
  Drawer,
  EmptyState,
  Input,
  PageHeader,
  Select,
} from '../components/common';
import { ReportMarkdownBody } from '../components/report/ReportMarkdownBody';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { UiTextKey } from '../i18n/uiText';
import type {
  CustomDashboard,
  DashboardMetricTone,
  DashboardWidget,
  DashboardWidgetType,
  DashboardWidgetWidth,
  MetricWidgetData,
  StockListItem,
  StockListWidgetData,
} from '../types/dashboard';
import { cn } from '../utils/cn';

// openclaw edits arrive through the REST API; poll so they show up without a manual reload.
const POLL_INTERVAL_MS = 15000;

const WIDTH_CLASS: Record<DashboardWidgetWidth, string> = {
  sm: 'xl:col-span-1',
  md: 'md:col-span-2 xl:col-span-2',
  lg: 'md:col-span-2 xl:col-span-3',
  full: 'col-span-full',
};

const TONE_CLASS: Record<DashboardMetricTone, string> = {
  default: 'text-foreground',
  primary: 'text-cyan',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

const TYPE_LABEL_KEYS: Record<DashboardWidgetType, UiTextKey> = {
  markdown: 'customDashboard.type.markdown',
  metric: 'customDashboard.type.metric',
  stock_list: 'customDashboard.type.stockList',
};

const WIDTH_LABEL_KEYS: Record<DashboardWidgetWidth, UiTextKey> = {
  sm: 'customDashboard.width.sm',
  md: 'customDashboard.width.md',
  lg: 'customDashboard.width.lg',
  full: 'customDashboard.width.full',
};

const TONE_LABEL_KEYS: Record<DashboardMetricTone, UiTextKey> = {
  default: 'customDashboard.tone.default',
  primary: 'customDashboard.tone.primary',
  success: 'customDashboard.tone.success',
  warning: 'customDashboard.tone.warning',
  danger: 'customDashboard.tone.danger',
};

type EditorState = {
  widgetId: string | null;
  type: DashboardWidgetType;
  title: string;
  width: DashboardWidgetWidth;
  content: string;
  value: string;
  hint: string;
  tone: DashboardMetricTone;
  items: string;
};

const EMPTY_EDITOR: EditorState = {
  widgetId: null,
  type: 'markdown',
  title: '',
  width: 'md',
  content: '',
  value: '',
  hint: '',
  tone: 'default',
  items: '',
};

const TEXTAREA_CLASS = 'input-surface input-focus-glow w-full rounded-xl border bg-transparent px-4 py-2.5 text-sm transition-all focus:outline-none';

function formatStockItems(items: StockListItem[] = []): string {
  return items
    .map((item) => [item.code, item.name ?? '', item.note ?? ''].join(' | ').replace(/( \| )+$/, ''))
    .join('\n');
}

function parseStockItems(text: string): StockListItem[] {
  return text
    .split('\n')
    .map((line) => line.split('|').map((part) => part.trim()))
    .filter(([code]) => Boolean(code))
    .map(([code, name, note]) => ({
      code,
      ...(name ? { name } : {}),
      ...(note ? { note } : {}),
    }));
}

function editorFromWidget(widget: DashboardWidget): EditorState {
  const metric = widget.data as MetricWidgetData;
  return {
    widgetId: widget.id,
    type: widget.type,
    title: widget.title,
    width: widget.width,
    content: String(widget.data.content ?? ''),
    value: metric.value === undefined ? '' : String(metric.value),
    hint: metric.hint ?? '',
    tone: metric.tone ?? 'default',
    items: formatStockItems((widget.data as StockListWidgetData).items),
  };
}

function editorData(editor: EditorState): Record<string, unknown> {
  if (editor.type === 'markdown') {
    return { content: editor.content };
  }
  if (editor.type === 'metric') {
    return { value: editor.value, hint: editor.hint || null, tone: editor.tone };
  }
  return { items: parseStockItems(editor.items) };
}

const WidgetBody: React.FC<{ widget: DashboardWidget; emptyText: string }> = ({ widget, emptyText }) => {
  if (widget.type === 'markdown') {
    const content = String(widget.data.content ?? '');
    return content ? <ReportMarkdownBody content={content} /> : <p className="text-sm text-secondary-text">{emptyText}</p>;
  }
  if (widget.type === 'metric') {
    const metric = widget.data as MetricWidgetData;
    return (
      <div>
        <div className={cn('text-3xl font-semibold tracking-tight', TONE_CLASS[metric.tone ?? 'default'])}>
          {metric.value === undefined || metric.value === '' ? '-' : String(metric.value)}
        </div>
        {metric.hint ? <p className="mt-2 text-sm text-secondary-text">{metric.hint}</p> : null}
      </div>
    );
  }
  const items = (widget.data as StockListWidgetData).items ?? [];
  if (!items.length) {
    return <p className="text-sm text-secondary-text">{emptyText}</p>;
  }
  return (
    <ul className="divide-y divide-border/60">
      {items.map((item, index) => (
        <li key={`${item.code}-${index}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 text-sm">
          <span className="font-mono font-semibold text-foreground">{item.code}</span>
          {item.name ? <span className="text-foreground">{item.name}</span> : null}
          {item.note ? <span className="basis-full text-secondary-text sm:basis-auto">{item.note}</span> : null}
        </li>
      ))}
    </ul>
  );
};

const CustomDashboardPage: React.FC = () => {
  const { t, language } = useUiLanguage();
  const [dashboard, setDashboard] = useState<CustomDashboard | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DashboardWidget | null>(null);
  const [metaEditor, setMetaEditor] = useState<{ title: string; description: string } | null>(null);
  const busyRef = useRef(false);
  busyRef.current = saving || editor !== null || metaEditor !== null;

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    try {
      const next = await dashboardApi.get();
      setDashboard((prev) => (prev && prev.version === next.version ? prev : next));
      setError(null);
    } catch (err) {
      if (!silent) {
        setError(getParsedApiError(err));
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    document.title = t('customDashboard.documentTitle');
  }, [t]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (!busyRef.current && document.visibilityState === 'visible') {
        void load(true);
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const runWrite = async (action: (version: number) => Promise<CustomDashboard>): Promise<boolean> => {
    if (!dashboard) {
      return false;
    }
    setSaving(true);
    try {
      setDashboard(await action(dashboard.version));
      setError(null);
      return true;
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed);
      if (parsed.status === 409) {
        // Someone else (usually openclaw) changed the dashboard; show their version.
        await load(true);
      }
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveEditor = async () => {
    if (!editor) {
      return;
    }
    const data = editorData(editor);
    const ok = await runWrite((version) => (
      editor.widgetId
        ? dashboardApi.updateWidget(editor.widgetId, { title: editor.title, width: editor.width, data }, version)
        : dashboardApi.addWidget({ type: editor.type, title: editor.title, width: editor.width, data }, version)
    ));
    if (ok) {
      setEditor(null);
    }
  };

  const saveMeta = async () => {
    if (!metaEditor) {
      return;
    }
    const ok = await runWrite((version) => dashboardApi.updateMeta(metaEditor, version));
    if (ok) {
      setMetaEditor(null);
    }
  };

  const moveWidget = (index: number, offset: number) => {
    const widget = dashboard?.widgets[index];
    if (widget) {
      void runWrite((version) => dashboardApi.updateWidget(widget.id, { position: index + offset }, version));
    }
  };

  const confirmDelete = async () => {
    const widget = pendingDelete;
    if (!widget) {
      return;
    }
    await runWrite((version) => dashboardApi.deleteWidget(widget.id, version));
    setPendingDelete(null);
  };

  const updatedHint = dashboard?.updatedAt
    ? t('customDashboard.updatedBy', {
      actor: dashboard.updatedBy || '-',
      time: new Date(dashboard.updatedAt).toLocaleString(language === 'en' ? 'en-US' : 'zh-CN'),
    })
    : t('customDashboard.neverSaved');
  const apiUrl = `${window.location.origin}/api/v1/dashboard`;
  const widgets = dashboard?.widgets ?? [];

  return (
    <AppPage>
      <PageHeader
        eyebrow={t('customDashboard.eyebrow')}
        title={dashboard?.title ?? t('customDashboard.defaultTitle')}
        description={dashboard?.description || updatedHint}
        actions={(
          <>
            <Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading} aria-label={t('customDashboard.refresh')}>
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={!dashboard}
              onClick={() => dashboard && setMetaEditor({ title: dashboard.title, description: dashboard.description })}
            >
              {t('customDashboard.editInfo')}
            </Button>
            <Button variant="primary" size="sm" disabled={!dashboard} onClick={() => setEditor({ ...EMPTY_EDITOR })}>
              <Plus className="h-4 w-4" />
              {t('customDashboard.addWidget')}
            </Button>
          </>
        )}
      />

      {dashboard?.description ? <p className="mt-3 text-xs text-secondary-text">{updatedHint}</p> : null}

      {error ? (
        <div className="mt-4">
          <ApiErrorAlert error={error} />
        </div>
      ) : null}

      {dashboard && !widgets.length ? (
        <EmptyState
          className="mt-4"
          icon={<Bot className="h-8 w-8" />}
          title={t('customDashboard.emptyTitle')}
          description={t('customDashboard.emptyDescription')}
          action={(
            <Button variant="primary" size="sm" onClick={() => setEditor({ ...EMPTY_EDITOR })}>
              <Plus className="h-4 w-4" />
              {t('customDashboard.addWidget')}
            </Button>
          )}
        />
      ) : null}

      {widgets.length ? (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {widgets.map((widget, index) => (
            <Card key={widget.id} padding="md" className={cn('min-w-0 rounded-2xl', WIDTH_CLASS[widget.width])}>
              <div className="mb-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="truncate text-base font-semibold text-foreground">
                    {widget.title || t(TYPE_LABEL_KEYS[widget.type])}
                  </h2>
                  <span className="text-xs text-secondary-text">{widget.id}</span>
                </div>
                <div className="flex shrink-0 items-center">
                  <Button variant="ghost" size="xsm" disabled={saving || index === 0} onClick={() => moveWidget(index, -1)} aria-label={t('customDashboard.moveUp')}>
                    <ArrowUp className="h-3.5 w-3.5" />
                  </Button>
                  <Button variant="ghost" size="xsm" disabled={saving || index === widgets.length - 1} onClick={() => moveWidget(index, 1)} aria-label={t('customDashboard.moveDown')}>
                    <ArrowDown className="h-3.5 w-3.5" />
                  </Button>
                  <Button variant="ghost" size="xsm" disabled={saving} onClick={() => setEditor(editorFromWidget(widget))} aria-label={t('customDashboard.edit')}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button variant="ghost" size="xsm" disabled={saving} onClick={() => setPendingDelete(widget)} aria-label={t('common.delete')}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              <WidgetBody widget={widget} emptyText={t('customDashboard.widgetEmpty')} />
            </Card>
          ))}
        </div>
      ) : null}

      <Card padding="md" className="mt-4 rounded-2xl" title={t('customDashboard.connectTitle')}>
        <p className="text-sm text-secondary-text">{t('customDashboard.connectDescription')}</p>
        <code className="mt-3 block break-all rounded-lg border border-border/60 px-3 py-2 text-xs text-foreground">{apiUrl}</code>
      </Card>

      <Drawer
        isOpen={editor !== null}
        onClose={() => setEditor(null)}
        title={editor?.widgetId ? t('customDashboard.editWidget') : t('customDashboard.addWidget')}
      >
        {editor ? (
          <div className="flex flex-col gap-4">
            {editor.widgetId ? null : (
              <Select
                label={t('customDashboard.fieldType')}
                value={editor.type}
                onChange={(value) => setEditor({ ...editor, type: value as DashboardWidgetType })}
                options={(Object.keys(TYPE_LABEL_KEYS) as DashboardWidgetType[]).map((type) => ({ value: type, label: t(TYPE_LABEL_KEYS[type]) }))}
              />
            )}
            <Input label={t('customDashboard.fieldTitle')} value={editor.title} maxLength={120} onChange={(e) => setEditor({ ...editor, title: e.target.value })} />
            <Select
              label={t('customDashboard.fieldWidth')}
              value={editor.width}
              onChange={(value) => setEditor({ ...editor, width: value as DashboardWidgetWidth })}
              options={(Object.keys(WIDTH_LABEL_KEYS) as DashboardWidgetWidth[]).map((width) => ({ value: width, label: t(WIDTH_LABEL_KEYS[width]) }))}
            />
            {editor.type === 'markdown' ? (
              <label className="flex flex-col gap-2 text-sm text-foreground">
                {t('customDashboard.fieldContent')}
                <textarea className={TEXTAREA_CLASS} rows={10} value={editor.content} onChange={(e) => setEditor({ ...editor, content: e.target.value })} />
              </label>
            ) : null}
            {editor.type === 'metric' ? (
              <>
                <Input label={t('customDashboard.fieldValue')} value={editor.value} onChange={(e) => setEditor({ ...editor, value: e.target.value })} />
                <Input label={t('customDashboard.fieldHint')} value={editor.hint} maxLength={200} onChange={(e) => setEditor({ ...editor, hint: e.target.value })} />
                <Select
                  label={t('customDashboard.fieldTone')}
                  value={editor.tone}
                  onChange={(value) => setEditor({ ...editor, tone: value as DashboardMetricTone })}
                  options={(Object.keys(TONE_LABEL_KEYS) as DashboardMetricTone[]).map((tone) => ({ value: tone, label: t(TONE_LABEL_KEYS[tone]) }))}
                />
              </>
            ) : null}
            {editor.type === 'stock_list' ? (
              <label className="flex flex-col gap-2 text-sm text-foreground">
                {t('customDashboard.fieldItems')}
                <textarea
                  className={cn(TEXTAREA_CLASS, 'font-mono')}
                  rows={8}
                  placeholder={'600519 | 贵州茅台 | hold\nAAPL'}
                  value={editor.items}
                  onChange={(e) => setEditor({ ...editor, items: e.target.value })}
                />
                <span className="text-xs text-secondary-text">{t('customDashboard.fieldItemsHint')}</span>
              </label>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditor(null)}>{t('common.cancel')}</Button>
              <Button variant="primary" isLoading={saving} onClick={() => void saveEditor()}>{t('customDashboard.save')}</Button>
            </div>
          </div>
        ) : null}
      </Drawer>

      <Drawer isOpen={metaEditor !== null} onClose={() => setMetaEditor(null)} title={t('customDashboard.editInfo')}>
        {metaEditor ? (
          <div className="flex flex-col gap-4">
            <Input label={t('customDashboard.fieldTitle')} value={metaEditor.title} maxLength={120} onChange={(e) => setMetaEditor({ ...metaEditor, title: e.target.value })} />
            <label className="flex flex-col gap-2 text-sm text-foreground">
              {t('customDashboard.fieldDescription')}
              <textarea className={TEXTAREA_CLASS} rows={4} maxLength={2000} value={metaEditor.description} onChange={(e) => setMetaEditor({ ...metaEditor, description: e.target.value })} />
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setMetaEditor(null)}>{t('common.cancel')}</Button>
              <Button variant="primary" isLoading={saving} onClick={() => void saveMeta()}>{t('customDashboard.save')}</Button>
            </div>
          </div>
        ) : null}
      </Drawer>

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        title={t('customDashboard.deleteTitle')}
        message={t('customDashboard.deleteMessage', { title: pendingDelete?.title || pendingDelete?.id || '' })}
        confirmText={t('common.delete')}
        cancelText={t('common.cancel')}
        isDanger
        confirmDisabled={saving}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </AppPage>
  );
};

export default CustomDashboardPage;
