import { Suspense, lazy } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { homePath, rulesPath } from "@/lib/routes"
import { DesktopBootstrap } from "@/components/DesktopBootstrap"
import { ConfirmProvider } from "@/components/ConfirmDialog"
import { isDesktop } from "@/lib/platform"

const HomePage = lazy(() => import("@/pages/HomePage"))
const ProjectPage = lazy(() => import("@/pages/ProjectPage"))
const RulesPage = lazy(() => import("@/pages/RulesPage"))
const BackgroundTasksPage = lazy(() => import("@/pages/BackgroundTasksPage"))
const DesktopLayoutLazy = lazy(() =>
  import("@/components/DesktopLayout").then((m) => ({ default: m.DesktopLayout })),
)

function AppShell({ children }: { children: React.ReactNode }) {
  if (!isDesktop()) return <>{children}</>
  return (
    <Suspense fallback={<>{children}</>}>
      <DesktopLayoutLazy>{children}</DesktopLayoutLazy>
    </Suspense>
  )
}

function App() {
  return (
    <DesktopBootstrap>
      <ConfirmProvider>
        <BrowserRouter>
          <AppShell>
            <div className="min-h-full bg-background">
              <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Загрузка экрана...</div>}>
                <Routes>
                  <Route path={homePath()} element={<HomePage />} />
                  <Route path={rulesPath()} element={<RulesPage />} />
                  <Route path="/projects/:projectSlug" element={<ProjectPage />} />
                  <Route path="/projects/:projectSlug/tasks" element={<BackgroundTasksPage />} />
                  <Route path="/projects/:projectSlug/features/:featureName" element={<ProjectPage />} />
                  <Route path="/projects/:projectSlug/features/:featureName/:tab" element={<ProjectPage />} />
                  <Route path="/projects/:projectSlug/dependencies/:depType/:depName" element={<ProjectPage />} />
                  <Route path="*" element={<Navigate to={homePath()} replace />} />
                </Routes>
              </Suspense>
            </div>
          </AppShell>
        </BrowserRouter>
      </ConfirmProvider>
    </DesktopBootstrap>
  )
}

export default App
