import { create } from "zustand"

type AppView = "home" | "project" | "rules"

interface UIState {
  currentView: AppView
  selectedProjectSlug: string | null
  selectedDocumentSlug: string | null
  selectedFeatureName: string | null
  selectedDependencyName: string | null
  activeSidebarItem: string | null
  sidebarWidth: number
  setSelectedProject: (slug: string | null) => void
  setSelectedDocument: (slug: string | null) => void
  setSelectedFeature: (name: string | null) => void
  setSelectedDependency: (name: string | null) => void
  setActiveSidebarItem: (item: string | null) => void
  setSidebarWidth: (width: number) => void
  goHome: () => void
  goToProject: (slug: string) => void
  goToRules: () => void
}

export const useUIStore = create<UIState>()((set) => ({
  currentView: "home" as AppView,
  selectedProjectSlug: null,
  selectedDocumentSlug: null,
  selectedFeatureName: null,
  selectedDependencyName: null,
  activeSidebarItem: null,
  sidebarWidth: 256,
  setSelectedProject: (slug) => set({ selectedProjectSlug: slug, selectedDocumentSlug: null, selectedFeatureName: null, selectedDependencyName: null, activeSidebarItem: null }),
  setSelectedDocument: (slug) => set({ selectedDocumentSlug: slug, selectedFeatureName: null, activeSidebarItem: null }),
  setSelectedFeature: (name) => set({ selectedFeatureName: name, selectedDependencyName: null }),
  setSelectedDependency: (name) => set({ selectedDependencyName: name, selectedFeatureName: null }),
  setActiveSidebarItem: (item) => set({ activeSidebarItem: item }),
  setSidebarWidth: (width) => set({ sidebarWidth: Math.min(480, Math.max(180, width)) }),
  goHome: () => set({ currentView: "home", selectedProjectSlug: null, selectedDocumentSlug: null, selectedFeatureName: null, selectedDependencyName: null, activeSidebarItem: null }),
  goToProject: (slug) => set({ currentView: "project", selectedProjectSlug: slug, selectedDocumentSlug: null, selectedFeatureName: null, selectedDependencyName: null, activeSidebarItem: null }),
  goToRules: () => set({ currentView: "rules", selectedProjectSlug: null, selectedDocumentSlug: null, selectedFeatureName: null, selectedDependencyName: null, activeSidebarItem: null }),
}))
