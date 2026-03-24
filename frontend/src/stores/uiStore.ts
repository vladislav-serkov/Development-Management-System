import { create } from "zustand"

interface UIState {
  selectedDocumentId: number | null
  selectedFeatureId: number | null
  activeSidebarItem: string | null  // "overview" | feature name | "db" | "external_api" | "cache" | "gaps"
  setSelectedDocument: (id: number | null) => void
  setSelectedFeature: (id: number | null) => void
  setActiveSidebarItem: (item: string | null) => void
  goHome: () => void
}

export const useUIStore = create<UIState>()((set) => ({
  selectedDocumentId: null,
  selectedFeatureId: null,
  activeSidebarItem: null,
  setSelectedDocument: (id) => set({ selectedDocumentId: id, selectedFeatureId: null, activeSidebarItem: null }),
  setSelectedFeature: (id) => set({ selectedFeatureId: id }),
  setActiveSidebarItem: (item) => set({ activeSidebarItem: item }),
  goHome: () => set({ selectedDocumentId: null, selectedFeatureId: null, activeSidebarItem: null }),
}))
