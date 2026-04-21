import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react"
import { isDesktop } from "@/lib/platform"
import { useDesktopStore } from "@/stores/desktopStore"
import { getBackendPort, hasApiKey, startBackend } from "@/api/desktop"

const SetupPage = lazy(() =>
  import("./SetupPage").then((m) => ({ default: m.SetupPage })),
)

interface Props {
  children: React.ReactNode
}

interface BackendReadyPayload {
  port: number
}

type BootState =
  | { kind: "checking" }
  | { kind: "needs-setup" }
  | { kind: "starting" }
  | { kind: "ready" }
  | { kind: "error"; message: string }

export function DesktopBootstrap({ children }: Props) {
  const setApiPort = useDesktopStore((s) => s.setApiPort)
  const setBackendReady = useDesktopStore((s) => s.setBackendReady)
  const [state, setState] = useState<BootState>({ kind: "checking" })
  const unlistenRef = useRef<(() => void) | null>(null)

  const subscribeBackendReady = useCallback(async () => {
    if (unlistenRef.current) return
    const { listen } = await import("@tauri-apps/api/event")
    unlistenRef.current = await listen<BackendReadyPayload>("backend-ready", (event) => {
      setApiPort(event.payload.port)
      setBackendReady(true)
      setState({ kind: "ready" })
    })

    const existingPort = await getBackendPort()
    if (existingPort) {
      setApiPort(existingPort)
      setBackendReady(true)
      setState({ kind: "ready" })
    }
  }, [setApiPort, setBackendReady])

  useEffect(() => {
    if (!isDesktop()) {
      setBackendReady(true)
      setState({ kind: "ready" })
      return
    }

    let cancelled = false

    const init = async () => {
      try {
        const keyPresent = await hasApiKey()
        if (cancelled) return

        if (!keyPresent) {
          setState({ kind: "needs-setup" })
          return
        }

        setState({ kind: "starting" })
        await subscribeBackendReady()
        await startBackend()
      } catch (e) {
        if (!cancelled) {
          setState({ kind: "error", message: e instanceof Error ? e.message : String(e) })
        }
      }
    }

    init()

    return () => {
      cancelled = true
      unlistenRef.current?.()
      unlistenRef.current = null
    }
  }, [setBackendReady, subscribeBackendReady])

  const handleSetupReady = useCallback(async () => {
    setState({ kind: "starting" })
    await subscribeBackendReady()
  }, [subscribeBackendReady])

  if (!isDesktop()) return <>{children}</>

  if (state.kind === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="max-w-md space-y-2 text-center">
          <h1 className="text-lg font-semibold text-destructive">Ошибка запуска</h1>
          <p className="text-sm text-muted-foreground">{state.message}</p>
        </div>
      </div>
    )
  }

  if (state.kind === "needs-setup") {
    return (
      <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Загрузка...</div>}>
        <SetupPage onReady={handleSetupReady} />
      </Suspense>
    )
  }

  if (state.kind === "checking" || state.kind === "starting") {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="space-y-2 text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="text-sm text-muted-foreground">
            {state.kind === "checking" ? "Проверка..." : "Запуск backend..."}
          </p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
