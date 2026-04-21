import { useCallback, useEffect, useRef, useState } from "react"
import { isDesktop } from "@/lib/platform"
import { useDesktopStore } from "@/stores/desktopStore"
import { TerminalPanel } from "./TerminalPanel"
import { Terminal as TerminalIcon, X } from "lucide-react"

interface Props {
  children: React.ReactNode
}

export function DesktopLayout({ children }: Props) {
  if (!isDesktop()) return <>{children}</>
  return <InnerLayout>{children}</InnerLayout>
}

function InnerLayout({ children }: Props) {
  const terminalOpen = useDesktopStore((s) => s.terminalOpen)
  const terminalHeight = useDesktopStore((s) => s.terminalHeight)
  const setTerminalOpen = useDesktopStore((s) => s.setTerminalOpen)
  const setTerminalHeight = useDesktopStore((s) => s.setTerminalHeight)
  const toggleTerminal = useDesktopStore((s) => s.toggleTerminal)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "`" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        toggleTerminal()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [toggleTerminal])

  return (
    <div className="flex h-screen flex-col">
      <div className="flex-1 min-h-0 overflow-auto">{children}</div>

      {terminalOpen && (
        <TerminalSection
          height={terminalHeight}
          onResize={setTerminalHeight}
          onClose={() => setTerminalOpen(false)}
        />
      )}

      {!terminalOpen && (
        <button
          onClick={() => setTerminalOpen(true)}
          className="fixed bottom-4 right-4 z-50 flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90"
          aria-label="Открыть терминал"
          title="Открыть терминал (⌘`)"
        >
          <TerminalIcon className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

interface SectionProps {
  height: number
  onResize: (h: number) => void
  onClose: () => void
}

function TerminalSection({ height, onResize, onClose }: SectionProps) {
  const [dragging, setDragging] = useState(false)
  const startRef = useRef<{ y: number; height: number } | null>(null)

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setDragging(true)
      startRef.current = { y: e.clientY, height }
    },
    [height],
  )

  useEffect(() => {
    if (!dragging) return
    const onMove = (e: MouseEvent) => {
      if (!startRef.current) return
      const delta = startRef.current.y - e.clientY
      onResize(startRef.current.height + delta)
    }
    const onUp = () => setDragging(false)
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
    return () => {
      window.removeEventListener("mousemove", onMove)
      window.removeEventListener("mouseup", onUp)
    }
  }, [dragging, onResize])

  return (
    <div
      className="flex flex-col border-t bg-[#0f0f10]"
      style={{ height }}
    >
      <div
        onMouseDown={onMouseDown}
        className="group flex h-1.5 w-full cursor-row-resize items-center justify-center bg-border hover:bg-primary/40"
      >
        <div className="h-0.5 w-10 rounded-full bg-muted-foreground/40 group-hover:bg-primary/60" />
      </div>
      <div className="flex items-center justify-between border-b border-border/30 bg-[#18181b] px-3 py-1.5 text-xs text-muted-foreground">
        <span className="font-medium">Терминал</span>
        <button
          onClick={onClose}
          className="rounded p-1 hover:bg-white/10"
          aria-label="Закрыть терминал"
          title="Закрыть (⌘`)"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex-1 min-h-0">
        <TerminalPanel />
      </div>
    </div>
  )
}
