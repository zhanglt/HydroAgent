'use client'

import dynamic from 'next/dynamic'
import { useEffect, useRef, useState } from 'react'
import type { EChartsCoreOption } from 'echarts/core'

const Chart = dynamic(() => import('@/components/visualization-chart'), { ssr: false })

export function DeferredChart({ option, height }: { option: EChartsCoreOption; height: number }) {
  const container = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const target = container.current
    if (!target) return
    if (!('IntersectionObserver' in window)) {
      const frame = requestAnimationFrame(() => setVisible(true))
      return () => cancelAnimationFrame(frame)
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true)
        observer.disconnect()
      }
    }, { rootMargin: '160px' })
    observer.observe(target)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={container} style={{ minHeight: height }} data-chart-state={visible ? 'active' : 'deferred'}>
      {visible ? <Chart option={option} height={height} /> : <div role="status" className="p-4 text-xs text-slate-500">图表将在进入可视区域时加载</div>}
    </div>
  )
}
