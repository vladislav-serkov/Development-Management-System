import { create } from "zustand"

const MIN_TERMINAL_HEIGHT = 120
const MAX_TERMINAL_HEIGHT = 800
const DEFAULT_TERMINAL_HEIGHT = 280

function clampHeight(h: number): number {
  return Math.min(MAX_TERMINAL_HEIGHT, Math.max(MIN_TERMINAL_HEIGHT, h))
}

interface DesktopState {
  apiPort: number | null
  backendReady: boolean
  terminalOpen: boolean
  terminalHeight: number
  setApiPort: (port: number) => void
  setBackendReady: (ready: boolean) => void
  setTerminalOpen: (open: boolean) => void
  toggleTerminal: () => void
  setTerminalHeight: (h: number) => void
}

export const useDesktopStore = create<DesktopState>()((set) => ({
  apiPort: null,
  backendReady: false,
  terminalOpen: false,
  terminalHeight: DEFAULT_TERMINAL_HEIGHT,
  setApiPort: (port) => set({ apiPort: port }),
  setBackendReady: (ready) => set({ backendReady: ready }),
  setTerminalOpen: (open) => set({ terminalOpen: open }),
  toggleTerminal: () => set((s) => ({ terminalOpen: !s.terminalOpen })),
  setTerminalHeight: (h) => set({ terminalHeight: clampHeight(h) }),
}))
