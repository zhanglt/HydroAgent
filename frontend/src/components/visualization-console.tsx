'use client'

import dynamic from 'next/dynamic'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Droplets, Gauge, GitBranch, RadioTower, Waves } from 'lucide-react'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet } from '@/lib/api-client'
import { AnalyticsOverview, VisualizationModelPlan, VisualizationSummary } from '@/lib/types'
import { formatNumber1 } from '@/lib/format'
import { formatDateTime } from '@/lib/utils'
import { labelFor, STATUS_LABELS } from '@/lib/labels'

const Charts = dynamic(() => import('@/components/visualization-charts'), {
  loading: () => <div role="status" className="visualization-empty min-h-80">正在加载图表区域…</div>,
})
const emptyPlans: VisualizationModelPlan[] = []

export function VisualizationConsole({ canReadSummary, canReadModels }: { canReadSummary: boolean; canReadModels: boolean }) {
  const summaryQuery = useQuery({
    queryKey: ['visualization', 'summary'],
    queryFn: () => apiGet<VisualizationSummary>('/api/visualization?section=summary'),
    enabled: canReadSummary,
    staleTime: 5_000,
    refetchInterval: 5_000,
  })
  const analyticsQuery = useQuery({
    queryKey: ['visualization', 'analytics'],
    queryFn: () => apiGet<AnalyticsOverview>('/api/analytics/overview?range=7d'),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })
  const modelsQuery = useQuery({
    queryKey: ['visualization', 'models'],
    queryFn: () => apiGet<{ plans: VisualizationModelPlan[] }>('/api/visualization?section=models'),
    enabled: canReadModels,
    staleTime: 30_000,
    refetchInterval: 30_000,
  })
  const summary = summaryQuery.data
  const kpis = [
    { label: '核心状态', value: summary ? 'ONLINE' : '--', detail: summary?.version || '等待有效数据', icon: RadioTower, tone: 'ok' },
    { label: '平均湿度', value: formatNumber1(summary?.average_soil_moisture, '%'), detail: summary?.city || '未知城市', icon: Droplets, tone: 'ok' },
    { label: '待审批', value: summary ? String(summary.pending_plan_count) : '--', detail: summary ? `${summary.plan_count} 个计划` : '等待计划统计', icon: GitBranch, tone: 'warn' },
    { label: '运行执行器', value: summary ? String(summary.running_actuator_count) : '--', detail: summary ? `${summary.zone_count} 个分区` : '等待设备统计', icon: Gauge, tone: 'muted' },
    { label: '活跃告警', value: summary ? String(summary.active_alert_count) : '--', detail: '已记录的未解决告警', icon: AlertTriangle, tone: 'warn' },
  ]

  return (
    <div className="visualization-screen">
      <section className="visualization-hero">
        <div>
          <SectionBadge label="Visualization" />
          <h1>数据大屏</h1>
          <span>指标更新时间 {formatDateTime(summary?.timestamp)}</span>
        </div>
        <div className="visualization-hero-status">
          <Waves className="size-5 text-[#0052FF]" />
          <strong>{summary ? labelFor(summary.irrigation_status, STATUS_LABELS) : '状态待确认'}</strong>
        </div>
      </section>

      {(!canReadSummary || summaryQuery.isError) && <p role="status" className="visualization-note">{!canReadSummary ? '没有分区指标读取权限' : summary ? '指标更新失败，正在显示上次数据' : '指标暂时不可用，正在等待重试'}</p>}
      <section className="visualization-kpis" aria-busy={canReadSummary && summaryQuery.isPending}>
        {kpis.map((item) => {
          const Icon = item.icon
          return (
            <div key={item.label} className={`visualization-kpi visualization-kpi-${item.tone}`}>
              <Icon className="size-5 text-[#0052FF]" />
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <p>{item.detail}</p>
            </div>
          )
        })}
      </section>
      {summary?.last_irrigation_at && <p className="visualization-note">最近灌溉记录 {formatDateTime(summary.last_irrigation_at)}</p>}
      {analyticsQuery.isError && analyticsQuery.data && <p role="status" className="visualization-note">分析更新失败，正在显示上次数据</p>}
      {modelsQuery.isError && modelsQuery.data && <p role="status" className="visualization-note">模型记录更新失败，正在显示上次数据</p>}
      <Charts overview={analyticsQuery.data ?? null} plans={modelsQuery.data?.plans ?? emptyPlans}
        analyticsPending={analyticsQuery.isPending} analyticsError={analyticsQuery.isError}
        modelPending={canReadModels && modelsQuery.isPending} modelError={!canReadModels || modelsQuery.isError} />
    </div>
  )
}
