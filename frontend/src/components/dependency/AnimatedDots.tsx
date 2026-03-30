import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"

const FRAMES = [".", "..", "...", "."]

interface AnimatedDotsProps {
  className?: string
}

export function AnimatedDots({ className }: AnimatedDotsProps) {
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setFrame((f) => (f + 1) % FRAMES.length)
    }, 400)
    return () => clearInterval(id)
  }, [])

  return (
    <span className={cn("inline-block min-w-6 text-muted-foreground", className)}>
      {FRAMES[frame]}
    </span>
  )
}
