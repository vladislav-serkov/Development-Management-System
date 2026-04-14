import { Suspense, lazy } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { homePath, rulesPath } from "@/lib/routes"

const HomePage = lazy(() => import("@/pages/HomePage"))
const ProjectPage = lazy(() => import("@/pages/ProjectPage"))
const RulesPage = lazy(() => import("@/pages/RulesPage"))

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Загрузка экрана...</div>}>
          <Routes>
            <Route path={homePath()} element={<HomePage />} />
            <Route path={rulesPath()} element={<RulesPage />} />
            <Route path="/projects/:projectSlug" element={<ProjectPage />} />
            <Route path="/projects/:projectSlug/features/:featureName" element={<ProjectPage />} />
            <Route path="/projects/:projectSlug/features/:featureName/:tab" element={<ProjectPage />} />
            <Route path="/projects/:projectSlug/dependencies/:depType/:depName" element={<ProjectPage />} />
            <Route path="*" element={<Navigate to={homePath()} replace />} />
          </Routes>
        </Suspense>
      </div>
    </BrowserRouter>
  )
}

export default App
