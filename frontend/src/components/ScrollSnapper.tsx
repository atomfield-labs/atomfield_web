import { useScroll } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'

export default function ScrollSnapper() {
  const scroll = useScroll()
  const isScrolling = useRef(false)
  const scrollTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const targetOffset = useRef<number | null>(null)

  useEffect(() => {
    // scroll.el is the native HTML element Drei creates for the scrollbar
    const el = scroll.el

    const onScroll = () => {
      isScrolling.current = true
      
      if (scrollTimeout.current) {
        clearTimeout(scrollTimeout.current)
      }
      
      // When the user stops scrolling for 60ms, calculate the nearest section to snap to
      scrollTimeout.current = setTimeout(() => {
        isScrolling.current = false
        
        const currentOffset = scroll.offset
        // We have 6 pages, meaning 5 scroll intervals (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        const nearestPageOffset = Math.round(currentOffset * 5) / 5
        
        targetOffset.current = nearestPageOffset
      }, 60) 
    }

    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [scroll])

  useFrame((_, delta) => {
    if (!isScrolling.current && targetOffset.current !== null) {
      const el = scroll.el
      const maxScroll = el.scrollHeight - el.clientHeight
      const targetScrollTop = targetOffset.current * maxScroll
      
      // Highly aggressive interpolation for a fast, snappy magnetic feel
      el.scrollTop = THREE.MathUtils.lerp(el.scrollTop, targetScrollTop, delta * 28)
      
      // Once we are close enough, stop applying the physics lerp
      if (Math.abs(el.scrollTop - targetScrollTop) < 1.5) {
        el.scrollTop = targetScrollTop
        targetOffset.current = null
      }
    }
  })

  return null
}
