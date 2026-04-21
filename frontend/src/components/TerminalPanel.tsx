import { useEffect, useRef } from "react"
import { Terminal } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import "@xterm/xterm/css/xterm.css"
import { killShell, resizeShell, spawnShell, writeToShell } from "@/api/desktop"

export function TerminalPanel() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const term = new Terminal({
      theme: {
        background: "#0f0f10",
        foreground: "#e5e5e5",
        cursor: "#e5e5e5",
        selectionBackground: "#3a3a3c",
      },
      fontFamily: "ui-monospace, Menlo, 'Courier New', monospace",
      fontSize: 13,
      cursorBlink: true,
      allowProposedApi: true,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon())
    term.open(container)
    fit.fit()

    termRef.current = term
    fitRef.current = fit

    let unlistenOutput: (() => void) | null = null
    let unlistenExit: (() => void) | null = null
    let disposed = false

    const init = async () => {
      const { listen } = await import("@tauri-apps/api/event")
      const outHandle = await listen<string>("pty-output", (event) => {
        term.write(event.payload)
      })
      if (disposed) {
        outHandle()
        return
      }
      unlistenOutput = outHandle

      const exitHandle = await listen("pty-exit", () => {
        term.writeln("\r\n\x1b[90m[shell exited]\x1b[0m")
      })
      if (disposed) {
        exitHandle()
        return
      }
      unlistenExit = exitHandle

      try {
        await spawnShell(term.cols, term.rows)
      } catch (e) {
        term.writeln(`\r\n\x1b[31mFailed to spawn shell: ${e}\x1b[0m`)
      }
    }
    init()

    const dataSub = term.onData((data) => {
      writeToShell(data).catch(() => {})
    })

    let resizeTimer: ReturnType<typeof setTimeout> | null = null
    const handleResize = () => {
      if (resizeTimer) clearTimeout(resizeTimer)
      resizeTimer = setTimeout(() => {
        fit.fit()
        resizeShell(term.cols, term.rows).catch(() => {})
      }, 80)
    }
    const ro = new ResizeObserver(handleResize)
    ro.observe(container)

    return () => {
      disposed = true
      dataSub.dispose()
      ro.disconnect()
      if (resizeTimer) clearTimeout(resizeTimer)
      unlistenOutput?.()
      unlistenExit?.()
      killShell().catch(() => {})
      term.dispose()
    }
  }, [])

  return <div ref={containerRef} className="h-full w-full bg-[#0f0f10] p-2" />
}
