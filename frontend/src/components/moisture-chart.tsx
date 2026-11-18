'use client'

import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

export default function MoistureChart({ option }: { option: echarts.EChartsCoreOption }) {
  return <ReactEChartsCore echarts={echarts} option={option} style={{ height: '100%', minHeight: 320 }} />
}
