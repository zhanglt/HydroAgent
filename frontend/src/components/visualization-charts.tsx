'use client'

import { memo } from 'react'
import { DeferredChart } from '@/components/deferred-chart'
import { ACTION_LABELS, PLAN_STAGE_LABELS, labelFor } from '@/lib/labels'
import { AnalyticsOverview, VisualizationModelPlan } from '@/lib/types'
import { formatNumber1 } from '@/lib/format'
import { formatDateTime } from '@/lib/utils'

type MlForecastPoint = {
  label: string
  value: number
}

type MlPredictionView = {
  current: number | null
  predicted: number | null
  confidence: string
  sampleCount: number | null
  planLabel: string
  points: MlForecastPoint[]
}

type DecisionModelView = {
  action: string
  duration: number | null
  confidence: number | null
  sampleCount: number | null
  planLabel: string
  topFactors: string[]
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function readMlPrediction(plan: VisualizationModelPlan): MlPredictionView | null {
  const evidence = readRecord(plan.evidence_summary)
  const rawPrediction = readRecord(evidence?.ml_prediction)
  if (!rawPrediction) return null

  const current = toNumber(rawPrediction.current_soil_moisture)
  const predicted = toNumber(rawPrediction.predicted_soil_moisture_24h)
  const sampleCount = toNumber(rawPrediction.sample_count)
  const confidenceValue = rawPrediction.confidence
  const confidence = typeof confidenceValue === 'string'
    ? confidenceValue
    : confidenceValue === null || confidenceValue === undefined
      ? '待校准'
      : String(confidenceValue)

  const rawSeries = Array.isArray(rawPrediction.forecast_series)
    ? rawPrediction.forecast_series
    : Array.isArray(rawPrediction.forecast_data)
      ? rawPrediction.forecast_data
      : []
  const points = rawSeries
    .map((item, index) => {
      const row = readRecord(item)
      const value = toNumber(row?.predicted_soil_moisture) ?? toNumber(row?.predicted_value) ?? toNumber(row?.soil_moisture) ?? toNumber(row?.value)
      if (value === null) return null
      return {
        label: typeof row?.timestamp === 'string' ? formatDateTime(row.timestamp) : `${index + 1}h`,
        value,
      }
    })
    .filter((item): item is MlForecastPoint => Boolean(item))

  if (points.length === 0 && current !== null && predicted !== null) {
    points.push({ label: '当前', value: current }, { label: '24h', value: predicted })
  }

  if (current === null && predicted === null && points.length === 0) return null

  return {
    current,
    predicted,
    confidence,
    sampleCount,
    planLabel: plan.zone_name || plan.zone_id || plan.plan_id,
    points,
  }
}

function readDecisionModel(plan: VisualizationModelPlan): DecisionModelView | null {
  const evidence = readRecord(plan.evidence_summary)
  const rawModel = readRecord(evidence?.decision_model)
  if (!rawModel) return null

  const actionValue = rawModel.recommended_action
  const action = typeof actionValue === 'string' && actionValue.trim() ? actionValue : '待校准'
  const duration = toNumber(rawModel.recommended_duration_minutes)
  const confidence = toNumber(rawModel.confidence)
  const sampleCount = toNumber(rawModel.sample_count)
  const topFactors = Array.isArray(rawModel.top_factors)
    ? rawModel.top_factors.map((item) => String(item)).filter(Boolean).slice(0, 3)
    : []

  return {
    action,
    duration,
    confidence,
    sampleCount,
    planLabel: plan.zone_name || plan.zone_id || plan.plan_id,
    topFactors,
  }
}

function findLatestMlPrediction(plans: VisualizationModelPlan[]): MlPredictionView | null {
  const sortedPlans = [...plans].sort((left, right) => {
    const leftTime = new Date(left.created_at || '').getTime() || 0
    const rightTime = new Date(right.created_at || '').getTime() || 0
    return rightTime - leftTime
  })
  for (const plan of sortedPlans) {
    const prediction = readMlPrediction(plan)
    if (prediction) return prediction
  }
  return null
}

function findLatestDecisionModel(plans: VisualizationModelPlan[]): DecisionModelView | null {
  const sortedPlans = [...plans].sort((left, right) => {
    const leftTime = new Date(left.created_at || '').getTime() || 0
    const rightTime = new Date(right.created_at || '').getTime() || 0
    return rightTime - leftTime
  })
  for (const plan of sortedPlans) {
    const decisionModel = readDecisionModel(plan)
    if (decisionModel) return decisionModel
  }
  return null
}

const emptyOverview: AnalyticsOverview = {
  range: '7d',
  kpis: { zone_count: 0, pending_plan_count: 0, active_alert_count: 0, executed_plan_count: 0 },
  soil_trend: { zone_id: '', zone_name: '', range: '7d', labels: [], soil_moisture: [], threshold: [] },
  plan_funnel: { range: '7d', items: [] },
  alert_trend: { range: '7d', labels: [], series: {} },
  zone_health: [],
}

function AnalyticsNotice({ pending, error }: { pending: boolean; error: boolean }) {
  return <div className="visualization-empty min-h-60" role="status">{pending ? '正在加载分析数据…' : error ? '分析数据暂时不可用，等待重试' : '暂无分析数据'}</div>
}

function chartTextStyle() {
  return { color: '#94A3B8', fontSize: 11 }
}

function chartAxisLine() {
  return { lineStyle: { color: '#E2E8F0' } }
}

export default memo(function VisualizationCharts({
  overview, plans, analyticsPending, analyticsError, modelPending, modelError,
}: {
  overview: AnalyticsOverview | null
  plans: VisualizationModelPlan[]
  analyticsPending: boolean
  analyticsError: boolean
  modelPending: boolean
  modelError: boolean
}) {
  const dataOverview = overview || emptyOverview
  const mlPrediction = findLatestMlPrediction(plans)
  const decisionModel = findLatestDecisionModel(plans)

  const sharedGrid = { left: 42, right: 18, top: 42, bottom: 36 }
  const moistureOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 4, textStyle: chartTextStyle(), data: ['土壤湿度', '阈值'] },
    grid: sharedGrid,
    xAxis: { type: 'category', data: dataOverview.soil_trend.labels, axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } } },
    series: [
      {
        name: '土壤湿度',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: dataOverview.soil_trend.soil_moisture.map((value) => value === null ? null : Number(value.toFixed(1))),
        lineStyle: { width: 3, color: '#0052FF' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(0, 82, 255, 0.22)' },
              { offset: 1, color: 'rgba(0, 82, 255, 0)' },
            ],
          },
        },
      },
      { name: '阈值', type: 'line', smooth: true, symbol: 'none', data: dataOverview.soil_trend.threshold.map((value) => value === null ? null : Number(value.toFixed(1))), lineStyle: { width: 2, type: 'dashed', color: '#CBD5E1' } },
    ],
  }

  const funnelOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    grid: sharedGrid,
    xAxis: { type: 'category', data: dataOverview.plan_funnel.items.map((item) => labelFor(item.stage, PLAN_STAGE_LABELS)), axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', minInterval: 1, axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } } },
    series: [
      {
        type: 'bar',
        data: dataOverview.plan_funnel.items.map((item) => item.count),
        barWidth: 18,
        itemStyle: { color: '#0052FF', borderRadius: [8, 8, 0, 0] },
      },
    ],
  }

  const alertOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 4, textStyle: chartTextStyle(), data: ['高风险', '中风险', '低风险'] },
    grid: sharedGrid,
    xAxis: { type: 'category', data: dataOverview.alert_trend.labels, axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', minInterval: 1, axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } } },
    series: [
      { name: '高风险', type: 'line', smooth: true, symbol: 'none', data: dataOverview.alert_trend.series.high || [], lineStyle: { color: '#E11D48', width: 3 } },
      { name: '中风险', type: 'line', smooth: true, symbol: 'none', data: dataOverview.alert_trend.series.medium || [], lineStyle: { color: '#F59E0B', width: 2 } },
      { name: '低风险', type: 'line', smooth: true, symbol: 'none', data: dataOverview.alert_trend.series.low || [], lineStyle: { color: '#10B981', width: 2 } },
    ],
  }

  const heatmapMax = Math.max(100, ...dataOverview.zone_health.map((item) => Math.max(item.soil_moisture ?? 0, item.deficit ?? 0, item.alert_count)))
  const heatmapOption = {
    backgroundColor: 'transparent',
    tooltip: {},
    grid: { left: 82, right: 20, top: 28, bottom: 56 },
    xAxis: { type: 'category', data: ['湿度', '缺口', '告警'], axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'category', data: dataOverview.zone_health.map((item) => item.zone_name), axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    visualMap: {
      min: 0,
      max: heatmapMax,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      textStyle: chartTextStyle(),
      inRange: { color: ['#EFF6FF', '#4D7CFF', '#0052FF'] },
    },
    series: [
      {
        type: 'heatmap',
        data: dataOverview.zone_health.flatMap((item, index) => [
          [0, index, item.soil_moisture === null ? null : Number(item.soil_moisture.toFixed(1))],
          [1, index, item.deficit === null ? null : Number(item.deficit.toFixed(1))],
          [2, index, item.alert_count],
        ].filter((cell) => cell[2] !== null)),
        label: { show: true, color: '#0F172A' },
      },
    ],
  }

  const mlOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: sharedGrid,
    xAxis: { type: 'category', data: mlPrediction?.points.map((item) => item.label) || [], axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } } },
    series: [
      {
        name: '预测湿度',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: mlPrediction?.points.map((item) => Number(item.value.toFixed(1))) || [],
        lineStyle: { width: 3, color: '#0052FF' },
        areaStyle: { color: 'rgba(0, 82, 255, 0.16)' },
      },
    ],
  }

  return (
      <section className="visualization-grid">
        <div className="visualization-panel visualization-panel-wide">
          <div className="visualization-panel-heading">
            <span>Moisture</span>
            <strong>湿度趋势</strong>
          </div>
          {overview ? <DeferredChart option={moistureOption} height={320} /> : <AnalyticsNotice pending={analyticsPending} error={analyticsError} />}
        </div>

        <div className="visualization-panel">
          <div className="visualization-panel-heading">
            <span>Prediction</span>
            <strong>ML 预测</strong>
          </div>
          {modelPending ? <div className="visualization-empty" role="status">正在加载模型记录…</div> : modelError ? <div className="visualization-empty" role="status">模型记录不可用或没有读取权限</div> : mlPrediction ? (
            <>
              <div className="visualization-ml-strip">
                <div>
                  <span>当前</span>
                  <strong>{formatNumber1(mlPrediction.current, '%')}</strong>
                </div>
                <div>
                  <span>24h</span>
                  <strong>{formatNumber1(mlPrediction.predicted, '%')}</strong>
                </div>
                <div>
                  <span>置信度</span>
                  <strong>{mlPrediction.confidence}</strong>
                </div>
                <div>
                  <span>样本</span>
                  <strong>{formatNumber1(mlPrediction.sampleCount)}</strong>
                </div>
              </div>
              <p className="visualization-note">{mlPrediction.planLabel}</p>
              <DeferredChart option={mlOption} height={240} />
            </>
          ) : (
            <div className="visualization-empty">
              <strong>等待模型预测数据</strong>
              <p>暂无 ml_prediction，当前以运营数据为准。</p>
            </div>
          )}
          <div className="visualization-decision">
            <div className="visualization-panel-heading">
              <span>Decision</span>
              <strong>决策模型建议</strong>
            </div>
            {decisionModel ? (
              <>
                <div className="visualization-ml-strip visualization-decision-strip">
                  <div>
                    <span>动作</span>
                    <strong>{labelFor(decisionModel.action, ACTION_LABELS)}</strong>
                  </div>
                  <div>
                    <span>时长</span>
                    <strong>{formatNumber1(decisionModel.duration, ' 分钟')}</strong>
                  </div>
                  <div>
                    <span>置信度</span>
                    <strong>{formatNumber1(decisionModel.confidence)}</strong>
                  </div>
                  <div>
                    <span>样本</span>
                    <strong>{formatNumber1(decisionModel.sampleCount)}</strong>
                  </div>
                </div>
                <p className="visualization-note">{decisionModel.planLabel}</p>
                <div className="visualization-factor-list">
                  {(decisionModel.topFactors.length ? decisionModel.topFactors : ['等待关键因子']).map((factor) => (
                    <span key={factor}>{factor}</span>
                  ))}
                </div>
              </>
            ) : (
              <p className="visualization-note">{modelPending ? '正在读取决策记录…' : modelError ? '决策记录暂时不可用' : '暂无 decision_model，等待历史计划样本。'}</p>
            )}
          </div>
        </div>

        <div className="visualization-panel">
          <div className="visualization-panel-heading">
            <span>Plan</span>
            <strong>计划漏斗</strong>
          </div>
          {overview ? <DeferredChart option={funnelOption} height={280} /> : <AnalyticsNotice pending={analyticsPending} error={analyticsError} />}
        </div>

        <div className="visualization-panel">
          <div className="visualization-panel-heading">
            <span>Alert</span>
            <strong>告警趋势</strong>
          </div>
          {overview ? <DeferredChart option={alertOption} height={280} /> : <AnalyticsNotice pending={analyticsPending} error={analyticsError} />}
        </div>

        <div className="visualization-panel visualization-panel-wide">
          <div className="visualization-panel-heading">
            <span>Zone</span>
            <strong>分区健康热力</strong>
          </div>
          {overview ? <DeferredChart option={heatmapOption} height={320} /> : <AnalyticsNotice pending={analyticsPending} error={analyticsError} />}
        </div>
      </section>
  )
})
