import { create } from "zustand"

interface UIState {
  selectedDocumentId: number | null
  selectedFeatureId: number | null
  activeSidebarItem: string | null  // "overview" | feature name | "db" | "external_api" | "cache" | "gaps"
  sidebarWidth: number
  setSelectedDocument: (id: number | null) => void
  setSelectedFeature: (id: number | null) => void
  setActiveSidebarItem: (item: string | null) => void
  setSidebarWidth: (width: number) => void
  goHome: () => void
}

export const useUIStore = create<UIState>()((set) => ({
  selectedDocumentId: null,
  selectedFeatureId: null,
  activeSidebarItem: null,
  sidebarWidth: 256,
  setSelectedDocument: (id) => set({ selectedDocumentId: id, selectedFeatureId: null, activeSidebarItem: null }),
  setSelectedFeature: (id) => set({ selectedFeatureId: id }),
  setActiveSidebarItem: (item) => set({ activeSidebarItem: item }),
  setSidebarWidth: (width) => set({ sidebarWidth: Math.min(480, Math.max(180, width)) }),
  goHome: () => set({ selectedDocumentId: null, selectedFeatureId: null, activeSidebarItem: null }),
}))
